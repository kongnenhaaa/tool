@echo off
echo ========================================================
echo   DANG DONG GOI PHAN MEM KYC AUTOMATION TOOL THANH .EXE
echo ========================================================
echo.
echo 1. Cai dat PyInstaller (Neu chua co)...
pip install pyinstaller

echo.
echo 2. Dang bien dich source code...
echo Vui long cho trong it phut (Co the mat 2-5 phut tuy cau hinh may)
python -m PyInstaller --noconsole --onefile --add-data "templates;templates" --collect-data opencv-python main.py

echo.
echo ========================================================
echo HOAN THANH! 
echo File chay cho khach hang: "dist\main.exe"
echo ========================================================
pause
