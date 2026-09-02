@echo off
echo === BUILD EXE WITH PYINSTALLER ===

REM dùng đúng python trong venv
venv\Scripts\python.exe --version

REM xóa build cũ
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM build exe
venv\Scripts\python.exe -m PyInstaller ^
 --onefile ^
 --noconsole ^
 telegram_improved.py

if errorlevel 1 (
  echo === BUILD FAILED ===
  pause
  exit /b 1
)

echo.
echo === BUILD DONE ===
pause
