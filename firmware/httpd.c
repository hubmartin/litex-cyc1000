/*
 * Minimal HTTP server for LiteX / CYC1000
 *
 * Serves a single static status page on port 80.
 * Sits on top of the minimal TCP layer (tcp.c).
 */

#include <stdio.h>

#include <generated/csr.h>

#include "tcp.h"
#include "httpd.h"

/* ------------------------------------------------------------------ */
/* HTML page (kept very small — every byte counts in 128 KB ROM)       */
/* ------------------------------------------------------------------ */

static const char http_200[] =
	"HTTP/1.0 200 OK\r\n"
	"Content-Type: text/html\r\n"
	"Connection: close\r\n"
	"\r\n"
	"<!DOCTYPE html><html><head><title>CYC1000</title></head>"
	"<body><h1>CYC1000 LiteX SoC</h1>"
	"<p>HTTP server running on VexRiscv @ 50 MHz</p>"
	"</body></html>\r\n";

static const char http_404[] =
	"HTTP/1.0 404 Not Found\r\n"
	"Content-Type: text/html\r\n"
	"Connection: close\r\n"
	"\r\n"
	"<h1>404 Not Found</h1>\r\n";

/* ------------------------------------------------------------------ */
/* HTTP request handler (called from TCP on data arrival)              */
/* ------------------------------------------------------------------ */

static void httpd_rx(uint32_t src_ip, uint16_t src_port,
                     uint16_t dst_port, const void *data, uint16_t len)
{
	const char *req = (const char *)data;

	(void)src_ip;
	(void)src_port;
	(void)dst_port;

	/* Very minimal HTTP parsing: look for "GET /" */
	if (len >= 5 &&
	    req[0]=='G' && req[1]=='E' && req[2]=='T' && req[3]==' ' && req[4]=='/') {
		if (req[5] == ' ' || req[5] == 'H' || req[5] == '\r') {
			tcp_write(http_200, sizeof(http_200) - 1);
		} else {
			tcp_write(http_404, sizeof(http_404) - 1);
		}
	} else {
		tcp_write(http_404, sizeof(http_404) - 1);
	}

	tcp_close();
}

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */

void httpd_start(void)
{
	tcp_init();
	tcp_listen(80, httpd_rx);
	printf("HTTPD: listening on port 80\n");
}

void httpd_stop(void)
{
	tcp_listen(0, NULL);
	printf("HTTPD: stopped\n");
}
