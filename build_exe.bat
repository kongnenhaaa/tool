@echo off
echo ========================================================
echo   DANG DONG GOI PHAN MEM KYC AUTOMATION TOOL THANH .EXE
echo ========================================================
echo.
echo 1. Cai dat PyInstaller va PyArmor...
pip install pyinstaller pyarmor

echo.
echo 2. Ma hoa file ban quyen (auth.py)...
pyarmor gen -O obf_dist auth.py
ren auth.py auth_backup.py
copy obf_dist\auth.py auth.py

echo.
echo 3. Dang bien dich source code...
echo Vui long cho trong it phut (Co the mat 2-5 phut tuy cau hinh may)
python -m PyInstaller --noconsole --onefile --name "Tool_KYC" --add-data "templates;templates" --collect-data opencv-python main.py

echo.
echo 4. Khoi phuc ma nguon goc...
del auth.py
ren auth_backup.py auth.py
rmdir /s /q obf_dist

echo.
echo ========================================================
echo HOAN THANH! 
echo File chay cho khach hang: "dist\Tool_KYC.exe"
echo ========================================================
pause
