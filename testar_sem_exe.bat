@echo off
cd /d "%~dp0"
rem Roda direto pelo Python, mostrando erros na tela (use depois do build.bat)
call .venv\Scripts\activate.bat
python app\main.py
pause
