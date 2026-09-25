# SPI flash burst – stav experimentu

Úkol byl 24. září 2026 pozastaven. Zdrojové změny experimentu byly následně
vráceny; tento soubor je záměrně jediný zachovaný výstup.

## Výchozí stav

- Deska: CYC1000, Cyclone 10 LP, flash Winbond W25Q16 (16 Mbit / 2 MiB).
- Flash obsluhuje Intel ASMI II hard IP. Po konfiguraci FPGA jsou konfigurační
  piny dostupné pouze přes tento hard block.
- Použitý read příkaz je `0x0b` (fast read), x1, DCLK 50 MHz, jedna dummy byte.
- BIOS je XIP na `0x20100000`, fyzicky ve flash od `0x00100000`.
- Zephyr FBI začíná na `0x20120000`, fyzicky ve flash od `0x00120000`, a kopíruje
  se do SDRAM. BIOS se do SDRAM nekopíruje.
- Testovaný FBI měl 339 644 B včetně 8B hlavičky; payload měl 339 636 B a CRC
  `0x6ddbd941`.

Teoretické limity při 50MHz x1 jsou:

| režim | přenesená data | režie 0x0b + adresa + dummy | ideální propustnost |
|---|---:|---:|---:|
| 1 slovo | 32 bitů | 40 bitů | 2,78 MB/s |
| burst 4 slov | 128 bitů | 40 bitů | 4,76 MB/s |
| burst 8 slov | 256 bitů | 40 bitů | 5,41 MB/s |

Hrubý limit linky bez režie je 6,25 MB/s. Skutečnost je nižší kvůli Avalon a
Wishbone handshaku, běhu BIOSu přímo z flash a střídání instrukčních a datových
přístupů.

## Co bylo implementováno a vyzkoušeno

Experimentální `ASMIFlashXIP` dostal 32B line buffer a při missu poslal do ASMI
jediný Avalon read s `burstcount=8`. Adresa byla zarovnána na osm 32bitových
slov. Následující Wishbone čtení měla být obsloužena z bufferu.

Důležité dílčí závěry:

1. `avl_mem_burstcount` má v Intel IP šířku 7 bitů. Prosté přiřazení Python
   hodnoty 8 vygenerovalo `4'd8`; Quartus hlásil nesprávné rozšíření portu a
   hardware se zastavil. Konstanta musí mít explicitně sedm bitů, například
   `Constant(BURST_WORDS, 7)`, nebo se musí použít 7bitový registrovaný signál.
2. Přímé ACK instrukčního Wishbone už během příchodu Avalon dat nebylo
   kompatibilní s refill sekvencí VexRiscv a CPU nevydal ani první UART znak.
3. Ani čekání na naplnění celé řádky a následné ACK podle aktuální Wishbone
   adresy nebylo pro instrukční refill spolehlivé.
4. CTI se přes LiteX arbiter skutečně propaguje. Instrukční refill používá
   `010`, poslední beat `111`; klasické datové čtení používá `000`.
5. Rozdělení na jednslovná čtení instrukcí a burst dat stále selhalo před UART,
   protože časný start BIOSu také čte data z vlastní XIP oblasti.
6. Omezení burstu pouze na Zephyr oblast od `0x20120000` obnovilo spolehlivý
   start BIOSu. Dlouhé čtení FBI ale dalo chybné CRC:
   `expected 6ddbd941, got acce991d`.
7. Prvních 128 B burst oblasti přečtených přes JTAGBone přesně odpovídalo FBI.
   Chyba se tedy objevuje až při delším sekvenčním čtení nebo při prokládání
   datových přístupů s instrukčními fetchi.
8. BIOS benchmark doběhl s hodnotou 3,0 MiB/s, ale starší nahraný BIOS měřil
   256 KiB od `0x20100000`: první polovina byla single a druhá burst. Toto číslo
   není čistá rychlost burstu a nesmí se používat jako finální výsledek.
9. Varianta se čtyřslovným burstem prošla kompletním Quartus buildem, ale před
   pozastavením už nebyla nahrána ani hardwarově ověřena.

Referenční SDRAM benchmark během bootu byl 14,3 MiB/s write a 24,3 MiB/s read,
takže po opravě flash cesty nebude kopírování limitováno SDRAM.

Quartus sestavení osmislovné varianty prošlo bez timing chyb; naměřený nejhorší
setup slack byl přibližně +4,38 ns a hold slack +0,383 ns. Spotřeba byla zhruba
8 133 LE (33 %), 4 629 registrů (18 %) a 220 864 RAM bitů (36 %).

## Instrumentace použitá při experimentu

- Lokální wrapper BIOS `boot.c` obalil `memcpy` a měl tisknout počet bytů, čas v
  mikrosekundách a KiB/s při kopii flash payloadu do SDRAM.
- BIOS příkaz `flash_speed` používal `memspeed()` nad mapovanou flash.
- Tyto soubory a Makefile změny byly při pozastavení odstraněny. Při pokračování
  je vhodné instrumentaci obnovit, ale benchmarkovat výhradně oblast od
  `0x20120000`.

## Doporučené pokračování

Nejdřív vytvořit malou simulaci adaptéru s prokládanými Wishbone instrukčními a
datovými požadavky a Avalon modelem, který vrací 4/8 beatů s mezerami. Kontrolovat
každé ACK, adresu a pořadí slov. Na hardware přidat čítače přijatých beatů,
line-missů a protokolových chyb nebo SignalTap.

Nejbezpečnější produkční varianta je samostatný boot-copy engine: CPU mu předá
zdroj ve flash, cíl v SDRAM a délku; engine provádí Avalon bursty a zapisuje do
SDRAM, zatímco CPU pouze čeká na dokončení. Tím se odstraní problematické
sdílení jednořádkového cache mezi instrukčním a datovým Wishbone provozem.

