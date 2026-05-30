from __future__ import annotations

import base64

import cv2


def get_cropped_face_base64(image_path: str) -> str | None:
	face_cascade = cv2.CascadeClassifier(
		cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
	)
	if face_cascade.empty():
		return None

	img = cv2.imread(image_path)
	if img is None:
		return None

	gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
	faces = face_cascade.detectMultiScale(gray, 1.3, 5)
	if len(faces) == 0:
		return None

	x, y, w, h = faces[0]
	margin = int(h * 0.3)
	x1 = max(0, x - margin)
	y1 = max(0, y - margin)
	x2 = min(img.shape[1], x + w + margin)
	y2 = min(img.shape[0], y + h + margin)

	cropped_face = img[y1:y2, x1:x2]
	ok, buffer = cv2.imencode(".jpg", cropped_face)
	if not ok:
		return None

	base64_str = base64.b64encode(buffer).decode("utf-8")
	return f"data:image/jpeg;base64,{base64_str}"
