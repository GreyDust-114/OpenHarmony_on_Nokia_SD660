#!/bin/busybox sh
# B2N K1 bring-up init (research initramfs; RAM-only boot, never installed).
#
# Goal: prove the 6.6 kernel + B2N DTB reach userspace on the real phone and
# leave a readable log over USB serial (ACM gadget) and the framebuffer
# console, then reboot back to the normal Android boot to keep the phone
# usable. It never mounts or writes any eMMC partition.
export PATH=/bin
BRINGUP_TIMEOUT=${BRINGUP_TIMEOUT:-300}

mount -t proc proc /proc 2>/dev/null
mount -t sysfs sysfs /sys 2>/dev/null
mount -t devtmpfs devtmpfs /dev 2>/dev/null
[ -c /dev/null ] || mdev -s 2>/dev/null
mkdir -p /dev/pts /sys/fs/pstore /sys/kernel/config
mount -t devpts devpts /dev/pts 2>/dev/null
mount -t configfs none /sys/kernel/config 2>/dev/null

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
	echo "b2n: usb acm serial ready ($(ls /sys/class/udc | head -n1))" > "$SERIAL"
fi

log() {
	echo "$*" > /dev/tty0 2>/dev/null
	[ -n "$SERIAL" ] && echo "$*" > "$SERIAL" 2>/dev/null
}

log "=== B2N 6.6 bring-up (research initramfs, RAM only) ==="
log "cmdline: $(cat /proc/cmdline)"
log "$(uname -a)"
if [ -n "$SERIAL" ]; then
	dmesg > "$SERIAL" 2>/dev/null
fi
dmesg | tail -n 80 > /dev/tty0 2>/dev/null
log "b2n: initramfs reached userspace; reboot in ${BRINGUP_TIMEOUT}s unless held"
if [ -c /dev/pmsg0 ]; then
	echo "B2N bring-up reached initramfs; see dmesg in pstore" > /dev/pmsg0 2>/dev/null
fi
sleep "$BRINGUP_TIMEOUT"
log "b2n: timeout reached, rebooting to the normal Android boot"
reboot -f
