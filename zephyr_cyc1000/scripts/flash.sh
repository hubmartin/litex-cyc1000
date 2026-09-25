#!/usr/bin/env bash
# Persist the FPGA image, matching LiteX BIOS, and Zephyr FBI image.
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
litex_dir="$project_dir/../litex_cyc1000"
litex_build="${LITEX_BUILD:-build-zephyr-ethernet}"
gateware="$litex_dir/$litex_build/gateware/trenz_cyc1000.rbf"
bios="$litex_dir/$litex_build/software/bios/bios.bin"
zephyr_image="$project_dir/build/zephyr/zephyr.fbi"
readonly bios_offset=1048576       # 0x00100000
readonly zephyr_offset=1179648     # 0x00120000
readonly storage_offset=1835008    # 0x001c0000: LittleFS, last 256 KiB

[[ -f "$gateware" && -f "$bios" && -f "$zephyr_image" ]]
[[ $(stat -c%s "$gateware") -le "$bios_offset" ]]
[[ $((bios_offset + $(stat -c%s "$bios"))) -le "$zephyr_offset" ]]
# The LittleFS tail is never written here, so its files survive reflashing.
[[ $((zephyr_offset + $(stat -c%s "$zephyr_image"))) -le "$storage_offset" ]]

# Each write is read back. The final SRAM load activates the new image now;
# later power resets use the same persisted configuration and boot image.
openFPGALoader --board cyc1000 --write-flash --verify "$gateware"
openFPGALoader --board cyc1000 --write-flash --verify --offset "$bios_offset" \
	--file-type bin "$bios"
openFPGALoader --board cyc1000 --write-flash --verify --offset "$zephyr_offset" \
	--file-type bin "$zephyr_image"
exec openFPGALoader --board cyc1000 "$gateware"
