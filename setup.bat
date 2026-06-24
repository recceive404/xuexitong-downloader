@echo off
chcp 65001 >nul
title XueXiTong Downloader - Setup

echo.
echo ==============================================
echo   XueXiTong Downloader - Setup
echo ==============================================
echo.

:: Step 1: Check Python
echo [1/4] Checking Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   [FAIL] Python not found. Please install Python 3.10+
    echo          https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   [OK] Python %PYVER%

:: Step 2: Create venv
echo.
echo [2/4] Creating virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo   [OK] Created .venv
) else (
    echo   [SKIP] .venv already exists
)

:: Step 3: Install dependencies
echo.
echo [3/4] Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo   [WARN] Mirror failed, trying default...
    pip install -r requirements.txt
)
echo   [OK] Dependencies installed

:: Step 4: Install Playwright browser
echo.
echo [4/4] Installing Playwright Chromium (~180MB)...
python -m playwright install chromium
echo   [OK] Chromium installed

:: Done
echo.
echo ==============================================
echo   Setup complete!
echo ==============================================
echo.
echo   Usage:
echo     .venv\Scripts\activate
echo     python main.py                  (wizard mode)
echo     python main.py login            (scan QR)
echo     python main.py courses          (list courses)
echo     python main.py download "name"  (download)
echo.
echo   For AI Q&A:
echo     cp .env.example .env
echo     edit .env with your DeepSeek API Key
echo     python main.py build-rag
echo     python main.py ask
echo.
pause
