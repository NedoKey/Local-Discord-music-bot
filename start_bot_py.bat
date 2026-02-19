@echo off
chcp 65001 >nul
echo ========================================
echo Запуск MusicBot ULTRA (Python)
echo ========================================
echo.

if exist "musicbot_ultra.py" (
    echo Проверка Python 3.11...
    py -3.11 --version >nul 2>&1
    if errorlevel 1 (
        echo Ошибка: Python 3.11 не найден!
        echo.
        echo Установите Python 3.11 или используйте другой способ запуска
        pause
        exit /b 1
    )
    
    echo Python найден, запуск бота...
    echo.
    py -3.11 musicbot_ultra.py
    
    if errorlevel 1 (
        echo.
        echo Ошибка при запуске бота!
        echo Проверьте:
        echo 1. Что все зависимости установлены: py -3.11 -m pip install -r requirements.txt
        echo 2. Что файл token.txt существует с токеном бота
        echo 3. Что config.json настроен правильно
        echo.
        pause
    )
) else (
    echo Ошибка: Файл musicbot_ultra.py не найден!
    echo.
    pause
)
