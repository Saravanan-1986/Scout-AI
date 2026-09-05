@echo off
title ScoutAI - Agentic Internship ^& Hackathon Discovery
cd /d "%~dp0"
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
    echo [Setup] First run detected - creating Python environment...
    where uv >nul 2>nul
    if errorlevel 1 (
        echo [Setup] uv not found. Please install Python 3.10+ from python.org, then run:
        echo            pip install -r requirements.txt
        echo            python cli.py
        pause
        exit /b 1
    )
    uv venv .venv --python 3.12
    uv pip install -r requirements.txt
)

.venv\Scripts\python.exe cli.py
pause
