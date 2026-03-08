#!/bin/bash
# LogSentinel Uninstall Script (Bash)

set -e

echo "Uninstalling LogSentinel..."

sudo python -m pip uninstall logsentinel -y || true
python -m pip uninstall logsentinel -y --user 2>/dev/null || true

echo "LogSentinel uninstalled successfully!"
