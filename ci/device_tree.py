"""Bounded, offline FDT-v17 inspection and B2N composed-DTS/DTB contracts."""
import hashlib
from pathlib import Path
import struct


def cells(value):
    if len(value) % 4:
        raise ValueError("Unaligned FDT integer property")
    return list(struct.unpack(">" + "I" * (len(value) // 4), value))


def strings(value):
    return [part.decode("utf-8") for part in value.rstrip(b"\0").split(b"\0") if part]


def parse_fdt(blob):
    if not 40 <= len(blob) <= 16 * 1024**2:
        raise ValueError("FDT size out of bounds")
    magic, total, off_struct, off_strings, reserve, version, compat, cpu, string_len, struct_len = struct.unpack_from(">10I", blob)
    if magic != 0xd00dfeed or total != len(blob) or version != 17 or compat > 17:
        raise ValueError("Invalid/unsupported FDT header")
    for offset, size in ((off_struct, struct_len), (off_strings, string_len)):
        if offset < 40 or offset + size > total:
            raise ValueError("FDT block outside file")
    data = blob[off_struct:off_struct + struct_len]
    names = blob[off_strings:off_strings + string_len]
    props, stack, nodes, pos = {}, [], set(), 0
    while pos + 4 <= len(data):
        token = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if token == 1:
            end = data.find(b"\0", pos)
            if end < 0:
                raise ValueError("Unterminated FDT node")
            name = data[pos:end].decode("ascii")
            if "/" in name or (not stack and (name or nodes)):
                raise ValueError("Invalid FDT root/name")
            stack.append(name)
            path = "/" + "/".join(stack[1:])
            if path in nodes:
                raise ValueError("Duplicate FDT node")
            nodes.add(path)
            pos = (end + 4) & ~3
        elif token == 2:
            if not stack:
                raise ValueError("Unbalanced FDT node")
            stack.pop()
        elif token == 3:
            if not stack or pos + 8 > len(data):
                raise ValueError("Truncated FDT property")
            size, nameoff = struct.unpack_from(">II", data, pos)
            pos += 8
            end = names.find(b"\0", nameoff) if nameoff < len(names) else -1
            if end < 0 or pos + size > len(data):
                raise ValueError("FDT property out of bounds")
            key = ("/" + "/".join(stack[1:]), names[nameoff:end].decode("ascii"))
            if key in props:
                raise ValueError("Duplicate FDT property")
            props[key] = data[pos:pos + size]
            pos = (pos + size + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            if stack or not nodes:
                raise ValueError("Unclosed/empty FDT")
            return props
        else:
            raise ValueError("Unexpected FDT token")
    raise ValueError("Incomplete FDT structure")


def inspect_dtb(path, profile=None):
    path = Path(path)
    if path.stat().st_size > 16 * 1024**2:
        raise ValueError("DTB exceeds inspection limit")
    blob = path.read_bytes()
    props = parse_fdt(blob)
    result = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
              "model": strings(props.get(("/", "model"), b"")),
              "compatible": strings(props.get(("/", "compatible"), b""))}
    profiles = [profile] if isinstance(profile, str) else list(profile or [])
    if not profiles:
        return result
    allowed = {"b2n-touch", "b2n-display"}
    if set(profiles) - allowed:
        raise ValueError("Unknown DTB inspection profile")
    if "b2n-touch" in profiles or "b2n-display" in profiles:
        _check_identity(result)
    if "b2n-touch" in profiles:
        result["b2n_touch_contract"] = _check_touch(props)
    if "b2n-display" in profiles:
        result["b2n_display_contract"] = _check_display(props)
    return result


def _blank_dts_noise(text):
    """Blank comments, strings and cpp lines, preserving length and newlines."""
    output = []
    for line in text.splitlines(True):
        if line.startswith("#"):
            output.append("".join("\n" if char == "\n" else " " for char in line))
        else:
            output.append(line)
    text = "".join(output)
    chars = list(text)
    index, length = 0, len(text)
    while index < length:
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("Unterminated DTS block comment")
            for pos in range(index, end + 2):
                if chars[pos] != "\n":
                    chars[pos] = " "
            index = end + 2
        elif text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end < 0 else end
            for pos in range(index, end):
                chars[pos] = " "
            index = end
        elif text[index] == '"':
            end = index + 1
            while end < length and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            if end >= length:
                raise ValueError("Unterminated DTS string")
            for pos in range(index + 1, end):
                if chars[pos] != "\n":
                    chars[pos] = " "
            index = end + 1
        else:
            index += 1
    return "".join(chars)


def _dts_line(text, index):
    return text.count("\n", 0, max(index or 0, 0)) + 1


def _dts_item_line(text, clean, start, end):
    """Line of the first non-blank character of a top-level item."""
    chunk = clean[start:end]
    return _dts_line(text, start + len(chunk) - len(chunk.lstrip()))


def check_dts_layout(text):
    """Reject composed board DTS whose device nodes escape the root node.

    dtc accepts only device-tree directives ('/dts-v1/;', '/memreserve/;', ...)
    and '&label { ... }' reference blocks at file top level. A node definition
    placed there - for example after a stray '};' that closes the root node
    early - makes dtc stop with a bare "syntax error" at the node line. Board
    sources assembled from our patch stack are checked here so the offending
    line is named before the cloud build fetches any kernel source. This is a
    placement pre-check, not a device-tree parser: dtc on the runner stays the
    authority for grammar, includes and semantics.
    """
    clean = _blank_dts_noise(text)
    depth = 0
    start = 0
    roots = []
    for index, char in enumerate(clean):
        if char == "{":
            if depth == 0:
                header = clean[start:index].strip()
                line = _dts_item_line(text, clean, start, index)
                if header == "/":
                    roots.append(line)
                elif not (header.startswith("&") and header[1:].strip()):
                    snippet = header.splitlines()[0][:60] if header else ""
                    raise ValueError(
                        f"DTS node definition at line {line} is outside the root node "
                        f"({snippet!r}); dtc rejects this as a syntax error")
                start = None
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise ValueError(f"Unbalanced '}}' in composed DTS at line {_dts_line(text, index)}")
            if depth == 0:
                start = index + 1
        elif char == ";" and depth == 0:
            header = clean[start:index].strip()
            if header and not header.startswith(
                    ("/dts-v1/", "/memreserve/", "/include/", "/plugin/")):
                snippet = header.splitlines()[0][:60]
                raise ValueError(
                    f"DTS statement at line {_dts_item_line(text, clean, start, index)} is "
                    f"not a device-tree directive ({snippet!r})")
            start = index + 1
    if depth:
        raise ValueError("Unbalanced '{' in composed DTS")
    if clean[start:].strip():
        raise ValueError(
            f"Trailing DTS item at line {_dts_item_line(text, clean, start, len(clean))}")
    if not roots:
        raise ValueError("Composed DTS has no root node '/ { }'")
    if len(roots) > 1:
        raise ValueError(f"Composed DTS defines the root node more than once (lines {roots})")


def _check_identity(result):
    if result["compatible"] != ["nokia,b2n", "qcom,sdm660"]:
        raise ValueError("B2N DTB compatible mismatch")
    if result["model"] != ["Nokia 7 Plus B2N (SDM660)"]:
        raise ValueError("B2N DTB model mismatch")


def _gpio_controller(props):
    controllers = [node for (node, name), value in props.items() if name == "compatible"
                   and "qcom,sdm660-pinctrl" in strings(value)]
    if len(controllers) != 1:
        raise ValueError("Expected exactly one SDM660 GPIO controller")
    return controllers[0], cells(props[(controllers[0], "phandle")])


def _check_touch(props):
    controllers, gpio = _gpio_controller(props)
    touch_nodes = [node for (node, name), value in props.items() if name == "compatible"
                   and "focaltech,ft8716" in strings(value)]
    if len(touch_nodes) != 1:
        raise ValueError("Expected exactly one FT8716 node")
    touch = touch_nodes[0]
    controller = touch.rsplit("/", 1)[0]
    if cells(props.get((controller, "reg"), b"")) != [0xc178000, 0x600]:
        raise ValueError("B2N touch I2C controller address mismatch")
    if "qcom,i2c-qup-v2.2.1" not in strings(props.get((controller, "compatible"), b"")):
        raise ValueError("B2N touch I2C controller compatible mismatch")
    expected = {"reg": [0x38], "interrupts-extended": gpio + [67, 2],
                "reset-gpios": gpio + [66, 1], "touchscreen-size-x": [1080], "touchscreen-size-y": [2160]}
    for name, value in expected.items():
        if cells(props.get((touch, name), b"")) != value:
            raise ValueError("B2N compiled touch property mismatch: " + name)
    if strings(props.get((touch, "compatible"), b"")) != ["focaltech,ft8716"]:
        raise ValueError("B2N touch compatible mismatch")
    if strings(props.get((touch, "status"), b"")) != ["okay"]:
        raise ValueError("B2N touch node is not enabled")
    present = {s for (node, name), value in props.items() if name == "compatible" for s in strings(value)}
    if not {"qcom,pm660", "qcom,pm660l"} <= present:
        raise ValueError("B2N PMIC includes missing from DTB")
    return {"path": touch, "gpio_controller": controllers, **expected}


def _check_display(props):
    controllers, gpio = _gpio_controller(props)
    panels = [node for (node, name), value in props.items() if name == "compatible"
              and "nokia,b2n-ft8716u" in strings(value)]
    if len(panels) != 1:
        raise ValueError("Expected exactly one B2N FT8716U panel node")
    panel = panels[0]
    if cells(props.get((panel, "reg"), b"")) != [0]:
        raise ValueError("B2N panel reg mismatch")
    if cells(props.get((panel, "reset-gpios"), b"")) != gpio + [53, 1]:
        raise ValueError("B2N panel reset GPIO mismatch")

    supply = cells(props.get((panel, "vddi0-supply"), b""))
    if len(supply) != 1:
        raise ValueError("B2N panel vddi0-supply missing")
    regulator = [node for (node, name), value in props.items()
                 if name == "phandle" and cells(value) == supply]
    if len(regulator) != 1:
        raise ValueError("B2N panel vddi0-supply does not resolve")
    volts = cells(props.get((regulator[0], "regulator-min-microvolt"), b""))
    if volts != [1780000]:
        raise ValueError("B2N panel I/O rail is not the 1.8V PM660 L11 rail")

    bias_nodes = [node for (node, name), value in props.items() if name == "compatible"
                  and "novatek,nt50356" in strings(value)]
    if len(bias_nodes) != 1:
        raise ValueError("Expected exactly one NT50356 bias node")
    bias = bias_nodes[0]
    controller = bias.rsplit("/", 1)[0]
    if cells(props.get((controller, "reg"), b"")) != [0xc1b7000, 0x600]:
        raise ValueError("B2N bias I2C controller address mismatch")
    if cells(props.get((bias, "reg"), b"")) != [0x11]:
        raise ValueError("B2N bias address mismatch")
    expected = {"bl-en-gpios": gpio + [13, 0], "enp-gpios": gpio + [35, 0],
                "enn-gpios": gpio + [48, 0], "id-gpios": gpio + [62, 0]}
    for name, value in expected.items():
        if cells(props.get((bias, name), b"")) != value:
            raise ValueError("B2N bias GPIO mismatch: " + name)
    return {"path": panel, "gpio_controller": controllers, "reset_gpios": gpio + [53, 1],
            "vddi0_regulator": regulator[0], "vddi0_microvolt": volts[0],
            "bias": bias, "bias_gpios": expected}
