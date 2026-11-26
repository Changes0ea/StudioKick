@echo off
REM KickStudio Windows .exe derleme
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name ChangesStudio --add-data "assets;assets" --icon assets/icon.ico main.py
echo.
echo Hazir: dist\ChangesStudio\ChangesStudio.exe
pause
