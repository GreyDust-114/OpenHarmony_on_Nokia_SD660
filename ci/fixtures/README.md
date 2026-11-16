# Offline source fixtures

`oh66-kvm-coalesced_mmio.c` is an unmodified GPL-2.0 source snapshot, retaining
its original license/copyright notices. It contains no device/host evidence.

- Source: https://github.com/eclipse-oniro-mirrors/kernel_linux_6.6/blob/31c8f21f4c95d59c8e730038b868109e9244a936/virt/kvm/coalesced_mmio.c
- Input SHA256: `affd97d507157f56bd2c3b0beebe36e399b781004b1ed018901bbf9c7997d570`
- Reference: Linux v6.6.101, commit `3a8ababb8b6a0ced2be230b60b6e3ddbd8d67014`, same path.
- Reference SHA256: `414f9b16edb7fd8562af7730ccdf47f6278c1b5ac17dcde46748b7f091fa8ffb`

The regression applies the declared KVM support patch in a temporary Git tree.
It checks removal of the obsolete duplicate destructor call and exact equality
with the stable reference file's hash. Before the fix it fails on the real
caller's stale helper, not on a mock compiler or a declaration-only contract.

The matching kernel `include/kvm/iodev.h` and bodies of
`kvm_io_bus_unregister_dev()` / `kvm_io_bus_destroy()` were separately compared
with the same stable version. They already match: device destruction belongs
to the bus path, so adding a public declaration/stub back would be wrong.

This is a source/patch regression, not a compiler or runtime test. Actual
compilation is performed only by the disposable GitHub Actions runner.

## XPM pageflag configuration regression

- `oh66-mmflags.h` is the unmodified GPL-2.0 header from the same pinned
  kernel commit, `include/trace/events/mmflags.h`.
  SHA256: `b5e688ad525a978a90136bc94b513d3701b3097268c22f5ec0be31fab081eb41`.
- `oh66-xpm-pageflags-enum.h` is the conditional enum excerpt from
  `include/linux/page-flags.h:146-149` at that commit, with source attribution.

`test_mmflags.py` applies the declared two-line guard patch in a temporary
Git tree. Its source-contract test compares actual enum/table guards for all
four combinations of `CONFIG_SECURITY_XPM` and `CONFIG_ARCH_USES_PG_ARCH_X`.
The original source fails both mixed combinations; the fixed source preserves
XPM's own condition independently of architecture flags.

Linux CI additionally compiles a minimized C harness containing the real enum
excerpt and macro definitions/calls for all four combinations, using native
GCC, `-Werror` and `-fsyntax-only`. A negative control must reproduce the
original undeclared `PG_xpm_readonly` error. On hosts without GCC this compiler
test is explicitly skipped; no compiler is installed locally. This matrix is
not a full kernel or runtime test.

## B2N vendor panel stream fixture

`nokia-b2n-ft8716u-panel.dtsi` is the public Nokia FT8716U panel source
snapshot previously collected under `evidence/hardware-audit/nokia-ft8716u-panel.dtsi`.
Its original Linux Foundation GPL-2.0 notice is retained. This is vendor source,
not a phone dump. `test_panel_hardware.py` compares every command byte and runs
the actual transport function against a host mock on Linux CI. The source has
120 on/2 off packets including 65 two-byte DCS long writes.

## B2N panel link fixtures

`oh66-panel-Kconfig` and `oh66-panel-Makefile` are unchanged source snapshots
from `drivers/gpu/drm/panel/{Kconfig,Makefile}` at the same pinned kernel
commit `31c8f21f4c95d59c8e730038b868109e9244a936`. Original SPDX notices are
retained. `test_display_link.py` applies both board and display patches in a
temporary Git tree, checks registration and exact panel source, and tests the
final System.map contract with missing/undefined/prefix-only negative cases.
No phone evidence is included.

## B2N panel power fixtures

`oh66-regulator-Kconfig` and `oh66-regulator-Makefile` are unchanged source
snapshots of `drivers/regulator/{Kconfig,Makefile}` at the pinned kernel commit
`31c8f21f4c95d59c8e730038b868109e9244a936`, retaining original SPDX notices.
`test_display_power.py` stacks the four B2N patches on these fixtures plus the
panel and qcom DTS makefiles, then asserts the PM660 L11 panel rail, the
NT50356 i2c7 node and the GPIO ordering, and that bias register programming is
opt-in only.

## B2N bring-up initramfs fixture

`b2n-bringup-init.sh` is the K1 research init: it mounts only proc/sys/dev/
configfs, brings up a USB ACM serial gadget so the host can read the boot log,
mirrors dmesg to the framebuffer console (`/dev/tty0`) and to pstore, then
reboots back to the normal Android boot after a timeout. It never mounts or
writes an eMMC partition, never writes userdata/NV and contains no flashing
command. `ci/boot_image.py` embeds it as `/init` together with the runner's
static busybox into a gzip newc initramfs; the resulting boot v0 image is for
`fastboot boot` in RAM only.

## B2N DTB build fixtures

`oh66-qcom-Makefile` is the unchanged qcom DTS Makefile (canonical LF) at
kernel commit `31c8f21f4c95d59c8e730038b868109e9244a936`:
`arch/arm64/boot/dts/qcom/Makefile`.
SHA256: `5ee3610b80756f073fd198444404ee83e1c36aa44e39c70b1835d7a421abc527`.

The B2N regression applies the actual board patch to this fixture and verifies
that the registered DTS equals the checked-in draft. FDT binary tests generate
synthetic trees in memory, checking phandle resolution, PMIC inclusion and the
GPIO67 falling-edge contract. No original device DTB is published as a fixture.
