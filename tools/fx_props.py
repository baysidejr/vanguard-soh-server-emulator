"""Print the tagged properties of exports in a client package (.u / .utx ...), e.g. the emitters
of an effect class:

    python tools/fx_props.py UnrealScript/FXmystical.u FXmystical_IOParticle001fx

With a class name, its sub-objects (SpriteEmitter0, ...) are printed too. Reads the player's own
client files; nothing is written. Struct values other than plain vectors/ranges print as hex.
"""
import os
import struct
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import upackage
from upackage import _compact

TYPES = {1: "byte", 2: "int", 3: "bool", 4: "float", 5: "object", 6: "name", 7: "delegate", 8: "class",
         9: "array", 10: "struct", 11: "vector", 12: "rotator", 13: "str", 14: "map", 15: "fixedarray"}


def props(p, i):
    e = p.exports[i]
    raw = p.raw[e["offset"]:e["offset"] + e["size"]]
    pos = 0
    out = []
    # UObject with RF_HasStack has a state frame first; emitter sub-objects normally don't.
    while pos < len(raw):
        n, pos = _compact(raw, pos)
        name = p.names[n] if 0 <= n < len(p.names) else f"?{n}"
        if name == "None":
            break
        info = raw[pos]; pos += 1
        t = info & 0x0F
        sz_code = (info >> 4) & 7
        array_flag = info & 0x80
        struct_name = None
        if t == 10:
            s, pos = _compact(raw, pos)
            struct_name = p.names[s]
        size = {0: 1, 1: 2, 2: 4, 3: 12, 4: 16}.get(sz_code)
        if size is None:
            if sz_code == 5:
                size = raw[pos]; pos += 1
            elif sz_code == 6:
                size = struct.unpack_from("<H", raw, pos)[0]; pos += 2
            else:
                size = struct.unpack_from("<I", raw, pos)[0]; pos += 4
        if array_flag and t != 3:
            idx = raw[pos]; pos += 1
            if idx >= 0x80:
                pos += 1 if idx < 0xC0 else 3
        val = raw[pos:pos + size]
        if t == 3:
            shown = bool(array_flag)
            size = 0
        elif t == 4 and size == 4:
            shown = round(struct.unpack("<f", val)[0], 3)
        elif t == 2 and size == 4:
            shown = struct.unpack("<i", val)[0]
        elif t == 1 and size == 1:
            shown = val[0]
        elif t in (5, 8):
            o, _ = _compact(val, 0)
            shown = ("export " + p.exports[o - 1]["name"]) if o > 0 else ("import " + p.imports[-o - 1][3]) if o < 0 else "None"
        elif t == 6:
            o, _ = _compact(val, 0)
            shown = p.names[o]
        elif t == 10 and struct_name in ("Range", "RangeVector", "Vector") and size in (8, 12, 24):
            shown = [round(x, 2) for x in struct.unpack(f"<{size // 4}f", val)]
        else:
            shown = val.hex()[:48]
        out.append((name, TYPES.get(t, t), struct_name, shown))
        pos += size
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    p = upackage.Package(argv[0])
    for name in argv[1:]:
        i = p.find_export(name)
        if i is None:
            print(f"no export {name}")
            continue
        for j in [i] + [k for k, e in enumerate(p.exports) if e["outer"] == i + 1]:
            e = p.exports[j]
            if p.class_name(e["class"]) in ("TextBuffer", "Class"):
                continue
            print(f"== {e['name']} ({p.class_name(e['class'])})")
            for row in props(p, j):
                print("  ", row)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
