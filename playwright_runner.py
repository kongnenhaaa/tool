from __future__ import annotations

import ctypes
import json
import os
from datetime import datetime

import pandas as pd
from typing import Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from utils import get_cropped_face_base64, get_face_frame_base64


class PlaywrightRunner:
	def __init__(self) -> None:
		self._playwright = sync_playwright().start()
		self._debug = os.getenv("KYC_DEBUG", "0") == "1"
		# Launch browser with flags for fake camera and disable security
		self._browser = self._playwright.chromium.launch(
			headless=False,
			args=[
				"--use-fake-ui-for-media-stream",
				"--use-fake-device-for-media-stream",
				"--disable-web-security"
			]
		)
		# Grant camera permission proactively
		self._context = self._browser.new_context(permissions=['camera'])
		self._page = self._context.new_page()
	# Mock camera script is injected per run via _build_mock_camera_script; no init script here.

	def run(
		self,
		record: dict,
		passport_path: str,
		portrait_path: str,
		log: Callable[[str], None] | None = None,
	) -> tuple[str, str]:
		base64_img = get_face_frame_base64(portrait_path)
		try:
			self._page.close()
		except Exception:
			pass
		self._page = self._context.new_page()
		self._attach_page_listeners(log)
		self._maximize_window(log)
		self._sync_viewport_to_screen(log)
		if base64_img:
			# Inject a mock camera script that streams the provided base64 image at 30 fps
			self._page.add_init_script(self._build_mock_camera_script(base64_img))
			if log:
				log("Injected mock camera script with base64 image")
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
				timeout=5000,
			)
		except Exception:
			pass

		confirm_button.click()
		if log:
			log("Clicked confirm")

		try:
			self._page.wait_for_selector("text=Hộ chiếu", timeout=5000)
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
		self._page.wait_for_timeout(2000)

		try:
			self._page.wait_for_selector("text='CHỤP LẠI'", timeout=30000)
			self._page.wait_for_timeout(1000)
			next_btn = self._page.locator(
				"div.vnpt-border.vnpt-cursor-pointer:has(p:has-text('TIẾP THEO'))"
			).first
			next_btn.wait_for(state="visible", timeout=15000)
			next_btn.scroll_into_view_if_needed()
			next_btn.click(force=True)
			if log:
				log("Clicked TIẾP THEO (passport preview)")
			self._page.wait_for_timeout(1500)
			try:
				self._page.wait_for_selector("text='CHỤP MẶT TRƯỚC'", timeout=15000)
			except Exception:
				pass
		except Exception as exc:
			if log:
				log(f"Passport preview next click failed: {exc}")

		try:
			understood_btn = self._page.locator(
				"div.vnpt-bg-primary.vnpt-cursor-pointer:has-text('TÔI ĐÃ HIỂU')"
			).first
			understood_btn.wait_for(state="visible", timeout=15000)
			understood_btn.scroll_into_view_if_needed()
			understood_btn.click(force=True)
			if log:
				log("Clicked TÔI ĐÃ HIỂU")
			try:
				self._page.wait_for_load_state("domcontentloaded", timeout=5000)
				if log:
					log(f"After TÔI ĐÃ HIỂU URL: {self._page.url}")
			except Exception:
				pass
			self._page.wait_for_timeout(1500)
			try:
				self._page.wait_for_selector("text='CHỤP MẶT TRƯỚC'", timeout=15000)
			except Exception:
				pass
		except Exception as exc:
			if log:
				log(f"TÔI ĐÃ HIỂU click failed: {exc}")

		# New face verification flow (no file upload needed)
		self._wait_and_finish_face_verification(log)

		body_text = self._page.inner_text("body")
		if log:
			log("Read result from page")
		status, message = self._classify_result(body_text)
		return status, message

	def _attach_page_listeners(
		self, log: Callable[[str], None] | None
	) -> None:
		if not log:
			return

		def _on_frame_navigated(frame) -> None:
			if frame == self._page.main_frame:
				log(f"Page navigated: {frame.url}")

		def _on_page_crash() -> None:
			log("Page crashed")

		def _on_page_close() -> None:
			log("Page closed")

		self._page.on("framenavigated", _on_frame_navigated)
		self._page.on("crash", _on_page_crash)
		self._page.on("close", _on_page_close)

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

	def _build_mock_camera_script(self, base64_img: str) -> str:
		"""Return a script that fakes a camera streaming the given base64 image at 30 fps.
		The script mirrors the logic described by the user.
		"""
		return f"""
		(() => {{
		  const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
		  navigator.mediaDevices.getUserMedia = async (constraints) => {{
		    if (constraints && constraints.video) {{
		      const canvas = document.createElement('canvas');
		      canvas.width = 640;
		      canvas.height = 480;
		      const ctx = canvas.getContext('2d');
		      const img = new Image();
		      img.src = "{base64_img}";
		      await new Promise((resolve) => {{
		        img.onload = resolve;
		        img.onerror = resolve;
		      }});
		      function drawFrame() {{
		        ctx.fillStyle = '#ffffff';
		        ctx.fillRect(0, 0, canvas.width, canvas.height);
		        const scale = Math.min(canvas.width / img.width, canvas.height / img.height);
		        const x = (canvas.width / 2) - (img.width / 2) * scale;
		        const y = (canvas.height / 2) - (img.height / 2) * scale;
		        ctx.drawImage(img, x, y, img.width * scale, img.height * scale);
		        requestAnimationFrame(drawFrame);
		      }}
		      drawFrame();
		      const stream = canvas.captureStream(30);
		      const originalGetVideoTracks = stream.getVideoTracks.bind(stream);
		      stream.getVideoTracks = function() {{
		        const tracks = originalGetVideoTracks();
		        if (tracks && tracks.length > 0) {{
		          Object.defineProperty(tracks[0], 'label', {{value: 'Fake Integrated Camera', writable: false}});
		        }}
		        return tracks;
		      }};
		      return stream;
		    }}
		    return originalGetUserMedia(constraints);
		  }};
		}})();
		"""

	# Updated face verification flow after clicking the passport "TIẾP THEO" button.
	# This replaces the previous _click_next_face_step / verification_clicked logic.
	# It waits for the AI to finish scanning and clicks the final "TIẾP THEO" button.
	def _wait_and_finish_face_verification(self, log: Callable[[str], None] | None) -> None:
		if log:
			log("Chuyển sang bước Xác thực khuôn mặt (Camera AI)")
		try:
			if log:
				log("Đang chờ AI quét khuôn mặt...")
			# Wait for possible network activity to settle
			self._page.wait_for_load_state("networkidle", timeout=60000)
			finish_btn = self._page.locator("button:has-text('TIẾP THEO'), p:has-text('TIẾP THEO'), div:has-text('TIẾP THEO')").filter(visible=True)
			finish_btn.first.wait_for(state="visible", timeout=45000)
			if finish_btn.count() > 0:
				finish_btn.first.click()
				if log:
					log("Bấm Tiếp theo sau khi quét mặt thành công")
		except Exception as exc:
			if log:
				log(f"Quá trình đợi quét khuôn mặt có thể bị timeout hoặc lỗi: {exc}")
		if log:
			log("Face verification completed")

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
