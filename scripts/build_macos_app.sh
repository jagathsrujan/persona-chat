#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

APP_NAME="Persona Chat.app"
DIST_APP="dist/$APP_NAME"
ZIP_PATH="dist/Persona-Chat-macos-arm64.zip"
USER_APPLICATIONS_DIR="${PERSONA_CHAT_APPLICATIONS_DIR:-$HOME/Applications}"
APP_SUPPORT_DIR="${PERSONA_CHAT_APP_SUPPORT_DIR:-$HOME/Library/Application Support/Persona Chat}"
ICON_SVG="assets/app_icon.svg"
ICON_ICNS="assets/app_icon.icns"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

DEFAULT_PYTHON="$PROJECT_DIR/tools/python/bin/python3.11"
if [ ! -x "$DEFAULT_PYTHON" ]; then
  DEFAULT_PYTHON="$(command -v python3.11 || command -v python3 || true)"
fi
PYTHON_COMMAND="${PERSONA_CHAT_PYTHON:-$DEFAULT_PYTHON}"
if [ -z "$PYTHON_COMMAND" ]; then
  echo "Python 3 was not found. Install Python 3.11 or run scripts/install_python_local.sh first." >&2
  exit 1
fi

needs_venv=0
if [ ! -x "$VENV_PYTHON" ]; then
  needs_venv=1
fi

if [ "$needs_venv" -eq 1 ]; then
  echo "Refreshing virtual environment at $VENV_DIR"
  if [ -d "$VENV_DIR" ] && "$PYTHON_COMMAND" -m venv --upgrade "$VENV_DIR"; then
    :
  else
    rm -rf "$VENV_DIR"
    "$PYTHON_COMMAND" -m venv "$VENV_DIR"
  fi
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt
"$VENV_PYTHON" -m pip install -r requirements-build.txt

generate_icon() {
  if [ ! -f "$ICON_SVG" ]; then
    echo "Skipping icon generation: $ICON_SVG was not found"
    return
  fi

  if [ -f "$ICON_ICNS" ] && [ "$ICON_ICNS" -nt "$ICON_SVG" ]; then
    echo "Using existing $ICON_ICNS"
    return
  fi

  echo "Generating $ICON_ICNS"
  local temp_root iconset
  temp_root="$(mktemp -d "${TMPDIR:-/tmp}/persona-chat-icon.XXXXXX")"
  iconset="$temp_root/app_icon.iconset"
  mkdir -p "$iconset"

  QT_QPA_PLATFORM=offscreen "$VENV_PYTHON" - "$ICON_SVG" "$iconset" <<'PY'
import sys
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

svg_path = Path(sys.argv[1])
iconset = Path(sys.argv[2])
renderer = QSvgRenderer(str(svg_path))
if not renderer.isValid():
    raise SystemExit(f"Could not render SVG icon: {svg_path}")

outputs = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}

for name, size in outputs.items():
    image = QImage(QSize(size, size), QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(iconset / name)):
        raise SystemExit(f"Could not write icon image: {name}")
PY

  iconutil -c icns "$iconset" -o "$ICON_ICNS"
  rm -rf "$temp_root"
}

migrate_app_data() {
  echo "Migrating local setup data to $APP_SUPPORT_DIR"
  mkdir -p "$APP_SUPPORT_DIR" "$APP_SUPPORT_DIR/temp"

  for file in persona.txt Modelfile; do
    if [ -f "$file" ]; then
      ditto "$file" "$APP_SUPPORT_DIR/$file"
    fi
  done

  for dir in voice_samples tools; do
    if [ -d "$dir" ]; then
      mkdir -p "$APP_SUPPORT_DIR/$dir"
      ditto "$dir" "$APP_SUPPORT_DIR/$dir"
    fi
  done
}

install_app() {
  echo "Installing $APP_NAME to $USER_APPLICATIONS_DIR"
  mkdir -p "$USER_APPLICATIONS_DIR"
  ditto "$DIST_APP" "$USER_APPLICATIONS_DIR/$APP_NAME"
}

generate_icon

"$VENV_PYTHON" -m PyInstaller --noconfirm --clean packaging/PersonaChat.spec

mkdir -p dist
ditto -c -k --keepParent "$DIST_APP" "$ZIP_PATH"
migrate_app_data
install_app

echo "Built $ZIP_PATH"
echo "Installed $USER_APPLICATIONS_DIR/$APP_NAME"
