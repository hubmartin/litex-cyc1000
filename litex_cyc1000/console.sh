#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
exec ../.venv/bin/python -m serial.tools.miniterm /dev/ttyUSB1 115200
