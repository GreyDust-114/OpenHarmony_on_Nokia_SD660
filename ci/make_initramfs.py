"""Build the bring-up initramfs as a raw newc cpio for kernel embedding.

The B2N research boot image ships an initramfs through the boot image ramdisk
field, but a bootloader that ignores/does not pass that field would leave the
kernel without /init.  Embedding the same initramfs through
CONFIG_INITRAMFS_SOURCE makes the kernel use it unconditionally (the built-in
image is always unpacked first; an external initrd only adds to it).

The initramfs is executed by an aarch64 kernel, so the busybox binary must be
aarch64 as well; the packer validates the ELF machine to avoid the
"No working init found" panic caused by a host-arch (x86-64) busybox.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_image


def build_initramfs_cpio(busybox: Path, init_script: Path, out: Path,
                         compress: bool = False) -> dict:
    if not busybox.is_file() or not init_script.is_file():
        raise FileNotFoundError("busybox or init script missing")
    script = init_script.read_bytes()
    if not script.startswith(b"#!"):
        raise ValueError("init script needs a shebang")
    busybox_bytes = busybox.read_bytes()
    boot_image.validate_busybox(busybox_bytes)
    blob = boot_image.build_initramfs({
        "init": (script, 0o100755),
        "bin/busybox": (busybox_bytes, 0o100755),
    }, directories=("bin",), compress=compress)
    parsed = boot_image.parse_initramfs(blob)
    for required in ("init", "bin/busybox"):
        if required not in parsed:
            raise ValueError("generated initramfs is missing " + required)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    return {
        "output": out.name,
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "compressed": compress,
        "entries": sorted(parsed),
        "busybox_sha256": hashlib.sha256(busybox_bytes).hexdigest(),
        "busybox_elf_machine": "aarch64",
        "init_script": init_script.name,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--busybox", type=Path, required=True)
    parser.add_argument("--init-script", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gzip", action="store_true",
                        help="gzip the cpio (default: raw, required for CONFIG_INITRAMFS_SOURCE)")
    args = parser.parse_args()
    if not args.out.name.endswith(".cpio") and not args.out.name.endswith(".cpio.gz"):
        parser.error("output name must end in .cpio or .cpio.gz")
    report = build_initramfs_cpio(args.busybox, args.init_script, args.out, args.gzip)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
