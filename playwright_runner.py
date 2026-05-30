from __future__ import annotations

import ctypes
import json
import os
from datetime import datetime

import pandas as pd
from typing import Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from utils import get_cropped_face_base64


class PlaywrightRunner:
	def __init__(self) -> None:
		self._playwright = sync_playwright().start()
		self._debug = os.getenv("KYC_DEBUG", "0") == "1"
		screen_width, screen_height = self._get_screen_size()
		self._browser = self._playwright.chromium.launch(
			headless=False,
			args=[
				"--use-fake-ui-for-media-stream",
				"--use-fake-device-for-media-stream",
				"--start-maximized",
				f"--window-size={screen_width},{screen_height}",
			],
		)
		self._context = self._browser.new_context(
			viewport={"width": screen_width, "height": screen_height}
		)
		mock_camera_js = (
			"window.fakeCamBase64 = '';\n"
			"const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);\n"
			"navigator.mediaDevices.getUserMedia = async (constraints) => {\n"
			"  if (constraints.video && window.fakeCamBase64) {\n"
			"    const canvas = document.createElement('canvas');\n"
			"    canvas.width = 640;\n"
			"    canvas.height = 480;\n"
			"    const ctx = canvas.getContext('2d');\n"
			"    const img = new Image();\n"
			"    img.src = window.fakeCamBase64;\n"
			"    await new Promise((resolve, reject) => {\n"
			"      img.onload = resolve;\n"
			"      img.onerror = reject;\n"
			"    });\n"
			"    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);\n"
			"    return canvas.captureStream(30);\n"
			"  }\n"
			"  return originalGetUserMedia(constraints);\n"
			"};\n"
		)
		self._context.add_init_script(mock_camera_js)
		self._page = self._context.new_page()

	def run(
		self,
		record: dict,
		passport_path: str,
		portrait_path: str,
		log: Callable[[str], None] | None = None,
	) -> tuple[str, str]:
		base64_img = get_cropped_face_base64(portrait_path)
		try:
			self._page.close()
		except Exception:
			pass
		self._page = self._context.new_page()
		self._maximize_window(log)
		self._sync_viewport_to_screen(log)
		if base64_img:
			self._page.add_init_script(
				f"window.fakeCamBase64 = {json.dumps(base64_img)};"
			)
			if log:
				log("Loaded fake webcam base64 data")
		else:
			if log:
				log("Warning: Không thể tạo Base64 cho ảnh chân dung")

		self._page.goto("https://digishop.vnpt.vn/tourist/", timeout=45000, wait_until="domcontentloaded")
		if log:
			log("Opened website")

		if self._debug:
			self._page.screenshot(path="debug.png", full_page=True)
			if log:
				log("Saved debug screenshot: debug.png")

			inputs = self._page.locator("input")
			try:
				count = inputs.count()
			except Exception:
				count = 0
			if log:
				log(f"Input count: {count}")

			if log and count > 0:
				for idx in range(count):
					try:
						html = inputs.nth(idx).evaluate("el => el.outerHTML")
						log(f"Input[{idx}]: {html}")
					except Exception as exc:
						log(f"Input[{idx}] read failed: {exc}")

		phone_selectors = [
			"#msisdn_validate",
			"input#msisdn_validate",
			"input[name='phone']",
			"input#phone",
			"input[name='mobile']",
			"input[placeholder*='phone']",
		]
		serial_selectors = [
			"#serial_validate",
			"input#serial_validate",
			"input[name='serial']",
			"input#serial",
			"input[name='passport']",
			"input[placeholder*='serial']",
		]

		self._fill_first_available(phone_selectors, record["phone"], "phone")
		self._fill_first_available(serial_selectors, record["serial"], "serial")
		if log:
			log("Filled phone and serial")

		confirm_button = self._page.locator("#serial_validate_button")
		self._scroll_to_confirm(confirm_button, log)
		try:
			self._page.wait_for_function(
				"btn => btn && !btn.disabled",
				arg=confirm_button,
				timeout=15000,
			)
		except Exception:
			pass

		confirm_button.click()
		if log:
			log("Clicked confirm")

		try:
			self._page.wait_for_selector("text=Hộ chiếu", timeout=15000)
			self._page.click("text=Hộ chiếu")
			if log:
				log("Selected passport document")
			self._click_start_button(log)
		except Exception as exc:
			if log:
				log(f"Modal click failed: {exc}")

		try:
			self._page.wait_for_selector("text='TẢI ẢNH LÊN'", timeout=15000)
			if log:
				log("TẢI ẢNH LÊN is visible")
		except Exception:
			pass

		try:
			self._page.wait_for_selector("input[type='file']", timeout=30000)
		except Exception:
			pass

		file_inputs = self._page.query_selector_all("input[type='file']")
		if log:
			log(f"File input count: {len(file_inputs)}")

		if len(file_inputs) < 1:
			try:
				with open("debug.html", "w", encoding="utf-8") as handle:
					handle.write(self._page.content())
				if log:
					log("Saved debug HTML: debug.html")
			except Exception:
				pass
			raise RuntimeError("No file input found")

		file_inputs[0].set_input_files(passport_path)
		if log:
			log("Uploaded passport")

		try:
			next_btn = self._page.locator(
				"div:has-text('TIẾP THEO'), button:has-text('TIẾP THEO')"
			).first
			next_btn.wait_for(state="visible", timeout=15000)
			next_btn.scroll_into_view_if_needed()
			next_btn.click(force=True)
			if log:
				log("Clicked TIẾP THEO (portrait step)")
		except Exception as exc:
			if log:
				log(f"Next button click failed: {exc}")

		try:
			understood_btn = self._page.locator(
				"button:has-text('TÔI ĐÃ HIỂU'), div:has-text('TÔI ĐÃ HIỂU')"
			).first
			understood_btn.wait_for(state="visible", timeout=15000)
			understood_btn.scroll_into_view_if_needed()
			understood_btn.click(force=True)
			if log:
				log("Clicked TÔI ĐÃ HIỂU")
		except Exception as exc:
			if log:
				log(f"TÔI ĐÃ HIỂU click failed: {exc}")

		verification_clicked = False
		try:
			self._page.wait_for_selector("text='CHỤP MẶT TRƯỚC'", timeout=15000)
			if log:
				log("Face capture step is visible")
		except Exception:
			pass

		try:
			verification_clicked = self._click_next_face_step(log)
		except Exception as exc:
			if log:
				log(f"Next face step click failed: {exc}")

		if verification_clicked:
			try:
				self._page.wait_for_load_state("networkidle", timeout=30000)
			except Exception:
				pass
			if log:
				log("Face verification completed")

		body_text = self._page.inner_text("body")
		if log:
			log("Read result from page")
		status, message = self._classify_result(body_text)
		return status, message

	def _click_start_button(self, log: Callable[[str], None] | None) -> None:
		selectors = [
			"div.vnpt-bg-primary:has-text('BẮT ĐẦU')",
			"div.vnpt-bg-primary:has-text('Bắt đầu')",
			"div:has-text('BẮT ĐẦU')",
			"div:has-text('Bắt đầu')",
		]
		for attempt, selector in enumerate(selectors, start=1):
			try:
				start_btn = self._page.locator(selector).first
				start_btn.wait_for(state="visible", timeout=15000)
				start_btn.scroll_into_view_if_needed()
				start_btn.click(force=True)
				if log:
					log(f"Clicked BẮT ĐẦU using selector #{attempt}")
				try:
					self._page.wait_for_selector(
						"text='TẢI ẢNH LÊN'", timeout=8000
					)
					if log:
						log("TẢI ẢNH LÊN is visible after click")
					return
				except Exception:
					try:
						self._page.wait_for_selector("input[type='file']", timeout=8000)
						if log:
							log("File input visible after click")
						return
					except Exception:
						pass
			except Exception as exc:
				if log:
					log(f"BẮT ĐẦU click failed using selector #{attempt}: {exc}")

	def _click_next_face_step(self, log: Callable[[str], None] | None) -> bool:
		selectors = [
			"div:has-text('CHỤP MẶT TRƯỚC') ~ div div:has-text('TIẾP THEO')",
			"div:has-text('TIẾP THEO'), button:has-text('TIẾP THEO')",
		]
		for attempt, selector in enumerate(selectors, start=1):
			try:
				next_btn = self._page.locator(selector).first
				next_btn.wait_for(state="visible", timeout=15000)
				next_btn.scroll_into_view_if_needed()
				next_btn.click(force=True)
				if log:
					log(f"Clicked TIẾP THEO (face step) using selector #{attempt}")
				return True
			except Exception as exc:
				if log:
					log(f"Face TIẾP THEO click failed using selector #{attempt}: {exc}")
		return False

	def _maximize_window(self, log: Callable[[str], None] | None) -> None:
		try:
			self._page.evaluate(
				"window.moveTo(0, 0); window.resizeTo(screen.availWidth, screen.availHeight);"
			)
			if log:
				log("Maximized browser window")
		except Exception as exc:
			if log:
				log(f"Failed to maximize window: {exc}")

	def _sync_viewport_to_screen(self, log: Callable[[str], None] | None) -> None:
		try:
			size = self._page.evaluate(
				"({ width: window.screen.availWidth, height: window.screen.availHeight })"
			)
			self._page.set_viewport_size({"width": int(size["width"]), "height": int(size["height"])})
			if log:
				log("Synced viewport to screen size")
		except Exception as exc:
			if log:
				log(f"Failed to sync viewport size: {exc}")

	def _get_screen_size(self) -> tuple[int, int]:
		try:
			user32 = ctypes.windll.user32
			try:
				user32.SetProcessDPIAware()
			except Exception:
				pass
			width = int(user32.GetSystemMetrics(0))
			height = int(user32.GetSystemMetrics(1))
			return max(width, 800), max(height, 600)
		except Exception:
			return 1920, 1080

	def _scroll_to_confirm(self, confirm_button, log: Callable[[str], None] | None) -> None:
		for attempt in range(5):
			try:
				if confirm_button.is_visible():
					return
			except Exception:
				pass

			try:
				confirm_button.scroll_into_view_if_needed()
			except Exception:
				self._page.evaluate("window.scrollBy(0, 500)")

			if log:
				log(f"Scrolled to confirm button (attempt {attempt + 1})")

	def _fill_first_available(self, selectors: list[str], value: str, label: str) -> None:
		last_error = ""
		for selector in selectors:
			try:
				self._page.wait_for_selector(selector, timeout=45000)
				self._page.fill(selector, value)
				return
			except Exception as exc:
				last_error = str(exc)
				continue

		raise RuntimeError(f"Could not find {label} input. Last error: {last_error}")

	def _classify_result(self, body_text: str) -> tuple[str, str]:
		text = body_text.lower()
		message = self._extract_message(body_text)
		if "thanh cong" in text or "thành công" in text:
			return "SUCCESS", message
		if "da duoc cap nhat" in text or "đã được cập nhật" in text:
			return "DUPLICATE", message
		if "dung ten 3 thue bao" in text or "đứng tên 3 thuê bao" in text:
			return "FAILED", message
		return "FAILED", message

	def _extract_message(self, body_text: str) -> str:
		lines = [line.strip() for line in body_text.splitlines() if line.strip()]
		if not lines:
			return "Unknown response"

		keywords = ["thành công", "thanh cong", "đã được cập nhật", "da duoc cap nhat", "đứng tên 3 thuê bao", "dung ten 3 thue bao"]
		for line in lines:
			lowered = line.lower()
			if any(keyword in lowered for keyword in keywords):
				return line

		return lines[0]

	def append_result(self, result_path: str, record_result: dict) -> None:
		if os.path.exists(result_path):
			existing = pd.read_excel(result_path, engine="openpyxl")
			updated = pd.concat([existing, pd.DataFrame([record_result])], ignore_index=True)
		else:
			updated = pd.DataFrame([record_result])
		updated.to_excel(result_path, index=False, engine="openpyxl")

	def save_screenshot(self, record_id: str) -> str | None:
		try:
			folder = os.path.join(os.getcwd(), "screenshots")
			os.makedirs(folder, exist_ok=True)
			ts = datetime.now().strftime("%Y%m%d_%H%M%S")
			path = os.path.join(folder, f"{record_id}_{ts}.png")
			self._page.screenshot(path=path, full_page=True)
			return path
		except Exception:
			return None

	def close(self) -> None:
		self._context.close()
		self._browser.close()
		self._playwright.stop()
