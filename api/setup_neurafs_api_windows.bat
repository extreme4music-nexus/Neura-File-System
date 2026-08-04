@echo off
echo ===================================================
echo  Starting HyperCompress Python FastAPI Engine...
echo ===================================================

if not exist "venv\Scripts\activate.bat" goto NO_VENV

call venv\Scripts\activate.bat
python server.py
goto END

:NO_VENV
echo [ERROR] Virtual environment (venv) not found!
echo Please run setup_weurafs_api_windows.bat first to set up the environment.
pause
exit /b 1

:END
pause