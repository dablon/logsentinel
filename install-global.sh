#!/bin/bash
# LogSentinel Global Install Script (Bash)
# Installs the tool system-wide (requires sudo)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Installing LogSentinel globally..."

# Uninstall first if exists
echo "Checking for existing installation..."
sudo python -m pip uninstall logsentinel -y 2>/dev/null || true

# Install globally with force reinstall
sudo python -m pip install --force-reinstall .

echo "LogSentinel installed successfully globally!"
echo "You can now run 'logsentinel' from anywhere."
