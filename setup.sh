#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

CHAT_SOURCE="${CHAT_SOURCE:-}"
SPEAKER_NAME="${SPEAKER_NAME:-}"
RAW_VOICE_DIR="${RAW_VOICE_DIR:-voice_samples/raw}"

echo "=== Persona Chat Setup ==="

require_command() {
  local command_name="$1"
  local install_hint="$2"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name"
    echo "$install_hint"
    exit 1
  fi
}

find_ollama() {
  if [ -n "${OLLAMA_BIN:-}" ] && [ -x "$OLLAMA_BIN" ]; then
    printf "%s\n" "$OLLAMA_BIN"
    return 0
  fi

  if command -v ollama >/dev/null 2>&1; then
    command -v ollama
    return 0
  fi

  local project_app_resource="$PROJECT_DIR/tools/Ollama.app/Contents/Resources/ollama"
  if [ -x "$project_app_resource" ]; then
    printf "%s\n" "$project_app_resource"
    return 0
  fi

  local app_resource="/Applications/Ollama.app/Contents/Resources/ollama"
  if [ -x "$app_resource" ]; then
    printf "%s\n" "$app_resource"
    return 0
  fi

  local user_app_resource="$HOME/Applications/Ollama.app/Contents/Resources/ollama"
  if [ -x "$user_app_resource" ]; then
    printf "%s\n" "$user_app_resource"
    return 0
  fi

  exit 1
}

find_python() {
  if [ -n "${PERSONA_CHAT_PYTHON:-}" ] && [ -x "$PERSONA_CHAT_PYTHON" ]; then
    printf "%s\n" "$PERSONA_CHAT_PYTHON"
    return 0
  fi

  local project_python="$PROJECT_DIR/tools/python/bin/python3.11"
  if [ -x "$project_python" ]; then
    printf "%s\n" "$project_python"
    return 0
  fi

  for candidate in python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done

  exit 1
}

require_command ffmpeg "Install ffmpeg somewhere on PATH, or expose the existing Homebrew ffmpeg to this user."
require_command ffprobe "Install ffmpeg somewhere on PATH; ffprobe ships with ffmpeg."

if ! OLLAMA_COMMAND="$(find_ollama)"; then
  echo "Ollama was not found for user $(id -un), and setup will not modify another user's Homebrew."
  echo "Install Ollama in this user's account, or point setup at a user-owned ollama binary:"
  echo "  OLLAMA_BIN=/path/to/ollama ./setup.sh"
  echo ""
  echo "For isolation, prefer a user-local install such as:"
  echo "  ./scripts/install_ollama_local.sh"
  exit 1
fi

if ! PYTHON_COMMAND="$(find_python)"; then
  echo "Python 3.11 was not found for user $(id -un)."
  echo "Install isolated Python locally, then rerun setup:"
  echo "  ./scripts/install_python_local.sh"
  echo "  ./setup.sh"
  echo ""
  echo "Or point setup at an existing user-owned Python 3.11:"
  echo "  PERSONA_CHAT_PYTHON=/path/to/python3.11 ./setup.sh"
  exit 1
fi

PYTHON_VERSION="$("$PYTHON_COMMAND" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

if [ "$PYTHON_VERSION" != "3.11" ]; then
  echo "Unsupported Python version: $PYTHON_VERSION"
  echo "This Apple Silicon TTS stack needs Python 3.11 to avoid the Coqui TTS / numpy conflict."
  echo "Install isolated Python locally, then rerun setup:"
  echo "  ./scripts/install_python_local.sh"
  echo "  ./setup.sh"
  exit 1
fi

echo "Using Python: $PYTHON_COMMAND ($PYTHON_VERSION)"
echo "Using Ollama: $OLLAMA_COMMAND"
export OLLAMA_BIN="$OLLAMA_COMMAND"

if ! curl -fsS "http://localhost:11434/api/tags" >/dev/null 2>&1; then
  echo "Starting local Ollama server for this user..."
  mkdir -p temp
  "$OLLAMA_COMMAND" serve > temp/ollama.log 2>&1 &
  OLLAMA_PID=$!
  sleep 3
  if ! curl -fsS "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    echo "Could not start Ollama. See temp/ollama.log for details."
    echo "You can also run this in another terminal, then rerun setup:"
    echo "  $OLLAMA_COMMAND serve"
    exit 1
  fi
  echo "✓ Ollama server started with PID $OLLAMA_PID"
fi

echo "Pulling base model llama3.1:8b..."
if ! "$OLLAMA_COMMAND" pull llama3.1:8b; then
  echo "Could not pull llama3.1:8b. Check your network for first-time setup, then retry."
  exit 1
fi

echo "Creating Python virtual environment..."
if [ -x ".venv/bin/python" ]; then
  VENV_VERSION="$(.venv/bin/python - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
  if [ "$VENV_VERSION" != "$PYTHON_VERSION" ]; then
    echo "Existing .venv uses Python $VENV_VERSION; recreating it with Python $PYTHON_VERSION."
    rm -rf .venv
  fi
fi
"$PYTHON_COMMAND" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

mkdir -p temp voice_samples

if [ -n "$CHAT_SOURCE" ]; then
  if [ -z "$SPEAKER_NAME" ]; then
    echo "CHAT_SOURCE was provided but SPEAKER_NAME is empty."
    echo "Example:"
    echo "  CHAT_SOURCE=\"/path/to/WhatsApp Chat.txt\" SPEAKER_NAME=\"Name\" ./setup.sh"
    exit 1
  fi
  echo "Extracting $SPEAKER_NAME messages into persona.txt..."
  if [ ! -f "$CHAT_SOURCE" ]; then
    echo "Missing chat export: $CHAT_SOURCE"
    exit 1
  fi
  python scripts/extract_whatsapp_persona.py "$CHAT_SOURCE" persona.txt "$SPEAKER_NAME"
elif [ ! -s "persona.txt" ]; then
  echo "persona.txt is missing or empty."
  echo "Add raw persona text to persona.txt, or provide a WhatsApp export:"
  echo "  CHAT_SOURCE=\"/path/to/WhatsApp Chat.txt\" SPEAKER_NAME=\"Name\" ./setup.sh"
  exit 1
fi

echo "Preparing voice sample..."
if [ ! -f "voice_samples/speaker.wav" ]; then
  existing_sources=()
  while IFS= read -r -d '' source; do
    existing_sources+=("$source")
  done < <(find "$RAW_VOICE_DIR" -type f \( -iname '*.ogg' -o -iname '*.opus' -o -iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a' -o -iname '*.flac' \) -print0 2>/dev/null || true)

  if [ "${#existing_sources[@]}" -eq 0 ]; then
    echo "No voice sources found."
    echo "Add a ready XTTS sample to voice_samples/speaker.wav, or put raw audio files in:"
    echo "  $RAW_VOICE_DIR"
    exit 1
  fi

  concat_list="$(mktemp)"
  trap 'rm -f "$concat_list"' EXIT
  for source in "${existing_sources[@]}"; do
    printf "file '%s'\n" "$source" >> "$concat_list"
  done

  if ! ffmpeg -y -f concat -safe 0 -i "$concat_list" -ar 22050 -ac 1 -af "silenceremove=1:0:-50dB,loudnorm" voice_samples/speaker.wav; then
    echo "ffmpeg failed to preprocess the voice sample. Verify the .ogg files are readable and try again."
    exit 1
  fi
fi

echo "Verifying voice sample format..."
if ! ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate,channels -of csv=p=0 voice_samples/speaker.wav | grep -q "22050,1"; then
  echo "voice_samples/speaker.wav is not 22050 Hz mono. Delete it and rerun setup.sh to regenerate it."
  exit 1
fi

echo "Verifying Python imports..."
python - <<'PY'
import numpy
import requests
import sounddevice
import soundfile
import mlx_whisper
from TTS.api import TTS
print("✓ Python imports ready")
PY

echo "Building persona model..."
python persona_builder.py

echo ""
echo "=== Setup Complete ==="
echo "Run:"
echo "  source .venv/bin/activate"
echo "  python main.py"
