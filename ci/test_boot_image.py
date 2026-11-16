"""Offline tests for the research boot v0 packer and bring-up initramfs."""
import gzip
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

import boot_image as packer
import build_kernel as builder


def fdt_blob(size=64):
    return struct.pack(">II", 0xD00DFEED, size) + b"\0" * (size - 8)


def fake_elf(machine=0xB7, size=64):
    """Minimal ELF64 header with the given e_machine (0xb7 = aarch64)."""
    header = b"\x7fELF" + bytes([2, 1, 1]) + b"\0" * 9 + b"\0\0" + struct.pack("<H", machine)
    return header + b"\0" * (size - len(header))


class BootHeaderTests(unittest.TestCase):
    def test_v0_header_roundtrip_preserves_stock_addresses(self):
        kernel = b"K" * 10000
        ramdisk = b"R" * 5000
        image = packer.build_boot_v0(kernel, ramdisk, "console=tty0")
        parsed = packer.parse_boot_v0(image)
        self.assertEqual(parsed["magic"], "ANDROID!")
        self.assertEqual(parsed["kernel"], kernel)
        self.assertEqual(parsed["ramdisk"], ramdisk)
        self.assertEqual(parsed["kernel_size"], len(kernel))
        self.assertEqual(parsed["ramdisk_size"], len(ramdisk))
        self.assertEqual(parsed["cmdline"], "console=tty0")
        self.assertEqual(parsed["page_size"], 4096)
        self.assertEqual(parsed["header_version"], 0)
        for key, expected in packer.DEFAULT_ADDRS.items():
            self.assertEqual(parsed[key], expected, key)
        self.assertEqual(len(image) % 4096, 0)
        self.assertEqual(parsed["second_size"], 0)

    def test_payloads_are_page_aligned_and_separated(self):
        image = packer.build_boot_v0(b"A" * 4097, b"B" * 1, "")
        header_end = packer.HEADER_V0.size
        kernel_start = (header_end + 4095) // 4096 * 4096
        self.assertEqual(image[kernel_start:kernel_start + 3], b"AAA")
        ramdisk = packer.parse_boot_v0(image)["ramdisk"]
        self.assertEqual(ramdisk, b"B")

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            packer.build_boot_v0(b"", b"r", "")
        with self.assertRaises(ValueError):
            packer.build_boot_v0(b"k", b"", "")
        with self.assertRaises(ValueError):
            packer.build_boot_v0(b"k", b"r", "x" * 513)
        with self.assertRaises(ValueError):
            packer.build_boot_v0(b"k", b"r", "", page_size=1024)
        with self.assertRaises(ValueError):
            packer.parse_boot_v0(b"NOTABOOT!" + b"\0" * 2000)
        with self.assertRaises(ValueError):
            packer.parse_boot_v0(b"ANDROID!" + b"\0" * 8)


class InitramfsTests(unittest.TestCase):
    def test_newc_roundtrip_and_determinism(self):
        files = {"init": (b"#!/bin/sh\necho hi\n", 0o100755),
                 "bin/busybox": (b"\x7fELFfake", 0o100755)}
        blob = packer.build_initramfs(files, directories=("bin",))
        parsed = packer.parse_initramfs(blob)
        self.assertEqual(parsed["init"], files["init"])
        self.assertEqual(parsed["bin/busybox"], files["bin/busybox"])
        self.assertEqual(parsed["bin"], (b"", 0o40755))
        self.assertEqual(blob, packer.build_initramfs(files, directories=("bin",)))
        self.assertTrue(blob.startswith(b"\x1f\x8b"))

    def test_raw_cpio_supported_for_kernel_embedding(self):
        files = {"init": (b"#!/bin/busybox sh\n", 0o100755),
                 "bin/busybox": (fake_elf(), 0o100755)}
        raw = packer.build_initramfs(files, directories=("bin",), compress=False)
        self.assertTrue(raw.startswith(b"070701"))
        self.assertFalse(raw.startswith(b"\x1f\x8b"))
        parsed = packer.parse_initramfs(raw)
        self.assertEqual(parsed["init"], files["init"])
        self.assertEqual(parsed["bin/busybox"], files["bin/busybox"])

    def test_unsafe_or_incomplete_inputs_rejected(self):
        with self.assertRaises(ValueError):
            packer.build_initramfs({"bin/busybox": (b"x", 0o100755)})
        with self.assertRaises(ValueError):
            packer.build_initramfs({"init": (b"x", 0o100755), "../escape": (b"y", 0o100644)})
        with self.assertRaises(ValueError):
            packer.build_initramfs({"init": (b"x", 0o100755), "/abs": (b"y", 0o100644)})

    def test_wrong_arch_busybox_rejected(self):
        packer.validate_busybox(fake_elf(0xB7))
        with self.assertRaises(ValueError):
            packer.validate_busybox(fake_elf(0x3E))  # x86-64
        with self.assertRaises(ValueError):
            packer.validate_busybox(b"\x7fELF\x01\x01\x01" + b"\0" * 20)  # 32-bit
        with self.assertRaises(ValueError):
            packer.validate_busybox(b"not an elf")


class MakeInitramfsTests(unittest.TestCase):
    """The embedded-initramfs helper must emit a valid raw cpio for the kernel."""

    def test_builds_raw_cpio_from_the_checked_in_aarch64_busybox(self):
        import make_initramfs
        project = builder.PROJECT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "init.sh"
            script.write_bytes(b"#!/bin/busybox sh\necho embedded\n")
            out = root / "k1-initramfs.cpio"
            report = make_initramfs.build_initramfs_cpio(
                project / "ci/fixtures/busybox-aarch64", script, out)
            self.assertTrue(out.is_file())
            self.assertEqual(report["entries"], [".", "bin", "bin/busybox", "init"])
            self.assertEqual(report["busybox_elf_machine"], "aarch64")
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b"070701"))
            parsed = packer.parse_initramfs(raw)
            self.assertEqual(parsed["init"][0], script.read_bytes())
            self.assertTrue(parsed["bin/busybox"][0].startswith(b"\x7fELF"))

    def test_rejects_host_arch_busybox(self):
        import make_initramfs
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "init.sh"
            script.write_bytes(b"#!/bin/busybox sh\n")
            x86 = root / "busybox-x86"
            x86.write_bytes(fake_elf(0x3E))
            with self.assertRaises(ValueError):
                make_initramfs.build_initramfs_cpio(x86, script, root / "out.cpio")


class ComposeTests(unittest.TestCase):
    def fixtures(self, root: Path) -> dict:
        image_gz = root / "Image.gz"
        image_gz.write_bytes(gzip.compress(b"ARM\x64 kernel image placeholder", mtime=0))
        dtb = root / "b2n.dtb"
        dtb.write_bytes(fdt_blob())
        busybox = root / "busybox"
        busybox.write_bytes(fake_elf())
        script = root / "init.sh"
        script.write_bytes(b"#!/bin/busybox sh\nreboot -f\n")
        return {"image_gz": image_gz, "dtb": dtb, "busybox": busybox, "script": script}

    def test_compose_embeds_gzip_and_dtb_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.fixtures(root)
            out = root / "out" / "boot-b2n-research.img"
            report_path = root / "report.json"
            report = packer.build_boot_image(
                paths["image_gz"], paths["dtb"], paths["busybox"], paths["script"],
                "console=tty0 test=1", out, report_path, max_bytes=64 * 1024**2)
            self.assertTrue(out.is_file())
            self.assertEqual(report["boot_image_bytes"], out.stat().st_size)
            self.assertEqual(report["cmdline"], "console=tty0 test=1")
            self.assertEqual(report["initramfs_entries"], [".", "bin", "bin/busybox", "init"])
            self.assertEqual(report["header"]["page_size"], 4096)
            self.assertIn("not-for-flashing", report["kind"])
            parsed = packer.parse_boot_v0(out.read_bytes())
            expected = paths["image_gz"].read_bytes() + paths["dtb"].read_bytes()
            self.assertEqual(parsed["kernel"], expected)
            self.assertEqual(report["appended_dtb"]["sha256"], packer.sha256_bytes(fdt_blob()))
            self.assertEqual(json.loads(report_path.read_text())["boot_image_sha256"],
                             report["boot_image_sha256"])

    def test_compose_rejects_bad_inputs_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.fixtures(root)
            out = root / "boot.img"
            report = root / "report.json"
            bad = root / "bad.gz"
            bad.write_bytes(b"not gzip")
            with self.assertRaises(ValueError):
                packer.build_boot_image(bad, paths["dtb"], paths["busybox"],
                                        paths["script"], "x", out, report)
            tiny = root / "tiny.dtb"
            tiny.write_bytes(b"nope")
            with self.assertRaises(ValueError):
                packer.build_boot_image(paths["image_gz"], tiny, paths["busybox"],
                                        paths["script"], "x", out, report)
            with self.assertRaises(ValueError):
                packer.build_boot_image(paths["image_gz"], paths["dtb"], paths["busybox"],
                                        paths["script"], "x", out, report, max_bytes=4096)

    def test_compose_rejects_host_arch_busybox(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.fixtures(root)
            paths["busybox"].write_bytes(fake_elf(0x3E))  # x86-64
            with self.assertRaises(ValueError):
                packer.build_boot_image(
                    paths["image_gz"], paths["dtb"], paths["busybox"], paths["script"],
                    "x", root / "boot.img", root / "report.json")

    def test_cli_matches_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.fixtures(root)
            out = root / "cli-boot.img"
            report = root / "cli-report.json"
            subprocess.run([
                sys.executable, "-B", str(builder.PROJECT / "ci/boot_image.py"),
                "--image-gz", str(paths["image_gz"]), "--dtb", str(paths["dtb"]),
                "--busybox", str(paths["busybox"]), "--init-script", str(paths["script"]),
                "--cmdline", "console=tty0 cli=1", "--out", str(out),
                "--report", str(report)], check=True, capture_output=True, text=True)
            parsed = packer.parse_boot_v0(out.read_bytes())
            self.assertEqual(parsed["cmdline"], "console=tty0 cli=1")
            self.assertTrue(json.loads(report.read_text())["fastboot_boot_only"])


class BootTargetContractTests(unittest.TestCase):
    """The manifest/init script must stay inside the no-flash red lines."""

    @classmethod
    def setUpClass(cls):
        cls.targets = builder.load_targets()
        cls.target = cls.targets["oh66-b2n-boot"]
        cls.script = (builder.PROJECT / cls.target["boot_image"]["init_script"]).read_text()

    def test_boot_target_plan_packages_after_image(self):
        steps = builder.build_plan(self.target, "OUT", 2, "ARTIFACTS")
        labels = [step["label"] for step in steps]
        self.assertEqual(labels[-1], "package-boot-image")
        self.assertLess(labels.index("compile-kernel"), labels.index("package-boot-image"))
        command = steps[-1]["command"]
        names = {Path(part).name for part in command}
        self.assertIn("boot_image.py", names)
        self.assertIn("boot-b2n-research.img", " ".join(command))
        # No packaging step is injected when the caller provides no artifact dir.
        self.assertNotIn("package-boot-image",
                         [s["label"] for s in builder.build_plan(self.target, "OUT", 2)])

    def test_boot_target_requires_bringup_config_and_symbols(self):
        for symbol in ("EXTCON", "USB_CONFIGFS", "USB_DWC3_QCOM", "PHY_QCOM_QUSB2",
                       "PSTORE", "PSTORE_CONSOLE", "PSTORE_RAM", "DRM_FBDEV_EMULATION",
                       "VT", "VT_CONSOLE", "FRAMEBUFFER_CONSOLE",
                       "SDM_GCC_660", "SDM_MMCC_660", "INTERCONNECT_QCOM_SDM660"):
            self.assertIn(symbol, self.target["enable_symbols"])
            self.assertIn("CONFIG_" + symbol + "=y", self.target["required_symbols"])
        self.assertEqual(self.target["boot_image"]["dtb"], "qcom/sdm660-nokia-b2n.dtb")
        self.assertIn(self.target["boot_image"]["dtb"], self.target["dtb_targets"])
        cmdline = self.target["boot_image"]["cmdline"]
        self.assertIn("console=tty0", cmdline)
        self.assertIn("panic=10", cmdline)
        self.assertNotIn("root=", cmdline)
        self.assertNotIn("dm-verity", cmdline)

    def test_init_script_stays_within_ram_only_red_lines(self):
        for forbidden in ("/dev/mmcblk", "userdata", "persist", "mkfs", "dd if=",
                          "flash", "mke2fs", "mount /dev/block"):
            self.assertNotIn(forbidden, self.script)
        self.assertIn("usb_gadget", self.script)
        self.assertIn("reboot -f", self.script)
        self.assertIn("dmesg", self.script)
        self.assertTrue(self.script.startswith("#!"))

    def test_init_script_recovers_pstore_and_redumps_logs(self):
        # A panic may truncate the session before the host opens the port, so
        # the script must replay previous pstore records and keep re-dumping.
        self.assertIn("/sys/fs/pstore", self.script)
        self.assertIn("cat /dev/kmsg", self.script)
        self.assertIn("b2n: alive t=", self.script)
        self.assertIn("dmesg > \"$SERIAL\"", self.script)
        self.assertIn("/dev/pmsg0", self.script)

    def test_boot_target_embeds_aarch64_initramfs(self):
        # The initramfs must not depend on the bootloader forwarding the
        # boot-image ramdisk field, and must use the aarch64 busybox fixture.
        self.assertEqual(self.target["embed_initramfs"], "ci/fixtures/k1-initramfs.cpio")
        self.assertEqual(self.target["boot_image"]["busybox"], "ci/fixtures/busybox-aarch64")
        fixture = builder.PROJECT / self.target["boot_image"]["busybox"]
        self.assertTrue(fixture.is_file())
        packer.validate_busybox(fixture.read_bytes())
        labels = [step["label"] for step in builder.build_plan(self.target, "OUT", 2, "ARTIFACTS")]
        self.assertIn("embed-initramfs", labels)
        embed = next(step for step in builder.build_plan(self.target, "OUT", 2, "ARTIFACTS")
                     if step["label"] == "embed-initramfs")
        self.assertIn("INITRAMFS_SOURCE", embed["command"])
        self.assertLess(labels.index("embed-initramfs"), labels.index("resolve-config"))
        self.assertLess(labels.index("resolve-config"), labels.index("compile-kernel"))
        package = next(step for step in builder.build_plan(self.target, "OUT", 2, "ARTIFACTS")
                       if step["label"] == "package-boot-image")
        self.assertIn("busybox-aarch64", " ".join(package["command"]))

    def test_workflow_offers_boot_target_and_aarch64_busybox(self):
        source = (builder.PROJECT / ".github/workflows/kernel-build.yml").read_text()
        self.assertIn("oh66-b2n-boot", source)
        self.assertNotIn("busybox-static", source)
        self.assertIn("ci/fixtures/busybox-aarch64", source)
        self.assertIn("ci/make_initramfs.py", source)


if __name__ == "__main__":
    unittest.main()
