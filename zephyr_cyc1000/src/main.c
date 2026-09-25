/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/kernel.h>
#include <zephyr/input/input.h>
#include <zephyr/fs/fs.h>
#include <zephyr/logging/log.h>
#include <zephyr/net/socket.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/printk.h>
#include <zephyr/version.h>

#include <errno.h>

LOG_MODULE_REGISTER(cyc1000, LOG_LEVEL_INF);

#define HTTP_PORT 80

#define LFS_NODE DT_NODELABEL(lfs_storage)
FS_FSTAB_DECLARE_ENTRY(LFS_NODE);

#define HTTP_STACK_SIZE 1536

static const char http_response[] =
	"HTTP/1.1 200 OK\r\n"
	"Content-Type: text/html; charset=utf-8\r\n"
	"Connection: close\r\n"
	"\r\n"
	"<!doctype html><html><head><title>CYC1000 Zephyr</title></head>"
	"<body><h1>CYC1000 Zephyr</h1>"
	"<p>LiteEth, UART shell and HTTP are active.</p>"
	"</body></html>\n";

static void http_server(void *p1, void *p2, void *p3)
{
	int family = POINTER_TO_INT(p1);
	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);
	struct sockaddr_in addr4 = {
		.sin_family = AF_INET,
		.sin_port = htons(HTTP_PORT),
		.sin_addr.s_addr = htonl(INADDR_ANY),
	};
	struct sockaddr_in6 addr6 = {
		.sin6_family = AF_INET6,
		.sin6_port = htons(HTTP_PORT),
		.sin6_addr = IN6ADDR_ANY_INIT,
	};
	const struct sockaddr *addr = family == AF_INET6 ?
		(const struct sockaddr *)&addr6 : (const struct sockaddr *)&addr4;
	socklen_t addr_len = family == AF_INET6 ? sizeof(addr6) : sizeof(addr4);
	int server;

	server = zsock_socket(family, SOCK_STREAM, IPPROTO_TCP);
	if (server < 0) {
		LOG_ERR("HTTP socket failed: %d", errno);
		return;
	}

	if (zsock_bind(server, addr, addr_len) < 0 ||
	    zsock_listen(server, 1) < 0) {
		LOG_ERR("HTTP/%s listen failed: %d",
			family == AF_INET6 ? "IPv6" : "IPv4", errno);
		zsock_close(server);
		return;
	}

	LOG_INF("HTTP/%s server listening on port %d",
		family == AF_INET6 ? "IPv6" : "IPv4", HTTP_PORT);
	while (true) {
		char request[128];
		int client = zsock_accept(server, NULL, NULL);

		if (client < 0) {
			LOG_ERR("HTTP accept failed: %d", errno);
			continue;
		}

		(void)zsock_recv(client, request, sizeof(request), 0);
		(void)zsock_send(client, http_response, sizeof(http_response) - 1, 0);
		zsock_close(client);
	}
}

K_THREAD_DEFINE(http_server_v4_thread, HTTP_STACK_SIZE, http_server,
		INT_TO_POINTER(AF_INET), NULL, NULL, 7, 0, 0);
K_THREAD_DEFINE(http_server_v6_thread, HTTP_STACK_SIZE, http_server,
		INT_TO_POINTER(AF_INET6), NULL, NULL, 7, 0, 0);

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
	shell_print(sh, "UART shell, LiteEth and HTTP are active.");
	return 0;
}

SHELL_CMD_REGISTER(cyc1000_info, NULL, "Show CYC1000 Zephyr configuration", cmd_info);

int main(void)
{
	int lfs_rc = fs_mount(&FS_FSTAB_ENTRY(LFS_NODE));
	if (lfs_rc && lfs_rc != -EBUSY) {
		LOG_ERR("LittleFS mount failed: %d", lfs_rc);
	} else {
		LOG_INF("LittleFS mounted at /lfs");
	}
	printk("\nCYC1000 Zephyr started. Type 'help' for the UART shell.\n");
	LOG_INF("UART logging, button input, LiteEth and HTTP are active");
	return 0;
}
