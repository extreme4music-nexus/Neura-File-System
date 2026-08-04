@echo off
echo ===================================================
echo  HyperCompress Node.js Web Manager Setup
echo  Target OS: Windows Server / Windows 10/11
echo ===================================================

:: 1. Check Node.js installation
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not added to PATH.
    echo Please install Node.js v18+ from https://nodejs.org/
    pause
    exit /b 1
)

:: 2. Create Storage & Application Directory Structure
echo [1/3] Initializing directory hierarchy...
if not exist "storage\compressed\media" mkdir "storage\compressed\media"
if not exist "storage\compressed\documents" mkdir "storage\compressed\documents"
if not exist "public" mkdir "public"
if not exist "temp" mkdir "temp"

:: 3. Initialize Node.js Package if missing
if not exist "package.json" (
    echo [2/3] Initializing Node.js package.json...
    call npm init -y
)

:: 4. Install NPM Dependencies
echo [3/3] Installing Express and Multer dependencies...
call npm install express multer

echo ===================================================
echo  Node.js Environment Setup Completed Successfully!
echo ===================================================
echo  Ensure your public\index.html and app.js files are in place.
echo  To launch the web server, run:
echo    node app.js
echo ===================================================
pause