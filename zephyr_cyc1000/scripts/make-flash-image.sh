#!/usr/bin/env bash
# Wrap zephyr.bin in the LiteX Flash Boot Image (FBI) length/CRC header.
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root_dir=$(cd -- "$project_dir/.." && pwd)
kernel="$project_dir/build/zephyr/zephyr.bin"
image="$project_dir/build/zephyr/zephyr.fbi"

if [[ ! -f "$kernel" ]]; then
	printf 'Zephyr binary not found: %s\nRun scripts/build.sh first.\n' "$kernel" >&2
	exit 1
fi

cd "$root_dir/litex_cyc1000"
source ./litex_env.sh
"$PYTHON" -m litex.soc.software.crcfbigen "$kernel" \
	--fbi --little --output "$image"
printf 'Created %s\n' "$image"
