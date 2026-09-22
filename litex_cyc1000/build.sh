#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
source ./litex_env.sh
export PATH=/home/martin/altera_lite/25.1std/quartus/bin:$PATH
"$PYTHON" soc.py \
  --build --with-buttons --with-ethernet --eth-ip 192.168.1.241 \
  --cpu-variant=lite --uart-fifo-depth 512 \
  --with-jtagbone \
  --sys-clk-freq 50e6 --output-dir build
/home/martin/altera_lite/25.1std/quartus/bin/quartus_cpf -c \
  build/gateware/trenz_cyc1000.sof build/gateware/trenz_cyc1000.rbf
