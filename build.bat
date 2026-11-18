@echo off
chcp 65001 >nul
title Gerando o Tradutor Runeteria
cd /d "%~dp0"

echo === 1/4 Procurando o Python ===
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

echo === 2/4 Instalando bibliotecas ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo Falha ao instalar as bibliotecas. Veja a mensagem acima.
  pause
  exit /b 1
)

echo === 3/4 Baixando o modelo de traducao offline (uma vez so, ~100 MB) ===
python baixar_modelo.py

echo === 4/4 Gerando o .exe ===
set ADDMODEL=
if exist modelos\en_pt set ADDMODEL=--add-data "modelos;modelos"
pyinstaller --noconfirm --clean --onedir --windowed --name TradutorRuneteria ^
  --paths app --add-data "app\data;data" %ADDMODEL% ^
  --collect-all winrt --collect-all ctranslate2 --collect-all sentencepiece ^
  --hidden-import rapidfuzz --collect-submodules rapidfuzz ^
  app\main.py
if errorlevel 1 (
  echo Falha ao gerar o .exe. Veja a mensagem acima.
  pause
  exit /b 1
)
copy /y LEIAME.txt dist\TradutorRuneteria\ >nul

echo.
echo PRONTO! O programa esta em: %~dp0dist\TradutorRuneteria\TradutorRuneteria.exe
echo Voce pode criar um atalho dele na area de trabalho.
explorer "%~dp0dist\TradutorRuneteria"
pause
