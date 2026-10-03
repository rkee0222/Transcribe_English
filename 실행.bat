@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto dependencies
set "TRANSCRIBE_PY=py -3.13"
py -3.13 -c "import sys, tkinter; assert sys.maxsize > 2**32" >nul 2>&1
if not errorlevel 1 goto create_env
set "TRANSCRIBE_PY=py -3.12"
py -3.12 -c "import sys, tkinter; assert sys.maxsize > 2**32" >nul 2>&1
if not errorlevel 1 goto create_env
set "TRANSCRIBE_PY=python"
python -c "import sys, tkinter; assert sys.version_info[:2] in [(3,12),(3,13)] and sys.maxsize > 2**32" >nul 2>&1
if errorlevel 1 goto missing_python
:create_env
echo Creating Python environment...
%TRANSCRIBE_PY% -m venv .venv
if errorlevel 1 goto failed
:dependencies
if exist ".venv\installed-notion-gpu-v1.ok" goto launch
echo Installing packages. First launch may take several minutes...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
echo installed>".venv\installed-notion-gpu-v1.ok"
:launch
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto failed
exit /b 0
:missing_python
echo Please install Python 3.12 or 3.13, Windows installer 64-bit, from python.org.
echo Keep the Python launcher and Tcl/Tk options enabled during installation.
echo Then run this file again. See README.md for Korean instructions.
pause
exit /b 1
:failed
echo Setup or execution failed. See the error above.
pause
exit /b 1
