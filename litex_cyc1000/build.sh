#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
ROOT=$(cd .. && pwd)
export PATH=/home/martin/altera_lite/25.1std/quartus/bin:$PATH
export PYTHON="$ROOT/.venv/bin/python"
"$PYTHON" soc.py \
  --build --with-buttons --with-etherbone --cpu-variant=lite --l2-size 0 --sys-clk-freq 50e6 --output-dir build
/home/martin/altera_lite/25.1std/quartus/bin/quartus_cpf -c \
  build/gateware/trenz_cyc1000.sof build/gateware/trenz_cyc1000.rbf
