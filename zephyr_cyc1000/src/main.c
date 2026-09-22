/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/printk.h>
#include <zephyr/version.h>

static int cmd_info(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	shell_print(sh, "CYC1000: Zephyr %s", KERNEL_VERSION_STRING);
	shell_print(sh, "UART shell is active; Ethernet is reserved for LiteX Etherbone.");
	return 0;
}

SHELL_CMD_REGISTER(cyc1000_info, NULL, "Show CYC1000 Zephyr configuration", cmd_info);

int main(void)
{
	printk("\nCYC1000 Zephyr started. Type 'help' for the UART shell.\n");
	return 0;
}
