"""Final-image display linkage contracts; runs without a local kernel build."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_kernel as builder


class DisplayLinkTests(unittest.TestCase):
    def test_patch_applies_after_board_and_registers_panel(self):
        target = builder.load_targets()["oh66-b2n-dts"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def install(name, data):
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data.replace(b"\r\n", b"\n"))
            install("arch/arm64/boot/dts/qcom/Makefile", (builder.PROJECT / "ci/fixtures/oh66-qcom-Makefile").read_bytes())
            for name in ("Kconfig", "Makefile"):
                install("drivers/gpu/drm/panel/" + name, (builder.PROJECT / ("ci/fixtures/oh66-panel-" + name)).read_bytes())
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for field in ("board_patch", "display_patch"):
                spec = target[field]
                data = (builder.PROJECT / spec["path"]).read_bytes().replace(b"\r\n", b"\n")
                self.assertEqual(hashlib.sha256(data).hexdigest(), spec["sha256"])
                patch = root / (field + ".patch")
                patch.write_bytes(data)
                subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--check", str(patch)], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "-c", "core.autocrlf=false", "apply", str(patch)], cwd=root, check=True, capture_output=True)
            panel = root / "drivers/gpu/drm/panel"
            self.assertIn("config DRM_PANEL_B2N_FT8716U", (panel / "Kconfig").read_text())
            self.assertIn("obj-$(CONFIG_DRM_PANEL_B2N_FT8716U) += panel-ft8716u.o", (panel / "Makefile").read_text())
            self.assertEqual((panel / "panel-ft8716u.c").read_text(), (builder.PROJECT / "docs/research/drafts/oh66-b2n-panel-ft8716u.c").read_text())

    def test_final_map_required_not_merely_object_or_config(self):
        target = builder.load_targets()["oh66-b2n-dts"]
        required = target["required_link_symbols"]
        good = "\n".join(f"ffff80008000{i:04x} d {s}" for i, s in enumerate(required))
        self.assertEqual(set(builder.check_link_symbols(good, required)), set(required))
        for bad in ("", "CC drivers/gpu/drm/panel/panel-ft8716u.o", good.replace(" d ", " U "), good.replace(required[0], required[0] + "_other")):
            with self.assertRaisesRegex(ValueError, "absent from final System.map"):
                builder.check_link_symbols(bad, required)
        self.assertEqual(builder.check_link_symbols("", []), {})

    def test_display_is_builtin_with_modular_dependency_caps_removed(self):
        target = builder.load_targets()["oh66-b2n-dts"]
        for name in ("DRM_MSM", "DRM_MSM_DSI", "DRM_MSM_DSI_14NM_PHY", "DRM_PANEL_B2N_FT8716U", "BACKLIGHT_CLASS_DEVICE"):
            self.assertIn(name, target["enable_symbols"])
            self.assertIn("CONFIG_" + name + "=y", target["required_symbols"])
        for name in ("QCOM_OCMEM", "QCOM_LLCC"):
            self.assertIn(name, target["enable_symbols"])
        self.assertIn("DRM_MSM_DPU", target["disable_symbols"])
        self.assertIn("# CONFIG_DRM_MSM_DPU is not set", target["required_disabled_symbols"])
        for name in ("nokia44-baseline", "oh66-ft8716"):
            self.assertNotIn("required_link_symbols", builder.load_targets()[name])


if __name__ == "__main__":
    unittest.main()
