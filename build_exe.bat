@echo off
echo ========================================================
echo   DANG DONG GOI PHAN MEM KYC AUTOMATION TOOL THANH .EXE
echo ========================================================
echo.
echo 1. Cai dat PyInstaller va Cython...
pip install pyinstaller cython

echo.
echo 2. Bien dich file ban quyen (auth.py) sang ma may (Cython)...
python setup.py build_ext --inplace
ren auth.py auth_backup.py
for %%f in (auth.*.pyd) do ren "%%f" auth.pyd

echo.
echo 3. Dang bien dich source code...
echo Vui long cho trong it phut (Co the mat 2-5 phut tuy cau hinh may)

if exist auth.pyd (
    echo [OK] Bien dich Cython thanh cong! Tien hanh dong goi bao mat...
    python -m PyInstaller --noconsole --onefile --name "Tool_KYC" --distpath "Tool" --hidden-import auth --add-data "templates;templates" --collect-data opencv-python main.py
) else (
    echo [CANH BAO] May tinh cua ban chua cai Microsoft C++ Build Tools nen khong the bien dich Cython!
    echo [CANH BAO] Tien trinh se tu dong dong goi bang phuong phap tieu chuan - Khong dung Cython...
    ren auth_backup.py auth.py
    python -m PyInstaller --noconsole --onefile --name "Tool_KYC" --distpath "Tool" --hidden-import auth --add-data "templates;templates" --collect-data opencv-python main.py
)

echo.
echo 4. Khoi phuc ma nguon goc va don dep...
if exist auth.pyd del auth.pyd
if exist auth_backup.py ren auth_backup.py auth.py
if exist build rmdir /s /q build
if exist auth.c del auth.c

echo.
echo ========================================================
echo HOAN THANH! 
echo File chay cho khach hang: "Tool\Tool_KYC.exe"
echo ========================================================
pause
