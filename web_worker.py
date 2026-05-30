from __future__ import annotations

import os
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from excel_reader import read_input_excel
from playwright_runner import PlaywrightRunner

class WebWorker(threading.Thread):
	def __init__(self, excel_path: str, photo_folder: str, message_queue: queue.Queue[dict[str, Any]]) -> None:
		super().__init__()
		self.excel_path = excel_path
		self.photo_folder = photo_folder
		self.message_queue = message_queue
		self.result_path = os.path.join(os.path.dirname(excel_path), "result.xlsx")
		self.log_path = os.path.join(os.path.dirname(excel_path), "log.txt")
		self.success = 0
		self.failed = 0
		self.duplicate = 0
		self.is_running = True

	def run(self) -> None:
		try:
			self._emit({"type": "status", "message": "Starting process..."})
			records = read_input_excel(self.excel_path)
			total = len(records)
			if total == 0:
				self._log("No records found in Excel.")
				self._emit({"type": "finished"})
				return

			runner = PlaywrightRunner()

			for index, record in enumerate(records, start=1):
				if not self.is_running:
					self._log("Process stopped by user.")
					break

				self._log(f"Processing ID={record['id']} phone={record['phone']} serial={record['serial']}")
				status, message = self._process_record(runner, record)

				if status == "SUCCESS":
					self.success += 1
				elif status == "DUPLICATE":
					self.duplicate += 1
				else:
					self.failed += 1

				record_result = {**record, "status": status, "message": message}
				runner.append_result(self.result_path, record_result)

				self._emit({
					"type": "counters",
					"success": self.success,
					"failed": self.failed,
					"duplicate": self.duplicate
				})
				
				progress = int(index / total * 100)
				self._emit({"type": "progress", "value": progress})

			runner.close()
			self._log("Done.")
			self._emit({"type": "finished", "result_path": self.result_path, "log_path": self.log_path})
		except Exception as exc:
			self._log(f"Fatal error: {exc}")
			self._emit({"type": "finished", "error": str(exc)})
		finally:
			self.is_running = False

	def stop(self):
		self.is_running = False

	def _emit(self, data: dict[str, Any]) -> None:
		self.message_queue.put(data)

	def _process_record(self, runner: PlaywrightRunner, record: dict) -> tuple[str, str]:
		passport, portrait = self._resolve_photos(record["id"])
		if not passport or not portrait:
			missing = "passport" if not passport else "portrait"
			return "FAILED", f"Missing {missing} image"

		attempts = 0
		last_error = ""
		while attempts < 2:
			attempts += 1
			try:
				status, message = runner.run(record, passport, portrait, log=self._log)
				return status, message
			except Exception as exc:
				last_error = str(exc)
				self._log(f"Attempt {attempts} failed: {last_error}")
				if attempts >= 2:
					screenshot = runner.save_screenshot(record["id"])
					if screenshot:
						self._log(f"Saved screenshot: {screenshot}")
					return "FAILED", last_error or "Unexpected error"

		return "FAILED", last_error or "Unknown error"

	def _resolve_photos(self, record_id: str) -> tuple[str | None, str | None]:
		base = Path(self.photo_folder) / str(record_id)
		passport = base / f"{record_id}a.jpg"
		portrait = base / f"{record_id}b.jpg"

		passport_path = str(passport) if passport.exists() else None
		portrait_path = str(portrait) if portrait.exists() else None
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
