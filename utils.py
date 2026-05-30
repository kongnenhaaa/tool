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


def get_face_frame_base64(
	image_path: str,
	target_width: int = 640,
	target_height: int = 360,
) -> str:
	"""
	Create a webcam-style frame focused on the face with a 16:9 aspect ratio.
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
		target_aspect = target_width / target_height

		if len(faces) > 0:
			x, y, w, h = faces[0]
			cx = x + w / 2
			cy = y + h / 2
			crop_h = max(h * 2.2, w / target_aspect)
			crop_w = crop_h * target_aspect
		else:
			cx = img.shape[1] / 2
			cy = img.shape[0] / 2
			crop_h = min(img.shape[0], img.shape[1] / target_aspect)
			crop_w = crop_h * target_aspect

		x1 = int(max(0, cx - crop_w / 2))
		x2 = int(min(img.shape[1], cx + crop_w / 2))
		y1 = int(max(0, cy - crop_h / 2))
		y2 = int(min(img.shape[0], cy + crop_h / 2))
		frame = img[y1:y2, x1:x2]

		frame = cv2.resize(frame, (target_width, target_height))
		ok, buffer = cv2.imencode(".jpg", frame)
		if not ok:
			return ""

		base64_str = base64.b64encode(buffer).decode("utf-8")
		return f"data:image/jpeg;base64,{base64_str}"
	except Exception as exc:
		print(f"Loi khi xu ly anh {image_path}: {exc}")
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
