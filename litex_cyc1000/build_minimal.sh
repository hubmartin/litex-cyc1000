#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
ROOT=$(cd .. && pwd)
export PATH=/home/martin/altera_lite/25.1std/quartus/bin:$PATH
export PYTHON="$ROOT/.venv/bin/python"
"$PYTHON" -m litex_boards.targets.trenz_cyc1000 \
  --build --with-buttons --sys-clk-freq 50e6 --integrated-main-ram-size 8192 \
  --output-dir build-minimal
/home/martin/altera_lite/25.1std/quartus/bin/quartus_cpf -c \
  build-minimal/gateware/trenz_cyc1000.sof build-minimal/gateware/trenz_cyc1000.rbf
