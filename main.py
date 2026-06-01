import os
import sys
import threading

import uvicorn
import webview

from web_app import app

import tkinter as tk
from tkinter import simpledialog, messagebox
import auth

class Api:
    def pick_excel(self):
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG, 
            allow_multiple=False, 
            file_types=('Excel Files (*.xlsx)', 'All Files (*.*)')
        )
        return result[0] if result else ""

    def pick_folder(self):
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else ""

    def open_path(self, path: str):
        if os.path.exists(path):
            os.startfile(path)

def start_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

def prompt_for_license():
    hwid = auth.get_hwid()
    root = tk.Tk()
    root.withdraw() # Ẩn cửa sổ chính
    
    # Tự động copy HWID vào clipboard
    root.clipboard_clear()
    root.clipboard_append(hwid)
    root.update() # Cần thiết để đẩy vào clipboard trên một số hệ điều hành
    
    msg = f"Mã máy (HWID) của bạn là: {hwid}\n(Mã này ĐÃ ĐƯỢC TỰ ĐỘNG COPY, bạn chỉ cần Paste/Ctrl+V gửi cho Admin!)\n\nNhập Key kích hoạt vào ô bên dưới:"
    key = simpledialog.askstring("Kích hoạt Bản Quyền", msg, parent=root)
    
    if key:
        if key.strip() == auth.generate_valid_key(hwid):
            auth.save_license(key)
            messagebox.showinfo("Thành công", "Kích hoạt bản quyền thành công! Vui lòng mở lại phần mềm.")
            return True
        else:
            messagebox.showerror("Lỗi", "Key kích hoạt không hợp lệ hoặc không dành cho máy này!")
            return False
    return False

if __name__ == '__main__':
    # Kiểm tra bản quyền trước khi chạy ứng dụng
    if not auth.check_license():
        if not prompt_for_license():
            sys.exit(0)
        else:
            sys.exit(0)

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
