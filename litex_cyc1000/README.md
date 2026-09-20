# LiteX on Trenz CYC1000

Upstream LiteX target `trenz_cyc1000` with a VexRiscv CPU at 50 MHz, LiteX BIOS, 115200 Bd UART, W9864G6JT SDR SDRAM, eight LEDs, and the user button.
The LED chaser output is PWM-limited to 10/1024 = 0.98% duty cycle. Its `leds_pwm_width` and `leds_pwm_period` CSRs allow later adjustment.

## Ethernet: Waveshare LAN8720 ETH Board

`build.sh` builds the SDRAM-enabled SoC with LiteEth's hardware ARP/IP/ICMP/UDP Etherbone core and the LAN8720 RMII PHY. It responds to ICMP echo requests at `192.168.1.50` and exposes Etherbone on UDP port 1234. The complete network path has been verified at 100BASE-TX full duplex with 100/100 successful pings and working remote CSR reads. To fit the 10CL025, the build uses no SDRAM L2 cache and the VexRiscv `lite` CPU variant.

The default Etherbone data path is implemented in FPGA gateware and does not depend on the VexRiscv firmware. The alternate `--with-ethernet` target instead provides a CPU-accessible packet MAC for the LiteX BIOS software network stack (ARP/IPv4/ICMP/UDP, DHCP and TFTP netboot). It is mutually exclusive with `--with-etherbone` in this target. Neither configuration provides TCP, HTTP, SSH or a network BIOS shell.

The module is rotated by 180 degrees on J6 so its power pins align with the PMOD's 3.3 V and GND pins. This orientation has been checked against the Waveshare P2 schematic and CYC1000 J6 pinout. `nINT` is the LAN8720's multiplexed `nINT/REFCLKO` output and is the required 50 MHz RMII reference clock, not an interrupt in this configuration.

| CYC1000 J6 / FPGA pin | LAN8720 signal | LiteEth RMII signal |
| --- | --- | --- |
| PIO_01 / F13 | TXD0 | `tx_data[0]` |
| PIO_02 / F15 | RXD1 | `rx_data[1]` |
| PIO_03 / F16 | CRS_DV | `crs_dv` |
| PIO_04 / D16 | MDC | `mdc` |
| PIO_05 / D15 | TX_EN | `tx_en` |
| PIO_06 / C15 | RXD0 | `rx_data[0]` |
| PIO_07 / B16 | nINT / REFCLKO | `ref_clk` (50 MHz, PHY to FPGA) |
| PIO_08 / C16 | MDIO | `mdio` |
| separate FPGA pin N2 | TXD1 | `tx_data[1]` |

MDC and MDIO make the PHY management registers available through LiteX CSRs. The RMII data path needs the seven data/clock signals; MDIO is the two additional wires. Supply the module only from the PMOD's 3.3 V pins and keep the 50 MHz clock wire short.

`PIO_03/F16` is also Cyclone 10 LP's optional `nCEO` configuration output. The build deliberately sets Quartus `CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION` to `Use as regular IO`, so it is available as `CRS_DV` after configuration. Intel documents that `nCEO` can be used as user I/O in a single-device chain.

After `./load.sh`, use the UART console to verify the PHY without changing its configuration:

```text
litex> mdio_read 1 2
MDIO read @0x1:
0x02 0x0007
litex> mdio_dump 1 32
```

The LAN8720 is strapped to MDIO PHY address 1. Register 2 returning `0x0007` confirms that MDC, MDIO, module power, and the PHY are communicating.

With the default Etherbone build and a valid link, test the complete hardware network path from a host on the same subnet:

```sh
ping -I enp4s0 -c 100 192.168.1.50
```

The ping verifies ARP, IP, ICMP and both directions of the RMII data path. Do not force 10 Mb/s half duplex when normal autonegotiation reports 100 Mb/s full duplex.

To access the SoC Wishbone bus over Etherbone, run the bridge in one terminal:

```sh
../.venv/bin/python -m litex.tools.litex_server --udp --udp-ip 192.168.1.50
```

Then use a second terminal for remote CSR and memory access:

```sh
../.venv/bin/python -m litex.tools.litex_client --csr-csv build/csr.csv --ident
../.venv/bin/python -m litex.tools.litex_client --csr-csv build/csr.csv --regs --filter main_eth
```

Etherbone is an unauthenticated Wishbone-over-UDP bridge, not a remote shell. Only expose it on a trusted network.

The resolved bring-up history, measured results and diagnostic CSR addresses are recorded in [`ETH_TROUBLESHOOTING.md`](ETH_TROUBLESHOOTING.md).

## Build and load

```sh
./build.sh
./load.sh
./console.sh
```

`load.sh` writes the full SDRAM-enabled SoC to FPGA SRAM only. A power cycle restores the bitstream stored in configuration flash. `flash.sh` programs flash explicitly.

The board UART is `/dev/ttyUSB1`. `console.sh` starts a serial console at 115200 Bd. At the `litex>` prompt, use `help`, `ident`, `buttons`, `leds`, and `sdram_test`.

## Minimal diagnostic variant

`build_minimal.sh` builds a CPU/UART-only image with 8 KiB internal main RAM; `load_minimal.sh` loads it into SRAM. It is useful if external SDRAM is being diagnosed.
