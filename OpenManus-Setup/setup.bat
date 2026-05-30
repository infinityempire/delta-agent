@echo off
REM OpenManus Automated Setup Script (Windows)
REM This script automates the complete setup of OpenManus

setlocal enabledelayedexpansion

echo ==================================
echo   OpenManus Automated Setup
echo ==================================
echo.

REM Check Python version
echo [1/7] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Please install Python 3.12+
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% found

REM Clone OpenManus repository
echo.
echo [2/7] Cloning OpenManus repository...
if not exist "OpenManus" (
    git clone https://github.com/FoundationAgents/OpenManus.git
    echo [OK] Repository cloned
) else (
    echo [OK] Repository already exists
)

cd OpenManus

REM Create Python virtual environment
echo.
echo [3/7] Creating Python virtual environment...
if not exist "venv" (
    python -m venv venv
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

REM Activate virtual environment
echo [4/7] Activating virtual environment...
call venv\Scripts\activate.bat
echo [OK] Virtual environment activated

REM Upgrade pip
echo.
echo [5/7] Upgrading pip...
python -m pip install --upgrade pip
echo [OK] pip upgraded

REM Install dependencies
echo.
echo [6/7] Installing dependencies (this may take several minutes)...
pip install -r requirements.txt
echo [OK] Dependencies installed

REM Install Playwright browsers
echo.
echo [7/7] Installing Playwright browsers...
playwright install
echo [OK] Playwright browsers installed

REM Create config directory and copy example config
echo.
echo Configuring OpenManus...
if not exist "config\config.toml" (
    if exist "config\config.example.toml" (
        copy config\config.example.toml config\config.toml
        echo [WARNING] config.toml created from example
        echo [WARNING] Please edit config\config.toml and add your API keys
    )
)

echo.
echo ==================================
echo [OK] OpenManus Setup Complete!
echo ==================================
echo.
echo Next steps:
echo 1. Edit config\config.toml and add your LLM API keys
echo 2. Activate the virtual environment: venv\Scripts\activate.bat
echo 3. Run OpenManus: python main.py
echo.
echo For more information, see README.md
echo.
pause
