#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
litex_dir="$project_dir/../litex_cyc1000"

cd "$litex_dir"
source ./litex_env.sh
export PATH=/home/martin/altera_lite/25.1std/quartus/bin:$PATH

"$PYTHON" soc.py \
  --build --with-buttons --with-ethernet --with-jtagbone --with-zephyr-flash-boot --with-flash-storage --eth-dynamic-ip \
  --cpu-variant=lite --uart-fifo-depth 512 --uart-rx-fifo-rx-we --timer-uptime --sys-clk-freq 50e6 \
  --output-dir build-zephyr-ethernet

/home/martin/altera_lite/25.1std/quartus/bin/quartus_cpf -c \
  build-zephyr-ethernet/gateware/trenz_cyc1000.sof \
  build-zephyr-ethernet/gateware/trenz_cyc1000.rbf
