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
				"--disable-web-security",
				"--start-maximized",
			],
		)
		# Grant camera permission proactively to avoid permission popups
		self._context = self._browser.new_context(
			permissions=["camera"],
			no_viewport=True
		)
		self._page = self._context.new_page()

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
			# Inject mock camera script that streams the base64 image at 30 fps
			self._page.add_init_script(self._build_mock_camera_script(base64_img))
			if log:
				log("Đã khởi tạo Camera ảo giả lập ảnh chân dung")
		else:
			if log:
				log("CẢNH BÁO: Không thể tạo ảnh chân dung để quét khuôn mặt")

		self._page.goto("https://digishop.vnpt.vn/tourist/", timeout=45000, wait_until="domcontentloaded")
		if log:
			log("Đã mở trang web")

		if self._debug:
			try:
				inputs = self._page.locator("input, textarea")
				inputs.first.wait_for(state="attached", timeout=2000)
			except Exception:
				pass

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

		# Delay 2s before starting to fill
		self._page.wait_for_timeout(2000)

		self._fill_first_available(phone_selectors, record["phone"], "phone")
		self._fill_first_available(serial_selectors, record["serial"], "serial")
		if log:
			log("Đã điền Số điện thoại & Serial")

		confirm_button = self._page.locator("#serial_validate_button")
		self._scroll_to_confirm(confirm_button, log)

		# Thực hiện ngay tức thì (bỏ wait 5s + 2s)
		confirm_button.click()
		if log:
			log("Đã bấm xác nhận (Tiếp tục)")

		try:
			self._page.wait_for_selector("text=Hộ chiếu", timeout=5000)
			self._page.click("text=Hộ chiếu")
			if log:
				log("Đã chọn loại giấy tờ: Hộ chiếu")
			self._click_start_button(log)
		except Exception as exc:
			if log:
				log(f"Lỗi khi chọn loại giấy tờ: {exc}")

		try:
			self._page.wait_for_selector("text='TẢI ẢNH LÊN'", timeout=15000)
		except Exception:
			pass

		try:
			self._page.wait_for_selector("input[type='file']", timeout=30000)
		except Exception:
			pass

		file_inputs = self._page.query_selector_all("input[type='file']")

		if len(file_inputs) < 1:
			try:
				with open("debug.html", "w", encoding="utf-8") as handle:
					handle.write(self._page.content())
				if log:
					log("Saved debug HTML: debug.html")
			except Exception:
				pass
			raise RuntimeError("No file input found")

		# Delay 2s before upload
		self._page.wait_for_timeout(2000)
		file_inputs[0].set_input_files(passport_path)
		if log:
			log("Đã tải lên ảnh Hộ chiếu thành công")
		self._page.wait_for_timeout(2000)

		try:
			self._page.wait_for_selector("text='CHỤP LẠI'", timeout=30000)
			self._page.wait_for_timeout(1000)
			next_btn = self._page.locator(
				"div.vnpt-border.vnpt-cursor-pointer:has(p:has-text('TIẾP THEO'))"
			).first
			next_btn.wait_for(state="visible", timeout=15000)
			next_btn.scroll_into_view_if_needed()
			
			# Delay 2s before clicking TIẾP THEO
			self._page.wait_for_timeout(2000)
			next_btn.click(force=True)
			if log:
				log("Đã bấm TIẾP THEO (sau khi load ảnh hộ chiếu)")
			
			# Chờ đúng 5s theo yêu cầu
			self._page.wait_for_timeout(5000)
		except Exception as exc:
			if log:
				log(f"Lỗi khi bấm TIẾP THEO: {exc}")

		try:
			understood_btn = self._page.locator(
				"div.vnpt-bg-primary.vnpt-cursor-pointer:has-text('TÔI ĐÃ HIỂU')"
			).first
			understood_btn.wait_for(state="visible", timeout=15000)
			understood_btn.scroll_into_view_if_needed()
			
			understood_btn.click(force=True)
			if log:
				log("Đã bấm TÔI ĐÃ HIỂU")
		except Exception as exc:
			if log:
				log(f"Lỗi khi bấm TÔI ĐÃ HIỂU: {exc}")

		# Wait for the confirmation page and fill the missing data
		# Delay 2s before filling confirmation info is handled inside the method itself (or here)
		self._page.wait_for_timeout(2000)
		self._fill_confirmation_info(record, log)

		result_text = ""
		try:
			notification = self._page.locator(".ant-notification-notice").first
			notification.wait_for(state="visible", timeout=15000)
			result_text = notification.inner_text()
			if log:
				# Format log into a single line to avoid messy logs
				log_text = result_text.replace('\n', ' - ')
				log(f"Đọc thông báo từ hệ thống: {log_text}")
		except Exception:
			result_text = self._page.inner_text("body")

		status, message = self._classify_result(result_text)
		return status, message

	# ------------------------------------------------------------------ #
	#  Page event listeners                                                #
	# ------------------------------------------------------------------ #
	def _attach_page_listeners(
		self, log: Callable[[str], None] | None
	) -> None:
		if not log:
			return

		def _on_page_crash() -> None:
			log("Lỗi: Trang web bị đứng (Crash)")

		def _on_page_close() -> None:
			pass

		self._page.on("crash", _on_page_crash)
		self._page.on("close", _on_page_close)

	# ------------------------------------------------------------------ #
	#  Click "BẮT ĐẦU"                                                    #
	# ------------------------------------------------------------------ #
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
					log("Đã bấm BẮT ĐẦU")
				try:
					self._page.wait_for_selector(
						"text='TẢI ẢNH LÊN'", timeout=8000
					)
					return
				except Exception:
					try:
						self._page.wait_for_selector("input[type='file']", timeout=8000)
						return
					except Exception:
						pass
			except Exception as exc:
				pass

	# ------------------------------------------------------------------ #
	#  Mock camera JS – full hardware simulation                           #
	# ------------------------------------------------------------------ #
	def _build_mock_camera_script(self, base64_img: str) -> str:
		"""Return JS that simulates a full physical webcam device.

		This script prevents the VNPT eKYC SDK from detecting a fake
		camera and reloading the page by:
		  1. Creating a canvas that redraws the portrait image at 30 fps
		     via requestAnimationFrame (prevents 0-FPS freeze detection).
		  2. Capturing the canvas as a MediaStream at 30 fps.
		  3. Patching the video track with getSettings(), getConstraints(),
		     and getCapabilities() so the SDK sees valid hardware metadata.
		  4. Overriding navigator.mediaDevices.enumerateDevices() to report
		     a videoinput device named "Integrated Camera".
		  5. Overriding navigator.mediaDevices.getUserMedia() to return the
		     fake stream whenever video is requested.
		"""
		return f"""
		(() => {{
		  /* ---------- save originals ---------- */
		  const _origGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
		  const _origEnumerate    = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);

		  /* ---------- constants ---------- */
		  const W  = 1280;
		  const H  = 720;
		  const FPS = 30;
		  const DEVICE_ID  = 'fake-cam-0a1b2c3d';
		  const GROUP_ID   = 'fake-grp-4e5f6a7b';
		  const CAM_LABEL  = 'Integrated Camera (USB2.0 HD UVC WebCam)';

		  /* ---------- build canvas + draw loop ---------- */
		  const canvas = document.createElement('canvas');
		  canvas.width  = W;
		  canvas.height = H;
		  const ctx = canvas.getContext('2d');

		  const img = new Image();
		  img.src = "{base64_img}";

		  const imgReady = new Promise(r => {{
		    img.onload  = r;
		    img.onerror = r;
		  }});

		  function drawFrame() {{
		    ctx.fillStyle = '#ffffff'; // Tô nền trắng xung quanh
		    ctx.fillRect(0, 0, canvas.width, canvas.height);
		    if (img.naturalWidth > 0 && img.naturalHeight > 0) {{
		        // --- CÔNG THỨC MỚI: Thu nhỏ ảnh ---
		        // Hệ số thu nhỏ (zoom_factor) ép ảnh lọt giữa nền trắng. 
		        // 0.45 là tỷ lệ vàng cho hệ thống eKYC VNPT.
		        const zoom_factor = 0.45; 
		        
		        const scale = Math.min(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight) * zoom_factor;
		        
		        const scaledWidth = img.naturalWidth * scale;
		        const scaledHeight = img.naturalHeight * scale;
		        
		        // Căn giữa ảnh theo chiều ngang (X) và chiều dọc (Y)
		        const dx = (canvas.width - scaledWidth) / 2;
		        const dy = (canvas.height - scaledHeight) / 2;
		        
		        ctx.drawImage(img, dx, dy, scaledWidth, scaledHeight);
		    }}
		    requestAnimationFrame(drawFrame);
		  }}

		  imgReady.then(() => {{ drawFrame(); }});

		  /* ---------- capture stream ---------- */
		  const fakeStream = canvas.captureStream(FPS);
		  const fakeTrack  = fakeStream.getVideoTracks()[0];

		  /* ---------- patch track metadata ---------- */
		  Object.defineProperty(fakeTrack, 'label', {{
		    value: CAM_LABEL, writable: false, configurable: true
		  }});

		  const _origGetSettings     = fakeTrack.getSettings     ? fakeTrack.getSettings.bind(fakeTrack)     : () => ({{}});
		  const _origGetConstraints  = fakeTrack.getConstraints  ? fakeTrack.getConstraints.bind(fakeTrack)  : () => ({{}});
		  const _origGetCapabilities = fakeTrack.getCapabilities ? fakeTrack.getCapabilities.bind(fakeTrack) : () => ({{}});

		  fakeTrack.getSettings = () => ({{
		    ..._origGetSettings(),
		    width: W,
		    height: H,
		    frameRate: FPS,
		    deviceId: DEVICE_ID,
		    groupId: GROUP_ID,
		    facingMode: 'user',
		    resizeMode: 'none'
		  }});

		  fakeTrack.getConstraints = () => ({{
		    ..._origGetConstraints(),
		    width:     {{ ideal: W }},
		    height:    {{ ideal: H }},
		    frameRate: {{ ideal: FPS }},
		    deviceId:  {{ exact: DEVICE_ID }},
		    facingMode: {{ ideal: 'user' }}
		  }});

		  fakeTrack.getCapabilities = () => ({{
		    ..._origGetCapabilities(),
		    width:      {{ min: 640,  max: 1920 }},
		    height:     {{ min: 480,  max: 1080 }},
		    frameRate:  {{ min: 15,   max: 60 }},
		    deviceId:   DEVICE_ID,
		    groupId:    GROUP_ID,
		    facingMode: ['user', 'environment']
		  }});

		  /* make sure stream always returns the patched track */
		  fakeStream.getVideoTracks = () => [fakeTrack];

		  /* ---------- override getUserMedia ---------- */
		  navigator.mediaDevices.getUserMedia = async (constraints) => {{
		    if (constraints && constraints.video) {{
		      return fakeStream;
		    }}
		    return _origGetUserMedia(constraints);
		  }};

		  /* ---------- override enumerateDevices ---------- */
		  navigator.mediaDevices.enumerateDevices = async () => {{
		    const real = await _origEnumerate().catch(() => []);
		    /* remove any real videoinput, then prepend our fake one */
		    const filtered = real.filter(d => d.kind !== 'videoinput');
		    const fakeDev = {{
		      deviceId: DEVICE_ID,
		      groupId:  GROUP_ID,
		      kind:     'videoinput',
		      label:    CAM_LABEL,
		      toJSON()  {{ return this; }}
		    }};
		    /* InputDeviceInfo prototype (some SDKs do instanceof checks) */
		    try {{
		      Object.setPrototypeOf(fakeDev, InputDeviceInfo.prototype);
		    }} catch(e) {{
		      try {{ Object.setPrototypeOf(fakeDev, MediaDeviceInfo.prototype); }} catch(e2) {{}}
		    }}
		    return [fakeDev, ...filtered];
		  }};

		  console.log('[FakeCam] Mock camera installed:', CAM_LABEL, W+'x'+H, '@'+FPS+'fps');
		}})();
		"""

	def _fill_confirmation_info(self, record: dict, log: Callable[[str], None] | None) -> None:
		try:
			# Đợi trang Xác nhận thông tin load (input Nơi cấp xuất hiện)
			self._page.wait_for_selector("input[name='noicap']", timeout=15000)
			if log:
				log("Trang Xác nhận thông tin đã tải")
			
			if record.get("noi_cap"):
				self._page.fill("input[name='noicap']", record["noi_cap"])
				if log: log(f"Đã điền Nơi cấp: {record['noi_cap']}")
			
			if record.get("ngay_cap"):
				# Tìm ô nhập "Ngày cấp" thông qua placeholder
				date_input = self._page.locator("input[placeholder='Chọn thời điểm']").first
				if date_input.count() > 0:
					date_input.fill(record["ngay_cap"])
					date_input.press("Enter")
					if log: log(f"Đã điền Ngày cấp: {record['ngay_cap']}")
				else:
					# Thử tìm qua name
					try:
						date_by_name = self._page.locator("input[name='ngaycap']").first
						date_by_name.fill(record["ngay_cap"])
						date_by_name.press("Enter")
						if log: log(f"Đã điền Ngày cấp (by name): {record['ngay_cap']}")
					except Exception:
						pass
						
			# Bấm nút Xác nhận / Tiếp theo
			confirm_btn = self._page.locator(
				"button:has-text('XÁC NHẬN'), div:has-text('XÁC NHẬN'), "
				"button:has-text('TIẾP THEO'), div:has-text('TIẾP THEO')"
			).filter(visible=True)
			
			if confirm_btn.count() > 0:
				# Thực hiện ngay tức thì (bỏ wait 2s)
				confirm_btn.last.click()
				if log: log("Đã bấm XÁC NHẬN thông tin")
		except Exception:
			pass

	# ------------------------------------------------------------------ #
	#  Window / viewport helpers                                           #
	# ------------------------------------------------------------------ #
	def _maximize_window(self, log: Callable[[str], None] | None) -> None:
		try:
			self._page.evaluate(
				"window.moveTo(0, 0); window.resizeTo(screen.availWidth, screen.availHeight);"
			)
		except Exception:
			pass

	def _sync_viewport_to_screen(self, log: Callable[[str], None] | None) -> None:
		try:
			size = self._page.evaluate(
				"({ width: window.screen.availWidth, height: window.screen.availHeight })"
			)
			self._page.set_viewport_size({"width": int(size["width"]), "height": int(size["height"])})
		except Exception:
			pass

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

	# ------------------------------------------------------------------ #
	#  Form helpers                                                        #
	# ------------------------------------------------------------------ #
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

	# ------------------------------------------------------------------ #
	#  Result classification                                               #
	# ------------------------------------------------------------------ #
	def _classify_result(self, body_text: str) -> tuple[str, str]:
		text = body_text.lower()
		message = self._extract_message(body_text)
		
		# 1. Check for Duplicate first because the error message often says "cập nhật thành công trước đó"
		if "cập nhật trước đó" in text or "đã được cập nhật" in text or "vượt quá số lần" in text:
			return "DUPLICATE", message
			
		# 2. Check for Success
		if "thanh cong" in text or "thành công" in text:
			return "SUCCESS", message
			
		# 3. Everything else is FAILED
		return "FAILED", message

	def _extract_message(self, body_text: str) -> str:
		lines = [line.strip() for line in body_text.splitlines() if line.strip()]
		if not lines:
			return "Unknown response"

		keywords = ["thành công", "thanh cong", "đã được cập nhật", "cập nhật trước đó", "vượt quá số lần", "đứng tên 3 thuê bao", "dung ten 3 thue bao"]
		for line in lines:
			lowered = line.lower()
			if any(keyword in lowered for keyword in keywords):
				return line

		# Nếu message từ popup thường rất ngắn gọn và không có ký tự xuống dòng nào, ta lấy luôn dòng đầu.
		return " - ".join(lines)

	# ------------------------------------------------------------------ #
	#  Result persistence & screenshots                                    #
	# ------------------------------------------------------------------ #
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
