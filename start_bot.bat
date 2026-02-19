@echo off
chcp 65001 >nul
echo ========================================
echo Запуск MusicBot ULTRA
echo ========================================
echo.

REM Проверяем наличие exe-файла
if exist "dist\MusicBot_ULTRA.exe" (
    echo Запуск из exe-файла...
    start "" "dist\MusicBot_ULTRA.exe"
    goto :end
)

REM Проверяем наличие Python скрипта
if exist "musicbot_ultra.py" (
    echo Запуск из Python скрипта...
    py -3.11 musicbot_ultra.py
    if errorlevel 1 (
        echo.
        echo Ошибка: Python не найден или скрипт не запустился
        echo Убедитесь, что Python 3.11 установлен
        pause
    )
    goto :end
)

echo Ошибка: Не найден ни exe-файл, ни Python скрипт!
echo.
echo Проверьте:
echo 1. Что вы находитесь в правильной папке
echo 2. Что exe-файл находится в папке dist\
echo 3. Или что файл musicbot_ultra.py существует
echo.
pause

:end
