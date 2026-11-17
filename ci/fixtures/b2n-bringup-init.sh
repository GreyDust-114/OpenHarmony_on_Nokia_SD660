#!/bin/busybox sh
# B2N K1 bring-up init (research initramfs; RAM-only boot, never installed).
#
# Goal: prove the 6.6 kernel + B2N DTB reach userspace on the real phone and
# leave a readable log over USB serial (ACM gadget), the framebuffer console
# and pstore, then reboot back to the normal Android boot to keep the phone
# usable. It never mounts or writes any eMMC partition.
#
# Log strategy: repeat dmesg dumps until the host attaches and pstore records
# are replayed first, because the USB driver may enumerate a few seconds after
# the first dump and a panic can truncate the session at any time.
#
# Debian/Ubuntu busybox-static is not a standalone shell: without /bin/<applet>
# symlinks every command would fail with 127, PID1 would exit and the kernel
# would panic with "Attempted to kill init". Install the applet links first,
# then keep PID1 alive even if a later step fails.
/bin/busybox --install -s /bin
trap '/bin/busybox sleep 2147483647' EXIT
echo "b2n: init started (busybox applet links installed)" > /dev/kmsg 2>/dev/null
export PATH=/bin
BRINGUP_TIMEOUT=${BRINGUP_TIMEOUT:-300}

mount -t proc proc /proc 2>/dev/null
mount -t sysfs sysfs /sys 2>/dev/null
mount -t devtmpfs devtmpfs /dev 2>/dev/null
[ -c /dev/null ] || mdev -s 2>/dev/null
mkdir -p /dev/pts /sys/fs/pstore /sys/kernel/config
mount -t devpts devpts /dev/pts 2>/dev/null
mount -t configfs none /sys/kernel/config 2>/dev/null

panel() { echo "$*" > /dev/tty0 2>/dev/null; }

panel "=== B2N 6.6 bring-up (research initramfs) ==="
panel "cmdline: $(cat /proc/cmdline)"
panel "$(uname -a)"

# Replay pstore from an earlier warm boot, if the bootloader preserved it.
#
# Reader mode: keep the recovered records on the panel for 90 seconds before
# any live dmesg dump, so the previous boot's panic log can be photographed.
# The panic image is booted with panic=0 and force-reset with the hardware
# keys, so RAM (and therefore pstore) survives until this reader image runs.
replay_pstore() {
	[ -d /sys/fs/pstore ] || return 0
	found=0
	for f in /sys/fs/pstore/*; do
		[ -f "$f" ] || continue
		found=1
		panel "=== pstore: $f ==="
		cat "$f" > /dev/tty0 2>/dev/null
	done
	[ "$found" = 1 ] || panel "=== pstore: (no records) ==="
}
mount -t pstore pstore /sys/fs/pstore 2>/dev/null
held=0
while [ "$held" -lt 90 ]; do
	panel "=== pstore reader mode: ${held}s / 90s ==="
	replay_pstore
	sleep 10
	held=$((held + 10))
done
if [ -c /dev/pmsg0 ]; then
	echo "B2N bring-up initramfs reached userspace" > /dev/pmsg0 2>/dev/null
fi

setup_gadget() {
	[ -d /sys/kernel/config/usb_gadget ] || return 1
	G=/sys/kernel/config/usb_gadget/b2n
	mkdir -p "$G" 2>/dev/null || return 1
	echo 0x1d6b > "$G/idVendor"
	echo 0x0104 > "$G/idProduct"
	mkdir -p "$G/strings/0x409"
	echo b2n-bringup > "$G/strings/0x409/serialnumber"
	echo Nokia > "$G/strings/0x409/manufacturer"
	echo "B2N bring-up" > "$G/strings/0x409/product"
	mkdir -p "$G/configs/c.1/strings/0x409"
	echo bringup > "$G/configs/c.1/strings/0x409/configuration"
	mkdir -p "$G/functions/acm.usb0" 2>/dev/null
	ln -s "$G/functions/acm.usb0" "$G/configs/c.1/" 2>/dev/null
	UDC=$(ls /sys/class/udc 2>/dev/null | head -n1)
	[ -n "$UDC" ] || return 1
	echo "$UDC" > "$G/UDC" || return 1
	sleep 2
	return 0
}

SERIAL=
if setup_gadget; then
	SERIAL=/dev/ttyGS0
	( cat /dev/kmsg > "$SERIAL" 2>/dev/null ) &
fi

log() {
	panel "$*"
	[ -n "$SERIAL" ] && echo "$*" > "$SERIAL" 2>/dev/null
}

dump() {
	if [ -n "$SERIAL" ]; then
		dmesg > "$SERIAL" 2>/dev/null
	fi
	dmesg | tail -n 120 > /dev/tty0 2>/dev/null
	if [ -c /dev/pmsg0 ]; then
		dmesg > /dev/pmsg0 2>/dev/null
	fi
}

log "b2n: initramfs reached userspace; serial=${SERIAL:-none}"
dump
seconds=0
while [ "$seconds" -lt "$BRINGUP_TIMEOUT" ]; do
	sleep 5
	seconds=$((seconds + 5))
	log "b2n: alive t=${seconds}s, uptime=$(cut -d' ' -f1 /proc/uptime)"
	if [ $((seconds % 15)) -eq 0 ]; then
		dump
	fi
done
log "b2n: timeout reached, rebooting to the normal Android boot"
reboot -f 2>/dev/null
# Never let PID1 exit even if the reboot applet is unavailable.
/bin/busybox sleep 2147483647
