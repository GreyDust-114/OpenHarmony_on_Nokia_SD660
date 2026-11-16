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
mount -t pstore pstore /sys/fs/pstore 2>/dev/null
if [ -d /sys/fs/pstore ]; then
	for f in /sys/fs/pstore/*; do
		[ -f "$f" ] || continue
		panel "=== pstore: $f ==="
		cat "$f" > /dev/tty0 2>/dev/null
	done
fi
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
reboot -f
