from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from worker import Worker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KYC AUTOMATION TOOL (MVP)")
        self.setMinimumWidth(720)

        self.worker: Worker | None = None
        self._last_result_path: str | None = None
        self._last_log_path: str | None = None

        container = QWidget(self)
        self.setCentralWidget(container)

        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        self._apply_styles()

        title = QLabel("KYC AUTOMATION TOOL (MVP)")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root_layout.addWidget(title)

        self.excel_path = QLineEdit()
        self.excel_path.setPlaceholderText("Chon file Excel input.xlsx")
        self.photo_folder = QLineEdit()
        self.photo_folder.setPlaceholderText("Chon folder photos/")

        self.btn_excel = QPushButton("Select Excel")
        self.btn_folder = QPushButton("Select Photo Folder")
        self.start_btn = QPushButton("START")
        self.start_btn.setProperty("primary", True)

        self.btn_excel.clicked.connect(self._pick_excel)
        self.btn_folder.clicked.connect(self._pick_folder)
        self.start_btn.clicked.connect(self._start)

        form_group = QGroupBox("Input")
        form_layout = QGridLayout(form_group)
        form_layout.addWidget(QLabel("Excel"), 0, 0)
        form_layout.addWidget(self.excel_path, 0, 1)
        form_layout.addWidget(self.btn_excel, 0, 2)
        form_layout.addWidget(QLabel("Photo folder"), 1, 0)
        form_layout.addWidget(self.photo_folder, 1, 1)
        form_layout.addWidget(self.btn_folder, 1, 2)
        root_layout.addWidget(form_group)

        root_layout.addWidget(self.start_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root_layout.addWidget(self.progress)

        counters_group = QGroupBox("Counters")
        counters_layout = QGridLayout(counters_group)
        self.success_label = QLabel("Success: 0")
        self.failed_label = QLabel("Failed: 0")
        self.duplicate_label = QLabel("Duplicate: 0")
        counters_layout.addWidget(self.success_label, 0, 0)
        counters_layout.addWidget(self.failed_label, 0, 1)
        counters_layout.addWidget(self.duplicate_label, 0, 2)
        root_layout.addWidget(counters_group)

        actions_group = QGroupBox("Actions")
        actions_layout = QGridLayout(actions_group)
        self.view_result_btn = QPushButton("View Result")
        self.view_log_btn = QPushButton("View Log")
        self.view_result_btn.setEnabled(False)
        self.view_log_btn.setEnabled(False)
        self.view_result_btn.clicked.connect(self._open_result)
        self.view_log_btn.clicked.connect(self._open_log)
        actions_layout.addWidget(self.view_result_btn, 0, 0)
        actions_layout.addWidget(self.view_log_btn, 0, 1)
        root_layout.addWidget(actions_group)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("LOG:\nProcessing...")
        root_layout.addWidget(self.log)

    def _pick_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel", "", "Excel Files (*.xlsx)"
        )
        if path:
            self.excel_path.setText(path)

    def _pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Photo Folder")
        if path:
            self.photo_folder.setText(path)

    def _start(self) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Running", "Worker is already running.")
            return

        excel_path = self.excel_path.text().strip()
        photo_folder = self.photo_folder.text().strip()
        if not excel_path or not photo_folder:
            QMessageBox.warning(self, "Missing input", "Please select Excel and photo folder.")
            return

        self._reset_ui()
        self.worker = Worker(excel_path=excel_path, photo_folder=photo_folder)
        self._last_result_path = self.worker.result_path
        self._last_log_path = self.worker.log_path
        self.worker.log_message.connect(self._append_log)
        self.worker.progress_updated.connect(self._update_progress)
        self.worker.counters_updated.connect(self._update_counters)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _reset_ui(self) -> None:
        self.log.clear()
        self.progress.setValue(0)
        self.success_label.setText("Success: 0")
        self.failed_label.setText("Failed: 0")
        self.duplicate_label.setText("Duplicate: 0")
        self.view_result_btn.setEnabled(False)
        self.view_log_btn.setEnabled(False)

    def _append_log(self, message: str) -> None:
        self.log.append(message)

    def _update_progress(self, value: int) -> None:
        self.progress.setValue(value)

    def _update_counters(self, success: int, failed: int, duplicate: int) -> None:
        self.success_label.setText(f"Success: {success}")
        self.failed_label.setText(f"Failed: {failed}")
        self.duplicate_label.setText(f"Duplicate: {duplicate}")

    def _on_finished(self) -> None:
        self.view_result_btn.setEnabled(True)
        self.view_log_btn.setEnabled(True)
        QMessageBox.information(self, "Done", "Processing finished.")

    def _open_result(self) -> None:
        if not self._last_result_path:
            QMessageBox.warning(self, "Missing file", "Result file not found yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_result_path))

    def _open_log(self) -> None:
        if not self._last_log_path:
            QMessageBox.warning(self, "Missing file", "Log file not found yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_log_path))

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            "QWidget { background: #f7f9fb; color: #1f2937; }"
            "QGroupBox { border: 1px solid #d7dee7; border-radius: 10px; margin-top: 12px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }"
            "QLineEdit { padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 6px; background: #ffffff; }"
            "QTextEdit { border: 1px solid #cbd5e1; border-radius: 8px; background: #ffffff; }"
            "QPushButton { padding: 8px 14px; border-radius: 8px; border: 1px solid #cbd5e1; background: #ffffff; }"
            "QPushButton:hover { border-color: #94a3b8; }"
            "QPushButton[primary='true'] { background: #2563eb; color: #ffffff; border-color: #2563eb; font-weight: 600; }"
            "QPushButton[primary='true']:hover { background: #1d4ed8; }"
            "QProgressBar { border: 1px solid #cbd5e1; border-radius: 8px; text-align: center; background: #ffffff; }"
            "QProgressBar::chunk { background: #22c55e; border-radius: 8px; }"
        )