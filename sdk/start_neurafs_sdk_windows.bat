@echo off
echo ===================================================
echo  Starting HyperCompress Node.js Web Manager...
echo ===================================================

:: Check if node_modules directory exists
if not exist "node_modules" (
    echo [ERROR] node_modules not found!
    echo Please run setup_node_windows.bat first to install dependencies.
    pause
    exit /b 1
)

:: Launch Node.js Server
node app.js

pause