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
