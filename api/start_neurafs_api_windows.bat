@echo off
echo ===================================================
echo  Starting HyperCompress Python FastAPI Engine...
echo ===================================================

:: Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment (venv) not found!
    echo Please run install_windows.bat first to set up the environment.
    pause
    exit /b 1
)

:: Activate Virtual Environment and Launch Server
call venv\Scripts\activate.bat
python server.py

pause