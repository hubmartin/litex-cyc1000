# LiteX on Trenz CYC1000

LiteX SoC for the Trenz CYC1000 (Cyclone 10 LP) with a 50 MHz VexRiscv CPU,
LiteX BIOS and a Waveshare LAN8720 RMII Ethernet module.

## Current default build

`build.sh` creates the verified application-Ethernet variant:

- static address `192.168.1.241`;
- CPU-driven LiteEth MAC and BIOS network stack;
- ARP and ICMP echo replies (ping);
- 2 RX slots and 1 TX slot;
- VexRiscv `minimal` and 8 KiB integrated main RAM;
- UART at 115200 Bd and JTAGBone for local Wishbone diagnostics;
- TFTP netboot and the LED chaser disabled.

This bitstream does **not** contain Etherbone, TCP, HTTP, SSH or an Ethernet
shell. JTAGBone provides CSR/memory access through the USB/JTAG cable, not over
Ethernet. LiteEth's software UDP support is linked into the BIOS and can be
used by a future application; no general UDP service is currently listening.

The target still accepts `--with-etherbone` for a separate hardware Etherbone
build, but `--with-ethernet` and `--with-etherbone` are deliberately mutually
exclusive.

## Ethernet wiring

The LAN8720 module is rotated by 180 degrees on J6 so its power pins align with
the PMOD 3.3 V and GND pins. TXD1 uses a separate connection to FPGA pin N2.

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

`PIO_03/F16` is also the optional Cyclone 10 LP `nCEO` pin. The build reserves
it as regular user I/O after configuration so it can carry `CRS_DV`.

## Build, load and flash

```sh
./build.sh       # build gateware and BIOS
./load.sh        # load SRAM; lost after power-off
./flash.sh       # explicitly program configuration flash
./console.sh     # /dev/ttyUSB1, 115200 Bd
```

The Python-based build and console scripts source `litex_env.sh`. The virtual
environment supplies the Python interpreter and external dependencies, while
LiteX, LiteEth, LiteDRAM, Migen, LiteX-Boards, LiteVideo and the Python data
packages are imported directly from the commits pinned in `../third_party/`.
Copies in `.venv/site-packages` cannot override them.

If the link does not recover after loading or flashing, physically reconnect
RJ45 to force link-down/link-up and autonegotiation. The verified link is
100BASE-TX full duplex; a reconnect is not normally required by the final
image.

Test the application stack from a host on the same subnet:

```sh
ping -c 100 192.168.1.241
ping -c 100 -s 1472 192.168.1.241
```

The final build passed 300/300 ordinary pings and 100/100 full-MTU pings. Five
simultaneous high-rate ping streams can overrun the small polling BIOS stack;
this is a software throughput limit rather than an RMII link error.

## JTAGBone diagnostics

Start the local bridge using the included OpenOCD configuration:

```sh
source ./litex_env.sh
"$PYTHON" -m litex.tools.litex_server \
  --jtag --jtag-config openocd_cyc1000.cfg --jtag-chain 1 --bind-port 1235
```

Then connect one client at a time:

```sh
"$PYTHON" -m litex.tools.litex_client \
  --host localhost --port 1235 --csr-csv build/csr.csv --ident
```

The JTAG backend is a single serial transport. Concurrent clients can race and
timeout; use `--strict-timeout` when a diagnostic must not silently substitute
zeroes for a timed-out read.

## Important TX-slot alignment

Keep `nrxslots=2` with the current LiteEth version. With `1 RX + 1 TX`, LiteX
places TX at `0x80000800`, but LiteEth's single-slot Wishbone decoder rejects
that address because its slot-select bit is one. The transaction never receives
an ACK and the BIOS cannot fill its TX buffer. Two RX slots align TX at
`0x80001000`, which is acknowledged correctly.

Current memory map:

```text
ethmac_rx  0x80000000  4096 bytes
ethmac_tx  0x80001000  2048 bytes
```

## FPGA utilization

Quartus 25.1 Standard, final application-Ethernet build:

| Resource | Used | Available | Utilization |
| --- | ---: | ---: | ---: |
| Logic elements | 23,545 | 24,624 | 96% |
| LABs | 1,537 | 1,539 | 100% (2 free) |
| Registers | 18,386 | 25,304 | 73% |
| Block-memory bits | 456,544 | 608,256 | 75% |

The resolved bring-up history and measurements are in
[`ETH_TROUBLESHOOTING.md`](ETH_TROUBLESHOOTING.md).

## Minimal non-Ethernet diagnostic variant

`build_minimal.sh` builds a CPU/UART-only image and `load_minimal.sh` loads it
into SRAM. It remains useful for diagnostics independent of Ethernet.
