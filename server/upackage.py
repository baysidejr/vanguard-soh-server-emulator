"""Minimal reader for Unreal Engine 2 package files (.u, .vgr, ...).

The server never ships game data, but it needs to agree with the client on
object indices. In UE2 the server announces each package with a control-channel
"USES" line (GUID, generation, ...). Both sides then number every exported
object: package N's objects start after the export counts of packages 0..N-1.
The GUID and export counts are read from the player's own client files.

Vanguard packages are file version 129, licensee 35.
"""

import struct

PACKAGE_TAG = 0x9E2A83C1


def _compact(data, pos):
    b = data[pos]
    pos += 1
    neg = b & 0x80
    v = b & 0x3F
    shift = 6
    more = b & 0x40
    while more:
        b = data[pos]
        pos += 1
        v |= (b & 0x7F) << shift
        shift += 7
        more = b & 0x80
    return (-v if neg else v), pos


class Package:
    def __init__(self, path):
        with open(path, "rb") as f:
            data = f.read()
        self.path = path
        self.raw = data
        self.size = len(data)
        (tag, self.version, self.licensee, self.flags, name_count, name_off, export_count,
         export_off, import_count, import_off) = struct.unpack_from("<IHHIIIIIII", data, 0)
        if tag != PACKAGE_TAG:
            raise ValueError(f"{path}: not an Unreal package")
        self.guid = data[0x24:0x34]
        gen_count = struct.unpack_from("<I", data, 0x34)[0]
        self.generations = [struct.unpack_from("<II", data, 0x38 + 8 * i) for i in range(gen_count)]

        self.names = []
        pos = name_off
        for _ in range(name_count):
            n, pos = _compact(data, pos)
            self.names.append(data[pos:pos + n].rstrip(b"\0").decode("latin-1"))
            pos += n + 4  # chars + u32 flags

        self.imports = []
        pos = import_off
        for _ in range(import_count):
            class_pkg, pos = _compact(data, pos)
            class_name, pos = _compact(data, pos)
            outer = struct.unpack_from("<i", data, pos)[0]
            pos += 4
            name, pos = _compact(data, pos)
            self.imports.append((self.names[class_pkg], self.names[class_name], outer, self.names[name]))

        self.exports = []
        pos = export_off
        for _ in range(export_count):
            cls, pos = _compact(data, pos)
            sup, pos = _compact(data, pos)
            outer = struct.unpack_from("<i", data, pos)[0]
            pos += 4
            name, pos = _compact(data, pos)
            flags = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            size, pos = _compact(data, pos)
            offset = 0
            if size > 0:
                offset, pos = _compact(data, pos)
            self.exports.append({"class": cls, "super": sup, "outer": outer,
                                 "name": self.names[name], "flags": flags,
                                 "size": size, "offset": offset})

    @property
    def guid_text(self):
        """FGuid as UE2 prints it: four u32s in hex."""
        return "".join(f"{v:08X}" for v in struct.unpack("<4I", self.guid))

    def class_name(self, index):
        """Class of an export, from its ClassIndex (0 = UClass itself)."""
        if index == 0:
            return "Class"
        if index < 0:
            return self.imports[-index - 1][3]
        return self.exports[index - 1]["name"]

    def find_export(self, name, class_name=None):
        for i, e in enumerate(self.exports):
            if e["name"].lower() == name.lower() and (
                    class_name is None or self.class_name(e["class"]) == class_name):
                return i
        return None


    def actor_location(self, index):
        """Location of an actor export, from its tagged properties (a Vector
        StructProperty: name, info byte 0x3A, struct name, 3 floats)."""
        if "Location" not in self.names or "Vector" not in self.names:
            return None
        loc, vec = self.names.index("Location"), self.names.index("Vector")
        e = self.exports[index]
        raw = self.raw[e["offset"]:e["offset"] + e["size"]]
        for j in range(len(raw) - 16):
            n, pos = _compact(raw, j)
            if n == loc and raw[pos] == 0x3A:
                s, pos2 = _compact(raw, pos + 1)
                if s == vec and pos2 + 12 <= len(raw):
                    return struct.unpack_from("<3f", raw, pos2)
        return None

    def player_starts(self):
        return [self.actor_location(i) for i, e in enumerate(self.exports)
                if self.class_name(e["class"]) == "PlayerStart"]


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        p = Package(path)
        print(f"{path}: ver {p.version}/{p.licensee} flags {p.flags:#x} guid {p.guid_text} "
              f"gens {p.generations} names {len(p.names)} imports {len(p.imports)} exports {len(p.exports)}")
