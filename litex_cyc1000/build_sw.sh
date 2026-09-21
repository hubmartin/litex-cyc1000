#!/usr/bin/env bash
# Software-only rebuild (skips Quartus gateware compilation ~5 min → ~10 sec)
set -euo pipefail
cd -- "$(dirname -- "$0")"
ROOT=$(cd .. && pwd)
export PYTHON="$ROOT/.venv/bin/python"
"$PYTHON" soc.py \
  --build --no-compile-gateware \
  --with-buttons --no-led-chaser --with-ethernet --eth-ip 192.168.1.241 \
  --cpu-variant=minimal --integrated-main-ram-size 8192 \
  --with-jtagbone \
  --sys-clk-freq 50e6 --output-dir build
