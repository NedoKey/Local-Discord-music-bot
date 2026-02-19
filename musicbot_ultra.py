import sys
import os
import json
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import threading
import shutil

import discord

from discord.ext import commands

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel,
    QSlider, QFileDialog, QSystemTrayIcon,
    QMenu, QLineEdit, QInputDialog, QMessageBox
)

from PyQt6.QtGui import QIcon, QAction, QPixmap, QPalette, QPainter

from PyQt6.QtCore import Qt, QTimer

import keyboard


# ========================
# LOAD CONFIG
# ========================

# Определяем базовую директорию: при запуске из exe используем папку exe, иначе папку скрипта
if getattr(sys, 'frozen', False):
    # Запущено из exe (PyInstaller)
    BASE_DIR = os.path.dirname(sys.executable)
    # Ресурсы из exe находятся во временной папке
    MEIPASS = getattr(sys, '_MEIPASS', BASE_DIR)
else:
    # Запущено как скрипт Python
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    MEIPASS = BASE_DIR

def _abs(*parts: str) -> str:
    """Путь относительно базовой директории (где exe или скрипт)"""
    return os.path.join(BASE_DIR, *parts)

def _resource(*parts: str) -> str:
    """Путь к ресурсам: из временной папки при exe, иначе из BASE_DIR"""
    return os.path.join(MEIPASS, *parts)

# Файлы конфигурации и данные пользователя - рядом с exe/скриптом
CONFIG_PATH = _abs("config.json")
TOKEN_PATH = _abs("token.txt")
# Старая папка tracks для обратной совместимости (будет использоваться, если нет других папок)
LEGACY_TRACKS = _abs("tracks")

# FFmpeg - из ресурсов (в exe) или из папки проекта
if getattr(sys, 'frozen', False):
    FFMPEG = _resource("ffmpeg", "bin", "ffmpeg.exe")
else:
    FFMPEG = _abs("ffmpeg", "bin", "ffmpeg.exe")

# Загружаем конфиг или создаем по умолчанию
if os.path.exists(CONFIG_PATH):
    CONFIG = json.load(open(CONFIG_PATH, encoding="utf-8"))
    # Миграция старого формата конфига
    if "voice_channel_id" in CONFIG and "channels" not in CONFIG:
        # Старый формат - преобразуем в новый
        old_id = CONFIG.get("voice_channel_id", 0)
        if old_id and old_id != 0:
            CONFIG["channels"] = [{"id": int(old_id), "name": "Основной канал"}]
        else:
            CONFIG["channels"] = []
        # Удаляем старое поле
        if "voice_channel_id" in CONFIG:
            del CONFIG["voice_channel_id"]
        json.dump(CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2)
    # Убеждаемся, что есть список каналов
    if "channels" not in CONFIG:
        CONFIG["channels"] = []
    # Убеждаемся, что есть поле для фонового изображения
    if "background_image" not in CONFIG:
        CONFIG["background_image"] = ""
    # Миграция старого формата - если была папка tracks, добавляем её в список
    if "music_folders" not in CONFIG:
        # Старый формат - создаем список папок
        if os.path.exists(LEGACY_TRACKS):
            CONFIG["music_folders"] = [LEGACY_TRACKS]
        else:
            CONFIG["music_folders"] = []
        json.dump(CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2)
    # Убеждаемся, что есть список папок
    if "music_folders" not in CONFIG:
        CONFIG["music_folders"] = []
else:
    # Конфиг по умолчанию
    CONFIG = {"channels": [], "volume": 67, "background_image": "", "music_folders": []}
    json.dump(CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2)

# Текущий выбранный ID канала (по умолчанию первый из списка или 0)
VOICE_CHANNEL_ID = CONFIG["channels"][0]["id"] if CONFIG["channels"] else 0

# Загружаем токен
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN and os.path.exists(TOKEN_PATH):
    TOKEN = open(TOKEN_PATH, encoding="utf-8").read().strip()
if not TOKEN:
    print("ВНИМАНИЕ: Токен не найден! Создайте файл token.txt с токеном бота.")

# Создаем старую папку tracks для обратной совместимости, если её нет
os.makedirs(LEGACY_TRACKS, exist_ok=True)


# ========================
# DISCORD BOT
# ========================

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True  # Нужно для получения списка серверов и каналов
intents.members = True  # Может понадобиться для некоторых операций

bot = commands.Bot(command_prefix="!", intents=intents)

voice = None

queue = []

current = None

volume = CONFIG["volume"] / 100

# Режим бесконечного повтора текущего трека
repeat_enabled = False


@bot.event
async def on_ready():
    print(f"[INFO] Бот готов! Подключен как {bot.user}")
    print(f"[INFO] ID бота: {bot.user.id}")
    print(f"[INFO] Количество серверов: {len(bot.guilds)}")
    print(f"[INFO] ID канала из конфига: {VOICE_CHANNEL_ID}")
    
    # Выводим список серверов для диагностики
    for guild in bot.guilds:
        print(f"[INFO] Сервер: {guild.name} (ID: {guild.id})")
        voice_channels = [ch for ch in guild.channels if isinstance(ch, (discord.VoiceChannel, discord.StageChannel))]
        print(f"[INFO]   Голосовых каналов: {len(voice_channels)}")
        for vc in voice_channels[:5]:  # Показываем первые 5
            print(f"[INFO]     - {vc.name} (ID: {vc.id})")
    
    # Не подключаемся автоматически - ждем команды из GUI


async def connect():

    global voice

    if voice and voice.is_connected():
        print("[INFO] Уже подключен к голосовому каналу")
        return

    # Преобразуем ID в int для надежности
    channel_id = int(VOICE_CHANNEL_ID) if VOICE_CHANNEL_ID else None
    
    if not channel_id or channel_id == 0:
        print(f"[ERROR] Voice channel ID не указан или равен 0 в config.json!")
        print(f"[INFO] Укажите правильный ID голосового канала в config.json")
        return

    try:
        print(f"[INFO] Поиск канала с ID: {channel_id}")
        print(f"[INFO] Бот находится на {len(bot.guilds)} серверах")
        
        # Пытаемся получить канал из кеша
        channel = bot.get_channel(channel_id)
        
        if channel is None:
            print(f"[INFO] Канал не найден в кеше, загружаю через API...")
            print(f"[INFO] Проверяю все серверы бота...")
            
            # Пробуем найти канал на всех серверах
            found_channel = None
            for guild in bot.guilds:
                try:
                    ch = guild.get_channel(channel_id)
                    if ch:
                        found_channel = ch
                        print(f"[INFO] Канал найден на сервере: {guild.name}")
                        break
                except:
                    pass
            
            if found_channel:
                channel = found_channel
            else:
                # Пробуем загрузить через API
                try:
                    channel = await bot.fetch_channel(channel_id)
                    print(f"[INFO] Канал загружен через API")
                except discord.errors.NotFound:
                    print(f"[ERROR] Канал с ID {channel_id} не найден!")
                    print(f"[INFO] Проверьте:")
                    print(f"  1. Правильность ID канала")
                    print(f"  2. Что бот находится на том же сервере, что и канал")
                    print(f"  3. Что бот имеет доступ к серверу")
                    print(f"  4. Как получить ID: включите режим разработчика в Discord,")
                    print(f"     правый клик по каналу -> Копировать ID")
                    print(f"[INFO] Доступные серверы бота:")
                    for guild in bot.guilds:
                        print(f"     - {guild.name} (ID: {guild.id})")
                    return
                except discord.errors.Forbidden:
                    print(f"[ERROR] У бота нет доступа к каналу с ID {channel_id}!")
                    print(f"[INFO] Проверьте права бота на сервере")
                    return
                except Exception as e:
                    print(f"[ERROR] Ошибка при загрузке канала: {e}")
                    import traceback
                    traceback.print_exc()
                    return
        
        if channel is None:
            print(f"[ERROR] Не удалось найти канал с ID {channel_id}")
            return
        
        # Проверяем, что это голосовой канал
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            print(f"[ERROR] Канал с ID {channel_id} не является голосовым каналом!")
            print(f"[INFO] Тип канала: {type(channel).__name__}")
            return
        
        print(f"[INFO] Найден канал: {channel.name} (сервер: {channel.guild.name})")
        print(f"[INFO] Подключение к каналу...")
        
        # Отключаемся от предыдущего канала, если подключены
        if voice and voice.is_connected():
            await voice.disconnect()
        
        voice = await channel.connect()
        print(f"[OK] Успешно подключен к голосовому каналу: {channel.name}")
        
        # If this is a Stage channel, bots join suppressed by default (no audio output).
        try:
            me = voice.guild.me
            if me is not None and getattr(me.voice, "suppress", False):
                await me.edit(suppress=False)
                print(f"[OK] Stage канал: звук включен")
        except Exception as e:
            print(f"[WARNING] Не удалось включить звук на Stage канале: {e}")
            print(f"[INFO] Это может быть нормально, если у бота нет прав модератора")
                
    except discord.errors.Forbidden as e:
        print(f"[ERROR] У бота нет прав для подключения к каналу!")
        print(f"[INFO] Проверьте права бота на сервере:")
        print(f"  - Подключаться к голосовым каналам")
        print(f"  - Говорить в голосовых каналах")
        print(f"[DETAILS] {e}")
    except discord.errors.ClientException as e:
        print(f"[ERROR] Ошибка клиента Discord: {e}")
        print(f"[INFO] Возможно, бот уже подключен к другому каналу")
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка при подключении: {e}")
        import traceback
        traceback.print_exc()


async def next_track():

    global current, repeat_enabled

    # Если включен режим повтора и уже есть текущий трек – просто переигрываем его.
    if repeat_enabled and current is not None:
        # Ищем трек по имени во всех папках
        tracks = get_all_tracks()
        found_path = None
        for track in tracks:
            if track["name"] == current:
                found_path = track["path"]
                break
        if found_path:
            path = found_path
        else:
            print(f"[ERROR] Трек '{current}' не найден для повтора")
            current = None
            return
    else:
        if not queue:
            current = None
            return
        
        # current_path может быть полным путем или именем файла
        current_path = queue.pop(0)
        
        # Если это полный путь, используем его
        if os.path.exists(current_path):
            path = current_path
            current = os.path.basename(current_path)
        else:
            # Ищем трек по имени во всех папках
            tracks = get_all_tracks()
            found = None
            for track in tracks:
                if track["name"] == current_path:
                    found = track["path"]
                    break
            
            if found:
                path = found
                current = os.path.basename(found)
            else:
                print(f"[ERROR] Трек '{current_path}' не найден")
                await next_track()
                return

    if not os.path.isfile(path):
        print("[playback] file not found:", path)
        await next_track()
        return
    if not os.path.isfile(FFMPEG):
        print("[playback] ffmpeg not found:", FFMPEG)
        current = None
        return

    try:
        # Приводим звук к 48 kHz стерео PCM, как ожидает Discord.
        # Это помогает избавиться от "битого" / искажённого звука.
        # Упрощенные настройки FFmpeg для стабильной работы
        ffmpeg_source = discord.FFmpegPCMAudio(
            path,
            executable=FFMPEG,
            before_options="-nostdin",
            options="-vn -ac 2 -ar 48000"
        )
        # На всякий случай ограничим громкость до 1.0, чтобы избежать клиппинга.
        safe_volume = max(0.0, min(1.0, volume))
        source = discord.PCMVolumeTransformer(ffmpeg_source, volume=safe_volume)
    except Exception as e:
        print("[playback] failed to create FFmpeg source:", repr(e))
        await next_track()
        return

    voice.play(
        source,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            next_track(), bot.loop
        )
    )
    print("[playback] now playing:", current)


def get_all_tracks():
    """Получает список всех треков из всех папок"""
    tracks = []
    folders = CONFIG.get("music_folders", [])
    
    # Если папок нет, используем старую папку tracks
    if not folders:
        folders = [LEGACY_TRACKS]
    
    for folder in folders:
        if os.path.exists(folder):
            try:
                for f in os.listdir(folder):
                    if f.endswith(".mp3"):
                        full_path = os.path.join(folder, f)
                        tracks.append({
                            "name": f,
                            "path": full_path,
                            "folder": folder
                        })
            except Exception as e:
                print(f"[WARNING] Ошибка при чтении папки {folder}: {e}")
    
    return tracks


async def play(track_path_or_name):
    """Воспроизводит трек по имени или полному пути"""
    global voice
    
    await connect()
    
    # Проверяем, что подключение успешно
    if not voice or not voice.is_connected():
        print("[ERROR] Не удалось подключиться к голосовому каналу")
        return

    # Если передан полный путь, используем его
    if os.path.exists(track_path_or_name):
        queue.append(track_path_or_name)
    else:
        # Ищем трек по имени во всех папках
        tracks = get_all_tracks()
        found = None
        for track in tracks:
            if track["name"] == track_path_or_name:
                found = track["path"]
                break
        
        if found:
            queue.append(found)
        else:
            print(f"[ERROR] Трек '{track_path_or_name}' не найден в папках")
            return

    if not voice.is_playing():
        await next_track()


async def stop():

    queue.clear()

    if voice:
        voice.stop()


async def pause():
    if voice:
        voice.pause()


async def resume():
    if voice:
        voice.resume()


async def disconnect():
    """Отключается от голосового канала"""
    global voice
    
    if voice:
        try:
            await voice.disconnect()
            voice = None
            print("[OK] Отключен от голосового канала")
            return True
        except Exception as e:
            print(f"[ERROR] Ошибка при отключении: {e}")
            return False
    else:
        print("[INFO] Не подключен к каналу")
        return False


async def set_volume(v):

    global volume

    volume = v / 100

    # Обновляем громкость текущего источника в реальном времени, если он есть.
    if voice and voice.source and isinstance(voice.source, discord.PCMVolumeTransformer):
        safe_volume = max(0.0, min(1.0, volume))
        voice.source.volume = safe_volume

    CONFIG["volume"] = v

    json.dump(CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"))


async def set_repeat(enabled: bool):

    global repeat_enabled

    repeat_enabled = bool(enabled)


async def save_channels():
    """Сохраняет список каналов в config.json"""
    json.dump(CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2)
    print(f"[OK] Список каналов сохранен")


async def add_channel(channel_id: int, name: str):
    """Добавляет канал в список"""
    global VOICE_CHANNEL_ID
    
    try:
        channel_id = int(channel_id)
        name = name.strip() or f"Канал {channel_id}"
        
        # Проверяем, нет ли уже такого ID
        for ch in CONFIG["channels"]:
            if ch["id"] == channel_id:
                print(f"[WARNING] Канал с ID {channel_id} уже существует")
                return False
        
        CONFIG["channels"].append({"id": channel_id, "name": name})
        await save_channels()
        print(f"[OK] Канал добавлен: {name} (ID: {channel_id})")
        return True
    except (ValueError, TypeError) as e:
        print(f"[ERROR] Неверный формат ID канала: {e}")
        return False


async def remove_channel(channel_id: int):
    """Удаляет канал из списка"""
    global VOICE_CHANNEL_ID
    
    CONFIG["channels"] = [ch for ch in CONFIG["channels"] if ch["id"] != channel_id]
    await save_channels()
    
    # Если удалили текущий канал, выбираем первый из списка
    if VOICE_CHANNEL_ID == channel_id:
        VOICE_CHANNEL_ID = CONFIG["channels"][0]["id"] if CONFIG["channels"] else 0
    
    print(f"[OK] Канал удален: {channel_id}")
    return True


async def set_current_channel(channel_id: int):
    """Устанавливает текущий канал для подключения"""
    global VOICE_CHANNEL_ID
    
    # Проверяем, что канал есть в списке
    for ch in CONFIG["channels"]:
        if ch["id"] == channel_id:
            VOICE_CHANNEL_ID = channel_id
            print(f"[OK] Выбран канал: {ch['name']} (ID: {channel_id})")
            return True
    
    print(f"[ERROR] Канал с ID {channel_id} не найден в списке")
    return False


bot.play_music = play
bot.stop_music = stop
bot.pause_music = pause
bot.resume_music = resume
bot.set_volume_music = set_volume
bot.set_repeat_music = set_repeat
bot.save_channels = save_channels
bot.add_channel = add_channel
bot.remove_channel = remove_channel
bot.set_current_channel = set_current_channel
bot.connect_to_channel = connect
bot.disconnect_from_channel = disconnect


# Вспомогательная функция для быстрого вызова async функций из GUI
def call_async(coro):
    """Быстрый вызов async функции из GUI потока"""
    try:
        if hasattr(bot, 'loop') and bot.loop and bot.loop.is_running():
            # Используем call_soon_threadsafe для более быстрой реакции
            future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            # Не ждем результат, чтобы не блокировать GUI
            return future
        else:
            print("[WARNING] Bot loop не доступен, попытка выполнить позже...")
            return None
    except Exception as e:
        print(f"[ERROR] Ошибка при вызове async функции: {e}")
        return None


def run_bot():
    # Используем встроенный run, чтобы не создавать свой event loop через asyncio.run
    # Это предотвращает ошибку "Future attached to a different loop"
    bot.run(TOKEN)


threading.Thread(target=run_bot, daemon=True).start()


# ========================
# GUI
# ========================

class ChannelsWindow(QWidget):
    """Окно для управления списком каналов"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_panel = parent
        self.background_pixmap = None
        self.setWindowTitle("Голосовые каналы")
        self.resize(400, 500)
        
        layout = QVBoxLayout()
        
        label = QLabel("Голосовые каналы:")
        layout.addWidget(label)
        
        self.channels_list = QListWidget()
        self.channels_list.itemSelectionChanged.connect(self.on_channel_selected)
        layout.addWidget(self.channels_list)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        add_btn = QPushButton("+ Добавить")
        add_btn.clicked.connect(self.add_channel_dialog)
        buttons_layout.addWidget(add_btn)
        
        remove_btn = QPushButton("- Удалить")
        remove_btn.clicked.connect(self.remove_channel_dialog)
        buttons_layout.addWidget(remove_btn)
        
        connect_btn = QPushButton("Подключиться")
        connect_btn.clicked.connect(self.connect_to_channel)
        buttons_layout.addWidget(connect_btn)
        
        close_btn = QPushButton("✕ Закрыть")
        close_btn.clicked.connect(self.close)
        buttons_layout.addWidget(close_btn)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        self.apply_theme()
        self.load_channels()
    
    def apply_theme(self):
        """Применяет тему и фоновое изображение"""
        bg_image = CONFIG.get("background_image", "")
        
        if bg_image and os.path.exists(bg_image):
            # Загружаем изображение для масштабирования
            self.background_pixmap = QPixmap(bg_image)
            # Применяем стили для виджетов
            self.setStyleSheet("""
            QPushButton {
                background: rgba(51, 51, 51, 200);
                padding: 8px;
                border: 1px solid rgba(255, 255, 255, 100);
                color: white;
            }
            QLabel {
                background: rgba(30, 30, 30, 150);
                color: white;
            }
            QListWidget {
                background: rgba(30, 30, 30, 200);
                color: white;
            }
            """)
            # Обновляем виджет для перерисовки
            self.update()
        else:
            # Стандартная тема без фона
            self.background_pixmap = None
            self.setStyleSheet("""
            QWidget {background:#1e1e1e;color:white}
            QPushButton {background:#333;padding:8px}
            """)
    
    def paintEvent(self, event):
        """Отрисовывает фоновое изображение с масштабированием"""
        if self.background_pixmap and not self.background_pixmap.isNull():
            painter = QPainter(self)
            # Масштабируем изображение под размер окна (cover mode)
            scaled_pixmap = self.background_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            # Вычисляем позицию для центрирования
            x = (scaled_pixmap.width() - self.width()) // 2
            y = (scaled_pixmap.height() - self.height()) // 2
            # Отрисовываем обрезанное изображение
            painter.drawPixmap(0, 0, scaled_pixmap, x, y, self.width(), self.height())
        else:
            # Если нет фона, вызываем стандартную отрисовку
            super().paintEvent(event)
    
    def load_channels(self):
        """Загружает список каналов"""
        self.channels_list.clear()
        for ch in CONFIG["channels"]:
            item_text = f"{ch['name']} (ID: {ch['id']})"
            self.channels_list.addItem(item_text)
        
        global VOICE_CHANNEL_ID
        if VOICE_CHANNEL_ID:
            for i in range(self.channels_list.count()):
                item = self.channels_list.item(i)
                if str(VOICE_CHANNEL_ID) in item.text():
                    self.channels_list.setCurrentRow(i)
                    break
    
    def on_channel_selected(self):
        """Вызывается при выборе канала"""
        current_item = self.channels_list.currentItem()
        if current_item:
            text = current_item.text()
            try:
                id_start = text.rfind("(ID: ") + 5
                id_end = text.rfind(")")
                if id_start > 4 and id_end > id_start:
                    channel_id = int(text[id_start:id_end])
                    call_async(bot.set_current_channel(channel_id))
            except (ValueError, IndexError):
                pass
    
    def add_channel_dialog(self):
        """Диалог для добавления канала"""
        channel_id, ok1 = QInputDialog.getText(
            self, "Добавить канал", "Введите ID голосового канала:"
        )
        
        if not ok1 or not channel_id.strip():
            return
        
        try:
            channel_id = int(channel_id.strip())
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "ID канала должен быть числом!")
            return
        
        for ch in CONFIG["channels"]:
            if ch["id"] == channel_id:
                QMessageBox.warning(self, "Ошибка", f"Канал с ID {channel_id} уже существует!")
                return
        
        channel_name, ok2 = QInputDialog.getText(
            self, "Имя канала", "Введите имя для канала:",
            text=f"Канал {channel_id}"
        )
        
        if not ok2:
            return
        
        channel_name = channel_name.strip() or f"Канал {channel_id}"
        
        call_async(bot.add_channel(channel_id, channel_name))
        
        self.load_channels()
        
        for i in range(self.channels_list.count()):
            item = self.channels_list.item(i)
            if str(channel_id) in item.text():
                self.channels_list.setCurrentRow(i)
                break
    
    def remove_channel_dialog(self):
        """Удаляет выбранный канал"""
        current_item = self.channels_list.currentItem()
        
        if not current_item:
            QMessageBox.warning(self, "Ошибка", "Выберите канал для удаления!")
            return
        
        text = current_item.text()
        try:
            id_start = text.rfind("(ID: ") + 5
            id_end = text.rfind(")")
            if id_start > 4 and id_end > id_start:
                channel_id = int(text[id_start:id_end])
                
                reply = QMessageBox.question(
                    self, "Подтверждение",
                    f"Удалить канал '{text}'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    call_async(bot.remove_channel(channel_id))
                    self.load_channels()
        except (ValueError, IndexError):
            QMessageBox.warning(self, "Ошибка", "Не удалось определить ID канала!")
    
    def connect_to_channel(self):
        """Подключается к выбранному каналу"""
        current_item = self.channels_list.currentItem()
        
        if not current_item:
            QMessageBox.warning(self, "Ошибка", "Выберите канал из списка!")
            return
        
        text = current_item.text()
        try:
            id_start = text.rfind("(ID: ") + 5
            id_end = text.rfind(")")
            if id_start > 4 and id_end > id_start:
                channel_id = int(text[id_start:id_end])
                
                call_async(bot.set_current_channel(channel_id))
                call_async(bot.connect_to_channel())
        except (ValueError, IndexError):
            QMessageBox.warning(self, "Ошибка", "Не удалось определить ID канала!")


class TracksWindow(QWidget):
    """Окно для управления списком треков"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_panel = parent
        self.background_pixmap = None
        self.setWindowTitle("Музыкальные треки")
        self.resize(400, 500)
        
        layout = QVBoxLayout()
        
        label = QLabel("Музыкальные треки:")
        layout.addWidget(label)
        
        # Список папок
        folders_label = QLabel("Папки с музыкой:")
        layout.addWidget(folders_label)
        
        self.folders_list = QListWidget()
        self.folders_list.setMaximumHeight(100)
        layout.addWidget(self.folders_list)
        
        # Кнопки управления папками
        folders_buttons = QHBoxLayout()
        
        add_folder_btn = QPushButton("+ Папка")
        add_folder_btn.clicked.connect(self.add)
        folders_buttons.addWidget(add_folder_btn)
        
        remove_folder_btn = QPushButton("- Папка")
        remove_folder_btn.clicked.connect(self.remove_folder)
        folders_buttons.addWidget(remove_folder_btn)
        
        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(self.load_tracks)
        folders_buttons.addWidget(refresh_btn)
        
        close_folders_btn = QPushButton("✕ Закрыть")
        close_folders_btn.clicked.connect(self.close)
        folders_buttons.addWidget(close_folders_btn)
        
        layout.addLayout(folders_buttons)
        
        # Список треков
        tracks_label = QLabel("Треки:")
        layout.addWidget(tracks_label)
        
        self.tracks_list = QListWidget()
        layout.addWidget(self.tracks_list)
        
        # Кнопки управления треками
        buttons_layout = QHBoxLayout()
        
        play_btn = QPushButton("PLAY")
        play_btn.clicked.connect(self.play)
        buttons_layout.addWidget(play_btn)
        
        close_btn = QPushButton("✕ Закрыть")
        close_btn.clicked.connect(self.close)
        buttons_layout.addWidget(close_btn)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        self.apply_theme()
        self.load_folders()
        self.load_tracks()
    
    def apply_theme(self):
        """Применяет тему и фоновое изображение"""
        bg_image = CONFIG.get("background_image", "")
        
        if bg_image and os.path.exists(bg_image):
            # Загружаем изображение для масштабирования
            self.background_pixmap = QPixmap(bg_image)
            # Применяем стили для виджетов
            self.setStyleSheet("""
            QPushButton {
                background: rgba(51, 51, 51, 200);
                padding: 8px;
                border: 1px solid rgba(255, 255, 255, 100);
                color: white;
            }
            QLabel {
                background: rgba(30, 30, 30, 150);
                color: white;
            }
            QListWidget {
                background: rgba(30, 30, 30, 200);
                color: white;
            }
            """)
            # Обновляем виджет для перерисовки
            self.update()
        else:
            # Стандартная тема без фона
            self.background_pixmap = None
            self.setStyleSheet("""
            QWidget {background:#1e1e1e;color:white}
            QPushButton {background:#333;padding:8px}
            """)
    
    def paintEvent(self, event):
        """Отрисовывает фоновое изображение с масштабированием"""
        if self.background_pixmap and not self.background_pixmap.isNull():
            painter = QPainter(self)
            # Масштабируем изображение под размер окна (cover mode)
            scaled_pixmap = self.background_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            # Вычисляем позицию для центрирования
            x = (scaled_pixmap.width() - self.width()) // 2
            y = (scaled_pixmap.height() - self.height()) // 2
            # Отрисовываем обрезанное изображение
            painter.drawPixmap(0, 0, scaled_pixmap, x, y, self.width(), self.height())
        else:
            # Если нет фона, вызываем стандартную отрисовку
            super().paintEvent(event)
    
    def load_folders(self):
        """Загружает список папок"""
        self.folders_list.clear()
        folders = CONFIG.get("music_folders", [])
        
        # Если папок нет, показываем старую папку tracks
        if not folders:
            folders = [LEGACY_TRACKS]
        
        for folder in folders:
            self.folders_list.addItem(folder)
    
    def load_tracks(self):
        """Загружает список треков из всех папок"""
        self.tracks_list.clear()
        tracks = get_all_tracks()
        
        # Группируем по папкам для удобства
        folders_dict = {}
        for track in tracks:
            folder = track["folder"]
            if folder not in folders_dict:
                folders_dict[folder] = []
            folders_dict[folder].append(track)
        
        # Добавляем треки с указанием папки
        for folder, folder_tracks in folders_dict.items():
            folder_name = os.path.basename(folder) if folder != LEGACY_TRACKS else "tracks"
            for track in folder_tracks:
                display_name = f"{track['name']} [{folder_name}]"
                self.tracks_list.addItem(display_name)
                # Сохраняем полный путь в данных элемента
                item = self.tracks_list.item(self.tracks_list.count() - 1)
                item.setData(Qt.ItemDataRole.UserRole, track["path"])
    
    def play(self):
        """Воспроизводит выбранный трек"""
        item = self.tracks_list.currentItem()
        if item:
            # Получаем полный путь из данных элемента
            track_path = item.data(Qt.ItemDataRole.UserRole)
            if track_path:
                call_async(bot.play_music(track_path))
            else:
                # Fallback на старое поведение
                call_async(bot.play_music(item.text().split(" [")[0]))
    
    def add(self):
        """Добавляет новую папку с музыкой"""
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку с музыкальными файлами"
        )
        if folder:
            folders = CONFIG.get("music_folders", [])
            # Нормализуем путь
            folder = os.path.normpath(folder)
            # Проверяем, нет ли уже такой папки
            if folder not in folders:
                folders.append(folder)
                CONFIG["music_folders"] = folders
                json.dump(CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2)
                self.load_folders()
                self.load_tracks()
                QMessageBox.information(self, "Успешно", f"Папка добавлена: {folder}")
            else:
                QMessageBox.warning(self, "Ошибка", "Эта папка уже добавлена!")
    
    def remove_folder(self):
        """Удаляет выбранную папку"""
        item = self.folders_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Ошибка", "Выберите папку для удаления!")
            return
        
        folder = item.text()
        
        # Не позволяем удалить последнюю папку
        folders = CONFIG.get("music_folders", [])
        if len(folders) <= 1 and folder in folders:
            QMessageBox.warning(self, "Ошибка", "Нельзя удалить последнюю папку!")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить папку '{folder}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if folder in folders:
                folders.remove(folder)
                CONFIG["music_folders"] = folders
                json.dump(CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2)
                self.load_folders()
                self.load_tracks()
                QMessageBox.information(self, "Успешно", "Папка удалена")
    


class Panel(QWidget):

    def __init__(self):

        super().__init__()
        
        # Флаг для предотвращения конфликтов при ручном управлении паузой
        self.pause_manual_control = False
        
        # Фоновое изображение для масштабирования
        self.background_pixmap = None

        self.setWindowTitle("MusicBot ULTRA")

        self.resize(400, 500)

        layout = QVBoxLayout()

        self.status = QLabel("Ready")

        layout.addWidget(self.status)

        # Кнопки для открытия списков в отдельных окнах
        lists_layout = QHBoxLayout()
        
        channels_btn = QPushButton("📋 Каналы")
        channels_btn.clicked.connect(self.show_channels_window)
        lists_layout.addWidget(channels_btn)
        
        tracks_btn = QPushButton("🎵 Треки")
        tracks_btn.clicked.connect(self.show_tracks_window)
        lists_layout.addWidget(tracks_btn)
        
        layout.addLayout(lists_layout)
        
        # Кнопки подключения/отключения
        connection_layout = QHBoxLayout()
        
        connect_btn = QPushButton("Подключиться")
        connect_btn.clicked.connect(self.connect_to_channel)
        connection_layout.addWidget(connect_btn)
        
        disconnect_btn = QPushButton("Отключиться")
        disconnect_btn.clicked.connect(self.disconnect_from_channel)
        connection_layout.addWidget(disconnect_btn)
        
        layout.addLayout(connection_layout)
        
        # Инициализируем окна (но не показываем их)
        self.channels_window = None
        self.tracks_window = None

        # Кнопки управления воспроизведением
        playback_layout = QHBoxLayout()
        
        # Кнопка PLAY открывает окно треков для выбора трека
        play = QPushButton("PLAY")
        play.clicked.connect(self.show_tracks_window)
        playback_layout.addWidget(play)

        stop = QPushButton("STOP")
        stop.clicked.connect(self.stop)
        playback_layout.addWidget(stop)
        
        self.pause_btn = QPushButton("⏸ ПАУЗА")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self.toggle_pause)
        playback_layout.addWidget(self.pause_btn)
        
        layout.addLayout(playback_layout)

        repeat_btn = QPushButton("REPEAT: OFF")
        repeat_btn.setCheckable(True)
        repeat_btn.toggled.connect(self.toggle_repeat)
        self.repeat_btn = repeat_btn

        layout.addWidget(repeat_btn)

        # Кнопки управления
        manage_layout = QHBoxLayout()
        
        # Кнопка ADD теперь открывает окно треков
        add = QPushButton("ADD")
        add.clicked.connect(self.show_tracks_window)
        manage_layout.addWidget(add)
        
        bg_btn = QPushButton("🎨 Фон")
        bg_btn.clicked.connect(self.set_background)
        manage_layout.addWidget(bg_btn)
        
        layout.addLayout(manage_layout)

        vol = QSlider(Qt.Orientation.Horizontal)

        vol.setMinimum(0)

        vol.setMaximum(100)

        vol.setValue(CONFIG["volume"])

        vol.valueChanged.connect(self.volume)

        layout.addWidget(vol)

        self.setLayout(layout)

        self.apply_theme()

        self.startTimer(500)


    def timerEvent(self, e):

        global current, voice

        # Обновляем состояние кнопки паузы (только если нет ручного управления)
        if hasattr(self, "pause_btn") and not self.pause_manual_control:
            if voice and voice.is_connected():
                # Проверяем, играет ли что-то (включая паузу)
                is_playing = voice.is_playing() or voice.is_paused()
                
                if is_playing:
                    if voice.is_paused():
                        # На паузе - кнопка должна быть нажата
                        if not self.pause_btn.isChecked():
                            self.pause_btn.setChecked(True)
                            self.pause_btn.setText("▶ ПРОДОЛЖИТЬ")
                    else:
                        # Играет - кнопка не должна быть нажата
                        if self.pause_btn.isChecked():
                            self.pause_btn.setChecked(False)
                            self.pause_btn.setText("⏸ ПАУЗА")
                else:
                    # Если не играет, сбрасываем состояние кнопки
                    if self.pause_btn.isChecked():
                        self.pause_btn.setChecked(False)
                        self.pause_btn.setText("⏸ ПАУЗА")

        # Обновляем статус подключения
        if voice and voice.is_connected():
            if voice.is_paused():
                if current:
                    self.status.setText(f"⏸ Пауза: {current}")
                else:
                    self.status.setText("⏸ Пауза")
            elif current:
                text = f"Playing: {current}"
                if hasattr(self, "repeat_btn") and self.repeat_btn.isChecked():
                    text += " [REPEAT]"
                self.status.setText(text)
            else:
                self.status.setText("Подключен (Idle)")
        elif voice:
            self.status.setText("Ошибка подключения")
        else:
            if current:
                text = "Playing: " + current
                if hasattr(self, "repeat_btn") and self.repeat_btn.isChecked():
                    text += " [REPEAT]"
                self.status.setText(text)
            else:
                self.status.setText("Не подключен")


    def apply_theme(self):
        """Применяет тему и фоновое изображение"""
        bg_image = CONFIG.get("background_image", "")
        
        if bg_image and os.path.exists(bg_image):
            # Загружаем изображение для масштабирования
            self.background_pixmap = QPixmap(bg_image)
            # Применяем стили для виджетов
            self.setStyleSheet("""
            QPushButton {
                background: rgba(51, 51, 51, 200);
                padding: 8px;
                border: 1px solid rgba(255, 255, 255, 100);
                color: white;
            }
            QLabel {
                background: rgba(30, 30, 30, 150);
                color: white;
            }
            QSlider {
                background: rgba(30, 30, 30, 150);
            }
            QListWidget {
                background: rgba(30, 30, 30, 200);
                color: white;
            }
            """)
            # Обновляем виджет для перерисовки
            self.update()
        else:
            # Стандартная тема без фона
            self.background_pixmap = None
            self.setStyleSheet("""
            QWidget {background:#1e1e1e;color:white}
            QPushButton {background:#333;padding:8px}
            """)
    
    def paintEvent(self, event):
        """Отрисовывает фоновое изображение с масштабированием"""
        if self.background_pixmap and not self.background_pixmap.isNull():
            painter = QPainter(self)
            # Масштабируем изображение под размер окна (cover mode)
            scaled_pixmap = self.background_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            # Вычисляем позицию для центрирования
            x = (scaled_pixmap.width() - self.width()) // 2
            y = (scaled_pixmap.height() - self.height()) // 2
            # Отрисовываем обрезанное изображение
            painter.drawPixmap(0, 0, scaled_pixmap, x, y, self.width(), self.height())
        else:
            # Если нет фона, вызываем стандартную отрисовку
            super().paintEvent(event)


    def stop(self):
        call_async(bot.stop_music())


    def volume(self, v):
        call_async(bot.set_volume_music(v))


    def toggle_repeat(self, checked):
        self.repeat_btn.setText("REPEAT: ON" if checked else "REPEAT: OFF")
        call_async(bot.set_repeat_music(checked))


    def disconnect_from_channel(self):
        """Отключается от голосового канала"""
        self.status.setText("Отключение от канала...")
        call_async(bot.disconnect_from_channel())


    def toggle_pause(self, checked):
        """Ставит на паузу или возобновляет воспроизведение"""
        global voice
        
        if not voice or not voice.is_connected():
            self.pause_btn.setChecked(False)
            self.status.setText("Ошибка: Не подключен к каналу")
            return
        
        # Устанавливаем флаг ручного управления
        self.pause_manual_control = True
        
        if checked:
            # Ставим на паузу
            self.pause_btn.setText("▶ ПРОДОЛЖИТЬ")
            call_async(bot.pause_music())
            self.status.setText("Пауза")
        else:
            # Возобновляем
            self.pause_btn.setText("⏸ ПАУЗА")
            call_async(bot.resume_music())
        
        # Сбрасываем флаг через небольшую задержку, чтобы timerEvent не перезаписывал состояние
        QTimer.singleShot(1000, lambda: setattr(self, 'pause_manual_control', False))


    def show_channels_window(self):
        """Открывает окно со списком каналов"""
        if self.channels_window is None or not self.channels_window.isVisible():
            self.channels_window = ChannelsWindow(self)
        self.channels_window.show()
        self.channels_window.raise_()
        self.channels_window.activateWindow()

    def show_tracks_window(self):
        """Открывает окно со списком треков"""
        if self.tracks_window is None or not self.tracks_window.isVisible():
            self.tracks_window = TracksWindow(self)
        self.tracks_window.show()
        self.tracks_window.raise_()
        self.tracks_window.activateWindow()

    def set_background(self):
        """Устанавливает фоновое изображение"""
        file, _ = QFileDialog.getOpenFileName(
            self, "Выберите фоновое изображение", "", 
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file:
            # Копируем изображение в папку с exe для сохранения
            bg_dir = _abs("backgrounds")
            os.makedirs(bg_dir, exist_ok=True)
            bg_filename = os.path.basename(file)
            bg_path = os.path.join(bg_dir, bg_filename)
            shutil.copy(file, bg_path)
            
            # Сохраняем путь в конфиг
            CONFIG["background_image"] = bg_path
            json.dump(CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2)
            
            # Применяем тему
            self.apply_theme()
            
            # Обновляем окна, если они открыты
            if self.channels_window:
                self.channels_window.apply_theme()
            if self.tracks_window:
                self.tracks_window.apply_theme()
            
            self.status.setText(f"Фон установлен: {bg_filename}")

    def remove_background(self):
        """Убирает фоновое изображение"""
        CONFIG["background_image"] = ""
        json.dump(CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2)
        self.apply_theme()
        
        # Обновляем окна, если они открыты
        if self.channels_window:
            self.channels_window.apply_theme()
        if self.tracks_window:
            self.tracks_window.apply_theme()
        
        self.status.setText("Фон удален")


    def connect_to_channel(self):
        """Подключается к выбранному каналу (используется из окна каналов)"""
        if self.channels_window and self.channels_window.isVisible():
            self.channels_window.connect_to_channel()
        else:
            # Если окно не открыто, открываем его
            self.show_channels_window()
            QTimer.singleShot(500, lambda: self.channels_window.connect_to_channel() if self.channels_window else None)


# ========================
# SYSTEM TRAY
# ========================

class Tray(QSystemTrayIcon):

    def __init__(self, app, panel):

        # Пытаемся загрузить иконку из ресурсов или рядом с exe
        icon_path = _resource("icons", "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = _abs("icons", "icon.ico")
        
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        
        super().__init__(icon, app)

        menu = QMenu()

        show = QAction("Show")

        show.triggered.connect(panel.show)

        menu.addAction(show)

        quit = QAction("Exit")

        quit.triggered.connect(app.quit)

        menu.addAction(quit)

        self.setContextMenu(menu)

        self.show()


# ========================
# HOTKEYS
# ========================

def hotkeys():
    """Горячие клавиши для управления ботом"""
    def play_first_track():
        tracks = get_all_tracks()
        if tracks:
            call_async(bot.play_music(tracks[0]["path"]))
    
    keyboard.add_hotkey("ctrl+alt+1", play_first_track)


threading.Thread(target=hotkeys, daemon=True).start()


# ========================
# START
# ========================

app = QApplication(sys.argv)

panel = Panel()

tray = Tray(app, panel)

panel.show()

sys.exit(app.exec())
