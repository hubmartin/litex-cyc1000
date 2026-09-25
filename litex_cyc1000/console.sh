#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
source ./litex_env.sh
# The direct filter passes ANSI escape sequences through, so BIOS and Zephyr
# shell colors are rendered instead of being shown as control pictures.
exec "$PYTHON" -m serial.tools.miniterm --filter direct "${LITEX_UART:-/dev/ttyUSB3}" 115200
