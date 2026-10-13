"""Collidable obstacles of a chunk (rocks, trees, walls, tents ...) so server-driven NPC
movement can steer around them instead of walking through them.

    python obstacles.py chunk_n19_12 [x y]   -> obstacle count, and the ones nearest (x, y)

    from obstacles import obstacles, blocked, clear_path
    obs = obstacles("chunk_n19_12")          # [(x, y, radius, z_bottom, z_top), ...]
    blocked(obs, x, y, z)                    # point (NPC of radius 40 at height z) inside one?
    clear_path(obs, (x0, y0, z0), (x1, y1, z1))

Where the data comes from (all read from the player's client install, nothing is copied):
  * Assets/Maps/<chunk>.vgr: StaticMeshActor exports (StaticMesh, Location, Rotation, DrawScale,
    DrawScale3D, PrePivot, bCollideActors, bBlockActors) and CompoundObject exports
    (PrefabName + Location/Rotation/DrawScale). Most chunks place almost everything through
    CompoundObjects; only ~1 in 6 chunks has StaticMeshActors of its own.
  * Assets/Archives/binaryprefabs.sgo: "SGOA" + u32 2, then ~19.5k UE2 packages (tag 9E2A83C1,
    ver 128) laid end to end, one per prefab. A prefab's package holds the name
    "<PrefabName>exportBinaryPrefab<N>" and exports named "<PrefabName>StaticMeshActor<N>",
    "<PrefabName>CompoundObject<N>" (nested prefabs) ... with prefab-local Locations.
  * Assets/Meshes/<package>.usx: the StaticMesh named by the actor's import (the import's
    outermost package is the file name; groups are ignored, mesh names are unique).
    UStaticMesh = UPrimitive: tagged properties, then BoundingBox (min vec3, max vec3, u8
    valid) and BoundingSphere (vec3, f32 W) -- verified (e.g. MartokRock008: box +-632 x
    +-750 x +-321, sphere W 1033).
    Pawn collision (UE2 rules, nonzero-extent check): the mesh blocks if any material entry of
    the "Collision" array has "Enable Collision" true (per-poly collision) or it has a
    CollisionModel and UseSimpleBoxCollision is not false. The CollisionModel object
    reference sits after the lazy-array header block: the bytes 0D 00 00 00, 8 zero bytes,
    then a compact index of a Model export (0 = none). Big Martok rocks have per-poly
    collision off but a collision Model; weapons/skulls/bone piles have neither.

Shape: every obstacle is a circle in x/y plus a z range. The mesh box is transformed by the
actor (and enclosing prefabs), z range = world AABB of the 8 corners, footprint = the box in
the actor's yaw frame. Square-ish footprints become one circle (radius = longer half extent);
elongated ones (walls, fences, logs) become a row of circles of the short half extent.
Meshes named *tree* (SpeedTrees) are one trunk circle at the actor pivot (TRUNK_FRACTION of the
canopy half extent, 40..TRUNK_MAX), since their box is mostly canopy.

Filtered out (judgement, see the constants): bCollideActors/bBlockActors false; meshes with no
pawn collision; footprints under MIN_RADIUS (pebbles, bones) or thinner than MIN_THICKNESS and shorter than
THIN_MAX_LENGTH (weapons/poles: these do have collision Models); circles over
MAX_RADIUS (cliffs/rock formations whose box is mostly empty air or walkable slope); shapes
under MIN_HEIGHT tall or whose top is less than MIN_ABOVE_GROUND above the terrain (decals,
rugs, water planes, things NPCs step over or walk on); missing mesh packages and meshes
without a valid BoundingBox (valid byte != 1 -- a few SpeedTree meshes use another layout).

Results are cached in memory only (server/cache is not git-ignored, so nothing is written).
"""
import bisect
import functools
import math
import os
import re
import struct
import sys

from upackage import Package, PACKAGE_TAG, _compact
import terrain

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Assets")
MAPS = os.path.join(ASSETS, "Maps")
MESHES = os.path.join(ASSETS, "Meshes")
PREFABS = os.path.join(ASSETS, "Archives", "binaryprefabs.sgo")

MIN_RADIUS = 40.0         # longer half extent below this: too small to matter
MAX_RADIUS = 3000.0       # circle radius above this: cliff/rock formation, not a steerable obstacle
MIN_THICKNESS = 10.0      # thinner than this (weapons, poles, banners on racks) ...
THIN_MAX_LENGTH = 300.0   # ... and shorter than this: ignored
MIN_HEIGHT = 50.0         # flatter than this: walk over it
MIN_ABOVE_GROUND = 50.0   # top less than this above the terrain: sunk in / walkable
TRUNK_FRACTION = 0.12     # trees: trunk radius = this * canopy half extent ...
TRUNK_MAX = 150.0         # ... capped
MAX_PREFAB_DEPTH = 8
GRID = 1024.0             # bucket size of the lookup index

_SIZES = (1, 2, 4, 12, 16)


# ---------------------------------------------------------------- package helpers

class _MemPackage(Package):
    """A Package parsed from bytes (packages embedded in binaryprefabs.sgo); same header
    layout as upackage.Package, offsets relative to the start of `data`."""

    def __init__(self, data, path):
        self.path, self.raw, self.size = path, data, len(data)
        (tag, self.version, self.licensee, self.flags, name_count, name_off, export_count,
         export_off, import_count, import_off) = struct.unpack_from("<IHHIIIIIII", data, 0)
        if tag != PACKAGE_TAG:
            raise ValueError(f"{path}: not an Unreal package")
        self.guid = data[0x24:0x34]
        self.generations = []
        self.names = []
        pos = name_off
        for _ in range(name_count):
            n, pos = _compact(data, pos)
            self.names.append(data[pos:pos + n].rstrip(b"\0").decode("latin-1"))
            pos += n + 4
        self.imports = []
        pos = import_off
        for _ in range(import_count):
            cp, pos = _compact(data, pos)
            cn, pos = _compact(data, pos)
            outer = struct.unpack_from("<i", data, pos)[0]
            name, pos = _compact(data, pos + 4)
            self.imports.append((self.names[cp], self.names[cn], outer, self.names[name]))
        self.exports = []
        pos = export_off
        for _ in range(export_count):
            cls, pos = _compact(data, pos)
            sup, pos = _compact(data, pos)
            outer = struct.unpack_from("<i", data, pos)[0]
            name, pos = _compact(data, pos + 4)
            flags = struct.unpack_from("<I", data, pos)[0]
            size, pos = _compact(data, pos + 4)
            offset = 0
            if size > 0:
                offset, pos = _compact(data, pos)
            self.exports.append({"class": cls, "super": sup, "outer": outer, "name": self.names[name],
                                 "flags": flags, "size": size, "offset": offset})


def _tagged(p, raw, pos):
    """Strict UE2 tagged-property parse -> ({name: (type, struct, bytes, bool)}, end).
    Raises ValueError on anything that does not look like a clean property block."""
    out = {}
    names = p.names
    while True:
        n, pos = _compact(raw, pos)
        if not 0 <= n < len(names):
            raise ValueError("name")
        name = names[n]
        if name == "None":
            return out, pos
        info = raw[pos]
        pos += 1
        t, si, arr = info & 0xF, (info >> 4) & 7, info & 0x80
        if t == 0:
            raise ValueError("type")
        sname = None
        if t == 10:
            s, pos = _compact(raw, pos)
            if not 0 <= s < len(names):
                raise ValueError("struct")
            sname = names[s]
        if si < 5:
            size = _SIZES[si]
        elif si == 5:
            size = raw[pos]; pos += 1
        elif si == 6:
            size = struct.unpack_from("<H", raw, pos)[0]; pos += 2
        else:
            size = struct.unpack_from("<I", raw, pos)[0]; pos += 4
        idx = 0
        if arr and t != 3:
            b0 = raw[pos]
            idx = b0 if b0 < 0x80 else -1
            pos += 1 if b0 < 0x80 else (2 if b0 < 0xC0 else 4)
        if pos + size > len(raw):
            raise ValueError("size")
        if idx == 0:
            out.setdefault(name, (t, sname, raw[pos:pos + size], bool(arr)))
        pos += size


def _actor_props(p, e):
    """Decoded properties of an actor export. Vanguard actors start with a variable-length
    state header (8282ffff...): take the first offset that parses cleanly and has Tag."""
    raw = p.raw[e["offset"]:e["offset"] + e["size"]]
    for j in range(min(64, len(raw))):
        try:
            o, _ = _tagged(p, raw, j)
        except (ValueError, IndexError, struct.error):
            continue
        if "Tag" in o:
            out = {}
            for k, v in o.items():
                try:
                    out[k] = _value(p, v)
                except (IndexError, struct.error):
                    out[k] = v[2]
            return out
    return {}


def _value(p, v):
    t, sname, b, flag = v
    if t == 3:
        return flag
    if sname == "Vector" and len(b) == 12:
        return struct.unpack("<3f", b)
    if sname == "Rotator" and len(b) == 12:
        return struct.unpack("<3i", b)
    if t == 4 and len(b) == 4:
        return struct.unpack("<f", b)[0]
    if t == 2 and len(b) == 4:
        return struct.unpack("<i", b)[0]
    if t in (5, 6) and b:
        v = _compact(b, 0)[0]
        return p.names[v] if t == 6 and 0 <= v < len(p.names) else v
    if t == 13 and b:  # StrProperty: compact length + chars
        n, pos = _compact(b, 0)
        return b[pos:pos + abs(n)].rstrip(b"\0").decode("latin-1")
    return b


# ---------------------------------------------------------------- meshes

def _bool_true(p, raw, pos, wanted):
    """Is property `wanted` true in a tagged struct block?"""
    o, end = _tagged(p, raw, pos)
    v = o.get(wanted)
    return bool(v and v[0] == 3 and v[3]), end


def _mesh_info(p, idx):
    """(min, max, blocks_pawns) of StaticMesh export idx (0-based) of package p."""
    e = p.exports[idx]
    raw = p.raw[e["offset"]:e["offset"] + e["size"]]
    o, pos = _tagged(p, raw, 0)
    mn = struct.unpack_from("<3f", raw, pos)
    mx = struct.unpack_from("<3f", raw, pos + 12)
    if raw[pos + 24] != 1 or not all(-1e6 < v < 1e6 for v in mn + mx) or \
            any(a > b for a, b in zip(mn, mx)):
        # e.g. some SpeedTree meshes (MartokTree001_dead01, StoneTree001) use another layout
        raise ValueError("no valid BoundingBox")
    per_poly = False
    col = o.get("Collision")
    if col is not None:
        b = col[2]
        try:
            n, q = _compact(b, 0)
            for _ in range(n):
                hit, q = _bool_true(p, b, q, "Enable Collision")
                per_poly = per_poly or hit
        except (ValueError, IndexError):
            per_poly = True  # unknown layout: assume it collides
    has_model = None
    k = pos + 41
    while True:
        k = raw.find(b"\x0d\x00\x00\x00" + b"\x00" * 8, k, pos + 2000)
        if k < 0:
            break
        v = _compact(raw, k + 12)[0]
        if v == 0 or (0 < v <= len(p.exports) and p.class_name(p.exports[v - 1]["class"]) == "Model"):
            has_model = v > 0
            break
        k += 1
    simple_box = o.get("UseSimpleBoxCollision")
    simple_box = True if simple_box is None else simple_box[3]
    if has_model is None:      # header not found: be conservative
        blocks = True
    else:
        blocks = per_poly or (has_model and simple_box)
    return mn, mx, blocks


class _MeshLib:
    def __init__(self):
        self.files = {f.lower(): f for f in os.listdir(MESHES)} if os.path.isdir(MESHES) else {}
        self.pkgs = {}
        self.info = {}

    def package(self, name):
        if name not in self.pkgs:
            f = self.files.get(name.lower() + ".usx")
            try:
                self.pkgs[name] = Package(os.path.join(MESHES, f)) if f else None
            except (OSError, ValueError, struct.error):
                self.pkgs[name] = None
        return self.pkgs[name]

    def lookup(self, p, ref):
        """(mesh name, (min, max, blocks)) for an object reference in package p, or (name, None)."""
        if ref > 0:  # mesh stored in the level / prefab package itself
            key = (id(p), ref)
            if key not in self.info:
                try:
                    self.info[key] = _mesh_info(p, ref - 1)
                except (ValueError, IndexError, struct.error):
                    self.info[key] = None
            return p.exports[ref - 1]["name"], self.info[key]
        if ref == 0 or -ref > len(p.imports):
            return None, None
        im = p.imports[-ref - 1]
        name, outer = im[3], im[2]
        while outer < 0:
            top = p.imports[-outer - 1]
            outer = top[2]
            pkg_name = top[3]
        if im[2] >= 0:
            return name, None
        key = (pkg_name.lower(), name.lower())
        if key not in self.info:
            q = self.package(pkg_name)
            info = None
            if q is not None:
                i = q.find_export(name, "StaticMesh")
                if i is not None:
                    try:
                        info = _mesh_info(q, i)
                    except (ValueError, IndexError, struct.error):
                        info = None
            self.info[key] = info
        return name, self.info[key]


# ---------------------------------------------------------------- prefabs

@functools.lru_cache(maxsize=1)
def _prefab_archive(path=PREFABS):
    """(bytes, sorted package starts, {prefab name lower: start}) of binaryprefabs.sgo."""
    if not os.path.exists(path):
        return b"", [], {}
    with open(path, "rb") as f:
        d = f.read()
    tag = struct.pack("<I", PACKAGE_TAG)
    starts = [m.start() for m in re.finditer(re.escape(tag), d)]
    index = {}
    for m in re.finditer(rb"exportBinaryPrefab\d*\x00", d):
        i = m.start()
        j = i
        while j > i - 300 and 32 <= d[j - 1] < 127:
            j -= 1
        for k in range(j - 2, i):  # compact length (1 or 2 bytes) of this name entry
            n, q = _compact(d, k)
            if n == m.end() - q and n > 0:
                name = d[q:i].decode("latin-1").lower()
                s = starts[bisect.bisect_right(starts, i) - 1]
                index.setdefault(name, s)
                break
    return d, starts, index


@functools.lru_cache(maxsize=4096)
def _prefab_package(name):
    d, starts, index = _prefab_archive()
    s = index.get(name.lower())
    if s is None:
        return None
    n = bisect.bisect_right(starts, s)
    end = starts[n] if n < len(starts) else len(d)
    try:
        return _MemPackage(d[s:end], "prefab:" + name)
    except (ValueError, IndexError, struct.error):
        return None


# ---------------------------------------------------------------- transforms

def _rot(pitch, yaw, roll):
    """UE2 FRotationMatrix (columns = world directions of local X, Y, Z)."""
    k = 2 * math.pi / 65536.0
    sp, cp = math.sin(pitch * k), math.cos(pitch * k)
    sy, cy = math.sin(yaw * k), math.cos(yaw * k)
    sr, cr = math.sin(roll * k), math.cos(roll * k)
    ax = (cp * cy, cp * sy, sp)
    ay = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    az = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    return [[ax[i], ay[i], az[i]] for i in range(3)]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _apply(m, v):
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))


IDENTITY = ([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], (0.0, 0.0, 0.0))


def _actor_xform(o):
    """Actor LocalToWorld = T(Location) * R(Rotation) * S(DrawScale*DrawScale3D) * T(-PrePivot)."""
    loc = o.get("Location", (0.0, 0.0, 0.0))
    rot = o.get("Rotation", (0, 0, 0))
    s = o.get("DrawScale", 1.0)
    s3 = o.get("DrawScale3D", (1.0, 1.0, 1.0))
    pp = o.get("PrePivot", (0.0, 0.0, 0.0))
    if not isinstance(loc, tuple):
        loc = (0.0, 0.0, 0.0)
    if not isinstance(rot, tuple):
        rot = (0, 0, 0)
    if not isinstance(s, float):
        s = 1.0
    if not isinstance(s3, tuple):
        s3 = (1.0, 1.0, 1.0)
    if not isinstance(pp, tuple):
        pp = (0.0, 0.0, 0.0)
    r = _rot(*rot)
    m = [[r[i][j] * s * s3[j] for j in range(3)] for i in range(3)]
    t = _apply(m, (-pp[0], -pp[1], -pp[2]))
    return m, (t[0] + loc[0], t[1] + loc[1], t[2] + loc[2])


def _compose(parent, child):
    pm, pt = parent
    cm, ct = child
    t = _apply(pm, ct)
    return _mul(pm, cm), (t[0] + pt[0], t[1] + pt[1], t[2] + pt[2])


# ---------------------------------------------------------------- shapes

def _shapes(xf, mn, mx):
    """Circles [(x, y, r)] + (z_bottom, z_top) + longer half extent of a transformed box."""
    m, t = xf
    corners = [_apply(m, (a, b, c)) for a in (mn[0], mx[0]) for b in (mn[1], mx[1]) for c in (mn[2], mx[2])]
    corners = [(p[0] + t[0], p[1] + t[1], p[2] + t[2]) for p in corners]
    zb, zt = min(p[2] for p in corners), max(p[2] for p in corners)
    yaw = math.atan2(m[1][0], m[0][0]) if abs(m[0][0]) + abs(m[1][0]) > 1e-6 else 0.0
    c, s = math.cos(yaw), math.sin(yaw)
    us = [p[0] * c + p[1] * s for p in corners]
    vs = [-p[0] * s + p[1] * c for p in corners]
    cu, cv = (min(us) + max(us)) / 2, (min(vs) + max(vs)) / 2
    eu, ev = (max(us) - min(us)) / 2, (max(vs) - min(vs)) / 2
    long_, short = max(eu, ev), min(eu, ev)
    if long_ <= 1.5 * short:
        circles = [(cu, cv, long_)]
    else:
        n = int(math.ceil(long_ / short)) if short > 0 else 1
        n = max(2, min(n, 64))
        r = max(short, long_ / n)
        span = long_ - r
        circles = []
        for i in range(n):
            d = -span + 2 * span * i / (n - 1)
            circles.append((cu + d, cv, r) if eu >= ev else (cu, cv + d, r))
    out = [(u * c - v * s, u * s + v * c, r) for u, v, r in circles]
    return out, zb, zt, long_


class ObstacleList(list):
    """list of (x, y, radius, z_bottom, z_top) with a grid index and per-entry mesh names."""

    def __init__(self, items=(), names=None):
        super().__init__(items)
        self.names = list(names) if names is not None else [""] * len(self)
        self.grid = {}
        self.max_r = 0.0
        for i, (x, y, r, _zb, _zt) in enumerate(self):
            self.max_r = max(self.max_r, r)
            for gx in range(int(math.floor((x - r) / GRID)), int(math.floor((x + r) / GRID)) + 1):
                for gy in range(int(math.floor((y - r) / GRID)), int(math.floor((y + r) / GRID)) + 1):
                    self.grid.setdefault((gx, gy), []).append(i)


def _is_tree(name):
    n = (name or "").lower()
    return "tree" in n and "street" not in n


def _collect(p, xf, ml, out, depth, stats):
    for e in p.exports:
        cls = p.class_name(e["class"])
        if cls == "CompoundObject":
            if depth >= MAX_PREFAB_DEPTH:
                continue
            o = _actor_props(p, e)
            name = o.get("PrefabName")
            if not isinstance(name, str):
                continue
            q = _prefab_package(name)
            if q is None:
                stats["missing prefab"] = stats.get("missing prefab", 0) + 1
                continue
            stats["prefabs"] = stats.get("prefabs", 0) + 1
            _collect(q, _compose(xf, _actor_xform(o)), ml, out, depth + 1, stats)
        elif "StaticMesh" in cls or cls == "BlockingVolume":
            o = _actor_props(p, e)
            if o.get("bCollideActors") is False or o.get("bBlockActors") is False:
                stats["no collision (actor)"] = stats.get("no collision (actor)", 0) + 1
                continue
            if cls == "BlockingVolume":
                ref = o.get("Brush")
                if not isinstance(ref, int) or ref <= 0:
                    continue
                be = p.exports[ref - 1]
                raw = p.raw[be["offset"]:be["offset"] + be["size"]]
                try:
                    _, pos = _tagged(p, raw, 0)
                except (ValueError, IndexError):
                    continue
                mn, mx = struct.unpack_from("<3f", raw, pos), struct.unpack_from("<3f", raw, pos + 12)
                name, info = "BlockingVolume", (mn, mx, True)
            else:
                ref = o.get("StaticMesh")
                if not isinstance(ref, int):
                    continue
                name, info = ml.lookup(p, ref)
            if info is None:
                stats["missing mesh/bounds"] = stats.get("missing mesh/bounds", 0) + 1
                continue
            mn, mx, blocks = info
            if not blocks:
                stats["no collision (mesh)"] = stats.get("no collision (mesh)", 0) + 1
                continue
            wxf = _compose(xf, _actor_xform(o))
            circles, zb, zt, long_ = _shapes(wxf, mn, mx)
            if _is_tree(name):
                # the box is mostly canopy: block only a trunk at the actor's pivot
                circles = [(wxf[1][0], wxf[1][1], max(MIN_RADIUS, min(TRUNK_MAX, TRUNK_FRACTION * long_)))]
            out.append((name, (circles, zb, zt, long_)))


@functools.lru_cache(maxsize=16)
def _build(chunk, maps=MAPS):
    path = os.path.join(maps, chunk + ".vgr")
    p = Package(path)
    try:
        t = terrain.Terrain(path)
    except (StopIteration, ValueError, KeyError, IndexError, struct.error):
        t = None
    stats = {}
    raw = []
    _collect(p, IDENTITY, _MeshLib(), raw, 0, stats)
    items, names = [], []
    for name, (circles, zb, zt, long_) in raw:
        if long_ < MIN_RADIUS:
            stats["too small"] = stats.get("too small", 0) + 1
            continue
        if circles[0][2] < MIN_THICKNESS and long_ < THIN_MAX_LENGTH:
            stats["too thin"] = stats.get("too thin", 0) + 1
            continue
        if zt - zb < MIN_HEIGHT:
            stats["too flat"] = stats.get("too flat", 0) + 1
            continue
        if circles[0][2] > MAX_RADIUS:
            stats["too big"] = stats.get("too big", 0) + 1
            continue
        kept = False
        for x, y, r in circles:
            g = t.height(x, y) if t is not None else None
            if g is not None and zt < g + MIN_ABOVE_GROUND:
                continue
            items.append((x, y, r, zb, zt))
            names.append(name)
            kept = True
        if not kept:
            stats["below ground"] = stats.get("below ground", 0) + 1
    stats["kept"] = len(items)
    return ObstacleList(items, names), stats


def obstacles(chunk_name):
    """[(x, y, radius, z_bottom, z_top)] blocking obstacles of a chunk (an ObstacleList:
    also has .names and a grid index). Empty if the chunk file is missing."""
    try:
        return _build(chunk_name)[0]
    except OSError:
        return ObstacleList()


def _candidates(obs, x, y, radius):
    grid = getattr(obs, "grid", None)
    if grid is None:
        return obs
    seen = set()
    out = []
    for gx in range(int(math.floor((x - radius) / GRID)), int(math.floor((x + radius) / GRID)) + 1):
        for gy in range(int(math.floor((y - radius) / GRID)), int(math.floor((y + radius) / GRID)) + 1):
            for i in grid.get((gx, gy), ()):
                if i not in seen:
                    seen.add(i)
                    out.append(obs[i])
    return out


def hits(obs, x, y, z=None, radius=40.0):
    """Obstacles overlapping an NPC of `radius` at (x, y); z (None = ignore height) must lie
    within [z_bottom, z_top]."""
    out = []
    for ox, oy, r, zb, zt in _candidates(obs, x, y, radius):
        rr = r + radius
        dx, dy = x - ox, y - oy
        if dx * dx + dy * dy < rr * rr and (z is None or zb <= z <= zt):
            out.append((ox, oy, r, zb, zt))
    return out


def blocked(obs, x, y, z=None, radius=40.0):
    """True if an NPC of `radius` standing at (x, y) with height z is inside an obstacle."""
    return bool(hits(obs, x, y, z, radius))


def clear_path(obs, a, b, step=50.0, radius=40.0, ignore_start=True):
    """True if the segment a -> b ((x, y) or (x, y, z); z is interpolated) can be walked
    without entering an obstacle. Samples every `step` units including b. With ignore_start,
    obstacles that already contain a are ignored so an NPC caught in an over-sized box can
    still walk out of it."""
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    az = a[2] if len(a) > 2 else None
    bz = b[2] if len(b) > 2 else az
    skip = set(hits(obs, ax, ay, az, radius)) if ignore_start else set()
    d = math.hypot(bx - ax, by - ay)
    n = max(1, int(math.ceil(d / step)))
    for i in range(1 if ignore_start else 0, n + 1):
        f = i / n
        z = None if az is None or bz is None else az + (bz - az) * f
        for h in hits(obs, ax + (bx - ax) * f, ay + (by - ay) * f, z, radius):
            if h not in skip:
                return False
    return True


def main(argv):
    chunk = argv[1] if len(argv) > 1 else "chunk_n19_12"
    import time
    t0 = time.time()
    obs, stats = _build(chunk)
    print(f"{chunk}: {len(obs)} obstacle circles in {time.time() - t0:.1f}s  {stats}")
    if len(argv) >= 4:
        x, y = float(argv[2]), float(argv[3])
        n = int(argv[4]) if len(argv) > 4 else 15
        near = sorted(range(len(obs)), key=lambda i: math.hypot(obs[i][0] - x, obs[i][1] - y))[:n]
        for i in near:
            ox, oy, r, zb, zt = obs[i]
            print(f"  d={math.hypot(ox - x, oy - y):7.0f}  ({ox:8.0f},{oy:8.0f}) r={r:5.0f} "
                  f"z {zb:7.0f}..{zt:7.0f}  {obs.names[i]}")
        print("blocked here:", blocked(obs, x, y))


if __name__ == "__main__":
    main(sys.argv)
