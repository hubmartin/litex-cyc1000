/* SPDX-License-Identifier: Apache-2.0 */
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/kernel.h>
#include <zephyr/fs/fs.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/sys_io.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>

#define FLASH_NODE DT_NODELABEL(asmi_flash)
#define FLASH_SIZE DT_REG_SIZE_BY_NAME(FLASH_NODE, memory)
#define FLASH_BASE DT_REG_ADDR_BY_NAME(FLASH_NODE, memory)
#define CTRL_BASE DT_REG_ADDR_BY_NAME(FLASH_NODE, control)
#define ERASE_SIZE DT_PROP(FLASH_NODE, erase_block_size)
#define FLASH_PHYSICAL_BASE 0x00100000u
#define ASMI_RD_STATUS 3u
#define ASMI_SUBSECTOR_ERASE 5u
#define ASMI_STATUS_WIP BIT(0)

static K_MUTEX_DEFINE(asmi_lock);
static const struct flash_parameters params = {
	.write_block_size = 1, .erase_value = 0xff,
};
static const struct flash_pages_layout layout = {
	.pages_count = FLASH_SIZE / ERASE_SIZE, .pages_size = ERASE_SIZE,
};

static bool range_ok(off_t offset, size_t len)
{
	return offset >= 0 && offset <= FLASH_SIZE && len <= FLASH_SIZE - offset;
}

static int wait_ready(void)
{
	for (int i = 0; i < 10000; i++) {
		if (!(sys_read32(CTRL_BASE + ASMI_RD_STATUS * 4) & ASMI_STATUS_WIP)) {
			return 0;
		}
		k_busy_wait(1000);
	}
	return -ETIMEDOUT;
}

static int asmi_read(const struct device *dev, off_t offset, void *data, size_t len)
{
	ARG_UNUSED(dev);
	if (!range_ok(offset, len)) return -EINVAL;
	memcpy(data, (const void *)(FLASH_BASE + offset), len);
	return 0;
}

static int asmi_write(const struct device *dev, off_t offset, const void *data, size_t len)
{
	ARG_UNUSED(dev);
	if (!range_ok(offset, len)) return -EINVAL;
	k_mutex_lock(&asmi_lock, K_FOREVER);
	int rc = 0;
	for (size_t i = 0; i < len && !rc; i++) {
		sys_write8(((const uint8_t *)data)[i], FLASH_BASE + offset + i);
		k_busy_wait(1000);
		rc = wait_ready();
	}
	k_mutex_unlock(&asmi_lock);
	return rc;
}

static int asmi_erase(const struct device *dev, off_t offset, size_t len)
{
	ARG_UNUSED(dev);
	if (!range_ok(offset, len) || offset % ERASE_SIZE || len % ERASE_SIZE) return -EINVAL;
	k_mutex_lock(&asmi_lock, K_FOREVER);
	int rc = 0;
	for (size_t i = 0; i < len && !rc; i += ERASE_SIZE) {
		sys_write32(FLASH_PHYSICAL_BASE + offset + i, CTRL_BASE + ASMI_SUBSECTOR_ERASE * 4);
		k_busy_wait(1000);
		rc = wait_ready();
	}
	k_mutex_unlock(&asmi_lock);
	return rc;
}

static const struct flash_parameters *asmi_parameters(const struct device *dev)
{ ARG_UNUSED(dev); return &params; }
static void asmi_layout(const struct device *dev, const struct flash_pages_layout **l, size_t *n)
{ ARG_UNUSED(dev); *l = &layout; *n = 1; }
static const struct flash_driver_api api = {
	.read = asmi_read, .write = asmi_write, .erase = asmi_erase,
	.get_parameters = asmi_parameters, .page_layout = asmi_layout,
};
DEVICE_DT_DEFINE(DT_PARENT(FLASH_NODE), NULL, NULL, NULL, NULL, POST_KERNEL,
		 CONFIG_KERNEL_INIT_PRIORITY_DEVICE, &api);

static int cmd_asmi_info(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	shell_print(sh, "ASMI XIP: logical 0x%08x..0x%08x (%u KiB)",
		    FLASH_BASE, FLASH_BASE + FLASH_SIZE - 1, FLASH_SIZE / 1024);
	shell_print(sh, "physical: 0x%06x..0x%06x; erase: %u bytes; write: 1 byte",
		    FLASH_PHYSICAL_BASE, FLASH_PHYSICAL_BASE + FLASH_SIZE - 1,
		    ERASE_SIZE);
	shell_print(sh, "LittleFS: physical 0x1c0000..0x1fffff (256 KiB, 64 blocks)");
	shell_print(sh, "ASMI status: %#x (%s)",
		    sys_read32(CTRL_BASE + ASMI_RD_STATUS * 4),
		    (sys_read32(CTRL_BASE + ASMI_RD_STATUS * 4) & ASMI_STATUS_WIP) ?
		    "busy" : "ready");
	return 0;
}

static int cmd_asmi_dump(const struct shell *sh, size_t argc, char **argv)
{
	uint8_t data[64];
	unsigned long offset = strtoul(argv[1], NULL, 0);
	size_t len = argc == 3 ? strtoul(argv[2], NULL, 0) : 16;

	if (len == 0 || len > sizeof(data) || !range_ok(offset, len)) {
		shell_error(sh, "offset must be within 0..0x%x; length 1..%u", FLASH_SIZE - 1,
			    (unsigned int)sizeof(data));
		return -EINVAL;
	}
	asmi_read(NULL, offset, data, len);
	shell_print(sh, "ASMI logical offset 0x%06lx (physical 0x%06lx):", offset,
		    FLASH_PHYSICAL_BASE + offset);
	shell_hexdump(sh, data, len);
	return 0;
}

static int cmd_asmi_stress(const struct shell *sh, size_t argc, char **argv)
{
	struct fs_file_t file;
	uint8_t expected[64];
	uint8_t actual[64];
	size_t total = argc == 2 ? strtoul(argv[1], NULL, 0) : 8192;
	size_t off;
	int rc;

	if (total == 0 || total > 32768) {
		shell_error(sh, "size must be 1..32768 bytes");
		return -EINVAL;
	}
	fs_file_t_init(&file);
	rc = fs_open(&file, "/lfs/asmi-stress.bin", FS_O_CREATE | FS_O_WRITE | FS_O_TRUNC);
	if (rc) {
		shell_error(sh, "open for write: %d", rc);
		return rc;
	}
	for (off = 0; off < total && !rc; off += sizeof(expected)) {
		size_t len = MIN(sizeof(expected), total - off);
		for (size_t i = 0; i < len; i++) {
			expected[i] = (uint8_t)((off + i) * 37u + 11u);
		}
		if (fs_write(&file, expected, len) != len) {
			rc = -EIO;
		}
	}
	fs_close(&file);
	if (rc) {
		shell_error(sh, "write failed at %u: %d", (unsigned int)off, rc);
		return rc;
	}
	fs_file_t_init(&file);
	rc = fs_open(&file, "/lfs/asmi-stress.bin", FS_O_READ);
	for (off = 0; off < total && !rc; off += sizeof(expected)) {
		size_t len = MIN(sizeof(expected), total - off);
		for (size_t i = 0; i < len; i++) {
			expected[i] = (uint8_t)((off + i) * 37u + 11u);
		}
		if (fs_read(&file, actual, len) != len || memcmp(expected, actual, len)) {
			rc = -EIO;
		}
	}
	fs_close(&file);
	if (rc) {
		shell_error(sh, "verify failed at %u: %d", (unsigned int)off, rc);
	} else {
		shell_print(sh, "LittleFS stress passed: %u bytes written and verified", (unsigned int)total);
	}
	return rc;
}

SHELL_STATIC_SUBCMD_SET_CREATE(asmi_cmds,
	SHELL_CMD(info, NULL, "Print ASMI/LittleFS geometry and status", cmd_asmi_info),
	SHELL_CMD_ARG(dump, NULL, "Dump ASMI flash: <offset> [length<=64]", cmd_asmi_dump, 2, 1),
	SHELL_CMD_ARG(stress, NULL, "Write/read verify LittleFS pattern: [bytes<=32768]", cmd_asmi_stress, 1, 1),
	SHELL_SUBCMD_SET_END
);
SHELL_CMD_REGISTER(cyc1000_flash, &asmi_cmds, "CYC1000 ASMI flash diagnostics", NULL);
