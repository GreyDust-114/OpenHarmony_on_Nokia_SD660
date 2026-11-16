"""Offline evidence and executable transport regressions for B2N panel."""
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import build_kernel as builder

ROOT = builder.PROJECT
spec = importlib.util.spec_from_file_location('b2n_commands', ROOT / 'docs/research/scripts/generate_b2n_panel_commands.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class B2nPanelTests(unittest.TestCase):
    def test_header_matches_public_vendor_bytes(self):
        source = (ROOT / 'ci/fixtures/nokia-b2n-ft8716u-panel.dtsi').read_text()
        actual = (ROOT / 'docs/research/drafts/oh66-b2n-ft8716u-commands.h').read_text()
        self.assertEqual(actual, generator.render(source))
        for kind, count, waits, long_two in [('on', 120, [120], 65), ('off', 2, [10, 150], 0)]:
            stream = generator.command_bytes(source, 'qcom,mdss-dsi-' + kind + '-command')
            pos, packets = 0, []
            while pos < len(stream):
                size = int.from_bytes(stream[pos+5:pos+7], 'big')
                packets.append(stream[pos:pos+7+size])
                pos += 7 + size
            self.assertEqual(len(packets), count)
            self.assertEqual([p[4] for p in packets if p[4]], waits)
            self.assertEqual(sum(p[0] == 0x39 and len(p) == 9 for p in packets), long_two)

    def test_vendor_timing_and_reset_not_reference_defaults(self):
        source = (ROOT / 'docs/research/drafts/oh66-b2n-panel-ft8716u.c').read_text()
        for token in ('.hsync_start = 1080 + 32', '.hsync_end = 1080 + 32 + 2', '.htotal = 1080 + 32 + 2 + 32', '.height_mm = 136', 'MIPI_DSI_MODE_VIDEO_BURST', 'MIPI_DSI_MODE_VIDEO_SYNC_PULSE', '"nokia,b2n-ft8716u"'):
            self.assertIn(token, source)
        self.assertNotIn('mipi_dsi_dcs_write_seq', source)
        self.assertNotIn('MIPI_DSI_MODE_NO_EOT_PACKET', source)
        reset = source.split('static void mdss_dsi_ft8716u_reset', 1)[1].split('static int', 1)[0]
        self.assertEqual(re.findall(r'gpiod_set_value_cansleep\(ctx->reset_gpio, ([01])\)', reset), ['0', '1', '0'])
        self.assertEqual(re.findall(r'usleep_range\((\d+),', reset), ['1000', '1000', '10000'])

    def test_transport_with_real_streams_and_failures(self):
        gcc = shutil.which('gcc')
        if not gcc:
            if sys.platform == 'linux':
                self.fail('Linux CI must provide GCC for transport contract')
            self.skipTest('No local GCC; transport harness runs on Linux CI')
        source = (ROOT / 'docs/research/drafts/oh66-b2n-panel-ft8716u.c').read_text()
        function = source[source.index('static int b2n_send_commands'):source.index('static void mdss_dsi_ft8716u_reset')]
        prefix = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
#include <sys/types.h>
typedef uint8_t u8;
#define MIPI_DSI_MSG_USE_LPM 2
#define MIPI_DSI_MSG_REQ_ACK 1
struct mipi_dsi_msg { u8 channel, type; unsigned flags; size_t tx_len; const void *tx_buf; };
struct mipi_dsi_host;
struct mipi_dsi_host_ops { ssize_t (*transfer)(struct mipi_dsi_host *, const struct mipi_dsi_msg *); };
struct mipi_dsi_host { const struct mipi_dsi_host_ops *ops; };
struct mipi_dsi_device { struct mipi_dsi_host *host; u8 channel; };
static const u8 *expected;
static size_t cursor, calls, sleeps;
static unsigned expected_flags;
static int fail_at = -1, short_at = -1;
static void msleep(unsigned delay) { assert(delay == expected[cursor + 4]); sleeps++; }
static ssize_t transfer(struct mipi_dsi_host *host, const struct mipi_dsi_msg *msg)
{
    (void)host;
    const u8 *h = expected + cursor;
    assert(msg->type == h[0] && msg->channel == h[2]);
    assert(msg->tx_len == (size_t)((h[5] << 8) | h[6]));
    assert(msg->flags == expected_flags);
    assert(!memcmp(msg->tx_buf, h + 7, msg->tx_len));
    if ((int)calls++ == fail_at) return -ETIMEDOUT;
    if ((int)calls - 1 == short_at) return 0;
    /* Delayed packets leave cursor at the header for msleep validation. */
    if (!h[4]) cursor += 7 + msg->tx_len;
    return msg->tx_len;
}
'''
        # The sleep mock advances the reference stream only after checking delay.
        prefix = prefix.replace('sleeps++; }', 'sleeps++; cursor += 7 + ((expected[cursor+5] << 8) | expected[cursor+6]); }')
        suffix = r'''
#include "commands.h"
int main(void)
{
    const struct mipi_dsi_host_ops ops = { .transfer = transfer };
    struct mipi_dsi_host host = { .ops = &ops };
    struct mipi_dsi_device dsi = { .host = &host };
    expected = b2n_on_commands; expected_flags = 2;
    assert(b2n_send_commands(&dsi, expected, sizeof(b2n_on_commands), true) == 0);
    assert(calls == 120 && sleeps == 1 && cursor == sizeof(b2n_on_commands));
    expected = b2n_off_commands; expected_flags = 0; cursor = calls = sleeps = 0;
    assert(b2n_send_commands(&dsi, expected, sizeof(b2n_off_commands), false) == 0);
    assert(calls == 2 && sleeps == 2 && cursor == sizeof(b2n_off_commands));
    expected = b2n_on_commands; expected_flags = 2; cursor = calls = sleeps = 0; fail_at = 2;
    assert(b2n_send_commands(&dsi, expected, sizeof(b2n_on_commands), true) == -ETIMEDOUT);
    assert(calls == 3 && sleeps == 0);
    cursor = calls = 0; fail_at = -1; short_at = 0;
    assert(b2n_send_commands(&dsi, expected, sizeof(b2n_on_commands), true) == -EIO);
    assert(calls == 1);
    short_at = -1; calls = 0;
    assert(b2n_send_commands(&dsi, expected, 6, true) == -EINVAL);
    assert(b2n_send_commands(&dsi, expected, 8, true) == -EINVAL);
    u8 invalid[] = {0x39, 0, 0, 0, 0, 0, 2, 0, 0};
    assert(b2n_send_commands(&dsi, invalid, sizeof(invalid), true) == -EINVAL);
    invalid[1] = 1; invalid[2] = 1;
    assert(b2n_send_commands(&dsi, invalid, sizeof(invalid), true) == -EINVAL);
    invalid[2] = 0; invalid[0] = 0x29;
    assert(b2n_send_commands(&dsi, invalid, sizeof(invalid), true) == -EINVAL);
    assert(calls == 0);
    dsi.host = NULL;
    assert(b2n_send_commands(&dsi, expected, sizeof(b2n_on_commands), true) == -ENOSYS);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'harness.c').write_text(prefix + function + suffix)
            shutil.copyfile(ROOT / 'docs/research/drafts/oh66-b2n-ft8716u-commands.h', root / 'commands.h')
            exe = root / 'harness'
            subprocess.run([gcc, '-std=c99', '-Wall', '-Wextra', '-Werror', str(root / 'harness.c'), '-o', str(exe)], check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)
