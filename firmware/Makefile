include ../include/generated/variables.mak
include $(SOC_DIRECTORY)/software/common.mak

CFLAGS += -I$(LIBFIRMWARE_DIRECTORY) -I$(BIOS_DIRECTORY)

OBJECTS = tcp.o httpd.o cmd_httpd.o

all: libfirmware.a

libfirmware.a: $(OBJECTS)
	$(AR) crs libfirmware.a $(OBJECTS)

# pull in dependency info for *existing* .o files
-include $(OBJECTS:.o=.d)

%.o: $(LIBFIRMWARE_DIRECTORY)/%.c
	$(compile)

.PHONY: all clean

clean:
	$(RM) $(OBJECTS) libfirmware.a .*~ *~
