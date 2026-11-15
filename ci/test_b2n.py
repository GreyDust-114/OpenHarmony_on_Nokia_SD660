"""B2N source/compiled-FDT contracts using public and synthetic fixtures."""
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

import build_kernel as builder
from device_tree import inspect_dtb, parse_fdt


def u32(*values):
    return struct.pack(">" + "I" * len(values), *values)


def fixture_fdt(irq=2, pmics=True, soc="/soc@0", address=0xc178000):
    props = {
        "/": {"model": b"Nokia 7 Plus B2N (SDM660)\0", "compatible": b"nokia,b2n\0qcom,sdm660\0"},
        soc + "/pinctrl@1000000": {"compatible": b"qcom,sdm660-pinctrl\0", "phandle": u32(42)},
        soc + "/i2c@c178000": {"compatible": b"qcom,i2c-qup-v2.2.1\0", "reg": u32(address, 0x600)},
        soc + "/i2c@c178000/touchscreen@38": {
            "compatible": b"focaltech,ft8716\0", "status": b"okay\0", "reg": u32(0x38),
            "interrupts-extended": u32(42, 67, irq), "reset-gpios": u32(42, 66, 1),
            "touchscreen-size-x": u32(1080), "touchscreen-size-y": u32(2160)},
    }
    if pmics:
        props[soc + "/spmi/pmic@0"] = {"compatible": b"qcom,pm660\0qcom,spmi-pmic\0"}
        props[soc + "/spmi/pmic@2"] = {"compatible": b"qcom,pm660l\0qcom,spmi-pmic\0"}
    root = {"props": {}, "children": {}}
    names, offsets = bytearray(), {}
    for path, values in props.items():
        node = root
        for part in path.strip("/").split("/") if path != "/" else []:
            node = node["children"].setdefault(part, {"props": {}, "children": {}})
        node["props"] = values
        for name in values:
            if name not in offsets:
                offsets[name] = len(names)
                names.extend(name.encode() + b"\0")
    def pad(b):
        return b + b"\0" * (-len(b) % 4)
    def emit(name, node):
        data = u32(1) + pad(name.encode() + b"\0")
        for key, value in node["props"].items():
            data += u32(3, len(value), offsets[key]) + pad(value)
        for key, child in node["children"].items():
            data += emit(key, child)
        return data + u32(2)
    block = emit("", root) + u32(9)
    total = 56 + len(block) + len(names)
    return u32(0xd00dfeed, total, 56, 56 + len(block), 40, 17, 16, 0, len(names), len(block)) + b"\0" * 16 + block + names


class B2nBuildTests(unittest.TestCase):
    def setUp(self):
        self.targets = builder.load_targets()
        self.target = self.targets["oh66-b2n-dts"]

    def test_dtb_build_precedes_object_and_image_and_control_is_retained(self):
        steps = builder.build_plan(self.target, "OUT", 2)
        labels = [s["label"] for s in steps]
        self.assertLess(labels.index("resolve-config"), labels.index("compile-device-trees"))
        self.assertLess(labels.index("compile-device-trees"), labels.index("compile-ft8716-object"))
        self.assertEqual(steps[-1]["label"], "compile-kernel")
        dtbs = next(s["command"] for s in steps if s["label"] == "compile-device-trees")
        self.assertIn("qcom/sdm660-nokia-b2n.dtb", dtbs)
        self.assertIn("qcom/sdm660-xiaomi-lavender.dtb", dtbs)
        self.assertNotIn("-k", dtbs)
        self.assertNotIn("dtb_targets", self.targets["oh66-ft8716"])
        self.assertEqual(self.target["support_patches"], self.targets["oh66-ft8716"]["support_patches"])
        self.assertEqual(self.target["panel_object_target"], "drivers/gpu/drm/panel/panel-ft8716u.o")
        self.assertEqual(self.target["display_patch"]["sha256"], builder.sha256(builder.PROJECT / self.target["display_patch"]["path"]))
        self.assertIn("compile-ft8716u-panel-object", labels)

    def test_board_patch_applies_and_installs_exact_draft(self):
        spec = self.target["board_patch"]
        patch = builder.PROJECT / spec["path"]
        self.assertEqual(builder.sha256(patch), spec["sha256"])
        fixture = builder.PROJECT / "ci/fixtures/oh66-qcom-Makefile"
        self.assertEqual(builder.sha256(fixture), "5ee3610b80756f073fd198444404ee83e1c36aa44e39c70b1835d7a421abc527")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            makefile = root / "arch/arm64/boot/dts/qcom/Makefile"
            makefile.parent.mkdir(parents=True)
            makefile.write_bytes(fixture.read_bytes())
            prefix = ["git", "-c", "core.autocrlf=false", "-C", str(root)]
            subprocess.run(prefix + ["init", "-q"], check=True, capture_output=True)
            subprocess.run(prefix + ["apply", "--check", str(patch)], check=True, capture_output=True)
            subprocess.run(prefix + ["apply", str(patch)], check=True, capture_output=True)
            dts = makefile.with_name("sdm660-nokia-b2n.dts")
            self.assertEqual(dts.read_bytes(), (builder.PROJECT / "docs/research/drafts/oh66-b2n.dts").read_bytes())
            self.assertIn("sdm660-nokia-b2n.dtb", makefile.read_text())

    def test_compiled_dtb_contract_rejects_wrong_edge_and_missing_pmics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b2n.dtb"
            for soc in ("/soc", "/soc@0"):
                path.write_bytes(fixture_fdt(soc=soc))
                details = inspect_dtb(path, "b2n-touch")["b2n_touch_contract"]
                self.assertEqual(details["path"], soc + "/i2c@c178000/touchscreen@38")
                self.assertEqual(details["reg"], [56])
            for blob in (fixture_fdt(irq=1), fixture_fdt(pmics=False), fixture_fdt(address=0xc175000)):
                path.write_bytes(blob)
                with self.assertRaises(ValueError):
                    inspect_dtb(path, "b2n-touch")
            for blob in (b"short", fixture_fdt()[:-1], b"X" * 40):
                with self.assertRaises(ValueError):
                    parse_fdt(blob)

    def test_collects_verified_dtb_and_exact_source_before_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output, artifact = root / "src", root / "out", root / "artifact"
            target = {"dtb_targets": ["qcom/sdm660-nokia-b2n.dtb"],
                      "dtb_profiles": {"qcom/sdm660-nokia-b2n.dtb": "b2n-touch"}}
            dtb = output / "arch/arm64/boot/dts/qcom/sdm660-nokia-b2n.dtb"
            dtb.parent.mkdir(parents=True)
            dtb.write_bytes(fixture_fdt())
            dts = source / "arch/arm64/boot/dts/qcom/sdm660-nokia-b2n.dts"
            dts.parent.mkdir(parents=True)
            dts.write_text("// synthetic fixture\n")
            result = builder.collect_device_trees(target, source, output, artifact)
            self.assertEqual(len(result), 1)
            self.assertEqual((artifact / "research-device-trees/qcom/sdm660-nokia-b2n.dtb").read_bytes(), dtb.read_bytes())
            self.assertEqual((artifact / "device-tree-sources/qcom/sdm660-nokia-b2n.dts").read_bytes(), dts.read_bytes())

    def test_all_diagnostic_dtbs_survive_a_contract_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ["qcom/sdm660-nokia-b2n.dtb", "qcom/sdm660-xiaomi-lavender.dtb"]
            for name in names:
                dtb = root / "out/arch/arm64/boot/dts" / name
                dts = root / "src/arch/arm64/boot/dts" / Path(name).with_suffix(".dts")
                dtb.parent.mkdir(parents=True, exist_ok=True)
                dts.parent.mkdir(parents=True, exist_ok=True)
                dtb.write_bytes(fixture_fdt(irq=1))
                dts.write_text("// synthetic source\n")
            target = {"dtb_targets": names, "dtb_profiles": {names[0]: "b2n-touch"}}
            with self.assertRaises(ValueError):
                builder.collect_device_trees(target, root / "src", root / "out", root / "artifact")
            for name in names:
                self.assertTrue((root / "artifact/research-device-trees" / name).is_file())

    def test_unsafe_dtb_target_rejected(self):
        data = json.loads(builder.TARGETS_FILE.read_text())
        data["targets"]["oh66-b2n-dts"]["dtb_targets"] = ["qcom/../../escape.dtb"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "targets.json"
            path.write_text(json.dumps(data))
            with mock.patch.object(builder, "TARGETS_FILE", path), self.assertRaises(ValueError):
                builder.load_targets()


if __name__ == "__main__":
    unittest.main()
