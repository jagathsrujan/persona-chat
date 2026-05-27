#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$PROJECT_DIR/tools"
ZIP_PATH="$TOOLS_DIR/Ollama-darwin.zip"
DOWNLOAD_URL="${OLLAMA_DOWNLOAD_URL:-https://github.com/ollama/ollama/releases/latest/download/Ollama-darwin.zip}"

echo "=== Local Ollama Install ==="
echo "This installs Ollama only inside:"
echo "  $TOOLS_DIR"
echo "No sudo, no Homebrew writes, no /Applications writes."

mkdir -p "$TOOLS_DIR"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to download Ollama."
  exit 1
fi

if ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is required to extract Ollama."
  exit 1
fi

echo "Downloading Ollama..."
curl --fail --show-error --location --progress-bar -o "$ZIP_PATH" "$DOWNLOAD_URL"

echo "Extracting Ollama..."
rm -rf "$TOOLS_DIR/Ollama.app"
unzip -q "$ZIP_PATH" -d "$TOOLS_DIR"

OLLAMA_BIN="$TOOLS_DIR/Ollama.app/Contents/Resources/ollama"
if [ ! -x "$OLLAMA_BIN" ]; then
  echo "Ollama binary was not found after extraction:"
  echo "  $OLLAMA_BIN"
  exit 1
fi

echo "✓ Ollama installed locally:"
echo "  $OLLAMA_BIN"
echo ""
echo "Next:"
echo "  ./setup.sh"
