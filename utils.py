from __future__ import annotations

import base64
import os

import cv2


def get_cropped_face_base64(image_path: str) -> str:
	"""
	Đọc ảnh, tìm khuôn mặt, cắt (crop) và trả về chuỗi Base64.
	Nếu không nhận diện được mặt, sẽ lấy toàn bộ ảnh gốc.
	"""
	if not os.path.exists(image_path):
		return ""

	try:
		face_cascade = cv2.CascadeClassifier(
			cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
		)
		img = cv2.imread(image_path)
		if img is None:
			return ""

		gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
		faces = face_cascade.detectMultiScale(gray, 1.3, 5)

		if len(faces) > 0:
			x, y, w, h = faces[0]
			margin = int(h * 0.3)
			y1 = max(0, y - margin)
			y2 = min(img.shape[0], y + h + margin)
			x1 = max(0, x - margin)
			x2 = min(img.shape[1], x + w + margin)
			face_img = img[y1:y2, x1:x2]
		else:
			face_img = img

		face_img = cv2.resize(face_img, (640, 480))
		ok, buffer = cv2.imencode(".jpg", face_img)
		if not ok:
			return ""

		base64_str = base64.b64encode(buffer).decode("utf-8")
		return f"data:image/jpeg;base64,{base64_str}"
	except Exception as exc:
		print(f"Lỗi khi xử lý ảnh {image_path}: {exc}")
		return ""


def get_face_frame_base64(
	image_path: str,
	target_width: int = 1280,
	target_height: int = 720,
) -> str:
	"""
	Xác định khuôn mặt trong ảnh, crop theo tỷ lệ chuẩn 16:9 (1280x720)
	và trả về chuỗi base64. Nếu không tìm thấy, crop center.
	"""
	if not os.path.exists(image_path):
		return ""

	try:
		face_cascade = cv2.CascadeClassifier(
			cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
		)
		img = cv2.imread(image_path)
		if img is None:
			return ""

		img_h, img_w = img.shape[:2]
		gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
		faces = face_cascade.detectMultiScale(
			gray,
			scaleFactor=1.1,
			minNeighbors=5,
			minSize=(60, 60),
		)

		target_aspect = target_width / target_height

		if len(faces) > 0:
			# We want the face to occupy exactly 30% of the frame height
			desired_face_ratio = 0.30
			face_target_h = int(target_height * desired_face_ratio)
			
			# Lấy khuôn mặt to nhất
			faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
			x, y, w, h = faces_sorted[0]
			
			# Tọa độ trung tâm khuôn mặt
			cx = x + w / 2
			cy = y + h / 2 - h * 0.05  # Nhích lên một chút cho tự nhiên
			
			scale = face_target_h / h
		else:
			cx = img_w / 2
			cy = img_h / 2
			scale = target_height / img_h

		# Scale ảnh gốc theo tỷ lệ để khuôn mặt đạt chuẩn 30% chiều cao
		new_w = int(img_w * scale)
		new_h = int(img_h * scale)
		scaled_img = cv2.resize(img, (new_w, new_h))

		scaled_cx = int(cx * scale)
		scaled_cy = int(cy * scale)

		# Tính toán vị trí để đặt ảnh scaled_img sao cho khuôn mặt nằm giữa frame
		paste_x = target_width // 2 - scaled_cx
		paste_y = target_height // 2 - scaled_cy

		# 1. TẠO HÌNH NỀN BỊ LÀM MỜ (BLURRED BACKGROUND)
		# Tránh viền đen/trắng, thay bằng viền mờ tự nhiên từ ảnh gốc
		bg_scale = max(target_width / img_w, target_height / img_h)
		bg_w = int(img_w * bg_scale)
		bg_h = int(img_h * bg_scale)
		bg = cv2.resize(img, (bg_w, bg_h))
		
		bg_x = (bg_w - target_width) // 2
		bg_y = (bg_h - target_height) // 2
		frame = bg[bg_y:bg_y+target_height, bg_x:bg_x+target_width].copy()
		
		# Làm mờ thật mạnh phông nền
		frame = cv2.GaussianBlur(frame, (99, 99), 0)

		# 2. DÁN ẢNH CHÂN DUNG LÊN TRÊN NỀN MỜ
		y1 = max(0, paste_y)
		y2 = min(target_height, paste_y + new_h)
		x1 = max(0, paste_x)
		x2 = min(target_width, paste_x + new_w)

		img_y1 = max(0, -paste_y)
		img_y2 = img_y1 + (y2 - y1)
		img_x1 = max(0, -paste_x)
		img_x2 = img_x1 + (x2 - x1)

		if y2 > y1 and x2 > x1:
			frame[y1:y2, x1:x2] = scaled_img[img_y1:img_y2, img_x1:img_x2]

		ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
		if not ok:
			return ""

		base64_str = base64.b64encode(buffer).decode("utf-8")
		return f"data:image/jpeg;base64,{base64_str}"
	except Exception as exc:
		print(f"Loi khi xu ly anh {image_path}: {exc}")
		return ""

def get_id_photo_base64(image_path: str) -> str:
	"""
	Crop một ảnh 3:4 chuẩn thẻ (như ảnh thẻ CMND) quanh khuôn mặt
	để hiển thị trên trang Xác nhận thông tin. Không bù viền mờ.
	"""
	if not os.path.exists(image_path):
		return ""

	try:
		img = cv2.imread(image_path)
		if img is None:
			return ""

		face_cascade = cv2.CascadeClassifier(
			cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
		)

		img_h, img_w = img.shape[:2]
		gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
		faces = face_cascade.detectMultiScale(
			gray,
			scaleFactor=1.1,
			minNeighbors=5,
			minSize=(60, 60),
		)

		# Tỷ lệ chuẩn của khung ảnh thẻ là 3:4 (Portrait)
		target_aspect = 3.0 / 4.0

		if len(faces) > 0:
			# Khuôn mặt chiếm khoảng 45% khung hình
			desired_face_ratio = 0.45
			faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
			x, y, w, h = faces_sorted[0]
			
			cx = x + w / 2
			# Cộng thêm vào cy (dịch tâm cắt xuống dưới) để lấy được phần ngực/vai ở phía dưới
			cy = y + h / 2 + h * 0.15
			
			crop_h = h / desired_face_ratio
			crop_w = crop_h * target_aspect

			# Nếu lố viền thì clamp lại
			if crop_w > img_w:
				crop_w = img_w
				crop_h = crop_w / target_aspect
			if crop_h > img_h:
				crop_h = img_h
				crop_w = crop_h * target_aspect
		else:
			cx = img_w / 2
			cy = img_h / 2
			crop_h = min(img_h, img_w / target_aspect)
			crop_w = crop_h * target_aspect

		x1 = int(max(0, cx - crop_w / 2))
		x2 = int(min(img_w, cx + crop_w / 2))
		y1 = int(max(0, cy - crop_h / 2))
		y2 = int(min(img_h, cy + crop_h / 2))

		# Fix lẹm góc
		if x2 - x1 < int(crop_w):
			if x1 == 0: x2 = min(img_w, int(crop_w))
			elif x2 == img_w: x1 = max(0, img_w - int(crop_w))
		if y2 - y1 < int(crop_h):
			if y1 == 0: y2 = min(img_h, int(crop_h))
			elif y2 == img_h: y1 = max(0, img_h - int(crop_h))

		frame = img[y1:y2, x1:x2]
		# Thay đổi kích thước ảnh thẻ chuẩn 480x640 (Portrait)
		frame = cv2.resize(frame, (480, 640))

		ok, buffer = cv2.imencode(".png", frame)
		if not ok:
			return ""

		base64_str = base64.b64encode(buffer).decode("utf-8")
		return f"data:image/png;base64,{base64_str}"
	except Exception as exc:
		print(f"Loi khi xu ly id photo {image_path}: {exc}")
		return ""
