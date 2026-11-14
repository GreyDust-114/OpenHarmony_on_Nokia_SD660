# Offline source fixture

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
