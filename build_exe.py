"""
Скрипт для сборки MusicBot ULTRA в исполняемый файл (.exe)
Запустите: py -3.11 build_exe.py
"""

import os
import sys
import subprocess
import shutil

# Настраиваем кодировку для Windows консоли
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def build_exe():
    """Собирает приложение в exe-файл"""
    
    print("=" * 60)
    print("Сборка MusicBot ULTRA в исполняемый файл")
    print("=" * 60)
    
    # Проверяем наличие PyInstaller
    try:
        import PyInstaller
        print("[OK] PyInstaller найден")
    except ImportError:
        print("[ERROR] PyInstaller не установлен!")
        print("Устанавливаю PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("[OK] PyInstaller установлен")
    
    # Очищаем предыдущие сборки
    print("\nОчистка предыдущих сборок...")
    for folder in ["build", "__pycache__"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                print(f"  Удалено: {folder}")
            except PermissionError:
                print(f"  Пропущено: {folder} (занят другим процессом)")
    
    # Пытаемся удалить dist, но не критично, если не получится
    if os.path.exists("dist"):
        try:
            shutil.rmtree("dist")
            print(f"  Удалено: dist")
        except PermissionError:
            print(f"  Пропущено: dist (возможно, запущен exe-файл)")
            print(f"  Продолжаем сборку...")
    
    # Обновляем spec-файл, добавляя иконку, если она есть
    icon_path = None
    if os.path.exists("icons/icon.ico"):
        icon_path = os.path.abspath("icons/icon.ico")
        print(f"[OK] Найдена иконка: {icon_path}")
        # Обновляем spec-файл, если он существует
        if os.path.exists("musicbot_ultra.spec"):
            with open("musicbot_ultra.spec", "r", encoding="utf-8") as f:
                spec_content = f.read()
            if "icon=None" in spec_content or "icon=None," in spec_content:
                spec_content = spec_content.replace(
                    "icon=None,  # Можно указать путь к иконке, если она есть",
                    f"icon=r'{icon_path}',"
                )
                spec_content = spec_content.replace("icon=None,", f"icon=r'{icon_path}',")
                with open("musicbot_ultra.spec", "w", encoding="utf-8") as f:
                    f.write(spec_content)
                print("[OK] Spec-файл обновлен с иконкой")
    
    # Используем spec-файл для более точной настройки
    use_spec = os.path.exists("musicbot_ultra.spec")
    
    # Определяем команду для запуска PyInstaller
    pyinstaller_cmd = [sys.executable, "-m", "PyInstaller"]
    
    if use_spec:
        print("Используется spec-файл")
        cmd = pyinstaller_cmd + ["--clean", "musicbot_ultra.spec"]
    else:
        # Команда сборки без spec-файла
        cmd = pyinstaller_cmd + [
            "--name=MusicBot_ULTRA",
            "--onefile",  # Один exe файл
            "--windowed",  # Без консоли (GUI приложение)
        ]
        
        # Добавляем иконку, если она есть
        if os.path.exists("icons/icon.ico"):
            cmd.append("--icon=icons/icon.ico")
        
        cmd.extend([
            "--add-data=ffmpeg/bin;ffmpeg/bin",  # Включаем FFmpeg
            "--add-data=config.json;.",  # Включаем config.json
            "--hidden-import=discord",
            "--hidden-import=discord.ext.commands",
            "--hidden-import=PyQt6",
            "--hidden-import=PyQt6.QtCore",
            "--hidden-import=PyQt6.QtGui",
            "--hidden-import=PyQt6.QtWidgets",
            "--hidden-import=keyboard",
            "--hidden-import=nacl",
            "--collect-all=discord",
            "--collect-all=PyQt6",
            "musicbot_ultra.py"
        ])
    
    print("\nЗапуск сборки...")
    print(f"Команда: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        subprocess.check_call(cmd)
        print("-" * 60)
        print("\n[OK] Сборка завершена успешно!")
        print(f"\nИсполняемый файл находится в: {os.path.abspath('dist/MusicBot_ULTRA.exe')}")
        print("\nВАЖНО:")
        print("1. Скопируйте папку 'dist' на другой компьютер")
        print("2. В папке 'dist' должен быть файл MusicBot_ULTRA.exe")
        print("3. Создайте файл token.txt с токеном бота в той же папке")
        print("4. Папка 'tracks' создастся автоматически при первом запуске")
        print("5. FFmpeg уже включен в exe-файл")
        
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Ошибка при сборке: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_exe()
