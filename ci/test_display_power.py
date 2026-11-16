"""B2N display power chain: PM660 L11 panel I/O plus NT50356 bias sequencing."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_kernel as builder
from device_tree import check_dts_layout


class DisplayPowerTests(unittest.TestCase):
    def test_power_patch_applies_after_previous_layers(self):
        target = builder.load_targets()["oh66-b2n-dts"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def put(rel, data):
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data.replace(b"\r\n", b"\n"))
            put("arch/arm64/boot/dts/qcom/Makefile", (builder.PROJECT / "ci/fixtures/oh66-qcom-Makefile").read_bytes())
            for name in ("Kconfig", "Makefile"):
                put("drivers/gpu/drm/panel/" + name, (builder.PROJECT / ("ci/fixtures/oh66-panel-" + name)).read_bytes())
                put("drivers/regulator/" + name, (builder.PROJECT / ("ci/fixtures/oh66-regulator-" + name)).read_bytes())
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for field in ("board_patch", "display_patch", "hardware_patch", "power_patch"):
                spec = target[field]
                data = (builder.PROJECT / spec["path"]).read_bytes().replace(b"\r\n", b"\n")
                self.assertEqual(hashlib.sha256(data).hexdigest(), spec["sha256"], field)
                patch = root / (field + ".patch")
                patch.write_bytes(data)
                subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--check", str(patch)],
                               cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "-c", "core.autocrlf=false", "apply", str(patch)],
                               cwd=root, check=True, capture_output=True)

            dts = (root / "arch/arm64/boot/dts/qcom/sdm660-nokia-b2n.dts").read_text()
            # Run #16 shipped the vph_pwr regulator outside the root node and
            # dtc stopped with a bare syntax error; keep the layout check here
            # so the composed source is rejected before any cloud build.
            check_dts_layout(dts)
            for token in ('vddi0-supply = <&vreg_l11a_1p8>', "vreg_l11a_1p8: l11",
                          'regulator-min-microvolt = <1780000>', "nt50356@11",
                          'bl-en-gpios = <&tlmm 13 GPIO_ACTIVE_HIGH>',
                          'id-gpios = <&tlmm 62 GPIO_ACTIVE_HIGH>',
                          'reset-gpios = <&tlmm 53 GPIO_ACTIVE_LOW>'):
                self.assertIn(token, dts)
            self.assertEqual(dts.count("nt50356@11"), 1)
            self.assertNotIn('status = "disabled";\n};\n\n/*\n * Display bias', dts)

            panel = (root / "drivers/gpu/drm/panel/panel-ft8716u.c").read_text()
            self.assertEqual(panel, (builder.PROJECT / "docs/research/drafts/oh66-b2n-panel-ft8716u.c").read_text())
            self.assertIn("mdss_dsi_ft8716u_supply_on", panel)
            self.assertIn('devm_regulator_get_optional(dev, "vddi0")', panel)

            regulator = (root / "drivers/regulator/nt50356.c").read_text()
            self.assertEqual(regulator, (builder.PROJECT / "docs/research/drafts/oh66-nt50356.c").read_text())
            self.assertIn("novatek,nt50356", regulator)
            self.assertIn("obj-$(CONFIG_REGULATOR_NT50356) += nt50356.o",
                          (root / "drivers/regulator/Makefile").read_text())
            self.assertIn("config REGULATOR_NT50356", (root / "drivers/regulator/Kconfig").read_text())

    def test_bias_sequencing_matches_vendor_order_and_is_opt_in(self):
        source = (builder.PROJECT / "docs/research/drafts/oh66-nt50356.c").read_text()
        # GPIO order: HWEN (bl-en) -> ENP -> ENN, reverse on power off.
        on = source.split("static int nt50356_power_on", 1)[1].split("static void nt50356_power_off", 1)[0]
        order = [line.strip() for line in on.splitlines() if "gpiod_set_value_cansleep" in line]
        self.assertEqual([line.split("->")[1].split(",")[0] for line in order], ["bl_en", "enp", "enn"])
        off = source.split("static void nt50356_power_off", 1)[1].split("static const struct regmap_config", 1)[0]
        order = [line.strip() for line in off.splitlines() if "gpiod_set_value_cansleep" in line]
        self.assertEqual([line.split("->")[1].split(",")[0] for line in order], ["enn", "enp", "bl_en"])
        # Register bias programming must never run unless the DT opts in.
        self.assertIn('device_property_read_bool(chip->dev, "novatek,program-bias")', source)
        self.assertIn("if (!chip->program_bias)", source)

    def test_target_requires_bias_builtin_and_linked(self):
        target = builder.load_targets()["oh66-b2n-dts"]
        for name in ("REGULATOR", "REGULATOR_NT50356"):
            self.assertIn(name, target["enable_symbols"])
            self.assertIn("CONFIG_" + name + "=y", target["required_symbols"])
        self.assertIn("nt50356_driver", target["required_link_symbols"])
        self.assertEqual(target["bias_object_target"], "drivers/regulator/nt50356.o")
        self.assertEqual(target["dtb_profiles"]["qcom/sdm660-nokia-b2n.dtb"], ["b2n-touch", "b2n-display"])
        labels = [s["label"] for s in builder.build_plan(target, "OUT", 2)]
        self.assertLess(labels.index("compile-ft8716u-panel-object"), labels.index("compile-nt50356-object"))
        self.assertLess(labels.index("compile-nt50356-object"), labels.index("compile-kernel"))


if __name__ == "__main__":
    unittest.main()
