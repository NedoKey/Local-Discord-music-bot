@echo off
chcp 65001 >nul
echo ========================================
echo Запуск MusicBot ULTRA (exe)
echo ========================================
echo.

if exist "dist\MusicBot_ULTRA.exe" (
    echo Запуск MusicBot_ULTRA.exe...
    cd dist
    start "" "MusicBot_ULTRA.exe"
    cd ..
    echo.
    echo Бот запущен!
    echo Закройте это окно или нажмите любую клавишу для выхода...
    pause >nul
) else (
    echo Ошибка: Файл dist\MusicBot_ULTRA.exe не найден!
    echo.
    echo Сначала соберите exe-файл командой:
    echo py -3.11 build_exe.py
    echo.
    pause
)
