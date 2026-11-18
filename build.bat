@echo off
chcp 65001 >nul
title Gerando o Tradutor Runeteria
cd /d "%~dp0"

echo === 1/5 Procurando o Python ===
where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python nao encontrado. Instale o Python 3.12 em https://www.python.org/downloads/
  echo Na instalacao marque "Add python.exe to PATH". Depois rode este arquivo de novo.
  pause
  exit /b 1
)

if not exist .venv (
  py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv
)
call .venv\Scripts\activate.bat

echo === 2/5 Instalando bibliotecas ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo Falha ao instalar as bibliotecas. Veja a mensagem acima.
  pause
  exit /b 1
)

echo === 3/5 Baixando o modelo de traducao offline (uma vez so, ~100 MB) ===
python baixar_modelo.py
if not exist app\fonts\Lexend.ttf python tools\baixar_fontes.py

echo === 4/5 Gerando o programa ===
set ADDMODEL=
if exist modelos\en_pt set ADDMODEL=--add-data "modelos;modelos"
pyinstaller --noconfirm --clean --onedir --windowed --name TradutorRuneteria ^
  --icon app\icone.ico ^
  --paths app --add-data "app\data;data" --add-data "app\fonts;fonts" --add-data "app\assets;assets" --add-data "app\icone.ico;." %ADDMODEL% ^
  --collect-all winrt --collect-all ctranslate2 --collect-all sentencepiece ^
  --hidden-import rapidfuzz --collect-submodules rapidfuzz ^
  app\main.py
if errorlevel 1 (
  echo Falha ao gerar o programa. Veja a mensagem acima.
  pause
  exit /b 1
)
copy /y LEIAME.txt dist\TradutorRuneteria\ >nul

echo === 5/5 Gerando o instalador ===
set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if "%ISCC%"=="" goto sem_inno

for /f %%v in ('python -c "import sys; sys.path.insert(0, 'app'); import config; print(config.APP_VERSION)"') do set APPVER=%%v
"%ISCC%" /Q /DAppVersion=%APPVER% instalador.iss
if errorlevel 1 (
  echo Falha ao gerar o instalador. Veja a mensagem acima.
  pause
  exit /b 1
)
echo.
echo PRONTO! Envie este arquivo para os jogadores:
echo   %~dp0dist\TradutorRuneteria-Instalar.exe
goto fim

:sem_inno
echo Inno Setup nao encontrado: o instalador nao foi gerado.
echo Para gerar, instale com:  winget install JRSoftware.InnoSetup   e rode este arquivo de novo.
echo O programa sem instalador esta em dist\TradutorRuneteria\TradutorRuneteria.exe

:fim
explorer "%~dp0dist"
pause
