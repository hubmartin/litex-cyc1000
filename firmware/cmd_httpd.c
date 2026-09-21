/*
 * BIOS shell command: httpd
 *
 * Registers "httpd_start" and "httpd_stop" commands in the LiteX BIOS shell.
 */

#include <stdio.h>
#include <stdlib.h>

#include <generated/csr.h>

#include <command.h>

#include "httpd.h"

/**
 * Command: httpd_start
 */
static void httpd_start_handler(int nb_params, char **params)
{
	(void)nb_params;
	(void)params;
	httpd_start();
}

define_command(httpd_start, httpd_start_handler, "Start HTTP server on port 80", LITEETH_CMDS);

/**
 * Command: httpd_stop
 */
static void httpd_stop_handler(int nb_params, char **params)
{
	(void)nb_params;
	(void)params;
	httpd_stop();
}

define_command(httpd_stop, httpd_stop_handler, "Stop HTTP server", LITEETH_CMDS);
