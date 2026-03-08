#!/bin/bash
# LogSentinel Local Install Script (Bash)
# Installs the tool in editable/development mode

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Installing LogSentinel locally (editable mode)..."

python -m pip install -e .

echo "LogSentinel installed successfully in editable mode!"
echo "You can now run 'logsentinel' from anywhere."
