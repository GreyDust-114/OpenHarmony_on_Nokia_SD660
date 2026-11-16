"""Android boot v0 image and initramfs builder for the B2N research target.

This produces a *research* boot image for `fastboot boot` only: Android header
v0, page size 4096, `Image.gz` + appended B2N DTB as the kernel payload, and a
minimal busybox initramfs that logs over USB serial/fbcon and reboots. The
output is never a flashable image and this module never talks to a device.

Header field values follow the stock 00WW_4_15I boot_a header captured from the
retained device evidence (kernel_addr 0x8000, ramdisk_addr 0x1000000,
second_addr 0xF00000, tags_addr 0x100, page_size 4096).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct

BOOT_MAGIC = b"ANDROID!"
HEADER_V0 = struct.Struct("<8s10I16s512s8I1024s")
PAGE_SIZE = 4096
DEFAULT_MAX_BYTES = 64 * 1024**2
DEFAULT_ADDRS = {
    "kernel_addr": 0x8000,
    "ramdisk_addr": 0x1000000,
    "second_addr": 0xF00000,
    "tags_addr": 0x100,
}
CMDLINE_LIMIT = 512


def _align(value: int, page: int = PAGE_SIZE) -> int:
    return (value + page - 1) // page * page


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_boot_v0(kernel: bytes, ramdisk: bytes, cmdline: str, *,
                  kernel_addr: int = DEFAULT_ADDRS["kernel_addr"],
                  ramdisk_addr: int = DEFAULT_ADDRS["ramdisk_addr"],
                  second_addr: int = DEFAULT_ADDRS["second_addr"],
                  tags_addr: int = DEFAULT_ADDRS["tags_addr"],
                  page_size: int = PAGE_SIZE, os_version: int = 0,
                  name: bytes = b"") -> bytes:
    """Pack one boot v0 image; kernel already contains any appended DTB."""
    if page_size not in (2048, 4096):
        raise ValueError("Unsupported boot page size")
    if not kernel or not ramdisk:
        raise ValueError("Kernel and ramdisk payloads must be non-empty")
    if len(cmdline.encode("utf-8")) > CMDLINE_LIMIT:
        raise ValueError("cmdline exceeds the v0 512-byte field")
    if len(name) > 16:
        raise ValueError("boot name exceeds 16 bytes")
    header = HEADER_V0.pack(
        BOOT_MAGIC, len(kernel), kernel_addr, len(ramdisk), ramdisk_addr,
        0, second_addr, tags_addr, page_size, 0, os_version,
        name, cmdline.encode("utf-8"), *([0] * 8), b"")
    image = bytearray(_align(len(header), page_size))
    image[:len(header)] = header
    image += kernel
    image += b"\0" * (_align(len(image), page_size) - len(image))
    image += ramdisk
    image += b"\0" * (_align(len(image), page_size) - len(image))
    return bytes(image)


def parse_boot_v0(data: bytes) -> dict:
    """Parse a boot v0 image back into fields plus payload slices (for tests)."""
    if len(data) < HEADER_V0.size or data[:8] != BOOT_MAGIC:
        raise ValueError("Not an Android boot image")
    fields = HEADER_V0.unpack_from(data)
    (magic, kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size,
     second_addr, tags_addr, page_size, header_version, os_version,
     name, cmdline, *ident, extra_cmdline) = fields
    if page_size not in (2048, 4096):
        raise ValueError("Unsupported boot page size")
    if header_version != 0:
        raise ValueError("Only boot header v0 is supported")
    def slice_at(offset: int, size: int) -> bytes:
        start = _align(offset, page_size)
        return data[start:start + size]
    kernel_offset = _align(HEADER_V0.size, page_size)
    ramdisk_offset = kernel_offset + _align(kernel_size, page_size)
    second_offset = ramdisk_offset + _align(ramdisk_size, page_size)
    payload = {
        "magic": magic.decode("ascii"),
        "kernel_size": kernel_size, "kernel_addr": kernel_addr,
        "ramdisk_size": ramdisk_size, "ramdisk_addr": ramdisk_addr,
        "second_size": second_size, "second_addr": second_addr,
        "tags_addr": tags_addr, "page_size": page_size,
        "header_version": header_version, "os_version": os_version,
        "name": name.rstrip(b"\0"), "cmdline": cmdline.rstrip(b"\0").decode("utf-8"),
        "kernel": slice_at(HEADER_V0.size, kernel_size),
        "ramdisk": slice_at(ramdisk_offset, ramdisk_size),
        "second": slice_at(second_offset, second_size) if second_size else b"",
        "image_bytes": len(data),
    }
    return payload


def _newc_header(name: str, mode: int, size: int, ino: int) -> bytes:
    fields = (ino, mode, 0, 0, 1, 0, size, 0, 0, 0, 0, len(name.encode()) + 1, 0)
    return b"070701" + b"".join(f"{value:08x}".encode() for value in fields)


def _cpio_entry(name: str, mode: int, ino: int, data: bytes = b"") -> bytes:
    header = _newc_header(name, mode, len(data), ino)
    entry = header + name.encode() + b"\0"
    entry += b"\0" * (-len(entry) % 4)
    entry += data
    entry += b"\0" * (-len(data) % 4)
    return entry


def build_initramfs(files: dict[str, tuple[bytes, int]], *, directories: tuple[str, ...] = ()) -> bytes:
    """Build a gzip-compressed newc cpio initramfs from path -> (bytes, mode)."""
    if "init" not in files:
        raise ValueError("initramfs requires an 'init' file")
    for name in files:
        if name.startswith("/") or ".." in name.split("/") or not name:
            raise ValueError("Unsafe initramfs path")
    entries = bytearray()
    ino = 1
    entries += _cpio_entry(".", 0o40755, ino)
    ino += 1
    for directory in bool(directories) and directories or ():
        if directory.startswith("/") or ".." in directory.split("/") or not directory:
            raise ValueError("Unsafe initramfs directory")
        entries += _cpio_entry(directory, 0o40755, ino)
        ino += 1
    for name in sorted(files):
        data, mode = files[name]
        parts = name.split("/")
        for depth in range(1, len(parts)):
            parent = "/".join(parts[:depth])
            if parent in directories or parent == ".":
                continue
            entries += _cpio_entry(parent, 0o40755, ino)
            ino += 1
            directories = directories + (parent,)
        entries += _cpio_entry(name, mode, ino, data)
        ino += 1
    entries += _cpio_entry("TRAILER!!!", 0, ino)
    return gzip.compress(bytes(entries), mtime=0, compresslevel=9)


def parse_initramfs(blob: bytes) -> dict[str, tuple[bytes, int]]:
    """Parse a gzip newc initramfs back into path -> (bytes, mode)."""
    raw = gzip.decompress(blob)
    result = {}
    offset = 0
    while True:
        if raw[offset:offset + 6] != b"070701":
            raise ValueError("Invalid newc magic")
        fields = [int(raw[offset + 6 + 8 * i:offset + 14 + 8 * i], 16) for i in range(13)]
        _, mode, _, _, _, _, size, _, _, _, _, name_size, _ = fields
        offset += 110
        name = raw[offset:offset + name_size - 1].decode()
        offset += name_size + (-(110 + name_size) % 4)
        data = raw[offset:offset + size]
        offset += size + (-size % 4)
        if name == "TRAILER!!!":
            break
        result[name] = (data, mode)
    return result


def build_boot_image(image_gz: Path, dtb: Path, busybox: Path, init_script: Path,
                     cmdline: str, out: Path, report: Path, *,
                     max_bytes: int = DEFAULT_MAX_BYTES, **addrs) -> dict:
    """Compose kernel payload + initramfs, verify the result, write report."""
    if not image_gz.is_file() or not dtb.is_file():
        raise FileNotFoundError("Kernel image or DTB missing")
    if not busybox.is_file() or not init_script.is_file():
        raise FileNotFoundError("busybox or init script missing")
    if max_bytes <= 0 or max_bytes > 512 * 1024**2:
        raise ValueError("Unreasonable boot image size limit")
    kernel_gz = image_gz.read_bytes()
    if not kernel_gz.startswith(b"\x1f\x8b"):
        raise ValueError("Kernel image is not gzip")
    dtb_bytes = dtb.read_bytes()
    if len(dtb_bytes) < 40 or dtb_bytes[:4] != b"\xd0\x0d\xfe\xed":
        raise ValueError("DTB magic missing")
    payload = kernel_gz + dtb_bytes
    script = init_script.read_bytes()
    if not script.startswith(b"#!"):
        raise ValueError("init script needs a shebang")
    initramfs = build_initramfs({
        "init": (script, 0o100755),
        "bin/busybox": (busybox.read_bytes(), 0o100755),
    }, directories=("bin",))
    image = build_boot_v0(payload, initramfs, cmdline, **addrs)
    if len(image) > max_bytes:
        raise ValueError(f"Boot image {len(image)} bytes exceeds limit {max_bytes}")
    parsed = parse_boot_v0(image)
    if parsed["kernel"] != payload or parsed["ramdisk"] != initramfs:
        raise ValueError("Pack/parse round-trip mismatch")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image)
    report_data = {
        "kind": "research-boot-image-not-for-flashing",
        "output": out.name, "boot_image_bytes": len(image),
        "boot_image_sha256": sha256_bytes(image),
        "partition_limit_bytes": max_bytes,
        "kernel_payload_bytes": len(payload),
        "kernel_payload_sha256": sha256_bytes(payload),
        "kernel_image": {"name": image_gz.name, "bytes": len(kernel_gz),
                         "sha256": sha256_bytes(kernel_gz)},
        "appended_dtb": {"name": dtb.name, "bytes": len(dtb_bytes),
                         "sha256": sha256_bytes(dtb_bytes)},
        "initramfs_bytes": len(initramfs), "initramfs_sha256": sha256_bytes(initramfs),
        "initramfs_entries": sorted(parse_initramfs(initramfs)),
        "cmdline": cmdline,
        "header": {key: parsed[key] for key in (
            "magic", "kernel_size", "kernel_addr", "ramdisk_size", "ramdisk_addr",
            "second_size", "second_addr", "tags_addr", "page_size",
            "header_version", "os_version")},
        "fastboot_boot_only": True,
        "warning": "Research boot image for fastboot boot in RAM only. Never flash it.",
    }
    report.write_text(json.dumps(report_data, indent=2) + "\n", encoding="utf-8")
    return report_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-gz", type=Path, required=True)
    parser.add_argument("--dtb", type=Path, required=True)
    parser.add_argument("--busybox", type=Path, required=True)
    parser.add_argument("--init-script", type=Path, required=True)
    parser.add_argument("--cmdline", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--kernel-addr", type=lambda v: int(v, 0), default=DEFAULT_ADDRS["kernel_addr"])
    parser.add_argument("--ramdisk-addr", type=lambda v: int(v, 0), default=DEFAULT_ADDRS["ramdisk_addr"])
    parser.add_argument("--second-addr", type=lambda v: int(v, 0), default=DEFAULT_ADDRS["second_addr"])
    parser.add_argument("--tags-addr", type=lambda v: int(v, 0), default=DEFAULT_ADDRS["tags_addr"])
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.img", args.out.name):
        parser.error("boot image name must be a plain .img file name")
    report = build_boot_image(
        args.image_gz, args.dtb, args.busybox, args.init_script, args.cmdline,
        args.out, args.report, max_bytes=args.max_bytes,
        kernel_addr=args.kernel_addr, ramdisk_addr=args.ramdisk_addr,
        second_addr=args.second_addr, tags_addr=args.tags_addr,
        page_size=args.page_size)
    print(json.dumps({key: report[key] for key in (
        "boot_image_bytes", "boot_image_sha256", "kernel_payload_bytes",
        "initramfs_entries", "cmdline")}, indent=2))


if __name__ == "__main__":
    main()
