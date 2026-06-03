@echo off
chcp 65001 >nul
title Electrochemistry Control App - R6244

REM ============================================================
REM  conda 仮想環境名をここに設定してください（### を書き換える）
set VENV_NAME=###
REM ============================================================

echo [INFO] conda 環境 "%VENV_NAME%" を起動します...

call conda activate %VENV_NAME%
if errorlevel 1 (
    echo.
    echo [ERROR] 仮想環境 "%VENV_NAME%" のアクティベートに失敗しました。
    echo         VENV_NAME が正しいか確認してください。
    echo         利用可能な環境一覧: conda env list
    pause
    exit /b 1
)

echo [INFO] アプリを起動します...
python "%~dp0src\main.py" %*

if errorlevel 1 (
    echo.
    echo [ERROR] アプリの実行中にエラーが発生しました。
    pause
)
