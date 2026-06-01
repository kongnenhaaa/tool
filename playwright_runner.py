from __future__ import annotations

import ctypes
import json
import os
import time
from datetime import datetime

import pandas as pd
from typing import Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from utils import get_cropped_face_base64, get_face_frame_base64, get_id_photo_base64


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
		apply_filter: bool = False,
	) -> tuple[str, str]:
		base64_img = get_face_frame_base64(portrait_path, apply_filter=apply_filter)
		portrait_b64 = get_id_photo_base64(portrait_path, apply_filter=apply_filter)
		self._portrait_path = portrait_path  # Lưu lại để dùng ở trang xác nhận
		try:
			self._page.close()
		except Exception:
			pass
		self._page = self._context.new_page()
		self._attach_page_listeners(log)
		self._maximize_window(log)
		self._sync_viewport_to_screen(log)
		if base64_img and portrait_b64:
			# Inject mock camera script that streams the base64 image at 30 fps
			self._page.add_init_script(self._build_mock_camera_script(base64_img, portrait_b64))
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

		# Delay 1s before upload
		self._page.wait_for_timeout(1000)
		file_inputs[0].set_input_files(passport_path)
		if log:
			log("Đã tải lên ảnh Hộ chiếu thành công")
		
		# Chờ 5s rồi bấm TIẾP THEO
		self._page.wait_for_timeout(5000)

		try:
			next_btn = self._page.locator(
				"div.vnpt-border.vnpt-cursor-pointer:has(p:has-text('TIẾP THEO'))"
			).first
			next_btn.click(force=True)
			if log:
				log("Đã bấm TIẾP THEO (sau khi load ảnh hộ chiếu)")
			
			# Chờ 5s cho bước TÔI ĐÃ HIỂU
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

		# Chờ kết quả eKYC (chuyển sang trang Xác nhận hoặc báo lỗi ngay lập tức)
		try:
			success_locator = self._page.locator("input[name='noicap']")
			error_locator = self._page.locator(".ant-notification-notice")
			either_locator = success_locator.or_(error_locator)
			
			# Đợi tối đa 20s cho 1 trong 2 cái xuất hiện
			either_locator.first.wait_for(state="visible", timeout=20000)
			
			if error_locator.first.is_visible():
				err_text = error_locator.first.inner_text()
				if "không đạt" in err_text.lower() or "thử lại" in err_text.lower() or "lỗi" in err_text.lower():
					if log: log(f"Lỗi eKYC ngay tại bước Xác thực khuôn mặt: {err_text.replace(chr(10), ' - ')}")
					self._page.wait_for_timeout(2000) # Đợi 2s cho người dùng đọc
					return "FAILED", err_text.replace('\n', ' - ')
		except Exception:
			pass

		# Chờ thêm 5s trước khi điền form Xác nhận (nếu qua được bước trên)
		self._page.wait_for_timeout(5000)
		self._fill_confirmation_info(record, log)

		try:
			notification = self._page.locator(".ant-notification-notice").first
			# Đợi 7 giây theo yêu cầu, nếu không có thì nhảy xuống except
			notification.wait_for(state="visible", timeout=7000)
			result_text = notification.inner_text()
			if log:
				log_text = result_text.replace('\n', ' - ')
				log(f"Đọc thông báo từ hệ thống: {log_text}")
			
			# Phân loại kết quả từ thông báo
			status, message = self._classify_result(result_text)
		except Exception:
			# Quá 7 giây mà không có thông báo nào hiện lên -> Mặc định là thành công
			if log:
				log("Đợi 7s không thấy thông báo lỗi -> Tài khoản đã thành công!")
			status, message = "SUCCESS", "Cập nhật thành công (Không có thông báo)"
		
		# Chờ 5s cuối cùng để xem kết quả trước khi đóng/chuyển web
		self._page.wait_for_timeout(5000)
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
	def _build_mock_camera_script(self, base64_img: str, portrait_b64: str) -> str:
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
		  /* ---------- ULTIMATE HACK: Inject HD Portrait safely without breaking Liveness ---------- */
		  const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
		  const _origToBlob    = HTMLCanvasElement.prototype.toBlob;
		  const recentFaces = [];
		  const HD_PORTRAIT_URI = "{portrait_b64}";
		  const hdPortraitRaw = HD_PORTRAIT_URI.split(',')[1];
		  
		  // 1. Đánh chặn toDataURL: Canvas lớn (chụp khuôn mặt) → trả thẳng ảnh HD Portrait
		  //    Canvas nhỏ (helper) → giữ nguyên + ghi log cho replaceFaceInPayload
		  HTMLCanvasElement.prototype.toDataURL = function(type, encoderOptions) {{
		      // Canvas lớn = chụp khuôn mặt → trả ảnh HD Portrait sạch đẹp, KHÔNG viền mờ
		      if (this.width >= 400 && this.height >= 400) {{
		          return HD_PORTRAIT_URI;
		      }}
		      const res = _origToDataURL.apply(this, arguments);
		      if (res && res.length > 5000) {{
		          const parts = res.split(',');
		          if (parts.length === 2) {{
		              recentFaces.push(parts[1]);
		              if (recentFaces.length > 200) recentFaces.shift();
		          }}
		      }}
		      return res;
		  }};
		  
		  // 2. Thay thế toBlob (thường chỉ dùng 1 lần lúc chụp thật)
		  HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {{
		      if (this.width >= 400 && this.height >= 400) {{
		          console.log("[FakeCam] HACKED toBlob! Injecting HD Portrait to Server!");
		          fetch(HD_PORTRAIT_URI).then(res => res.blob()).then(blob => callback(blob));
		          return;
		      }}
		      return _origToBlob.apply(this, arguments);
		  }};

		  // Hàm hỗ trợ quét và thay thế
		  function replaceFaceInPayload(bodyStr) {{
		      if (typeof bodyStr !== 'string' || !hdPortraitRaw) return bodyStr;
		      let modified = bodyStr;
		      // Quét ngược từ frame mới nhất về cũ nhất
		      for (let i = recentFaces.length - 1; i >= 0; i--) {{
		          const plainFace = recentFaces[i];
		          
		          // 1. Dạng base64 thuần
		          if (modified.includes(plainFace)) {{
		              console.log("[FakeCam] HACKED! Gửi ảnh siêu nét lên server (Plain - Frame " + i + ").");
		              modified = modified.split(plainFace).join(hdPortraitRaw);
		          }}
		          
		          // 2. Dạng URL Encoded (thường dùng trong form urlencoded)
		          const urlEncodedFace = encodeURIComponent(plainFace);
		          if (modified.includes(urlEncodedFace)) {{
		              console.log("[FakeCam] HACKED! Gửi ảnh siêu nét lên server (UrlEncoded - Frame " + i + ").");
		              modified = modified.split(urlEncodedFace).join(encodeURIComponent(hdPortraitRaw));
		          }}
		          
		          // 3. Dạng JSON Escaped (thường dùng trong JSON stringify)
		          const jsonEscapedFace = plainFace.split('/').join('\\\\/');
		          const hdEscapedFace = hdPortraitRaw.split('/').join('\\\\/');
		          if (modified.includes(jsonEscapedFace)) {{
		              console.log("[FakeCam] HACKED! Gửi ảnh siêu nét lên server (JSON Escaped - Frame " + i + ").");
		              modified = modified.split(jsonEscapedFace).join(hdEscapedFace);
		          }}
		      }}
		      return modified;
		  }}

		  // 3. Đánh chặn XHR (Thay ruột gói tin API trước khi bay lên server)
		  const _origXHRSend = XMLHttpRequest.prototype.send;
		  XMLHttpRequest.prototype.send = function(body) {{
		      body = replaceFaceInPayload(body);
		      return _origXHRSend.apply(this, arguments);
		  }};

		  // 4. Đánh chặn fetch API (Cả body lẫn data URI)
		  const _origFetch = window.fetch;
		  window.fetch = async function(...args) {{
		      if (args[0] && typeof args[0] === 'string' && args[0].startsWith('data:')) {{
		          args[0] = replaceFaceInPayload(args[0]);
		      }}
		      if (args[1] && typeof args[1].body === 'string') {{
		          args[1].body = replaceFaceInPayload(args[1].body);
		      }}
		      return _origFetch.apply(this, args);
		  }};

		  // 5. Đánh chặn FormData (Trường hợp API dùng form-data gửi string)
		  const _origAppend = FormData.prototype.append;
		  FormData.prototype.append = function(name, value, filename) {{
		      if (typeof value === 'string') {{
		          value = replaceFaceInPayload(value);
		      }}
		      return _origAppend.apply(this, arguments);
		  }};

		  // 6. Đánh chặn sessionStorage / localStorage (Ngăn SDK truyền ảnh mờ sang trang Xác nhận)
		  const _origSetItem = Storage.prototype.setItem;
		  Storage.prototype.setItem = function(key, value) {{
		      if (typeof value === 'string') {{
		          value = replaceFaceInPayload(value);
		      }}
		      return _origSetItem.apply(this, arguments);
		  }};

		  // 7. Đánh chặn atob (Trường hợp SDK dùng atob để convert base64 thành Blob)
		  const _origAtob = window.atob;
		  window.atob = function(data) {{
		      if (typeof data === 'string') {{
		          data = replaceFaceInPayload(data);
		      }}
		      return _origAtob.apply(this, arguments);
		  }};

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

		  window.fakeCamZoom = 1.0;
		  
		  // Auto-zoom AI: tự động nhận diện cảnh báo của VNPT để zoom gần/xa
		  setInterval(() => {{
		      const warningMsg = document.querySelector('.warning-message p, .vnpt-text-warning');
		      if (warningMsg) {{
		          const text = warningMsg.textContent.trim().toLowerCase();
		          if (text.includes('gần hơn nữa')) {{
		              window.fakeCamZoom += 0.015; // Phóng to dần đều
		          }} else if (text.includes('xa hơn') || text.includes('vừa khung hình')) {{
		              window.fakeCamZoom -= 0.015; // Thu nhỏ dần đều
                      if (window.fakeCamZoom < 1.0) window.fakeCamZoom = 1.0; // KHÔNG BAO GIỜ CHO PHÉP NHỎ HƠN 1 ĐỂ CHỐNG VIỀN ĐEN!
		          }}
		      }}
		  }}, 100);

		  function drawFrame() {{
		    if (img.naturalWidth > 0 && img.naturalHeight > 0) {{
		        // Dùng object-fit cover logic để ảnh không bị méo tỷ lệ
		        const baseScale = Math.max(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight);
		        const scale = baseScale * window.fakeCamZoom;
		        
		        const scaledWidth = img.naturalWidth * scale;
		        const scaledHeight = img.naturalHeight * scale;
		        const dx = (canvas.width - scaledWidth) / 2;
		        const dy = (canvas.height - scaledHeight) / 2;
		        
		        // Xóa nền canvas bằng màu đen (đề phòng khi zoom out)
		        ctx.fillStyle = '#000000';
		        ctx.fillRect(0, 0, canvas.width, canvas.height);
		        
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
			# Inject CSS xóa nền trắng + điền ảnh gốc chân dung vào khung
			try:
				if hasattr(self, '_portrait_path') and self._portrait_path:
					portrait_b64 = get_id_photo_base64(self._portrait_path)
					
					self._page.evaluate(f"""
						const myPayload = '{portrait_b64}';
						
						// Dùng setInterval chạy siêu nhanh (10ms) để không bị nháy ảnh mờ (Flicker)
						const interval = setInterval(() => {{
							const boxes = document.querySelectorAll('.inbox-idcard');
							if (boxes.length >= 2) {{
								const faceBox = boxes[boxes.length - 1]; // Khung chứa khuôn mặt
								
								// LÀM ĐÚNG NHƯ USER YÊU CẦU: CHỈ THAY THẾ ẢNH (KHÔNG THÊM/XÓA DOM ĐỂ CHỐNG CRASH)
								const imgs = faceBox.querySelectorAll('img');
								imgs.forEach(img => {{
									// 1. Phân biệt ảnh chụp và viền xanh dựa vào DUNG LƯỢNG (độ dài chuỗi base64).
									// 2. Ảnh chụp webcam thường rất lớn (> 50,000 ký tự). Viền xanh thì nhẹ hơn nhiều.
									if (img.src && img.src.length > 50000) {{
										if (img.src !== myPayload) {{
											img.src = myPayload;
										}}
										// Thu nhỏ ảnh xuống 85% để tạo khoảng trống, nằm lọt thỏm giữa 4 góc viền xanh
										img.style.setProperty('transform', 'scale(0.85)', 'important');
									}}
								}});
								
								// Dọn dẹp các thẻ rác do mã cũ tạo ra để dọn dẹp DOM
								const oldMyImg = document.getElementById('my-awesome-face');
								if (oldMyImg) oldMyImg.remove();
							}}
						}}, 10); // 10ms = Mắt người không kịp nhìn thấy ảnh cũ
						
						// Dừng interval sau 15 giây
						setTimeout(() => clearInterval(interval), 15000);
					""")
			except Exception:
				pass


			if record.get("noi_cap"):
				self._page.wait_for_timeout(5000)
				self._page.fill("input[name='noicap']", record["noi_cap"])
				if log: log(f"Đã điền Nơi cấp: {record['noi_cap']}")
			
			if record.get("ngay_cap"):
				self._page.wait_for_timeout(5000)
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
				self._page.wait_for_timeout(5000)
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

	def _cleanup_old_screenshots(self) -> None:
		try:
			folder = os.path.join(os.getcwd(), "screenshots")
			if not os.path.exists(folder):
				return
			
			# Lấy danh sách tất cả file png
			files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.png')]
			if not files:
				return
				
			now = time.time()
			# Sắp xếp file theo thời gian tạo, cũ nhất đứng đầu
			files.sort(key=lambda x: os.path.getmtime(x))
			
			# 1. Xóa file quá 3 ngày tuổi
			max_age_seconds = 3 * 24 * 3600
			surviving_files = []
			for f in files:
				try:
					if now - os.path.getmtime(f) > max_age_seconds:
						os.remove(f)
					else:
						surviving_files.append(f)
				except Exception:
					surviving_files.append(f)
					
			# 2. Xóa bớt nếu tổng số ảnh còn lại vượt quá 100
			if len(surviving_files) > 100:
				excess = len(surviving_files) - 100
				for f in surviving_files[:excess]:
					try:
						os.remove(f)
					except Exception:
						pass
		except Exception:
			pass

	def save_screenshot(self, record_id: str) -> str | None:
		try:
			self._cleanup_old_screenshots()
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
