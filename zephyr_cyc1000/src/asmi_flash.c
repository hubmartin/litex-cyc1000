/* SPDX-License-Identifier: Apache-2.0 */

/*
 * Flash driver for the CYC1000 LiteX ASMI storage window.
 *
 * The gateware maps only the SPI flash tail at the soc-nv-flash node, so the
 * configuration image, BIOS and Zephyr boot image can not be reached from
 * here. Reads and writes are plain uncached bus accesses: the ASMI IP turns
 * every store into write enable + page program and stalls the next flash
 * access until programming completed. Erase uses the gateware engine, which
 * blocks the storage window until the flash reports idle again.
 */

#define DT_DRV_COMPAT cyc1000_asmi_flash_controller

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/sys_io.h>

#include <string.h>

LOG_MODULE_REGISTER(cyc1000_asmi_flash, CONFIG_FLASH_LOG_LEVEL);

#define FLASH_NODE    DT_NODELABEL(storage_flash)
#define STORAGE_BASE  DT_REG_ADDR(FLASH_NODE)
#define STORAGE_SIZE  DT_REG_SIZE(FLASH_NODE)
#define ERASE_SIZE    DT_PROP(FLASH_NODE, erase_block_size)
#define ERASE_REG     DT_INST_REG_ADDR_BY_NAME(0, erase)
#define STATUS_REG    DT_INST_REG_ADDR_BY_NAME(0, status)

#define STATUS_BUSY   BIT(0)
/* 4 KiB subsector erase: typically 45 ms, at most 400 ms on the W25Q16. */
#define ERASE_TIMEOUT_MS 1000

static K_MUTEX_DEFINE(asmi_lock);

static const struct flash_parameters asmi_flash_parameters = {
	.write_block_size = DT_PROP(FLASH_NODE, write_block_size),
	.erase_value = 0xff,
};

#if defined(CONFIG_FLASH_PAGE_LAYOUT)
static const struct flash_pages_layout asmi_flash_layout = {
	.pages_count = STORAGE_SIZE / ERASE_SIZE,
	.pages_size = ERASE_SIZE,
};
#endif

static bool asmi_range_valid(off_t offset, size_t len)
{
	return offset >= 0 && (size_t)offset <= STORAGE_SIZE &&
	       len <= STORAGE_SIZE - (size_t)offset;
}

static int asmi_flash_read(const struct device *dev, off_t offset, void *data, size_t len)
{
	ARG_UNUSED(dev);

	if (!asmi_range_valid(offset, len)) {
		return -EINVAL;
	}

	k_mutex_lock(&asmi_lock, K_FOREVER);
	memcpy(data, (const void *)(STORAGE_BASE + offset), len);
	k_mutex_unlock(&asmi_lock);
	return 0;
}

static int asmi_flash_write(const struct device *dev, off_t offset, const void *data, size_t len)
{
	const uint8_t *src = data;
	mem_addr_t addr = STORAGE_BASE + offset;

	ARG_UNUSED(dev);

	if (!asmi_range_valid(offset, len)) {
		return -EINVAL;
	}

	/*
	 * Only aligned byte and word stores are issued: the ASMI IP supports
	 * byte-enable patterns of single bytes, halves and full words only.
	 * A word program is one flash command, so prefer words where aligned.
	 */
	k_mutex_lock(&asmi_lock, K_FOREVER);
	while (len > 0) {
		if ((addr & 3) == 0 && len >= 4) {
			uint32_t word;

			memcpy(&word, src, sizeof(word));
			sys_write32(word, addr);
			addr += 4;
			src += 4;
			len -= 4;
		} else {
			sys_write8(*src, addr);
			addr++;
			src++;
			len--;
		}
	}
	k_mutex_unlock(&asmi_lock);
	return 0;
}

static int asmi_flash_erase(const struct device *dev, off_t offset, size_t size)
{
	int rc = 0;

	ARG_UNUSED(dev);

	if (!asmi_range_valid(offset, size) || offset % ERASE_SIZE || size % ERASE_SIZE) {
		return -EINVAL;
	}

	k_mutex_lock(&asmi_lock, K_FOREVER);
	for (size_t done = 0; done < size && rc == 0; done += ERASE_SIZE) {
		int64_t deadline = k_uptime_get() + ERASE_TIMEOUT_MS;

		sys_write32(offset + done, ERASE_REG);
		/* Never touch the storage window while the engine is busy: the
		 * access would stall the CPU bus until the erase finished.
		 */
		while (sys_read32(STATUS_REG) & STATUS_BUSY) {
			if (k_uptime_get() > deadline) {
				LOG_ERR("erase at 0x%lx timed out", (long)(offset + done));
				rc = -ETIMEDOUT;
				break;
			}
			k_msleep(1);
		}
	}
	k_mutex_unlock(&asmi_lock);
	return rc;
}

static const struct flash_parameters *asmi_flash_get_parameters(const struct device *dev)
{
	ARG_UNUSED(dev);
	return &asmi_flash_parameters;
}

#if defined(CONFIG_FLASH_PAGE_LAYOUT)
static void asmi_flash_page_layout(const struct device *dev,
				   const struct flash_pages_layout **layout, size_t *layout_size)
{
	ARG_UNUSED(dev);
	*layout = &asmi_flash_layout;
	*layout_size = 1;
}
#endif

static const struct flash_driver_api asmi_flash_api = {
	.read = asmi_flash_read,
	.write = asmi_flash_write,
	.erase = asmi_flash_erase,
	.get_parameters = asmi_flash_get_parameters,
#if defined(CONFIG_FLASH_PAGE_LAYOUT)
	.page_layout = asmi_flash_page_layout,
#endif
};

DEVICE_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
		      CONFIG_FLASH_INIT_PRIORITY, &asmi_flash_api);
