#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
QUARTUS=/home/martin/altera_lite/25.1std/quartus/bin
"$QUARTUS/quartus_sh" --flow compile cyc1000_blinky
"$QUARTUS/quartus_cpf" -c cyc1000_blinky.sof cyc1000_blinky.rbf
