# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

a = Analysis(
    ['musicbot_ultra.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ffmpeg/bin/ffmpeg.exe', 'ffmpeg/bin'),
        ('ffmpeg/bin/ffplay.exe', 'ffmpeg/bin'),
        ('ffmpeg/bin/ffprobe.exe', 'ffmpeg/bin'),
        ('config.json', '.'),
    ] + ([('icons/icon.ico', 'icons')] if os.path.exists('icons/icon.ico') else []),
    hiddenimports=[
        'discord',
        'discord.ext.commands',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'keyboard',
        'nacl',
        'asyncio',
        'threading',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MusicBot_ULTRA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Без консоли для GUI приложения
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.abspath('icons/icon.ico') if os.path.exists('icons/icon.ico') else None,
)
