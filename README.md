# Cyclone 10 LP / CYC1000 projects

- [LED chaser](cyc1000_blinky/README.md)
- [LiteX SoC](litex_cyc1000/README.md) — verified LAN8720 application Ethernet
  at `192.168.1.241`, with UART and JTAGBone diagnostics

## Git dependencies

The repositories in `third_party/` are Git submodules pinned to the exact
commits used when this project was initialized. Clone with:

```sh
git clone --recurse-submodules <repository-url>
```

For an existing checkout, restore the pinned dependencies with:

```sh
git submodule update --init --recursive
```

Build outputs, the local `.venv/` Python environment and downloaded `.tools/`
are excluded from Git. The virtual environment provides the interpreter and
external dependencies; project scripts force all LiteX-related imports to the
commits pinned in `third_party/`. The build scripts currently use a local
Quartus installation; see each project's README and scripts for details.
