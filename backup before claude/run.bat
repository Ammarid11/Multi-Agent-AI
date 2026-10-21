@echo off
title Second Brain Multi-Agent AI System
cd /d "%~dp0"

REM Hanya lakukan pengecekan jika belum pernah setup (.setup_done belum ada)
if not exist ".setup_done" (
    echo ============================================================
    echo   [PERTAMA KALI] MENYIAPKAN DEPENDENSI & MODEL OLLAMA...
    echo ============================================================
    python "check_environment.py"
    if errorlevel 1 (
        echo [ERROR] Setup gagal. Silakan periksa kembali koneksi atau Ollama Anda.
        pause
        exit /b 1
    )
)

REM Jika sudah pernah setup, langsung jalankan tanpa delay/pengecekan
python "main.py"
pause