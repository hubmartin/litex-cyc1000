# CYC1000 + Waveshare LAN8720: uzavřený záznam oživování

Aktualizováno: 2026-09-20

Stav: **vyřešeno — 100BASE-TX full duplex, ping i Etherbone fungují**

## Cíl

LiteX/LiteEth RMII Ethernet na Trenz CYC1000 s Waveshare **LAN8720 ETH Board**. Aktuální bitstream se nahrává pouze do FPGA SRAM pomocí `./load.sh`.

## Aktuální projekt a build

Adresář projektu: `/home/martin/dev/ai/Cyclone10LP/litex_cyc1000`

```sh
./build.sh
./load.sh
./console.sh
```

`build.sh` vytváří LiteEth Etherbone konfiguraci:

- hardwarový ARP/IP/ICMP echo responder na `192.168.1.50`;
- Etherbone UDP port `1234`;
- LiteX UART na `/dev/ttyUSB1`, 115200 Bd;
- SDRAM zůstává aktivní;
- CPU je `VexRiscv lite`, SDRAM L2 cache je vypnutá kvůli kapacitě M9K.

Hostitelský počítač: `enp4s0 = 192.168.1.216/24`.

## Zapojení použité v gateware

| LAN8720 | CYC1000 | FPGA pin | LiteEth |
|---|---|---|---|
| TXD0 | PIO_01 | F13 | `tx_data[0]` |
| RXD1 | PIO_02 | F15 | `rx_data[1]` |
| CRS_DV | PIO_03 | F16 | `crs_dv` |
| MDC | PIO_04 | D16 | `mdc` |
| TX_EN | PIO_05 | D15 | `tx_en` |
| RXD0 | PIO_06 | C15 | `rx_data[0]` |
| nINT / REFCLKO | PIO_07 | B16 | `ref_clk`, PHY → FPGA, 50 MHz |
| MDIO | PIO_08 | C16 | `mdio` |
| TXD1 | samostatný vodič | N2 | `tx_data[1]` |

Modul je fyzicky otočený o 180°, aby se napájení a zem potkaly s PMODem.

`F16` je také volitelný konfigurační pin `nCEO`. `soc.py` proto nastavuje Quartus volbu:

```tcl
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "Use as regular IO"
```

## Konečný ověřený stav

- UniFi switch hlásí `FE`, full duplex, tedy 100BASE-TX full duplex.
- RXD0, RXD1 a CRS_DV jsou aktivní a FPGA přijímá platné rámce.
- TX_EN, TXD0 a TXD1 vysílají odpovědi.
- Test `ping -I enp4s0 -c 100 192.168.1.50` skončil 100/100, 0 % packet loss.
- RTT min/avg/max/mdev bylo `0.126/0.170/0.286/0.025 ms`.
- Etherbone na UDP portu 1234 přečetl identifikátor SoC i diagnostická CSR.
- UART není pro hardwarový ARP/IP/ICMP/UDP/Etherbone datový směr potřeba.

Ověřený Etherbone identifikátor:

```text
LiteX SoC on CYC1000 2026-09-19 23:46:52
```

Příklad vzdáleně přečtených čítačů:

```text
0xf0002800 : 0x28b9e625 main_eth_refclk_cycles
0xf0002804 : 0x000f15e5 main_eth_rx_bytes
0xf0002808 : 0x0001c0f0 main_eth_tx_bytes
0xf000280c : 0x003d6634 main_eth_crs_cycles
0xf0002810 : 0x001ea1f0 main_eth_rx_pin_cycles
```

## MDIO a PHY

- LAN8720 je na MDIO adrese **1**.
- `mdio_read 1 2` vrací `0x0007`: MDIO/MDC komunikace funguje.
- Po fyzickém odpojení a opětovném zapojení RJ45 proběhla autonegociace správně.
- Starý diagnostický příkaz `mdio_write 1 0 0x0000` se již nemá používat: vynutil by 10 Mb/s half duplex a zrušil funkční autonegociaci.

### REFCLKO

- `nINT/REFCLKO` na `PIO_07/B16` je v gateware vyveden jako RMII 50MHz clock.
- Osciloskop potvrzuje 50 MHz.
- Diagnostické CSR čítadlo ve FPGA také potvrdilo běžící clock.

## Původní symptom a jeho uzavření

Po vynucení 10 Mb/s half duplex bylo z hostitele posláno 10 pingů na `192.168.1.50`.

- Ping: 100% packet loss, ARP soused zůstává `INCOMPLETE`.
- Čítač LiteEth RX bajtů: `0`.
- Čítač LiteEth TX bajtů: `0`.
- Hrubý čítač přímo na `CRS_DV/F16`: nenulový (`0x00028231`), tedy PHY oznamuje příchod rámců.
- Hrubý čítač přímo na `RXD[1:0]`: `0` — FPGA během testu nikdy nevidělo nenulový dvoubitový symbol.

Tehdejší měření lokalizovalo problém do RX datové cesty. Kontrolované spoje byly:

```text
LAN8720 P2.9  RXD1  → CYC1000 PIO_02 / F15
LAN8720 P2.10 RXD0  → CYC1000 PIO_06 / C15
```

Po novém flashnutí a reconnectu RJ45 začal čítač `RXD[1:0] != 0` růst:

```text
0x00079efa
0x0007a0d2
0x0007a6f6
```

Saleae současně ukázal přijatý rámec na `CRS_DV/RXD[1:0]` a následnou odpověď na `TX_EN/TXD[1:0]`. Odpověď na ping a funkční Etherbone definitivně potvrzují celou obousměrnou cestu.

## Diagnostická CSR

| Adresa | Význam |
|---|---|
| `0xf0002800` | čítač REFCLKO |
| `0xf0002804` | LiteEth RX bajty |
| `0xf0002808` | LiteEth TX bajty |
| `0xf000280c` | cykly s `CRS_DV=1` |
| `0xf0002810` | cykly s `RXD[1:0] != 0` |

Přímé čtení z UART BIOSu:

```text
litex> mem_read 0xf0002804 4
litex> mem_read 0xf0002810 4
```

Přes Etherbone z hostitele:

```sh
../.venv/bin/python -m litex.tools.litex_server --udp --udp-ip 192.168.1.50
../.venv/bin/python -m litex.tools.litex_client --csr-csv build/csr.csv --regs --filter main_eth
```

`litex_server` musí běžet v samostatném terminálu. Etherbone zpřístupňuje Wishbone CSR a paměť, neposkytuje BIOS shell. Nemá autentizaci ani šifrování, proto patří pouze do důvěryhodné sítě.
