# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_dir = Path.cwd()
icon_path = project_dir / "assets" / "app_icon.icns"

datas = [
    (str(project_dir / "requirements.txt"), "."),
    (str(project_dir / "requirements-build.txt"), "."),
    (str(project_dir / "persona.example.txt"), "."),
    (str(project_dir / "scripts"), "scripts"),
    (str(project_dir / "assets"), "assets"),
]

hiddenimports = [
    "scripts.extract_whatsapp_persona",
    "sounddevice",
    "soundfile",
    "mlx_whisper",
]
for package in ("TTS", "mlx_whisper", "sounddevice", "soundfile"):
    try:
        hiddenimports += collect_submodules(package)
    except Exception:
        pass

for package in ("TTS", "mlx_whisper"):
    try:
        datas += collect_data_files(package)
    except Exception:
        pass

a = Analysis(
    [str(project_dir / "gui.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Persona Chat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Persona Chat",
)

app = BUNDLE(
    coll,
    name="Persona Chat.app",
    icon=str(icon_path) if icon_path.exists() else None,
    bundle_identifier="local.persona.chat",
    info_plist={
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Persona Chat uses the microphone for local voice input.",
    },
)
