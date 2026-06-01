from __future__ import annotations

import json
import os
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from excel_reader import read_input_excel
from playwright_runner import PlaywrightRunner

class WebWorker(threading.Thread):
	def __init__(self, excel_path: str, photo_folder: str, message_queue: queue.Queue[dict[str, Any]], resume: bool = False) -> None:
		super().__init__()
		self.excel_path = excel_path
		self.photo_folder = photo_folder
		self.message_queue = message_queue
		self.resume = resume
		self.result_path = os.path.join(os.path.dirname(excel_path), "result.xlsx")
		self.log_path = os.path.join(os.path.dirname(excel_path), "log.txt")
		self.success = 0
		self.failed = 0
		self.duplicate = 0
		self.is_running = True
		self.progress_file = os.path.join(os.path.dirname(excel_path), "progress.json")
		self.completed_ids = set()

	def _load_progress(self):
		if self.resume and os.path.exists(self.progress_file):
			try:
				with open(self.progress_file, "r", encoding="utf-8") as f:
					data = json.load(f)
					self.completed_ids = set(data.get("completed_ids", []))
					self.success = data.get("success", 0)
					self.failed = data.get("failed", 0)
					self.duplicate = data.get("duplicate", 0)
				self._log(f"Đã nạp {len(self.completed_ids)} records từ tiến trình cũ.")
			except Exception as e:
				self._log(f"Lỗi khi nạp progress: {e}")
		else:
			if os.path.exists(self.progress_file):
				try:
					os.remove(self.progress_file)
				except:
					pass

	def _save_progress(self, record_id: str):
		self.completed_ids.add(record_id)
		try:
			data = {
				"completed_ids": list(self.completed_ids),
				"success": self.success,
				"failed": self.failed,
				"duplicate": self.duplicate
			}
			with open(self.progress_file, "w", encoding="utf-8") as f:
				json.dump(data, f, ensure_ascii=False)
		except Exception as e:
			pass

	def run(self) -> None:
		try:
			self._emit({"type": "status", "message": "Đang khởi động tiến trình..."})
			self._load_progress()
			
			records = read_input_excel(self.excel_path)
			total = len(records)
			if total == 0:
				self._log("Lỗi: Không tìm thấy dữ liệu khách hàng trong file Excel.")
				self._emit({"type": "finished"})
				return

			self.runner = PlaywrightRunner()

			for index, record in enumerate(records, start=1):
				if not self.is_running:
					self._log("Tiến trình đã bị dừng bởi người dùng.")
					break
				
				record_id = record["id"]
				
				if record_id in self.completed_ids:
					progress = int(index / total * 100)
					self._emit({"type": "progress", "value": progress})
					self._emit({
						"type": "counters",
						"success": self.success,
						"failed": self.failed,
						"duplicate": self.duplicate
					})
					continue

				self._log(f"Đang xử lý Khách hàng: ID={record_id} | Số điện thoại={record['phone']} | Serial={record['serial']}")
				
				# Generate Preview
				passport, portrait = self._resolve_photos(record_id)
				if portrait and os.path.exists(portrait):
					from utils import get_id_photo_base64
					# Lấy base64 nguyên bản (thay vì tải đường dẫn)
					orig_b64 = get_id_photo_base64(portrait, apply_filter=False)
					proc_b64 = get_id_photo_base64(portrait, apply_filter=True)
					self._emit({
						"type": "preview",
						"original": orig_b64,
						"processed": proc_b64
					})
					
				# Chạy lần 1 với ảnh gốc (không có bộ lọc đổi da)
				status, message = self._process_record(self.runner, record, apply_filter=False)

				# Nếu lần 1 bị rớt do lỗi Liveness (không đạt), thử lại lần 2 với bộ lọc "đổi da"
				if status == "FAILED" and "không đạt" in message.lower() and self.is_running:
					self._log("Lỗi eKYC! Kích hoạt chế độ THỬ LẠI với bộ lọc thay đổi da (Anti-Glare & CLAHE)...")
					# Chạy lần 2 (có bộ lọc)
					status, message = self._process_record(self.runner, record, apply_filter=True)

				# Nếu đã bấm STOP thì dừng, không lưu kết quả STOPPED
				if status == "STOPPED":
					self._log("Đã dừng tiến trình thành công.")
					break

				if status == "SUCCESS":
					self.success += 1
				elif status == "DUPLICATE":
					self.duplicate += 1
				else:
					self.failed += 1

				record_result = {**record, "status": status, "message": message}
				self.runner.append_result(self.result_path, record_result)
				self._save_progress(record_id)

				self._emit({
					"type": "counters",
					"success": self.success,
					"failed": self.failed,
					"duplicate": self.duplicate
				})
				
				progress = int(index / total * 100)
				self._emit({"type": "progress", "value": progress})

			if hasattr(self, 'runner') and self.runner:
				try:
					self.runner.close()
				except Exception:
					pass
			self._log("Hoàn thành toàn bộ tiến trình!")
			self._emit({"type": "finished", "result_path": self.result_path, "log_path": self.log_path})
		except Exception as exc:
			self._log(f"Lỗi nghiêm trọng: {exc}")
			self._emit({"type": "finished", "error": str(exc)})
		finally:
			self.is_running = False

	def stop(self):
		self.is_running = False
		if hasattr(self, 'runner') and self.runner:
			try:
				# Aggressively close the runner to interrupt any blocking Playwright calls
				self.runner.close()
			except Exception:
				pass

	def _emit(self, data: dict[str, Any]) -> None:
		self.message_queue.put(data)

	def _process_record(self, runner: PlaywrightRunner, record: dict, apply_filter: bool = False) -> tuple[str, str]:
		passport, portrait = self._resolve_photos(record["id"])
		if not passport or not portrait:
			missing = "Ảnh Hộ chiếu" if not passport else "Ảnh chân dung"
			return "FAILED", f"Thiếu {missing}"

		try:
			status, message = runner.run(record, passport, portrait, log=self._log, apply_filter=apply_filter)
			return status, message
		except Exception as exc:
			# Nếu stop được gọi trong khi đang chạy, không tính là FAILED
			if not self.is_running:
				return "STOPPED", "Tiến trình bị dừng bởi người dùng"
			last_error = str(exc)
			self._log(f"Lỗi khi xử lý: {last_error}")
			screenshot = runner.save_screenshot(record["id"])
			if screenshot:
				self._log(f"Đã lưu ảnh chụp màn hình lỗi: {screenshot}")
			return "FAILED", last_error or "Lỗi không xác định"

	def _resolve_photos(self, record_id: str) -> tuple[str | None, str | None]:
		base = Path(self.photo_folder)
		
		# Hỗ trợ tìm kiếm theo nhiều đuôi file khác nhau
		extensions = ['.jpg', '.png', '.jpeg']
		
		passport_path = None
		portrait_path = None
		
		for ext in extensions:
			# Tìm file giấy tờ (1a, 2a...)
			p1 = base / f"{record_id}a{ext}"
			p2 = base / f"{record_id}A{ext}"
			if p1.exists(): passport_path = str(p1)
			elif p2.exists(): passport_path = str(p2)
			
			# Tìm file chân dung (1b, 2b...)
			p3 = base / f"{record_id}b{ext}"
			p4 = base / f"{record_id}B{ext}"
			if p3.exists(): portrait_path = str(p3)
			elif p4.exists(): portrait_path = str(p4)
			
		return passport_path, portrait_path

	def _log(self, message: str) -> None:
		timestamp = datetime.now().strftime("%H:%M:%S")
		line = f"[{timestamp}] {message}"
		self._emit({"type": "log", "message": line})
		try:
			with open(self.log_path, "a", encoding="utf-8") as handle:
				handle.write(line + "\n")
		except OSError:
			pass
