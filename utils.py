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

		target_aspect = target_width / target_height

		if len(faces) > 0:
			# Pick the largest face
			faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
			x, y, w, h = faces_sorted[0]

			# Center of the detected face
			cx = x + w / 2
			cy = y + h / 2

			# We want the face to occupy ~25% of the output frame height
			# so it fits comfortably inside the VNPT oval frame with
			# enough margin for forehead, chin, and both sides.
			# face_h ≈ 0.25 * target_height  →  crop_h = h / 0.25
			# The face bounding box height in the source image is `h`.
			desired_face_ratio = 0.25  # face fills 25% of frame height
			crop_h = h / desired_face_ratio
			crop_w = crop_h * target_aspect

			# If crop is larger than image, clamp
			if crop_w > img_w:
				crop_w = img_w
				crop_h = crop_w / target_aspect
			if crop_h > img_h:
				crop_h = img_h
				crop_w = crop_h * target_aspect

			# Move center up slightly (faces look more natural when slightly
			# above center — show a bit more forehead area)
			cy = cy - h * 0.05
		else:
			# No face detected — center crop
			cx = img_w / 2
			cy = img_h / 2
			crop_h = min(img_h, img_w / target_aspect)
			crop_w = crop_h * target_aspect

		# Compute crop bounds, keeping within image
		x1 = int(max(0, cx - crop_w / 2))
		x2 = int(min(img_w, cx + crop_w / 2))
		y1 = int(max(0, cy - crop_h / 2))
		y2 = int(min(img_h, cy + crop_h / 2))

		# If the crop was clamped at an edge, shift the other side
		if x2 - x1 < int(crop_w):
			if x1 == 0:
				x2 = min(img_w, int(crop_w))
			elif x2 == img_w:
				x1 = max(0, img_w - int(crop_w))
		if y2 - y1 < int(crop_h):
			if y1 == 0:
				y2 = min(img_h, int(crop_h))
			elif y2 == img_h:
				y1 = max(0, img_h - int(crop_h))

		frame = img[y1:y2, x1:x2]
		frame = cv2.resize(frame, (target_width, target_height))

		ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
		if not ok:
			return ""

		base64_str = base64.b64encode(buffer).decode("utf-8")
		return f"data:image/jpeg;base64,{base64_str}"
	except Exception as exc:
		print(f"Loi khi xu ly anh {image_path}: {exc}")
		return ""
