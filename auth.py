import uuid
import hashlib
import os

# MÃ BÍ MẬT: Chuỗi này chỉ bạn biết. Dùng để trộn với Mã máy (HWID) tạo ra Key.
# TUYỆT ĐỐI KHÔNG TIẾT LỘ CHUỖI NÀY CHO KHÁCH HÀNG.
SECRET_SALT = "VNPT_DIGISHOP_TOOL_EKYC_2026_@PHAT_SECRET"
KEY_FILE = "license.key"

# File đếm lượt dùng được mã hóa và đặt tên giả để che mắt khách hàng
USAGE_FILE = "system_cache.bin" 

def get_hwid() -> str:
    """Lấy địa chỉ MAC của máy tính làm Hardware ID, băm ra 16 ký tự."""
    mac = uuid.getnode()
    return hashlib.md5(str(mac).encode('utf-8')).hexdigest().upper()[:16]

def get_license_info():
    """Kiểm tra Key và trả về (Trạng thái hợp lệ: bool, Số lượt dùng tối đa: int)"""
    if not os.path.exists(KEY_FILE):
        return False, 0
        
    with open(KEY_FILE, "r", encoding="utf-8") as f:
        key = f.read().strip()
        
    if "-" not in key:
        return False, 0
        
    # Cấu trúc key mới: [SỐ_LƯỢT]-[MÃ_BĂM] (VD: 100-8F4A9B2C...)
    limit_str, hash_part = key.split("-", 1)
    
    if not limit_str.isdigit():
        return False, 0
        
    hwid = get_hwid()
    # Công thức băm: HWID + Số lượt + Salt
    raw_str = f"{hwid}_{limit_str}_{SECRET_SALT}"
    expected_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest().upper()[:20]
    
    if hash_part == expected_hash:
        return True, int(limit_str) # Trả về số lượt được cấp (vd: 100)
        
    return False, 0

def get_usage() -> int:
    """Đọc số lượt khách hàng đã sử dụng."""
    if not os.path.exists(USAGE_FILE):
        return 0 # Chưa dùng lượt nào
        
    with open(USAGE_FILE, "r", encoding="utf-8") as f:
        data = f.read().strip()
        
    if "_" not in data:
        return 999999 # Nếu khách cố tình mở file ra sửa bậy -> Khóa tool luôn
        
    used_str, hash_part = data.split("_", 1)
    
    # Kiểm tra xem khách có sửa số không
    expected_hash = hashlib.md5(f"{used_str}_USAGE_{SECRET_SALT}".encode()).hexdigest()
    if hash_part == expected_hash and used_str.isdigit():
        return int(used_str)
        
    return 999999 # Sai mã băm -> Khóa tool

def add_usage(amount=1):
    """Cộng thêm 1 lượt dùng mỗi khi chạy xong 1 hồ sơ."""
    current = get_usage()
    if current == 999999:
        return
        
    new_used = current + amount
    expected_hash = hashlib.md5(f"{new_used}_USAGE_{SECRET_SALT}".encode()).hexdigest()
    
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        f.write(f"{new_used}_{expected_hash}")

def save_license(key: str) -> None:
    """Lưu key mới và Reset số lượt đã dùng về 0"""
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key.strip())
        
    # Reset file đếm về 0 khi nhập Key mới (để khách nạp thêm lượt)
    expected_hash = hashlib.md5(f"0_USAGE_{SECRET_SALT}".encode()).hexdigest()
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        f.write(f"0_{expected_hash}")

def remove_license() -> None:
    """Xóa file license khi người dùng đăng xuất."""
    if os.path.exists(KEY_FILE):
        try:
            os.remove(KEY_FILE)
        except:
            pass
    if os.path.exists(USAGE_FILE):
        try:
            os.remove(USAGE_FILE)
        except:
            pass
