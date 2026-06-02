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
python -m PyInstaller --noconsole --onefile --name "Tool_KYC" --add-data "templates;templates" --collect-data opencv-python main.py

echo.
echo 4. Khoi phuc ma nguon goc va don dep...
del auth.pyd
ren auth_backup.py auth.py
rmdir /s /q build
del auth.c

echo.
echo ========================================================
echo HOAN THANH! 
echo File chay cho khach hang: "dist\Tool_KYC.exe"
echo ========================================================
pause
