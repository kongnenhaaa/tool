=================================================
          KYC AUTOMATION TOOL - PRO
=================================================

1. GIỚI THIỆU
-------------
KYC AUTOMATION TOOL - PRO là phần mềm tự động hóa quá trình xác thực eKYC trên hệ thống VNPT. 
Công cụ sử dụng công nghệ giả lập trình duyệt (Playwright) kết hợp với các thuật toán xử lý ảnh tiên tiến (OpenCV) để vượt qua các lớp bảo mật như Liveness Check và kiểm tra tính hợp lệ của ảnh thẻ.

Các tính năng chính:
- Tự động điền thông tin và thao tác eKYC hàng loạt dựa trên dữ liệu đầu vào.
- Vượt Liveness Check: Giả lập webcam và tiêm (inject) hình ảnh/video trực tiếp vào luồng (stream) của trình duyệt.
- Xử lý ảnh thông minh: Tự động crop ảnh theo tỷ lệ, áp dụng thuật toán Anti-Glare khử bóng chói trên màn hình, và thuật toán CLAHE tăng cường chiều sâu 3D (giúp ảnh nổi khối, vượt qua AI dễ dàng).
- Đánh chặn Network/Payload: Thay thế hoàn hảo các dữ liệu ảnh chụp mờ bằng ảnh chất lượng cao (HD Portrait) trên đường truyền (XHR, Fetch, FormData, atob, sessionStorage, toDataURL).
- Giao diện người dùng trực quan, thân thiện (phát triển bằng FastAPI & PyWebview).

2. YÊU CẦU HỆ THỐNG
-------------------
- Hệ điều hành: Windows 10/11 (hoặc tương đương).
- Python: Phiên bản 3.9 trở lên.
- Trình duyệt: Đã cài đặt các trình duyệt tiêu chuẩn cho Playwright (Chromium).

3. HƯỚNG DẪN CÀI ĐẶT
--------------------
Bước 1: Cài đặt Python 
Đảm bảo bạn đã cài đặt Python và đã thêm Python vào biến môi trường (PATH) của Windows.

Bước 2: Cài đặt các thư viện bắt buộc (Dependencies)
Mở Terminal (Command Prompt hoặc PowerShell) trong thư mục chứa mã nguồn và chạy lệnh sau:
> pip install -r requirements.txt

(Nếu không có file requirements.txt, hãy cài đặt thủ công các thư viện sau:)
> pip install fastapi uvicorn pywebview playwright opencv-python numpy

Bước 3: Cài đặt môi trường Playwright
Cần tải xuống các trình duyệt (Chromium) để Playwright có thể điều khiển:
> playwright install

4. HƯỚNG DẪN SỬ DỤNG
--------------------
Bước 1: Khởi động phần mềm
Click đúp vào file `start.bat` (nếu có) hoặc mở Terminal và chạy lệnh:
> python main.py

Bước 2: Thao tác trên Giao diện (UI)
- Màn hình chính của "KYC AUTOMATION TOOL - PRO" sẽ xuất hiện.
- Click vào nút chọn file Excel chứa dữ liệu khách hàng cần chạy eKYC.
- Chọn thư mục chứa ảnh thẻ/chân dung tương ứng (tên ảnh thường được map với ID trong file Excel).
- Bấm nút "Bắt đầu / Run" để hệ thống tự động chạy.

Bước 3: Quá trình tự động
- Công cụ sẽ mở một trình duyệt ẩn (hoặc hiển thị tùy cấu hình) để thực hiện các bước trên web VNPT eKYC.
- Thuật toán sẽ tự động đọc, cắt ảnh, loại bỏ ánh sáng chói, tăng cường chi tiết, dựng luồng webcam ảo và đánh chặn gói tin để gửi ảnh thẻ chuẩn lên server.
- Bạn có thể xem log hoạt động hoặc kết quả trả về trực tiếp trên giao diện Desktop.

5. CƠ CHẾ HOẠT ĐỘNG CỐT LÕI (DÀNH CHO KỸ THUẬT VIÊN)
-----------------------------------------------------
- Xử lý ảnh (utils.py): Sử dụng `apply_anti_glare` để khử chói màn hình (dựa vào HSV mask) và `cv2.createCLAHE` để tăng độ tương phản cục bộ, đánh lừa hệ thống chống giả mạo Liveness.
- Giả lập Camera (playwright_runner.py): Inject đoạn script Javascript vào trước khi trang web load (`add_init_script`). Hook vào hàm `getUserMedia` để cung cấp `canvas.captureStream()`. 
- Network Hooking: Đánh chặn `HTMLCanvasElement.prototype.toDataURL`, `toBlob`, `window.fetch`, `XMLHttpRequest.send`, `window.atob`, và `Storage.setItem` để bảo vệ và tráo đổi ảnh mờ lấy ảnh HD Portrait sắc nét khi dữ liệu được đóng gói gửi lên API server.

-------------------------------------------------
Chúc bạn sử dụng phần mềm hiệu quả!
Mọi thắc mắc xin vui lòng liên hệ đội ngũ phát triển.
