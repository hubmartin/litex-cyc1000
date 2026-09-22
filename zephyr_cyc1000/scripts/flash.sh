#!/usr/bin/env bash
# Persist the FPGA image, matching LiteX BIOS, and Zephyr FBI image.
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
litex_dir="$project_dir/../litex_cyc1000"
litex_build="${LITEX_BUILD:-build-zephyr-etherbone}"
gateware="$litex_dir/$litex_build/gateware/trenz_cyc1000.rbf"
bios="$litex_dir/$litex_build/software/bios/bios.bin"
zephyr_image="$project_dir/build/zephyr/zephyr.fbi"
readonly bios_offset=1048576       # 0x00100000
readonly zephyr_offset=1179648     # 0x00120000
readonly flash_size=2097152        # W25Q16: 2 MiB

[[ -f "$gateware" && -f "$bios" && -f "$zephyr_image" ]]
[[ $(stat -c%s "$gateware") -le "$bios_offset" ]]
[[ $((bios_offset + $(stat -c%s "$bios"))) -le "$zephyr_offset" ]]
[[ $((zephyr_offset + $(stat -c%s "$zephyr_image"))) -le "$flash_size" ]]

# Each write is read back. The final SRAM load activates the new image now;
# later power resets use the same persisted configuration and boot image.
openFPGALoader --board cyc1000 --write-flash --verify "$gateware"
openFPGALoader --board cyc1000 --write-flash --verify --offset "$bios_offset" \
	--file-type bin "$bios"
openFPGALoader --board cyc1000 --write-flash --verify --offset "$zephyr_offset" \
	--file-type bin "$zephyr_image"
exec openFPGALoader --board cyc1000 "$gateware"
