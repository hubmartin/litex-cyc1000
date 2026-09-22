#!/usr/bin/env bash
# Software-only rebuild (skips Quartus gateware compilation ~5 min → ~10 sec)
set -euo pipefail
cd -- "$(dirname -- "$0")"
source ./litex_env.sh
"$PYTHON" soc.py \
  --build --no-compile-gateware \
  --with-buttons --with-ethernet --eth-ip 192.168.1.241 \
  --cpu-variant=lite --uart-fifo-depth 512 \
  --with-jtagbone \
  --sys-clk-freq 50e6 --output-dir build
