#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
source ./litex_env.sh
exec "$PYTHON" -m serial.tools.miniterm "${LITEX_UART:-/dev/ttyUSB3}" 115200
