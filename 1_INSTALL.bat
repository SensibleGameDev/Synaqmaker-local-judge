@echo off
chcp 65001
title Установка Synaqmaker Local Judge

echo ==========================================
echo   УСТАНОВКА СИСТЕМЫ SYNAQMAKER LOCAL JUDGE
echo ==========================================
echo.

REM 1. Проверка Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден!
    echo Пожалуйста, установите Python 3.9+ и поставьте галочку "Add to PATH".
    echo Скачать: https://www.python.org/downloads/
    pause
    exit
)

REM 2. Проверка Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Docker Desktop не запущен или не установлен!
    echo Пожалуйста, установите Docker Desktop и запустите его.
    echo Скачать: https://www.docker.com/products/docker-desktop/
    pause
    exit
)

echo [1/3] Установка библиотек Python...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Ошибка установки библиотек!
    pause
    exit
)

echo.
echo [2/3] Сборка образа для Python (это может занять время)...
docker build -f Dockerfile.python -t testirovschik-python .

echo.
echo [3/3] Сборка образа для C++...
docker build -f Dockerfile.cpp -t testirovschik-cpp .

echo.
echo ==========================================
echo   УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!
echo ==========================================
echo Теперь вы можете запускать файл 2_START.bat
pause