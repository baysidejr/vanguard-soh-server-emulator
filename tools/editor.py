"""Content editor: a local web page for editing the server's content files (docs/CONTENT_EDITOR.md).

    python tools/editor.py                 then open http://127.0.0.1:8099
    python tools/editor.py --port 8100 --content server/content

What it does:
  * lists every content file (server/content/*.json and spawns/<chunk>.json) and edits it as JSON;
  * every save is checked first: the JSON must parse and content.validate() must find no problem
    with the change applied (it runs on a copy of the content folder), otherwise nothing is
    written and the problems are shown;
  * the previous version of a saved file goes to server/backups/content/<file>.<time>;
  * a Spawns tab draws a chunk's terrain (from the client's map) with its spawns: click a spawn to
    edit it, drag it to move it, click empty ground to add one, Delete to remove it.
A running server picks the changes up by itself (it reloads the content when the files change).

By default it listens on 127.0.0.1 with no logins: a tool for the person running the server.
--accounts turns on logins with the game server's accounts (server/accounts.py), so others can
help: "contributor" accounts (the default) submit a change as a proposal, which an "admin"
(`python server/accounts.py editor <name> admin`) reviews as a diff and approves or rejects in the
Proposals tab; only admins save directly. Use --host 0.0.0.0 to let others reach it and
--cert / --key for HTTPS (passwords travel in the clear without it).
Uses only the Python standard library.
"""
import argparse
import difflib
import hashlib
import http.server
import secrets
import ssl
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import urllib.parse
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import content as content_mod   # noqa: E402

CONTENT = os.path.join(ROOT, "server", "content")
BACKUPS = os.path.join(ROOT, "server", "backups", "content")
MAPS = os.path.join(ROOT, "Assets", "Maps")
ARCHIVE = os.path.join(ROOT, "crowdsourced", "raw")
ICONS = os.path.join(ROOT, "VGUIAssets", "Global", "Icons")
MESHES = os.path.join(ROOT, "Assets", "Characters", "Meshes")
PROPOSALS = os.path.join(ROOT, "server", "proposals")
SESSION_SECONDS = 12 * 3600
UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor_ui.html")
NAME = re.compile(r"^(spawns/)?[A-Za-z0-9_\-]+\.json$")


def content_files(directory):
    names = sorted(f for f in os.listdir(directory) if f.endswith(".json"))
    spawn_dir = os.path.join(directory, "spawns")
    if os.path.isdir(spawn_dir):
        names += sorted("spawns/" + f for f in os.listdir(spawn_dir) if f.endswith(".json"))
    return names


def safe_path(directory, name):
    if not name or not NAME.match(name):
        raise ValueError(f"bad file name {name!r}")
    return os.path.join(directory, *name.split("/"))


def check(directory, name, text):
    """Problems with saving text as name (empty list = fine): JSON errors, then the content
    validator run on a copy of the folder with the change applied."""
    try:
        json.loads(text)
    except ValueError as e:
        return [f"{name}: not valid JSON: {e}"]
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "content")
        shutil.copytree(directory, copy)
        path = safe_path(copy, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            problems = content_mod.validate(copy)
        except Exception as e:            # a structure the loader can't read at all
            problems = [f"{name}: {type(e).__name__}: {e}"]
    return problems


def spawn_warnings(directory, name, text):
    """Hints (not errors) for a spawn file: a creature standing inside a rock or wall, a patrol
    leg that walks through one (the server's steering would have to go around it)."""
    if not name.startswith("spawns/"):
        return []
    import obstacles as obstacles_mod
    chunk = name[len("spawns/"):-len(".json")]
    try:
        doc = json.loads(text)
        mobs = content_mod.Content(directory).mobs
    except (ValueError, OSError):
        return []
    obs = obstacles_mod.obstacles(chunk)
    if not obs:
        return []
    t = terrain(chunk)
    out = []
    for n, sp in enumerate(doc.get("spawns", []), 1):
        m = mobs.get(sp.get("mob"), {})
        if m.get("prop") or m.get("station") or "x" not in sp:
            continue                                   # scenery is meant to sit among objects
        label = f"spawn {n} ({m.get('name', sp.get('mob'))})"
        z = sp.get("z") if sp.get("z") is not None else (t.height(sp["x"], sp["y"]) if t else None)
        if z is not None and obstacles_mod.blocked(obs, sp["x"], sp["y"], z + 50):
            out.append(f"{label} stands inside an obstacle at ({sp['x']}, {sp['y']})")
        path = sp.get("path") or []
        for a, b in zip(path, path[1:] + path[:1]):
            za = t.height(a[0], a[1]) if t else None
            zb = t.height(b[0], b[1]) if t else None
            pa = (a[0], a[1], za + 50) if za is not None else tuple(a)
            pb = (b[0], b[1], zb + 50) if zb is not None else tuple(b)
            if not obstacles_mod.clear_path(obs, pa, pb):
                out.append(f"{label}: patrol leg {tuple(a)} -> {tuple(b)} crosses an obstacle")
    return out


def save(directory, name, text, backups=BACKUPS):
    """Write text after a successful check; returns the problems (nothing written if any)."""
    problems = check(directory, name, text)
    if problems:
        return problems
    path = safe_path(directory, name)
    if os.path.exists(path):
        os.makedirs(backups, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, os.path.join(backups, name.replace("/", "_") + "." + stamp))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nl = "\n"
    if os.path.exists(path):
        with open(path, "rb") as f:
            nl = "\r\n" if b"\r\n" in f.read() else "\n"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\r\n", "\n").replace("\n", nl))
    return []


def png_rgba(width, height, rows):
    """An RGBA PNG from rows of bytes (4 per pixel)."""
    raw = b"".join(b"\0" + bytes(r) for r in rows)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


_ICON_INDEX, _TEXTURES = {}, {}
ICON_ENTRY = re.compile(r'<AnimationInfo name="(\d+)">\s*<AnimationFrame[^>]*>\s*<TextureName>([^<]+)</TextureName>\s*'
                        r'<Rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"')


def icon_index(path=None):
    """{icon number: (texture file, x, y, w, h)} from the client's iconsTK.xml."""
    if not _ICON_INDEX:
        path = path or os.path.join(ICONS, "iconsTK.xml")
        if os.path.exists(path):
            with open(path, encoding="utf-8-sig") as f:
                for m in ICON_ENTRY.finditer(f.read()):
                    _ICON_INDEX.setdefault(int(m.group(1)), (m.group(2), *map(int, m.group(3, 4, 5, 6))))
    return _ICON_INDEX


def texture(name):
    """Rows (top-down) of RGBA bytes of an uncompressed TGA or BMP icon sheet."""
    if name not in _TEXTURES:
        with open(os.path.join(ICONS, name), "rb") as f:
            d = f.read()
        rows = []
        if name.lower().endswith(".tga") and d[2] == 2:
            idlen, (w, h), bpp, desc = d[0], struct.unpack_from("<HH", d, 12), d[16], d[17]
            px, start, bottom_up = bpp // 8, 18 + idlen, not desc & 0x20
            stride = w * px
        elif name.lower().endswith(".bmp") and d[:2] == b"BM":
            start = struct.unpack_from("<I", d, 10)[0]
            w, h = struct.unpack_from("<ii", d, 18)
            px = struct.unpack_from("<H", d, 28)[0] // 8
            stride, bottom_up, h = (w * px + 3) & ~3, h > 0, abs(h)
        else:
            raise ValueError(f"unsupported texture {name}")
        for j in range(h):
            line = d[start + j * stride:start + j * stride + w * px]
            out = bytearray(4 * w)
            out[0::4], out[1::4], out[2::4] = line[2::px], line[1::px], line[0::px]
            out[3::4] = line[3::px] if px == 4 else b"\xff" * w
            rows.append(bytes(out))
        if bottom_up:
            rows.reverse()
        _TEXTURES[name] = rows
    return _TEXTURES[name]


def icon_png(n):
    """A PNG of client icon number n (the items.json "icon"), or None."""
    entry = icon_index().get(int(n))
    if entry is None:
        return None
    name, x, y, w, h = entry
    rows = texture(name)
    return png_rgba(w, h, [rows[y + j][4 * x:4 * (x + w)] for j in range(h)])


def png(width, height, gray):
    """A grayscale PNG from rows of 0-255 values (standard library only)."""
    raw = b"".join(b"\0" + bytes(row) for row in gray)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


_TERRAIN = {}


def terrain(chunk):
    if chunk not in _TERRAIN:
        import terrain as terrain_mod
        path = os.path.join(MAPS, chunk + ".vgr")
        _TERRAIN[chunk] = terrain_mod.Terrain(path) if os.path.exists(path) else None
    return _TERRAIN[chunk]


def terrain_png(chunk, size=512, box=None):
    """(png bytes, {extent, z_min, z_max}) of a chunk's heightmap as a shaded size x size image;
    box = (x0, y0, x1, y1) renders only that area (bilinear, with its own contrast)."""
    t = terrain(chunk)
    if t is None:
        return None, None
    ex = t.extent()
    x0, y0, x1, y1 = box or ex
    pts = [[t.height(x0 + (x1 - x0) * (i + 0.5) / size, y0 + (y1 - y0) * (j + 0.5) / size)
            for i in range(size)] for j in range(size)]
    vals = [h for row in pts for h in row if h is not None]
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 1.0)
    span = max(1.0, hi - lo)
    step = (x1 - x0) / size
    rows = []
    for j in range(size):
        row = []
        for i in range(size):
            h = pts[j][i]
            if h is None:
                row.append(0)
                continue
            east = pts[j][min(size - 1, i + 1)]
            south = pts[min(size - 1, j + 1)][i]
            slope = ((east if east is not None else h) - h + (south if south is not None else h) - h) / max(step, 1)
            row.append(max(0, min(255, int(50 + 150 * (h - lo) / span - 120 * slope))))
        rows.append(row)
    return png(size, size, rows), {"extent": list(ex), "box": [x0, y0, x1, y1], "z_min": lo, "z_max": hi}


def races(doc=os.path.join(ROOT, "docs", "CREATURES.md")):
    """[{id, name, models}] from the race table in docs/CREATURES.md (player races and creatures)."""
    out = []
    if not os.path.exists(doc):
        return out
    for line in open(doc, encoding="utf-8"):
        m = re.match(r"\| (\d+) \| 0x[0-9a-fA-F]+ \| ([^|]+)\|[^|]*\|[^|]*\| ([^|]*)\|", line)
        if m:
            models = sorted({int(n) for n in re.findall(r"(\d+)", " ".join(re.findall(r"\[([^\]]*)\]", m.group(3))))})
            out.append({"id": int(m.group(1)), "name": m.group(2).strip(), "models": models})
    return out


def schema():
    """Vocabularies the forms offer (taken from the server code, so they never drift)."""
    import grouploot
    import vgmsg
    import zone
    return {"item_types": sorted(zone.ITEM_TYPE_IDS), "slots": sorted(vgmsg.EQUIP_SLOTS),
            "flags": list(zone.ITEM_FLAGS), "rarities": list(grouploot.RARITY_NAMES),
            "stats": sorted(k for k in vgmsg.STAT_IDS if k in vgmsg.ATTRIBUTES or k.startswith("res_")),
            "mods": sorted(vgmsg.MOD_TYPES), "slot_ids": vgmsg.EQUIP_SLOTS,
            "gear_types": {str(k): v for k, v in GEAR_TYPES.items()}}


_ARCHIVE = []


def archive_index(directory=ARCHIVE):
    """The newest collected record per (type, name) from crowdsourced/raw/*/*.jsonl (the archive
    reference; read once, ~1 s)."""
    if _ARCHIVE:
        return _ARCHIVE[0]
    best = {}
    for folder in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        if not os.path.isdir(os.path.join(directory, folder)):
            continue
        for f in os.listdir(os.path.join(directory, folder)):
            if not f.endswith(".jsonl") or f == "gaps.jsonl":
                continue
            with open(os.path.join(directory, folder, f), encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(r, dict) or not r.get("name") or not r.get("type"):
                        continue
                    key = (r["type"], r["name"])
                    if key not in best or str(r.get("collected_at", "")) >= str(best[key].get("collected_at", "")):
                        best[key] = r
    _ARCHIVE.append(best)
    return best


def archive_search(query, kind=None, limit=40):
    """Archive records whose name contains query (case-insensitive), exact matches first."""
    q = (query or "").strip().lower()
    if len(q) < 2:
        return []
    hits = [r for (t, n), r in archive_index().items() if (kind in (None, "", t)) and q in n.lower()]
    hits.sort(key=lambda r: (r["name"].lower() != q, len(r["name"]), r["name"]))
    return hits[:limit]


def draft(kind, name):
    """A starting point for a new mob or item from the archive record (type, name): only the
    values the archive actually has (nothing invented), the source in "_source", and the fields a
    person still has to fill in "_needs". Items go through crowdsourced/convert.py's mapping."""
    rec = archive_index().get((kind, name))
    if rec is None:
        return None
    sys.path.insert(0, os.path.join(ROOT, "crowdsourced"))
    import convert
    src = (rec.get("sources") or [{}])[0].get("url")
    if kind in ("creature", "npc"):
        race = convert.find_race(convert.creature_races(), rec.get("creature_kind") or rec.get("race"))
        level = rec.get("level") or (rec.get("level_range") or [None])[0]
        m = {"name": rec["name"], "pawn_class": "SGONPCPawn"}
        for k, v in (("race", race), ("level", level), ("health", rec.get("health")), ("title", rec.get("title"))):
            if v is not None:
                m[k] = v
        if isinstance(rec.get("damage"), list):
            m["damage"] = rec["damage"]
        if str(rec.get("aggressive", "")).lower() == "yes" and rec.get("aggro_range") is not None:
            m["aggro_radius"] = rec["aggro_range"]
        m["_needs"] = [k for k in ("race", "level", "health", "damage") if k not in m]
        m["_source"] = src
        return {"file": "mobs.json", "key": convert.slug(rec["name"]), "value": m}
    if kind == "item":
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "all.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps(dict(rec, notes=rec.get("notes") or "", confidence=rec.get("confidence") or "low")))
            batch = convert.Batch(d, include_low=True)
            out = convert.convert(batch, convert.creature_races())
        it = out["items.json"].get(rec["name"])
        if it is None:
            return {"error": "; ".join(batch.issues) or "the converter could not map this item"}
        it["_needs"] = ["icon"] + [k for k in ("type",) if k not in it]
        return {"file": "items.json", "key": rec["name"], "value": it}
    return {"error": f"no draft for {kind} records yet"}


# Gear mesh types (docs/GEAR.md "PackageIndex"): type -> name (the <NAME>_ITEMS.uem package)
GEAR_TYPES = {7: "ARM", 8: "BACK", 9: "CHEST", 11: "FACE", 12: "FEET", 13: "FINGER", 14: "HAND", 15: "HEAD",
              16: "LEG", 17: "NECK", 18: "SHOULDER", 19: "WAIST", 20: "WRIST", 21: "TOOL", 22: "AXE", 23: "BOW",
              24: "CLUB", 25: "CROSSBOW", 26: "DAGGER", 27: "FLAIL", 28: "HAMMER", 29: "MACE", 30: "POLEARM",
              31: "STAFF", 32: "THROWN", 33: "SWORD", 34: "SHIELD", 35: "SPEAR", 36: "FIST", 37: "SPADE",
              38: "KNIFE", 39: "MARTIALFIST", 40: "MARTIALSWORD", 41: "MARTIALSTAFF", 42: "FOCUS", 43: "BARD",
              601: "FULLSUIT"}
_MESHES = {}


def mesh_numbers(gear_type):
    """Mesh numbers that exist in the client's <TYPE>_ITEMS.uem for a gear type (sorted)."""
    name = GEAR_TYPES.get(int(gear_type))
    if name is None:
        return []
    if name not in _MESHES:
        path = os.path.join(MESHES, name + "_ITEMS.uem")
        nums = set()
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            pat = re.compile(rb"(?<![A-Z])(?:M_|F_|[A-Z]+_M_|[A-Z]+_F_)?" + name.encode() + rb"_(\d+)")
            nums = {int(n) for n in pat.findall(data)}
        _MESHES[name] = sorted(nums)
    return _MESHES[name]


def class_abilities_list():
    """[{class, name, id}] of every class's rank-I abilities in the client's .aby packages."""
    import class_abilities
    import races_classes
    out = []
    for klass in class_abilities.CLASS_PREFIX:
        for aid, tag in class_abilities.class_ability_list(ROOT, klass):
            out.append({"class": races_classes.class_name(klass), "name": class_abilities.display_name(tag), "id": aid})
    return out


def ability_from_archive(name):
    """abilities.json fields the archive record for this ability name has: icon (the archive's
    icon file number is the client's icon number), description (the tooltip), cast, refresh."""
    rec = archive_index().get(("ability", name))
    if rec is None:
        return {}
    out = {}
    digits = "".join(c for c in str(rec.get("icon_name") or "") if c.isdigit())
    if digits and int(digits) in icon_index():
        out["icon"] = int(digits)
    if rec.get("tooltip"):
        out["description"] = rec["tooltip"]
    if isinstance(rec.get("cast_time_seconds"), (int, float)) and rec["cast_time_seconds"] > 0:
        out["cast"] = float(rec["cast_time_seconds"])
    if isinstance(rec.get("refresh_seconds"), (int, float)) and rec["refresh_seconds"] >= 0:
        out["refresh"] = float(rec["refresh_seconds"])
    if out:
        out["_source"] = (rec.get("sources") or [{}])[0].get("url")
    return out


def ability_fill(directory):
    """{ability name: fields} the archive can add to abilities.json for the class abilities: only
    fields an entry doesn't have yet (nothing already set is replaced)."""
    with open(os.path.join(directory, "abilities.json"), encoding="utf-8") as f:
        current = json.load(f)
    out = {}
    for a in class_abilities_list():
        have = current.get(a["name"]) or {}
        new = {k: v for k, v in ability_from_archive(a["name"]).items() if k not in have}
        if any(k != "_source" for k in new):
            out[a["name"]] = new
    return out


def chunks():
    return sorted(f[:-4] for f in os.listdir(MAPS) if f.startswith("chunk_") and f.endswith(".vgr")) \
        if os.path.isdir(MAPS) else []


def file_hash(directory, name):
    path = safe_path(directory, name)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def proposal_path(pid, folder=PROPOSALS):
    if not re.match(r"^[0-9a-f]{16}$", pid or ""):
        raise ValueError("bad proposal id")
    return os.path.join(folder, pid + ".json")


def propose(directory, user, name, text, note="", folder=PROPOSALS):
    """Store a change for review (after the same checks a save gets): (proposal id, problems)."""
    problems = check(directory, name, text)
    if problems:
        return None, problems
    os.makedirs(folder, exist_ok=True)
    pid = secrets.token_hex(8)
    doc = {"id": pid, "user": user, "name": name, "note": note[:500], "created": int(time.time()),
           "status": "open", "base": file_hash(directory, name), "text": text}
    with open(proposal_path(pid, folder), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return pid, []


def proposals(user=None, folder=PROPOSALS):
    """Proposal summaries, newest first (only user's own when user is given)."""
    out = []
    for f in os.listdir(folder) if os.path.isdir(folder) else []:
        if f.endswith(".json"):
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                d = json.load(fh)
            if user is None or d["user"] == user:
                out.append({k: v for k, v in d.items() if k != "text"})
    return sorted(out, key=lambda d: -d["created"])


def proposal_diff(directory, pid, folder=PROPOSALS):
    with open(proposal_path(pid, folder), encoding="utf-8") as f:
        d = json.load(f)
    path = safe_path(directory, d["name"])
    old = open(path, encoding="utf-8").read().replace("\r\n", "\n") if os.path.exists(path) else ""
    diff = "".join(difflib.unified_diff(old.splitlines(True), d["text"].replace("\r\n", "\n").splitlines(True),
                                        "current/" + d["name"], "proposed/" + d["name"], n=3))
    stale = d.get("base") != file_hash(directory, d["name"])
    return dict({k: v for k, v in d.items() if k != "text"}, diff=diff, stale=stale)


def review(directory, pid, action, reviewer, folder=PROPOSALS, backups=BACKUPS):
    """approve (save it, after the checks) or reject a proposal: the problems (empty = done)."""
    path = proposal_path(pid, folder)
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if d["status"] != "open":
        return [f"proposal {pid} is already {d['status']}"]
    if action == "approve":
        problems = save(directory, d["name"], d["text"], backups)
        if problems:
            return problems
        d["status"] = "approved"
    elif action == "reject":
        d["status"] = "rejected"
    else:
        return [f"unknown action {action!r}"]
    d["reviewed_by"], d["reviewed"] = reviewer, int(time.time())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f)
    return []


class Handler(http.server.BaseHTTPRequestHandler):
    directory = CONTENT
    login_required = False
    secure = False
    proposals_dir = PROPOSALS
    backups_dir = BACKUPS
    sessions = {}                  # cookie token -> (account, role, expiry)

    def account(self):
        """(account, role) of the request, or (None, None). Without --accounts everyone is admin."""
        if not self.login_required:
            return "local", "admin"
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "vgsession" and v in self.sessions:
                user, role, expiry = self.sessions[v]
                if expiry > time.time():
                    return user, role
                self.sessions.pop(v, None)
        return None, None

    def body(self):
        self._body_read = True
        return self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 20_000_000)).decode("utf-8")

    def log_message(self, fmt, *a):
        pass

    def reply(self, code, body, kind="application/json"):
        if not getattr(self, "_body_read", False):
            # A refusal sent before the request body was read: read it off first. Closing a
            # socket with unread data makes Windows send a reset, which can reach the client
            # before the reply does (the intermittent unit-test failure of 2026-10-15).
            n = int(self.headers.get("Content-Length", 0) or 0)
            if 0 < n <= 20_000_000:
                self.rfile.read(n)
            self._body_read = True
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        user, role = self.account()
        try:
            if u.path == "/":
                with open(UI, "rb") as f:
                    return self.reply(200, f.read(), "text/html; charset=utf-8")
            if u.path == "/api/me":
                return self.reply(200, {"user": user, "role": role, "login_required": self.login_required})
            if user is None:
                return self.reply(401, {"error": "log in first"})
            if u.path == "/api/proposals":
                return self.reply(200, proposals(None if role == "admin" else user, self.proposals_dir))
            if u.path == "/api/proposal":
                d = proposal_diff(self.directory, q.get("id"), self.proposals_dir)
                if role != "admin" and d["user"] != user:
                    return self.reply(403, {"error": "not your proposal"})
                return self.reply(200, d)
            if u.path == "/api/files":
                return self.reply(200, content_files(self.directory))
            if u.path == "/api/file":
                with open(safe_path(self.directory, q.get("name")), encoding="utf-8") as f:
                    return self.reply(200, {"name": q["name"], "text": f.read()})
            if u.path == "/api/archive":
                return self.reply(200, archive_search(q.get("q"), q.get("type")))
            if u.path == "/api/draft":
                d = draft(q.get("type"), q.get("name"))
                return self.reply(200, d) if d else self.reply(404, {"error": "no such record"})
            if u.path == "/api/icon.png":
                data = icon_png(q.get("n", "0"))
                return self.reply(200, data, "image/png") if data else self.reply(404, {"error": "no such icon"})
            if u.path == "/api/icons":
                return self.reply(200, sorted(icon_index()))
            if u.path == "/api/obstacles":
                import obstacles as obstacles_mod
                return self.reply(200, [[round(o[0]), round(o[1]), round(o[2])] for o in obstacles_mod.obstacles(q.get("chunk", ""))])
            if u.path == "/api/class_abilities":
                return self.reply(200, class_abilities_list())
            if u.path == "/api/ability_fill":
                return self.reply(200, ability_fill(self.directory))
            if u.path == "/api/meshes":
                return self.reply(200, mesh_numbers(q.get("type", "0")))
            if u.path == "/api/schema":
                return self.reply(200, schema())
            if u.path == "/api/races":
                return self.reply(200, races())
            if u.path == "/api/chunks":
                return self.reply(200, chunks())
            if u.path == "/api/terrain.png":
                box = tuple(float(q[k]) for k in ("x0", "y0", "x1", "y1")) if "x0" in q else None
                data, _info = terrain_png(q.get("chunk", ""), 512, box)
                return self.reply(200, data, "image/png") if data else self.reply(404, {"error": "no such map"})
            if u.path == "/api/terrain":
                _data, info = terrain_png(q.get("chunk", ""))
                return self.reply(200, info) if info else self.reply(404, {"error": "no such map"})
        except (ValueError, OSError) as e:
            return self.reply(400, {"error": str(e)})
        self.reply(404, {"error": "not found"})

    def guard(self):
        """(account, role) for a change request, or None after replying with the refusal. In login
        mode a change needs the X-Editor header, which a page from another site cannot send."""
        user, role = self.account()
        if user is None:
            self.reply(401, {"error": "log in first"})
            return None
        if self.login_required and self.headers.get("X-Editor") != "1":
            self.reply(403, {"error": "missing X-Editor header"})
            return None
        return user, role

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/api/login":
            import accounts
            ip = self.client_address[0]
            if accounts.throttled(ip):
                return self.reply(429, {"error": "Too many failed logins; wait a few minutes."})
            try:
                d = json.loads(self.body())
            except ValueError:
                return self.reply(400, {"error": "bad request"})
            name = accounts.check_password(d.get("username"), d.get("password"))
            if name is None or accounts.is_suspended(name):
                accounts.record_failure(ip)
                return self.reply(403, {"error": "Wrong username or password."})
            token = secrets.token_urlsafe(24)
            self.sessions[token] = (name, accounts.editor_role(name), time.time() + SESSION_SECONDS)
            body = json.dumps({"user": name, "role": accounts.editor_role(name)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", f"vgsession={token}; HttpOnly; SameSite=Strict; Path=/"
                                           + ("; Secure" if self.secure else ""))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        g = self.guard()
        if g is None:
            return
        user, role = g
        if u.path == "/api/logout":
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "vgsession":
                    self.sessions.pop(v, None)
            return self.reply(200, {"ok": True})
        if u.path == "/api/review":
            if role != "admin":
                return self.reply(403, {"error": "only admins review proposals"})
            try:
                problems = review(self.directory, q.get("id"), q.get("action"), user, self.proposals_dir, self.backups_dir)
            except (ValueError, OSError) as e:
                return self.reply(400, {"error": str(e)})
            return self.reply(200 if not problems else 422, {"problems": problems})
        self.reply(404, {"error": "not found"})

    def do_PUT(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path not in ("/api/file", "/api/check", "/api/propose"):
            return self.reply(404, {"error": "not found"})
        g = self.guard()
        if g is None:
            return
        user, role = g
        text = self.body()
        try:
            name = q.get("name")
            safe_path(self.directory, name)
            if u.path == "/api/propose":
                pid, problems = propose(self.directory, user, name, text, q.get("note", ""), self.proposals_dir)
                return self.reply(200 if pid else 422, {"proposal": pid, "problems": problems})
            if u.path == "/api/file" and role != "admin":
                return self.reply(403, {"error": "contributors submit proposals; an admin approves them"})
            problems = check(self.directory, name, text) if u.path == "/api/check" else save(self.directory, name, text, self.backups_dir)
            warnings = [] if problems else spawn_warnings(self.directory, name, text)
        except ValueError as e:
            return self.reply(400, {"error": str(e)})
        self.reply(200 if not problems else 422, {"saved": u.path == "/api/file" and not problems,
                                                  "problems": problems, "warnings": warnings})


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--content", default=CONTENT)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 lets other machines reach it (use with --accounts)")
    ap.add_argument("--accounts", action="store_true", help="log in with the game server's accounts")
    ap.add_argument("--data-dir", help="the server's --data-dir, for its accounts")
    ap.add_argument("--cert", help="HTTPS certificate (with --key)")
    ap.add_argument("--key")
    a = ap.parse_args()
    Handler.directory = os.path.abspath(a.content)
    Handler.login_required = a.accounts
    if a.host not in ("127.0.0.1", "localhost", "::1") and not a.accounts:
        sys.exit("Refusing to listen beyond this machine without --accounts (anyone could edit the content).")
    if a.data_dir:
        import accounts
        accounts.ACCOUNTS_FILE = os.path.join(os.path.abspath(a.data_dir), "accounts.json")
    httpd = http.server.ThreadingHTTPServer((a.host, a.port), Handler)
    scheme = "http"
    if a.cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(a.cert, a.key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        Handler.secure, scheme = True, "https"
    elif a.accounts and a.host not in ("127.0.0.1", "localhost", "::1"):
        print("Warning: without --cert/--key, passwords cross the network unencrypted.")
    print(f"Content editor on {scheme}://{a.host}:{a.port}  (editing {Handler.directory}"
          f"{'; logins with game accounts' if a.accounts else ''}; Ctrl+C stops)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
