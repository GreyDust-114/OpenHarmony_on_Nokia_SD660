"""Bounded, offline FDT-v17 inspection and B2N compiled-DTB contracts."""
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
    if profile is None:
        return result
    if profile != "b2n-touch":
        raise ValueError("Unknown DTB inspection profile")
    if result["compatible"] != ["nokia,b2n", "qcom,sdm660"]:
        raise ValueError("B2N DTB compatible mismatch")
    if result["model"] != ["Nokia 7 Plus B2N (SDM660)"]:
        raise ValueError("B2N DTB model mismatch")
    controllers = [node for (node, name), value in props.items() if name == "compatible"
                   and "qcom,sdm660-pinctrl" in strings(value)]
    if len(controllers) != 1:
        raise ValueError("Expected exactly one SDM660 GPIO controller")
    gpio = cells(props[(controllers[0], "phandle")])
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
    result["b2n_touch_contract"] = {"path": touch, "gpio_controller": controllers[0], **expected}
    return result
