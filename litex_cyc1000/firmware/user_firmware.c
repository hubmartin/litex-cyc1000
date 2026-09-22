#include <stdio.h>

#include <generated/csr.h>
#include <bios/command.h>
#include <system.h>

static void user_led_sweep(void)
{
	unsigned int led;

	/* A CSR write switches LedChaser from its gateware default to direct
	 * software control, making this a test of code built into the XIP BIOS. */
	for (led = 0; led < 8; led++) {
		leds_out_write(1u << led);
		busy_wait(100);
	}
	for (led = 7; led > 0; led--) {
		leds_out_write(1u << led);
		busy_wait(100);
	}
	leds_out_write(0);
}

static void user_main(int nb_params, char **params)
{
	(void)nb_params;
	(void)params;
	puts("Running user firmware compiled into the XIP BIOS...");
	user_led_sweep();
	puts("User firmware complete.");
}

define_command_args(main, user_main, "Run user firmware", "main", 0, 0, SYSTEM_CMDS);
