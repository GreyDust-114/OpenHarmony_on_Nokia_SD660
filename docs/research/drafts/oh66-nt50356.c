// SPDX-License-Identifier: GPL-2.0-only
/*
 * Novatek NT50356 / TI LM36274 display bias sequencer for Nokia B2N.
 *
 * Facts taken from the public Nokia vendor driver (nokia-boost_nt50356.c) and
 * the stock 00WW_4_15I device tree: i2c7 address 0x11, HWEN on GPIO13, ENP on
 * GPIO35, ENN on GPIO48, ID strap on GPIO62, bias codes 0x20/0x20, and 1.8V
 * panel I/O from PM660 L11.
 *
 * The vendor driver has two exclusive branches chosen by the ID pin
 * (0 = TI/LM36274, 1 = Novatek) and writes bias codes that do not match the
 * device-tree values. Register programming is therefore opt-in through
 * "novatek,program-bias" and requires bench validation. Without that property
 * only the documented GPIO power sequence runs, which is what a first light-up
 * needs and what cannot damage the panel through a guessed voltage code.
 */
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/regmap.h>

#define NT50356_REG_BSTO	0x09
#define NT50356_REG_AVDD	0x0d
#define NT50356_REG_AVEE	0x0e
#define NT50356_REG_BL_CONF	0x0a
#define NT50356_REG_BL_ENABLE	0x0b

#define NT50356_BSTO_VALUE	0x28
#define NT50356_BSTO_FINAL	0x9e
#define NT50356_BL_CONF_TI	0x28
#define NT50356_BL_CONF_NT	0x89
#define NT50356_BL_ENABLE_TI	0x13
#define NT50356_BL_ENABLE_NT	0x1f

#define NT50356_RAIL_DELAY_US	2000

struct nt50356 {
	struct device *dev;
	struct regmap *regmap;
	struct gpio_desc *bl_en;
	struct gpio_desc *enp;
	struct gpio_desc *enn;
	struct gpio_desc *id;
	bool program_bias;
	u32 avdd_code;
	u32 avee_code;
	bool bias_on;
};

static int nt50356_write(struct nt50356 *chip, unsigned int reg, unsigned int value)
{
	int ret = regmap_write(chip->regmap, reg, value);

	if (ret)
		dev_err(chip->dev, "register 0x%02x write failed: %d\n", reg, ret);
	return ret;
}

static int nt50356_program_bias(struct nt50356 *chip, bool on)
{
	int ret;

	if (!chip->program_bias)
		return 0;
	if (!on)
		return nt50356_write(chip, NT50356_REG_BSTO, 0);

	ret = nt50356_write(chip, NT50356_REG_BSTO, NT50356_BSTO_VALUE);
	if (ret)
		return ret;
	ret = nt50356_write(chip, NT50356_REG_AVDD, chip->avdd_code);
	if (ret)
		return ret;
	ret = nt50356_write(chip, NT50356_REG_AVEE, chip->avee_code);
	if (ret)
		return ret;
	return nt50356_write(chip, NT50356_REG_BSTO, NT50356_BSTO_FINAL);
}

static int nt50356_power_on(struct nt50356 *chip)
{
	int ret;

	/* Vendor order: HWEN first, then ENP, then ENN, 2ms between steps. */
	gpiod_set_value_cansleep(chip->bl_en, 1);
	usleep_range(NT50356_RAIL_DELAY_US, NT50356_RAIL_DELAY_US + 500);
	gpiod_set_value_cansleep(chip->enp, 1);
	usleep_range(NT50356_RAIL_DELAY_US, NT50356_RAIL_DELAY_US + 500);
	gpiod_set_value_cansleep(chip->enn, 1);
	usleep_range(NT50356_RAIL_DELAY_US, NT50356_RAIL_DELAY_US + 500);

	ret = nt50356_program_bias(chip, true);
	if (ret)
		return ret;
	chip->bias_on = chip->program_bias;
	return 0;
}

static void nt50356_power_off(struct nt50356 *chip)
{
	if (chip->bias_on) {
		nt50356_program_bias(chip, false);
		chip->bias_on = false;
	}
	gpiod_set_value_cansleep(chip->enn, 0);
	gpiod_set_value_cansleep(chip->enp, 0);
	gpiod_set_value_cansleep(chip->bl_en, 0);
}

static const struct regmap_config nt50356_regmap_config = {
	.reg_bits = 8,
	.val_bits = 8,
	.max_register = 0x20,
	.cache_type = REGCACHE_NONE,
};

static int nt50356_probe(struct i2c_client *client)
{
	struct nt50356 *chip;
	int id, ret;

	chip = devm_kzalloc(&client->dev, sizeof(*chip), GFP_KERNEL);
	if (!chip)
		return -ENOMEM;
	chip->dev = &client->dev;

	chip->regmap = devm_regmap_init_i2c(client, &nt50356_regmap_config);
	if (IS_ERR(chip->regmap))
		return dev_err_probe(chip->dev, PTR_ERR(chip->regmap),
				     "Failed to create regmap\n");

	chip->bl_en = devm_gpiod_get(chip->dev, "bl-en", GPIOD_OUT_LOW);
	if (IS_ERR(chip->bl_en))
		return dev_err_probe(chip->dev, PTR_ERR(chip->bl_en), "bl-en GPIO\n");
	chip->enp = devm_gpiod_get(chip->dev, "enp", GPIOD_OUT_LOW);
	if (IS_ERR(chip->enp))
		return dev_err_probe(chip->dev, PTR_ERR(chip->enp), "enp GPIO\n");
	chip->enn = devm_gpiod_get(chip->dev, "enn", GPIOD_OUT_LOW);
	if (IS_ERR(chip->enn))
		return dev_err_probe(chip->dev, PTR_ERR(chip->enn), "enn GPIO\n");
	chip->id = devm_gpiod_get_optional(chip->dev, "id", GPIOD_IN);
	if (IS_ERR(chip->id))
		return dev_err_probe(chip->dev, PTR_ERR(chip->id), "id GPIO\n");

	chip->program_bias = device_property_read_bool(chip->dev, "novatek,program-bias");
	if (device_property_read_u32(chip->dev, "novatek,avdd-voltage", &chip->avdd_code))
		chip->avdd_code = 0x20;
	if (device_property_read_u32(chip->dev, "novatek,avee-voltage", &chip->avee_code))
		chip->avee_code = 0x20;

	i2c_set_clientdata(client, chip);
	ret = nt50356_power_on(chip);
	if (ret)
		return ret;

	id = chip->id ? gpiod_get_value_cansleep(chip->id) : -ENOENT;
	dev_info(chip->dev, "bias rails up (id=%d, register bias programming %s)\n",
		 id, chip->program_bias ? "enabled" : "disabled");
	return 0;
}

static void nt50356_remove(struct i2c_client *client)
{
	nt50356_power_off(i2c_get_clientdata(client));
}

static const struct of_device_id nt50356_of_match[] = {
	{ .compatible = "novatek,nt50356" },
	{ }
};
MODULE_DEVICE_TABLE(of, nt50356_of_match);

static struct i2c_driver nt50356_driver = {
	.driver = {
		.name = "nt50356",
		.of_match_table = nt50356_of_match,
	},
	.probe = nt50356_probe,
	.remove = nt50356_remove,
};
module_i2c_driver(nt50356_driver);

MODULE_DESCRIPTION("Nokia B2N NT50356/LM36274 display bias sequencer");
MODULE_LICENSE("GPL");
