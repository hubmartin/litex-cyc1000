#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
litex_dir="$project_dir/../litex_cyc1000"
kernel="$project_dir/build/zephyr/zephyr.bin"

if [[ ! -f "$kernel" ]]; then
	printf 'Zephyr binary not found: %s\nRun scripts/build.sh first.\n' "$kernel" >&2
	exit 1
fi

cd "$litex_dir"
source ./litex_env.sh
openFPGALoader --board cyc1000 build-zephyr-etherbone/gateware/trenz_cyc1000.rbf
exec "$PYTHON" -m litex.tools.litex_term "${LITEX_UART:-/dev/ttyUSB3}" \
	--speed 115200 --serial-boot --kernel "$kernel"
