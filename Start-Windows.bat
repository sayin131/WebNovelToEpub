@echo off
rem Double-click this file to start Novel to EPUB on Windows.
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3

%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)

if not exist venv\Scripts\python.exe %PY% -m venv venv
if not exist venv\.installed (
  echo Installing requirements ^(first run only^)...
  venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Install failed.
    pause
    exit /b 1
  )
  echo done> venv\.installed
)
start "" venv\Scripts\pythonw.exe novel2epub_gui.py
