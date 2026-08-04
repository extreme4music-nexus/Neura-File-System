@echo off
TITLE NeuraFS v12.0.0 Launcher
ECHO ===================================================
ECHO  NeuraFS v12.0.0 — Windows Environment Launcher
ECHO ===================================================

:: 1. Check Python virtual environment
IF NOT EXIST "venv" (
    ECHO [Installer] Creating Python virtual environment...
    python -m venv venv
)

ECHO [Installer] Activating Python environment...
CALL venv\Scripts\activate.bat

ECHO [Installer] Checking Python dependencies...
python -m pip install --upgrade pip -q
pip install fastapi uvicorn torch scipy numpy pydub pydantic python-multipart -q

:: 2. Check Node.js modules
IF NOT EXIST "node_modules" (
    ECHO [Installer] Installing Node.js dependencies...
    CALL npm install express multer
)

:: 3. Launch Engine in separate Command Prompt windows
ECHO ===================================================
ECHO  Starting NeuraFS Engine Services...
ECHO  Python API: http://localhost:8000
ECHO  Web VFS:    http://localhost:3000
ECHO ===================================================

START "NeuraFS Python Engine (Port 8000)" cmd /k "venv\Scripts\activate.bat && python api\server.py"
TIMEOUT /T 3 >nul

START "NeuraFS Web VFS (Port 3000)" cmd /k "node sdk\app.js"
TIMEOUT /T 2 >nul

:: 4. Open Web VFS in default browser
START http://localhost:3000

ECHO.
ECHO NeuraFS is running! Close the command windows to stop services.
PAUSE