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
    QApplication, QWidget, QVBoxLayout,
    QPushButton, QListWidget, QLabel,
    QSlider, QFileDialog, QSystemTrayIcon,
    QMenu
)

from PyQt6.QtGui import QIcon, QAction

from PyQt6.QtCore import Qt

import keyboard


# ========================
# LOAD CONFIG
# ========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _abs(*parts: str) -> str:
    return os.path.join(BASE_DIR, *parts)

CONFIG_PATH = _abs("config.json")
TOKEN_PATH = _abs("token.txt")
TRACKS = _abs("tracks")
FFMPEG = _abs("ffmpeg", "bin", "ffmpeg.exe")

CONFIG = json.load(open(CONFIG_PATH, encoding="utf-8"))

VOICE_CHANNEL_ID = CONFIG["voice_channel_id"]

TOKEN = os.getenv("DISCORD_TOKEN") or open(TOKEN_PATH, encoding="utf-8").read().strip()

os.makedirs(TRACKS, exist_ok=True)


# ========================
# DISCORD BOT
# ========================

intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

voice = None

queue = []

current = None

volume = CONFIG["volume"] / 100

# Режим бесконечного повтора текущего трека
repeat_enabled = False


@bot.event
async def on_ready():
    await connect()


async def connect():

    global voice

    if voice:
        return

    channel = bot.get_channel(VOICE_CHANNEL_ID) or await bot.fetch_channel(VOICE_CHANNEL_ID)
    if channel is None:
        raise RuntimeError(f"Voice channel {VOICE_CHANNEL_ID} not found (cache+fetch failed).")

    voice = await channel.connect()

    # If this is a Stage channel, bots join suppressed by default (no audio output).
    try:
        me = voice.guild.me
        if me is not None and getattr(me.voice, "suppress", False):
            await me.edit(suppress=False)
    except Exception as e:
        print("[voice] stage unsuppress failed:", repr(e))


async def next_track():

    global current, repeat_enabled

    # Если включен режим повтора и уже есть текущий трек – просто переигрываем его.
    if repeat_enabled and current is not None:
        track_name = current
    else:
        if not queue:
            current = None
            return
        current = queue.pop(0)
        track_name = current

    path = os.path.join(TRACKS, track_name)
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
        # Это помогает избавиться от “битого” / искажённого звука.
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


async def play(track):

    await connect()

    queue.append(track)

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


bot.play_music = play
bot.stop_music = stop
bot.pause_music = pause
bot.resume_music = resume
bot.set_volume_music = set_volume
bot.set_repeat_music = set_repeat


def run_bot():
    # Используем встроенный run, чтобы не создавать свой event loop через asyncio.run
    # Это предотвращает ошибку "Future attached to a different loop"
    bot.run(TOKEN)


threading.Thread(target=run_bot, daemon=True).start()


# ========================
# GUI
# ========================

class Panel(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("MusicBot ULTRA")

        self.resize(400, 500)

        layout = QVBoxLayout()

        self.status = QLabel("Ready")

        layout.addWidget(self.status)

        self.list = QListWidget()

        layout.addWidget(self.list)

        self.load_tracks()

        play = QPushButton("PLAY")

        play.clicked.connect(self.play)

        layout.addWidget(play)

        stop = QPushButton("STOP")

        stop.clicked.connect(self.stop)

        layout.addWidget(stop)

        repeat_btn = QPushButton("REPEAT: OFF")
        repeat_btn.setCheckable(True)
        repeat_btn.toggled.connect(self.toggle_repeat)
        self.repeat_btn = repeat_btn

        layout.addWidget(repeat_btn)

        add = QPushButton("ADD")

        add.clicked.connect(self.add)

        layout.addWidget(add)

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

        global current

        if current:
            text = "Playing: " + current
            if hasattr(self, "repeat_btn") and self.repeat_btn.isChecked():
                text += " [REPEAT]"
            self.status.setText(text)
        else:
            self.status.setText("Idle")


    def apply_theme(self):

        self.setStyleSheet("""

        QWidget {background:#1e1e1e;color:white}

        QPushButton {background:#333;padding:8px}

        """)


    def load_tracks(self):

        self.list.clear()

        for f in os.listdir(TRACKS):

            if f.endswith(".mp3") or f.endswith(".wav"):
                self.list.addItem(f)


    def play(self):

        item = self.list.currentItem()

        if item:

            asyncio.run_coroutine_threadsafe(
                bot.play_music(item.text()),
                bot.loop
            )


    def stop(self):

        asyncio.run_coroutine_threadsafe(
            bot.stop_music(),
            bot.loop
        )


    def volume(self, v):

        asyncio.run_coroutine_threadsafe(
            bot.set_volume_music(v),
            bot.loop
        )


    def toggle_repeat(self, checked):

        self.repeat_btn.setText("REPEAT: ON" if checked else "REPEAT: OFF")

        asyncio.run_coroutine_threadsafe(
            bot.set_repeat_music(checked),
            bot.loop
        )


    def add(self):

        file, _ = QFileDialog.getOpenFileName()

        if file:

            shutil.copy(file, TRACKS)

            self.load_tracks()


# ========================
# SYSTEM TRAY
# ========================

class Tray(QSystemTrayIcon):

    def __init__(self, app, panel):

        icon = QIcon("icons/icon.ico")

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

    keyboard.add_hotkey("ctrl+alt+1", lambda:
        asyncio.run_coroutine_threadsafe(
            bot.play_music(os.listdir(TRACKS)[0]),
            bot.loop
        )
    )


threading.Thread(target=hotkeys, daemon=True).start()


# ========================
# START
# ========================

app = QApplication(sys.argv)

panel = Panel()

tray = Tray(app, panel)

panel.show()

sys.exit(app.exec())
