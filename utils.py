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
	target_width: int = 640,
	target_height: int = 360,
) -> str:
	"""Create a webcam-style frame (16:9) with the face centered and sized
	to fill approximately 40% of the frame height, matching VNPT's 640x360 oval.

	This produces an image that looks natural inside the eKYC oval frame:
	- Face is vertically centered with enough forehead/chin margin.
	- Face horizontally centered.
	- Background filled with a neutral skin-friendly color.
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

		if len(faces) > 0:
			# We want the face to occupy exactly 35% of the frame height
			desired_face_ratio = 0.35
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

		# Scale ảnh gốc theo tỷ lệ để khuôn mặt đạt chuẩn 45% chiều cao
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
