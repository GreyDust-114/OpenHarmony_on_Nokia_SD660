// SPDX-License-Identifier: GPL-2.0-only
// B2N vendor timing/commands: Copyright (c) 2013 The Linux Foundation.
// Panel lifecycle adapted from the sdm660-mainline FT8716U reference.

#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/slab.h>

#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>

#include "panel-b2n-ft8716u-commands.h"

struct mdss_dsi_ft8716u {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi;
	struct gpio_desc *reset_gpio;
};

static inline struct mdss_dsi_ft8716u *to_mdss_dsi_ft8716u(struct drm_panel *panel)
{
	return container_of(panel, struct mdss_dsi_ft8716u, panel);
}

/* Preserve vendor data type, virtual channel, ACK, padding and post-delay.
 * The OH6.6 DCS helpers select type by length and would turn the vendor's
 * two-byte 0x39 long writes into 0x15 short writes. Call the host with an
 * explicit message instead, as the DRM core's private transfer helper does.
 * last=1 means standalone transfers; other batching semantics are rejected.
 */
static int b2n_send_commands(struct mipi_dsi_device *dsi, const u8 *stream,
			     size_t length, bool low_power)
{
	size_t offset = 0;

	if (!dsi->host || !dsi->host->ops || !dsi->host->ops->transfer)
		return -ENOSYS;

	while (offset < length) {
		const u8 *header = stream + offset;
		struct mipi_dsi_msg msg = { 0 };
		size_t size;
		ssize_t ret;

		if (length - offset < 7)
			return -EINVAL;
		size = (header[5] << 8) | header[6];
		if (!size || size > length - offset - 7 || header[1] != 1 ||
		    header[2] != dsi->channel || header[3] > 1)
			return -EINVAL;
		if ((header[0] != 0x05 && header[0] != 0x15 && header[0] != 0x39) ||
		    ((header[0] == 0x05 || header[0] == 0x15) && size != 2))
			return -EINVAL;

		msg.channel = header[2];
		msg.type = header[0];
		msg.flags = low_power ? MIPI_DSI_MSG_USE_LPM : 0;
		if (header[3])
			msg.flags |= MIPI_DSI_MSG_REQ_ACK;
		msg.tx_len = size;
		msg.tx_buf = header + 7;
		ret = dsi->host->ops->transfer(dsi->host, &msg);
		if (ret < 0)
			return ret;
		if ((size_t)ret != size)
			return -EIO;
		if (header[4])
			msleep(header[4]);
		offset += 7 + size;
	}
	return 0;
}

static void mdss_dsi_ft8716u_reset(struct mdss_dsi_ft8716u *ctx)
{
	/* Vendor physical levels <1 1>, <0 1>, <1 10>.
	 * GPIO_ACTIVE_LOW converts those to logical deassert/assert/deassert.
	 */
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);
	usleep_range(1000, 2000);
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	usleep_range(1000, 2000);
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);
	usleep_range(10000, 11000);
}

static int mdss_dsi_ft8716u_prepare(struct drm_panel *panel)
{
	struct mdss_dsi_ft8716u *ctx = to_mdss_dsi_ft8716u(panel);
	int ret;

	/* Bias and I/O supply integration is a separate board-power patch. */
	mdss_dsi_ft8716u_reset(ctx);
	/* Vendor qcom,mdss-dsi-init-delay-us = <5>, after reset. */
	usleep_range(5, 10);
	ret = b2n_send_commands(ctx->dsi, b2n_on_commands,
				 sizeof(b2n_on_commands), true);
	if (ret < 0) {
		dev_err(&ctx->dsi->dev, "B2N panel initialization failed: %d\n", ret);
		gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	}
	return ret;
}

static int mdss_dsi_ft8716u_unprepare(struct drm_panel *panel)
{
	struct mdss_dsi_ft8716u *ctx = to_mdss_dsi_ft8716u(panel);
	int ret;

	/* Vendor off-command-state is HS, with 10ms/150ms post delays. */
	ret = b2n_send_commands(ctx->dsi, b2n_off_commands,
				 sizeof(b2n_off_commands), false);
	if (ret < 0)
		dev_err(&ctx->dsi->dev, "B2N panel shutdown failed: %d\n", ret);
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	return ret;
}

static const struct drm_display_mode mdss_dsi_ft8716u_mode = {
	.clock = (1080 + 32 + 2 + 32) * (2160 + 16 + 2 + 16) * 60 / 1000,
	.hdisplay = 1080,
	.hsync_start = 1080 + 32,
	.hsync_end = 1080 + 32 + 2,
	.htotal = 1080 + 32 + 2 + 32,
	.vdisplay = 2160,
	.vsync_start = 2160 + 16,
	.vsync_end = 2160 + 16 + 2,
	.vtotal = 2160 + 16 + 2 + 16,
	.width_mm = 68,
	.height_mm = 136,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int mdss_dsi_ft8716u_get_modes(struct drm_panel *panel,
				     struct drm_connector *connector)
{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, &mdss_dsi_ft8716u_mode);
	if (!mode)
		return -ENOMEM;
	drm_mode_set_name(mode);
	drm_mode_probed_add(connector, mode);
	connector->display_info.width_mm = mdss_dsi_ft8716u_mode.width_mm;
	connector->display_info.height_mm = mdss_dsi_ft8716u_mode.height_mm;
	return 1;
}

static const struct drm_panel_funcs mdss_dsi_ft8716u_panel_funcs = {
	.prepare = mdss_dsi_ft8716u_prepare,
	.unprepare = mdss_dsi_ft8716u_unprepare,
	.get_modes = mdss_dsi_ft8716u_get_modes,
};

static int mdss_dsi_ft8716u_probe(struct mipi_dsi_device *dsi)
{
	struct device *dev = &dsi->dev;
	struct mdss_dsi_ft8716u *ctx;
	int ret;

	ctx = devm_kzalloc(dev, sizeof(*ctx), GFP_KERNEL);
	if (!ctx)
		return -ENOMEM;
	drm_panel_init(&ctx->panel, dev, &mdss_dsi_ft8716u_panel_funcs,
		       DRM_MODE_CONNECTOR_DSI);
	/* Vendor lp11-init: prepare the upstream DSI bridge before panel reset. */
	ctx->panel.prepare_prev_first = true;
	ctx->reset_gpio = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(ctx->reset_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->reset_gpio), "Failed to get reset GPIO\n");
	ctx->dsi = dsi;
	mipi_dsi_set_drvdata(dsi, ctx);
	dsi->lanes = 4;
	dsi->format = MIPI_DSI_FMT_RGB888;
	/* Vendor burst video, sync pulse, TX EOT enabled. Do not suppress EOT. */
	dsi->mode_flags = MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST |
			  MIPI_DSI_MODE_VIDEO_SYNC_PULSE;
	ret = drm_panel_of_backlight(&ctx->panel);
	if (ret)
		return dev_err_probe(dev, ret, "Failed to get backlight\n");
	drm_panel_add(&ctx->panel);
	ret = mipi_dsi_attach(dsi);
	if (ret < 0) {
		drm_panel_remove(&ctx->panel);
		return dev_err_probe(dev, ret, "Failed to attach to DSI host\n");
	}
	return 0;
}

static void mdss_dsi_ft8716u_remove(struct mipi_dsi_device *dsi)
{
	struct mdss_dsi_ft8716u *ctx = mipi_dsi_get_drvdata(dsi);
	int ret = mipi_dsi_detach(dsi);

	if (ret < 0)
		dev_err(&dsi->dev, "Failed to detach from DSI host: %d\n", ret);
	drm_panel_remove(&ctx->panel);
}

static const struct of_device_id mdss_dsi_ft8716u_of_match[] = {
	{ .compatible = "nokia,b2n-ft8716u" },
	{ }
};
MODULE_DEVICE_TABLE(of, mdss_dsi_ft8716u_of_match);

static struct mipi_dsi_driver mdss_dsi_ft8716u_driver = {
	.probe = mdss_dsi_ft8716u_probe,
	.remove = mdss_dsi_ft8716u_remove,
	.driver = {
		.name = "panel-b2n-ft8716u",
		.of_match_table = mdss_dsi_ft8716u_of_match,
	},
};
module_mipi_dsi_driver(mdss_dsi_ft8716u_driver);

MODULE_DESCRIPTION("Nokia B2N FT8716U DRM panel research port");
MODULE_LICENSE("GPL");
