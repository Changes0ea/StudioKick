@echo off
REM KickStudio Windows .exe derleme
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name KickStudio main.py
echo.
echo Hazir: dist\KickStudio\KickStudio.exe
pause
