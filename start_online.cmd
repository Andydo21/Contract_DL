@echo off
chcp 65001 >nul
title Deploy Online - Contract AI System
echo ========================================================
echo   KHOI DONG DEPLOY ONLINE (CLOUDFLARE TUNNEL)
echo ========================================================
echo.

:: 1. Kiem tra va khoi dong Workflow Service (Port 8003) neu chua chay
netstat -ano | findstr /R ":8003.*LISTENING" >nul
if %errorlevel% neq 0 (
    echo [*] Dang khoi dong Workflow Service o cong 8003...
    start /b "" "%~dp0.venv\Scripts\python.exe" "%~dp0workflow_service\manage.py" runserver 0.0.0.0:8003 >nul 2>&1
    timeout /t 2 >nul
    echo [+] Workflow Service da duoc bat thanh cong!
) else (
    echo [+] Workflow Service da dang chay o cong 8003.
)

:: 2. Khoi dong AI Knowledge Worker (xu ly tim kiem hoi dap toan cuc)
echo [*] Dang khoi dong AI Knowledge Worker...
start /b "" "%~dp0.venv\Scripts\python.exe" "%~dp0manage.py" knowledge_worker >nul 2>&1
echo [+] AI Knowledge Worker da san sang!

:: 2. Kiem tra cong 80 (Gateway) hoac cong 8000 (Django Web)
netstat -ano | findstr /R ":8000.*LISTENING" >nul
if %errorlevel% equ 0 (
    echo [+] Phat hien Django Web dang chay o cong 8000!
    set TARGET_PORT=8000
    goto START_TUNNEL
)

netstat -ano | findstr /R ":80.*LISTENING" >nul
if %errorlevel% equ 0 (
    echo [+] Phat hien Nginx Gateway dang chay o cong 80!
    set TARGET_PORT=80
    goto START_TUNNEL
)

echo [*] Dang khoi dong Django Web o cong 8000...
start /b "" "%~dp0.venv\Scripts\python.exe" "%~dp0manage.py" runserver 0.0.0.0:8000 >nul 2>&1
timeout /t 3 >nul
set TARGET_PORT=8000

:START_TUNNEL
echo.
echo ========================================================
echo [*] Dang tao duong link HTTPS Online cho bat cu ai truy cap...
echo [*] Hay copy duong link ket thuc bang ".trycloudflare.com" ben duoi gui cho moi nguoi!
echo ========================================================
echo.
"%~dp0scripts\cloudflared.exe" tunnel --url http://localhost:%TARGET_PORT%
pause
