@echo off
chcp 65001 >nul
title 学习通课件下载器 — 安装

echo.
echo ╔══════════════════════════════════════════════╗
echo ║     学习通课件下载器 — 一键安装              ║
echo ╚══════════════════════════════════════════════╝
echo.

:: 检查 Python
echo [1/4] 检查 Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   ❌ 未找到 Python，请先安装 Python 3.10+
    echo   📥 https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   ✅ Python %PYVER%

:: 创建虚拟环境
echo.
echo [2/4] 创建虚拟环境...
if not exist ".venv" (
    python -m venv .venv
    echo   ✅ 虚拟环境已创建
) else (
    echo   ⏭️  虚拟环境已存在，跳过
)

:: 激活虚拟环境并安装依赖
echo.
echo [3/4] 安装依赖（可能需要几分钟）...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo   ⚠️  镜像源安装失败，尝试默认源...
    pip install -r requirements.txt
)
echo   ✅ 依赖安装完成

:: 安装 Playwright 浏览器
echo.
echo [4/4] 安装 Playwright 浏览器（约 150MB）...
python -m playwright install chromium
echo   ✅ Playwright 浏览器安装完成

:: 配置 .env
echo.
echo ══════════════════════════════════════════════
echo   安装完成！
echo ══════════════════════════════════════════════
echo.
echo   使用方法：
echo     .venv\Scripts\activate
echo     python main.py login            # 扫码登录
echo     python main.py courses          # 查看课程
echo     python main.py download "课程名" # 下载课件
echo.
echo   💡 如需 AI 问答功能：
echo     1. 注册 DeepSeek：https://platform.deepseek.com
echo     2. cp .env.example .env
echo     3. 编辑 .env 填入 API Key
echo.
pause
