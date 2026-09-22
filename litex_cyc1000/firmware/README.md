# CYC1000 user firmware

This directory holds application code independently of the LiteX submodules.
It is compiled and linked **into the resident `bios.bin`**. The complete BIOS
and its user extension execute in place (XIP) from SPI flash.

Build it after building the SoC once:

```sh
./build.sh             # rebuilds build/software/bios/bios.bin
../flash.sh             # writes gateware and the complete XIP BIOS to flash
```

After reset, type `main` in the normal BIOS UART shell. The test command runs
a software-controlled LED sweep, returns, and the BIOS prompt remains active.
The `main` command is registered from `main.c` through the BIOS command table;
there is no separate RAM image or serial loader.
