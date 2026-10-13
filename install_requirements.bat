@echo off
title Installer Dependensi & Model Ollama
cd /d "%~dp0"

echo ============================================================
echo   MENGINSTAL / MEMPERBARUI DEPENDENSI & MODEL OLLAMA...
echo ============================================================
python "check_environment.py"

echo ============================================================
echo   SELESAI.
echo ============================================================
pause
