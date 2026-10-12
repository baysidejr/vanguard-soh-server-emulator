"""Terrain surface height for a Vanguard chunk (.vgr), read from the chunk file.

Usage:
    python terrain.py chunk_n19_12 [x y ...]     # heights at points
    python terrain_height.py chunk_n19_12 --grid 5      # NxN grid over the chunk
    python terrain_height.py chunk_n19_12 --spawns      # a few flat land points

    from terrain import Terrain
    t = Terrain(r"C:\\Vanguard EMU\\Assets\\Maps\\chunk_n19_12.vgr")
    z = t.height(x, y)          # world z of the terrain surface (None if off-terrain)

Model (checked against the chunk's 775 StaticMeshActors: median |actor.z - terrain z| ~ 12 units,
509/775 within 500 units):
    heightmap  = TerrainInfo.TerrainMap  (Texture, Format 10 = G16, 512x512 u16, mip 0 = the
                 last 512*512*2+10 bytes of the export; the trailing 10 bytes are USize,VSize,UBits,VBits)
    TerrainScale = class default (400, 400, 10)   (no per-level override in chunk_n19_12)
    Location     = TerrainInfo0.Location = (0, 0, -100000)
    world x = Location.x + (u - 256) * 400      (u = column, 0..511)
    world y = Location.y + (v - 256) * 400      (v = row)
    world z = Location.z + h * 10               (h = raw u16; NOT the stock UE2 (h-32768)/256 form)
Add the pawn's CollisionHeight (plus a small margin) to get a spawn z.
"""
import os
import struct
import sys

from upackage import Package, _compact

MAPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Assets", "Maps")
DEFAULT_SCALE = (400.0, 400.0, 10.0)  # Engine.u TerrainInfo defaults


def _props(p, raw, pos):
    """Tagged UE2 properties -> {name: (type, struct_name, raw_value)} (first array element only)."""
    out = {}
    sizes = [1, 2, 4, 12, 16]
    while True:
        n, pos = _compact(raw, pos)
        name = p.names[n]
        if name == "None":
            return out
        info = raw[pos]
        pos += 1
        t, si, arr = info & 0xF, (info >> 4) & 7, info & 0x80
        sname = None
        if t == 10:
            s, pos = _compact(raw, pos)
            sname = p.names[s]
        if si < 5:
            size = sizes[si]
        elif si == 5:
            size = raw[pos]; pos += 1
        elif si == 6:
            size = struct.unpack_from("<H", raw, pos)[0]; pos += 2
        else:
            size = struct.unpack_from("<I", raw, pos)[0]; pos += 4
        if arr and t != 3:
            b0 = raw[pos]
            pos += 1 if b0 < 0x80 else (2 if b0 < 0xC0 else 4)
        out.setdefault(name, (t, sname, raw[pos:pos + size]))
        pos += size


class Terrain:
    def __init__(self, path):
        p = Package(path)
        ti = next(i for i, e in enumerate(p.exports) if p.class_name(e["class"]) == "TerrainInfo")
        e = p.exports[ti]
        raw = p.raw[e["offset"]:e["offset"] + e["size"]]
        # Actor exports in these levels start with a 17-byte state/stack header; find the
        # TerrainMap tag rather than hard-coding it.
        tm = p.names.index("TerrainMap")
        start = next(j for j in range(64) if _compact(raw, j)[0] == tm and raw[_compact(raw, j)[1]] & 0xF == 5)
        props = _props(p, raw, start)
        self.location = struct.unpack("<3f", props["Location"][2]) if "Location" in props else (0.0, 0.0, 0.0)
        self.scale = struct.unpack("<3f", props["TerrainScale"][2]) if "TerrainScale" in props else DEFAULT_SCALE
        idx = _compact(props["TerrainMap"][2], 0)[0]
        he = p.exports[idx - 1]
        hraw = p.raw[he["offset"]:he["offset"] + he["size"]]
        self.w, self.h = struct.unpack_from("<II", hraw, len(hraw) - 10)
        n = self.w * self.h
        self.data = struct.unpack(f"<{n}H", hraw[-10 - 2 * n:-10])

    def raw_at(self, u, v):
        return self.data[v * self.w + u]

    def height(self, x, y):
        """Bilinear terrain z at world (x, y); None outside the heightmap."""
        u = (x - self.location[0]) / self.scale[0] + self.w / 2
        v = (y - self.location[1]) / self.scale[1] + self.h / 2
        if not (0 <= u < self.w - 1 and 0 <= v < self.h - 1):
            return None
        u0, v0 = int(u), int(v)
        fu, fv = u - u0, v - v0
        h = (self.raw_at(u0, v0) * (1 - fu) * (1 - fv) + self.raw_at(u0 + 1, v0) * fu * (1 - fv)
             + self.raw_at(u0, v0 + 1) * (1 - fu) * fv + self.raw_at(u0 + 1, v0 + 1) * fu * fv)
        return self.location[2] + h * self.scale[2]

    def extent(self):
        hx, hy = self.w / 2 * self.scale[0], self.h / 2 * self.scale[1]
        return (self.location[0] - hx, self.location[1] - hy, self.location[0] + hx, self.location[1] + hy)

    def flat_land(self, min_z=200.0, step=8, radius=2, max_slope=60.0, count=10):
        """Points above min_z whose neighbourhood varies by less than max_slope units."""
        found = []
        for v in range(radius, self.h - radius, step):
            for u in range(radius, self.w - radius, step):
                zs = [self.location[2] + self.raw_at(u + a, v + b) * self.scale[2]
                      for a in range(-radius, radius + 1) for b in range(-radius, radius + 1)]
                if min(zs) > min_z and max(zs) - min(zs) < max_slope:
                    x = self.location[0] + (u - self.w / 2) * self.scale[0]
                    y = self.location[1] + (v - self.h / 2) * self.scale[1]
                    found.append((round(abs(x) + abs(y)), x, y, zs[len(zs) // 2]))
        found.sort()
        return [(x, y, z) for _, x, y, z in found[:count]]


def main(argv):
    name = argv[1] if len(argv) > 1 else "chunk_n19_12"
    path = name if os.path.exists(name) else os.path.join(MAPS, name + ".vgr")
    t = Terrain(path)
    print(f"{os.path.basename(path)}: Location {t.location} TerrainScale {t.scale} heightmap {t.w}x{t.h} "
          f"extent {t.extent()}")
    args = argv[2:]
    if args[:1] == ["--grid"]:
        n = int(args[1]) if len(args) > 1 else 5
        x0, y0, x1, y1 = t.extent()
        for j in range(n):
            y = y0 + (y1 - y0) * (j + 0.5) / n
            row = []
            for i in range(n):
                x = x0 + (x1 - x0) * (i + 0.5) / n
                row.append(f"({x:8.0f},{y:8.0f}) z={t.height(x, y):8.0f}")
            print("  ".join(row))
    elif args[:1] == ["--spawns"]:
        for x, y, z in t.flat_land():
            print(f"flat land: x={x:.0f} y={y:.0f} terrain z={z:.0f}")
    else:
        for i in range(0, len(args) - 1, 2):
            x, y = float(args[i]), float(args[i + 1])
            print(f"({x}, {y}) terrain z = {t.height(x, y)}")


if __name__ == "__main__":
    main(sys.argv)
