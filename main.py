import os
import sys
import threading

import uvicorn
import webview

from web_app import app

class Api:
    def pick_excel(self):
        # Mở hộp thoại chọn file Excel
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG, 
            allow_multiple=False, 
            file_types=('Excel Files (*.xlsx)', 'All Files (*.*)')
        )
        return result[0] if result else ""

    def pick_folder(self):
        # Mở hộp thoại chọn thư mục
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else ""

    def open_path(self, path: str):
        # Mở thư mục hoặc file bằng trình mặc định của OS
        if os.path.exists(path):
            os.startfile(path)

def start_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

if __name__ == '__main__':
    # Khởi chạy FastAPI trong một luồng riêng
    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()

    # Tạo giao diện Desktop bằng pywebview
    api = Api()
    webview.create_window(
        "KYC AUTOMATION TOOL - PRO", 
        "http://127.0.0.1:8000", 
        js_api=api,
        width=1000,
        height=750,
        min_size=(800, 600)
    )
    webview.start()
    
    sys.exit(0)
