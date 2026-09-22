# BIOS overlay: retain the upstream build while adding local application code.
# `override` prevents generated variables.mak from redirecting BIOS_DIRECTORY
# back to this overlay when the upstream Makefile includes it a second time.
FIRMWARE_DIRECTORY := $(abspath $(dir $(firstword $(MAKEFILE_LIST)))/..)
include ../include/generated/variables.mak
override BIOS_DIRECTORY := $(SOC_DIRECTORY)/software/bios
include $(BIOS_DIRECTORY)/Makefile

VPATH += $(FIRMWARE_DIRECTORY)
OBJECTS += user_firmware.o
bios.elf: user_firmware.o
