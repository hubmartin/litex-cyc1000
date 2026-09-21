# CYC1000 + LAN8720: uzavřený záznam oživování

Aktualizováno: 2026-09-21

Stav: **vyřešeno — aplikační LiteEth MAC na `192.168.1.241` stabilně odpovídá na ping**

Dokument zůstává v repozitáři jako záznam skutečné příčiny a ověřeného řešení;
nejde už o otevřený problém.

## Konečná konfigurace

- LiteEth `--with-ethernet`, bez Etherbone;
- VexRiscv `minimal`, 8 KiB interní main RAM;
- 2 RX sloty, 1 TX slot;
- RX SRAM `0x80000000`, velikost 4096 B;
- TX SRAM `0x80001000`, velikost 2048 B;
- statická IPv4 adresa `192.168.1.241`;
- `NET_BOOT_DISABLE`, tedy bez automatického TFTP bootu;
- UART 115200 Bd a lokální JTAGBone pro diagnostiku;
- LED chaser vypnutý kvůli zaplnění FPGA.

## Ověřený výsledek

- UniFi: FE, full duplex (100BASE-TX full duplex).
- Saleae: aktivní `CRS_DV/RXD[1:0]` i `TX_EN/TXD[1:0]`.
- ARP request pro `192.168.1.241` byl v RX SRAM přijat bez CRC chyby.
- 20/20 počátečních pingů, průměrné RTT `0,404 ms`.
- 300/300 běžných pingů, průměrné RTT `0,390 ms`.
- 100/100 pingů s payloadem 1472 B, průměrné RTT `2,232 ms`.

Pět souběžných rychlých ping streamů způsobilo ztrátu 0–3,5 %. Jediný stream
při normální frekvenci neměl ztráty; limitem je jednoduchý polling BIOS stack,
nikoli fyzická linka.

## Regrese po lokální úpravě `libliteeth`

Pozdější experiment upravil `udp.c` a `udp.h` přímo v ignorované `.venv`.
Proto jej návrat Git repozitáře na poslední commit neodstranil. Rozšířený
`udp.h` vybíral strukturu Ethernet hlavičky podle `HW_PREAMBLE_CRC`, ale byl
načten dříve, než `udp.c` tento symbol odvodil z
`CSR_ETHMAC_PREAMBLE_CRC_ADDR`. Firmware pak očekával v MAC SRAM osm bajtů
preambule, kterou hardware správně odstranil.

Projev byl jednoznačný: RX sloty a eventy fungovaly, CRC chyby byly nulové,
BIOS měl správnou IP, ale ARP pole četl s posunem `+8` a TX SRAM zůstávala
prázdná. Projekt proto nyní nastavuje `PYTHONPATH` pomocí `litex_env.sh` na
připnuté submoduly v `third_party/`; pozměněná kopie v `.venv/site-packages`
se do buildu nepoužije. Opravený build s JTAGBone prošel 20/20 pingů bez
reconnectu RJ45.

## Skutečná příčina poslední TX závady

Při konfiguraci `nrxslots=1, ntxslots=1` vytvořil LiteX tuto mapu:

```text
RX  0x80000000
TX  0x80000800
```

LiteEth používá i pro jediný slot jeden adresní dekódovací bit. TX Wishbone
slave vyžadoval bit 9 word adresy nulový, ale základna `0x80000800` jej měla
jedničkový. Výsledek:

- platné ARP rámce se přijímaly a firmware je zpracoval;
- firmware nastavil délku TX rámce a spustil reader;
- zápis do TX SRAM nikdy nedostal Wishbone ACK;
- na Saleae se objevovaly TX pulzy, ale host nedostal platnou odpověď;
- rostl čítač bus errors a ping končil ztrátou.

Řešením je `nrxslots=2, ntxslots=1`. Dva RX sloty posunou TX na zarovnanou
adresu `0x80001000`, pro kterou dekodér ACK generuje. Po této změně ping začal
okamžitě fungovat.

## Pozor na JTAGBone diagnostiku

`litex_server --jtag` používá jediný sériový JTAG transport. Několik současných
nebo rychle po sobě spuštěných klientů může uvnitř serveru závodit. Standardní
`litex_client` navíc při read timeoutu bez `--strict-timeout` vrací nuly. První
domněnka, že TX SRAM obsahuje samé nuly, proto byla falešná; šlo o timeout bez
ACK na chybně dekódované adrese.

Pro spolehlivou diagnostiku:

```sh
source ./litex_env.sh
"$PYTHON" -m litex.tools.litex_server \
  --jtag --jtag-config openocd_cyc1000.cfg --jtag-chain 1 --bind-port 1235

"$PYTHON" -m litex.tools.litex_client \
  --host localhost --port 1235 --csr-csv build/csr.csv \
  --strict-timeout --ident
```

Používat jen jeden klient najednou. JTAGBone je Wishbone přístup přes USB/JTAG,
nikoli shell a nikoli služba dostupná z Ethernetu.

## Dříve vyřešená fyzická část

Před opravou TX mapy bylo ověřeno:

- LAN8720 na MDIO adrese 1, `mdio_read 1 2` vrací `0x0007`;
- `nINT/REFCLKO` dodává do FPGA 50 MHz;
- `F16` je v Quartusu uvolněn z funkce `nCEO` pro `CRS_DV`;
- po novém flashnutí a reconnectu RJ45 začaly růst RX čítače;
- vynucení `mdio_write 1 0 0x0000` je nevhodné, protože nastaví 10 Mb/s half
  duplex; správně se používá autonegociace.

## Zapojení

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

## Utilizace finálního bitstreamu

```text
Logic elements:     23 545 / 24 624  (96 %)
LABs:                1 537 / 1 539   (100 %, 2 volné)
Registers:          18 386 / 25 304  (73 %)
Block memory bits: 456 544 / 608 256 (75 %)
```

Časování 50MHz `sys_clk` i 50MHz RMII clocku vyhovuje. Quartus nadále hlásí
záporný setup slack na vstupní `clk12`; nejde o datovou RMII cestu.
