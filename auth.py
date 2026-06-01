import uuid
import hashlib
import os

# MÃ BÍ MẬT: Chuỗi này chỉ bạn biết. Dùng để trộn với Mã máy (HWID) tạo ra Key.
# TUYỆT ĐỐI KHÔNG TIẾT LỘ CHUỖI NÀY CHO KHÁCH HÀNG.
SECRET_SALT = "VNPT_DIGISHOP_TOOL_EKYC_2026_@PHAT_SECRET"
KEY_FILE = "license.key"

def get_hwid() -> str:
    """Lấy địa chỉ MAC của máy tính làm Hardware ID, băm ra 16 ký tự."""
    mac = uuid.getnode()
    return hashlib.md5(str(mac).encode('utf-8')).hexdigest().upper()[:16]

def generate_valid_key(hwid: str) -> str:
    """Thuật toán sinh Key dựa trên HWID của máy và Mã bí mật."""
    raw_str = f"{hwid}_{SECRET_SALT}"
    # Băm SHA-256 để ra một mã kích hoạt dài và bảo mật
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest().upper()

def check_license() -> bool:
    """Kiểm tra xem máy tính này đã có file license.key hợp lệ chưa."""
    if not os.path.exists(KEY_FILE):
        return False
        
    with open(KEY_FILE, "r", encoding="utf-8") as f:
        saved_key = f.read().strip()
        
    hwid = get_hwid()
    valid_key = generate_valid_key(hwid)
    
    return saved_key == valid_key

def save_license(key: str) -> None:
    """Lưu key khách hàng nhập vào file."""
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key.strip())
