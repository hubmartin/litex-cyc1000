#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
litex_dir="$project_dir/../litex_cyc1000"

cd "$litex_dir"
source ./litex_env.sh
export PATH=/home/martin/altera_lite/25.1std/quartus/bin:$PATH

# No --with-ethernet: LAN8720 is instantiated only for LiteX Etherbone's PHY.
"$PYTHON" soc.py \
  --build --with-buttons --with-etherbone --with-zephyr-flash-boot --eth-ip "${ETHERBONE_IP:-192.168.1.241}" \
  --cpu-variant=lite --uart-fifo-depth 512 --uart-rx-fifo-rx-we --timer-uptime --sys-clk-freq 50e6 \
  --output-dir build-zephyr-etherbone

/home/martin/altera_lite/25.1std/quartus/bin/quartus_cpf -c \
  build-zephyr-etherbone/gateware/trenz_cyc1000.sof \
  build-zephyr-etherbone/gateware/trenz_cyc1000.rbf
