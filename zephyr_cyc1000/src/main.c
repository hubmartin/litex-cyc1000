/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/kernel.h>
#include <zephyr/input/input.h>
#include <zephyr/logging/log.h>
#include <zephyr/net/mqtt.h>
#include <zephyr/net/socket.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/printk.h>
#include <zephyr/version.h>

#include <errno.h>
#include <string.h>

LOG_MODULE_REGISTER(cyc1000, LOG_LEVEL_INF);

#define HTTP_PORT 80
#define MQTT_PORT 1883
#define MQTT_BROKER_ADDR "192.168.1.112" /* nasbuntu.home */
#define MQTT_TOPIC "cyc1000/test"

#define HTTP_STACK_SIZE 1536
#define MQTT_STACK_SIZE 2048

static uint8_t mqtt_rx_buffer[256];
static uint8_t mqtt_tx_buffer[256];
static struct sockaddr_storage mqtt_broker;
static bool mqtt_connected;

static const char http_response[] =
	"HTTP/1.1 200 OK\r\n"
	"Content-Type: text/html; charset=utf-8\r\n"
	"Connection: close\r\n"
	"\r\n"
	"<!doctype html><html><head><title>CYC1000 Zephyr</title></head>"
	"<body><h1>CYC1000 Zephyr</h1>"
	"<p>LiteEth, UART shell, HTTP and MQTT are active.</p>"
	"</body></html>\n";

static void http_server(void *p1, void *p2, void *p3)
{
	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);
	struct sockaddr_in addr = {
		.sin_family = AF_INET,
		.sin_port = htons(HTTP_PORT),
		.sin_addr.s_addr = htonl(INADDR_ANY),
	};
	int server;

	server = zsock_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
	if (server < 0) {
		LOG_ERR("HTTP socket failed: %d", errno);
		return;
	}

	if (zsock_bind(server, (struct sockaddr *)&addr, sizeof(addr)) < 0 ||
	    zsock_listen(server, 1) < 0) {
		LOG_ERR("HTTP listen failed: %d", errno);
		zsock_close(server);
		return;
	}

	LOG_INF("HTTP server listening on port %d", HTTP_PORT);
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

static void mqtt_event_handler(struct mqtt_client *client,
			       const struct mqtt_evt *evt)
{
	ARG_UNUSED(client);

	if (evt->type == MQTT_EVT_CONNACK) {
		if (evt->result == 0) {
			mqtt_connected = true;
			LOG_INF("MQTT connected to nasbuntu.home");
		} else {
			LOG_ERR("MQTT CONNACK failed: %d", evt->result);
		}
	} else if (evt->type == MQTT_EVT_DISCONNECT) {
		mqtt_connected = false;
		LOG_WRN("MQTT disconnected: %d", evt->result);
	}
}

static void mqtt_broker_init(void)
{
	struct sockaddr_in *broker = (struct sockaddr_in *)&mqtt_broker;

	memset(&mqtt_broker, 0, sizeof(mqtt_broker));
	broker->sin_family = AF_INET;
	broker->sin_port = htons(MQTT_PORT);
	(void)zsock_inet_pton(AF_INET, MQTT_BROKER_ADDR, &broker->sin_addr);
}

static int mqtt_connect_to_broker(struct mqtt_client *client)
{
	struct zsock_pollfd poll_fd;
	int rc;

	mqtt_client_init(client);
	mqtt_broker_init();
	client->broker = (struct sockaddr *)&mqtt_broker;
	client->evt_cb = mqtt_event_handler;
	client->client_id.utf8 = (uint8_t *)"cyc1000-zephyr";
	client->client_id.size = strlen((char *)client->client_id.utf8);
	client->protocol_version = MQTT_VERSION_3_1_1;
	client->rx_buf = mqtt_rx_buffer;
	client->rx_buf_size = sizeof(mqtt_rx_buffer);
	client->tx_buf = mqtt_tx_buffer;
	client->tx_buf_size = sizeof(mqtt_tx_buffer);
	client->transport.type = MQTT_TRANSPORT_NON_SECURE;

	mqtt_connected = false;
	rc = mqtt_connect(client);
	if (rc != 0) {
		return rc;
	}

	poll_fd.fd = client->transport.tcp.sock;
	poll_fd.events = ZSOCK_POLLIN;
	if (zsock_poll(&poll_fd, 1, 3000) > 0) {
		rc = mqtt_input(client);
	}

	return mqtt_connected ? 0 : (rc != 0 ? rc : -ETIMEDOUT);
}

static int mqtt_publish_test(struct mqtt_client *client, uint32_t sequence)
{
	char payload[64];
	struct mqtt_publish_param param = { 0 };

	snprintk(payload, sizeof(payload), "CYC1000 Zephyr test message %u", sequence);
	param.message.topic.qos = MQTT_QOS_0_AT_MOST_ONCE;
	param.message.topic.topic.utf8 = (uint8_t *)MQTT_TOPIC;
	param.message.topic.topic.size = strlen(MQTT_TOPIC);
	param.message.payload.data = (uint8_t *)payload;
	param.message.payload.len = strlen(payload);
	param.message_id = sequence;
	return mqtt_publish(client, &param);
}

static void mqtt_publisher(void *p1, void *p2, void *p3)
{
	struct mqtt_client client;
	uint32_t sequence = 1;

	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);

	k_sleep(K_SECONDS(5));
	while (true) {
		int rc = mqtt_connect_to_broker(&client);

		if (rc != 0) {
			LOG_WRN("MQTT connect to %s:%d failed: %d", MQTT_BROKER_ADDR,
				MQTT_PORT, rc);
			k_sleep(K_SECONDS(5));
			continue;
		}

		rc = mqtt_publish_test(&client, sequence++);
		if (rc == 0) {
			LOG_INF("MQTT published to " MQTT_TOPIC);
		} else {
			LOG_WRN("MQTT publish failed: %d", rc);
		}

		(void)mqtt_disconnect(&client);
		k_sleep(K_SECONDS(10));
	}
}

K_THREAD_DEFINE(http_server_thread, HTTP_STACK_SIZE, http_server, NULL, NULL,
		NULL, 7, 0, 0);
K_THREAD_DEFINE(mqtt_publisher_thread, MQTT_STACK_SIZE, mqtt_publisher, NULL,
		NULL, NULL, 7, 0, 0);

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
	shell_print(sh, "UART shell, LiteEth, HTTP and MQTT are active.");
	return 0;
}

SHELL_CMD_REGISTER(cyc1000_info, NULL, "Show CYC1000 Zephyr configuration", cmd_info);

int main(void)
{
	printk("\nCYC1000 Zephyr started. Type 'help' for the UART shell.\n");
	LOG_INF("UART logging, button input, LiteEth, HTTP and MQTT are active");
	return 0;
}
