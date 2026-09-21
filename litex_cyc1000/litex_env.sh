#!/usr/bin/env bash

# Use the repositories pinned as Git submodules for all LiteX-related Python
# imports.  The virtual environment supplies only the interpreter and external
# Python dependencies; copies under .venv/site-packages must not shadow these
# sources.
CYC10LP_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

export PYTHON="$CYC10LP_ROOT/.venv/bin/python"

CYC10LP_REQUIRED_SOURCES=(
    third_party/migen/migen/__init__.py
    third_party/litex/litex/__init__.py
    third_party/litex-boards/litex_boards/__init__.py
    third_party/liteeth/liteeth/__init__.py
    third_party/litedram/litedram/__init__.py
    third_party/litevideo/litevideo/__init__.py
    third_party/pythondata-cpu-vexriscv/pythondata_cpu_vexriscv/__init__.py
    third_party/pythondata-software-compiler_rt/pythondata_software_compiler_rt/__init__.py
    third_party/pythondata-software-picolibc/pythondata_software_picolibc/__init__.py
)

for CYC10LP_SOURCE in "${CYC10LP_REQUIRED_SOURCES[@]}"; do
    if [[ ! -f "$CYC10LP_ROOT/$CYC10LP_SOURCE" ]]; then
        echo "Missing pinned dependency: $CYC10LP_SOURCE" >&2
        echo "Run: git submodule update --init --recursive" >&2
        return 1
    fi
done
unset CYC10LP_SOURCE CYC10LP_REQUIRED_SOURCES

CYC10LP_PINNED_PYTHONPATH="$CYC10LP_ROOT/third_party/migen"
CYC10LP_PINNED_PYTHONPATH+=":$CYC10LP_ROOT/third_party/litex"
CYC10LP_PINNED_PYTHONPATH+=":$CYC10LP_ROOT/third_party/litex-boards"
CYC10LP_PINNED_PYTHONPATH+=":$CYC10LP_ROOT/third_party/liteeth"
CYC10LP_PINNED_PYTHONPATH+=":$CYC10LP_ROOT/third_party/litedram"
CYC10LP_PINNED_PYTHONPATH+=":$CYC10LP_ROOT/third_party/litevideo"
CYC10LP_PINNED_PYTHONPATH+=":$CYC10LP_ROOT/third_party/pythondata-cpu-vexriscv"
CYC10LP_PINNED_PYTHONPATH+=":$CYC10LP_ROOT/third_party/pythondata-software-compiler_rt"
CYC10LP_PINNED_PYTHONPATH+=":$CYC10LP_ROOT/third_party/pythondata-software-picolibc"

export PYTHONPATH="$CYC10LP_PINNED_PYTHONPATH${PYTHONPATH:+:$PYTHONPATH}"
