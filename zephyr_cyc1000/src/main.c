/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/kernel.h>
#include <zephyr/input/input.h>
#include <zephyr/logging/log.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/printk.h>
#include <zephyr/version.h>

LOG_MODULE_REGISTER(cyc1000, LOG_LEVEL_INF);

static void log_1s_thread(void *unused1, void *unused2, void *unused3)
{
	ARG_UNUSED(unused1);
	ARG_UNUSED(unused2);
	ARG_UNUSED(unused3);

	while (true) {
		LOG_INF("1 s task heartbeat");
		k_sleep(K_SECONDS(1));
	}
}

static void log_2s_thread(void *unused1, void *unused2, void *unused3)
{
	ARG_UNUSED(unused1);
	ARG_UNUSED(unused2);
	ARG_UNUSED(unused3);

	while (true) {
		LOG_INF("2 s task heartbeat");
		k_sleep(K_SECONDS(2));
	}
}

K_THREAD_DEFINE(log_1s_thread_id, 768, log_1s_thread, NULL, NULL, NULL,
		5, 0, 0);
K_THREAD_DEFINE(log_2s_thread_id, 768, log_2s_thread, NULL, NULL, NULL,
		5, 0, 0);

static void button_event(struct input_event *evt, void *user_data)
{
	ARG_UNUSED(user_data);

	if (evt->type == INPUT_EV_KEY && evt->code == INPUT_KEY_0 && evt->value) {
		LOG_INF("CYC1000 button pressed");
	}
}

INPUT_CALLBACK_DEFINE(NULL, button_event, NULL);

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
	LOG_INF("UART logging is active; periodic tasks and button input are enabled");
	return 0;
}
