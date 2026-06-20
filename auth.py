import uuid
import hashlib
import os
import winreg
import time

# MÃ BÍ MẬT: Chuỗi này chỉ bạn biết. Dùng để trộn với Mã máy (HWID) tạo ra Key.
# TUYỆT ĐỐI KHÔNG TIẾT LỘ CHUỖI NÀY CHO KHÁCH HÀNG.
SECRET_SALT = "VNPT_DIGISHOP_TOOL_EKYC_2026_@PHAT_SECRET"
KEY_FILE = "license.key"

# GIẤU BỘ ĐẾM VÀO SÂU TRONG REGISTRY CỦA WINDOWS (Đặt tên giả để che mắt)
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\SystemMetrics"
REG_KEY_USAGE = "CacheDataMetrics"
REG_KEY_AUTH = "CacheAuthID"

# Lưu sâu vào ổ C:\Users\Tên_Máy\AppData\Roaming (Dùng để backup/migrate)
appdata_path = os.getenv('APPDATA') or os.path.expanduser("~")
USAGE_FILE = os.path.join(appdata_path, "Microsoft_SysVol_Config.bin")

def get_hwid() -> str:
    """Lấy địa chỉ MAC của máy tính làm Hardware ID, băm ra 16 ký tự."""
    mac = uuid.getnode()
    return hashlib.md5(str(mac).encode('utf-8')).hexdigest().upper()[:16]

def validate_key(key: str) -> bool:
    """Xác thực tính hợp lệ của Key mà không lưu"""
    if "-" not in key:
        return False
    parts = key.split("-")
    hwid = get_hwid()
    if len(parts) == 2:
        limit_str, hash_part = parts
        raw_str = f"{hwid}_{limit_str}_{SECRET_SALT}"
    elif len(parts) == 3:
        limit_str, nonce, hash_part = parts
        raw_str = f"{hwid}_{limit_str}_{nonce}_{SECRET_SALT}"
    else:
        return False
        
    if not limit_str.isdigit():
        return False
        
    expected_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest().upper()[:20]
    return hash_part == expected_hash

def get_license_info():
    """Kiểm tra Key và trả về (Trạng thái hợp lệ: bool, Số lượt dùng tối đa: int)"""
    if not os.path.exists(KEY_FILE):
        return False, 0
        
    with open(KEY_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        
    total_limit = 0
    valid_count = 0
    for key in content.splitlines():
        key = key.strip()
        if not key: continue
        if validate_key(key):
            valid_count += 1
            limit_str = key.split("-")[0]
            total_limit += int(limit_str)
            
    if valid_count > 0:
        return True, total_limit
    return False, 0

def topup_license(key: str) -> str:
    key = key.strip()
    if not validate_key(key):
        return "INVALID"
        
    key_hash = hashlib.sha256(key.encode('utf-8')).hexdigest()
    
    try:
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        history, _ = winreg.QueryValueEx(reg_key, REG_KEY_AUTH)
        winreg.CloseKey(reg_key)
    except FileNotFoundError:
        history = ""
        
    history_list = history.split(",") if history else []
    
    if key_hash in history_list:
        return "USED"
        
    history_list.append(key_hash)
    new_history = ",".join(history_list)
    
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE)
    winreg.SetValueEx(reg_key, REG_KEY_AUTH, 0, winreg.REG_SZ, new_history)
    winreg.CloseKey(reg_key)
    
    with open(KEY_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + key)
        
    return "SUCCESS"

def get_usage() -> int:
    """Đọc số lượt khách hàng đã sử dụng từ sâu trong Windows Registry."""
    
    # 1. Chuyển đổi dữ liệu cũ (nếu có) vào Registry
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                data = f.read().strip()
            if "_" in data:
                used_str, hash_part = data.split("_", 1)
                expected_hash = hashlib.md5(f"{used_str}_USAGE_{SECRET_SALT}".encode()).hexdigest()
                if hash_part == expected_hash and used_str.isdigit():
                    # Ghi vào Registry
                    winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
                    reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE)
                    winreg.SetValueEx(reg_key, REG_KEY_USAGE, 0, winreg.REG_SZ, data)
                    winreg.CloseKey(reg_key)
            os.remove(USAGE_FILE)
        except Exception:
            pass

    # 2. Đọc từ Registry
    try:
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        data, _ = winreg.QueryValueEx(reg_key, REG_KEY_USAGE)
        winreg.CloseKey(reg_key)
        
        if "_" not in data:
            return 999999
            
        used_str, hash_part = data.split("_", 1)
        expected_hash = hashlib.md5(f"{used_str}_USAGE_{SECRET_SALT}".encode()).hexdigest()
        
        if hash_part == expected_hash and used_str.isdigit():
            return int(used_str)
        return 999999 # Bị can thiệp bậy bạ
        
    except FileNotFoundError:
        # CHỐNG XÓA BỘ ĐẾM: Nếu có file KEY mà không có Registry -> Khách cố tình xóa Registry
        if os.path.exists(KEY_FILE):
            return 999999
        return 0 # Máy mới chưa xài
    except Exception:
        return 999999

def add_usage(amount=1):
    """Cộng thêm 1 lượt dùng mỗi khi chạy xong 1 hồ sơ vào Registry."""
    current = get_usage()
    if current >= 999999:
        return
        
    new_used = current + amount
    expected_hash = hashlib.md5(f"{new_used}_USAGE_{SECRET_SALT}".encode()).hexdigest()
    data = f"{new_used}_{expected_hash}"
    
    try:
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE)
        winreg.SetValueEx(reg_key, REG_KEY_USAGE, 0, winreg.REG_SZ, data)
        winreg.CloseKey(reg_key)
    except Exception as e:
        print("Lỗi hệ thống: Không thể ghi nhận lượt dùng!")

def save_license(key: str) -> str:
    """Lưu key và kiểm tra chống gian lận nhập lại Key cũ. Trả về 'RESTORE', 'NEW' hoặc 'INVALID'"""
    key = key.strip()
    
    if not validate_key(key):
        return "INVALID"
        
    # Băm cái Key khách vừa nhập để lát so sánh
    key_hash = hashlib.sha256(key.encode('utf-8')).hexdigest()
    
    # 1. ĐỌC LỊCH SỬ KEY TỪ REGISTRY (Bất tử dù khách có xóa App)
    try:
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        history, _ = winreg.QueryValueEx(reg_key, REG_KEY_AUTH)
        winreg.CloseKey(reg_key)
    except FileNotFoundError:
        history = ""
        
    history_list = history.split(",") if history else []
    
    # 2. Tạo lại file license.key để tool hoạt động bình thường
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key)
        
    # 3. QUYẾT ĐỊNH XEM CÓ RESET BỘ ĐẾM HAY KHÔNG?
    if key_hash in history_list:
        # Nếu trùng Key cũ -> KHÔNG RESET BỘ ĐẾM
        return "RESTORE" 
    else:
        # Nếu là Key mới mua -> RESET BỘ ĐẾM VỀ 0 VÀ LƯU KEY MỚI VÀO REGISTRY
        history_list.append(key_hash)
        new_history = ",".join(history_list)
        
        expected_hash = hashlib.md5(f"0_USAGE_{SECRET_SALT}".encode()).hexdigest()
        data = f"0_{expected_hash}"
        
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE)
        winreg.SetValueEx(reg_key, REG_KEY_USAGE, 0, winreg.REG_SZ, data)
        winreg.SetValueEx(reg_key, REG_KEY_AUTH, 0, winreg.REG_SZ, new_history) # Lưu lịch sử Key
        winreg.CloseKey(reg_key)
        
        return "NEW"

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
