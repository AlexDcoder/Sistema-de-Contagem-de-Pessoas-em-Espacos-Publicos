@echo off
setlocal
REM Ativa a venv e roda o orquestrador em um unico comando
if not exist .venv\Scripts\python.exe (
  echo Ambiente .venv nao encontrado. Crie com: python -m venv .venv
  exit /b 1
)
".venv\Scripts\python.exe" run_all.py

