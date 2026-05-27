#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$PROJECT_DIR/tools"
PYTHON_DIR="$TOOLS_DIR/python"
ARCHIVE_PATH="$TOOLS_DIR/cpython-3.11-aarch64-apple-darwin.tar.gz"
DOWNLOAD_URL="${PYTHON_STANDALONE_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20241008/cpython-3.11.10%2B20241008-aarch64-apple-darwin-install_only.tar.gz}"

echo "=== Local Python 3.11 Install ==="
echo "This installs Python only inside:"
echo "  $PYTHON_DIR"
echo "No sudo, no Homebrew writes, no system Python changes."

mkdir -p "$TOOLS_DIR"
rm -rf "$PYTHON_DIR"
mkdir -p "$PYTHON_DIR"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to download Python."
  exit 1
fi

echo "Downloading standalone Python 3.11..."
curl --fail --show-error --location --progress-bar -o "$ARCHIVE_PATH" "$DOWNLOAD_URL"

echo "Extracting Python..."
tar -xzf "$ARCHIVE_PATH" -C "$PYTHON_DIR" --strip-components=1

PYTHON_BIN="$PYTHON_DIR/bin/python3.11"
if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python binary was not found after extraction:"
  echo "  $PYTHON_BIN"
  exit 1
fi

"$PYTHON_BIN" --version
echo "✓ Python installed locally:"
echo "  $PYTHON_BIN"
echo ""
echo "Next:"
echo "  ./setup.sh"
