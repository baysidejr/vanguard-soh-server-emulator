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

Listens on 127.0.0.1 only; it is a tool for the person running the server, with no logins.
Uses only the Python standard library.
"""
import argparse
import http.server
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
    nl = "\r\n" if os.path.exists(path) and b"\r\n" in open(path, "rb").read() else "\n"
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
            "mods": sorted(vgmsg.MOD_TYPES)}


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


def chunks():
    return sorted(f[:-4] for f in os.listdir(MAPS) if f.startswith("chunk_") and f.endswith(".vgr")) \
        if os.path.isdir(MAPS) else []


class Handler(http.server.BaseHTTPRequestHandler):
    directory = CONTENT

    def log_message(self, fmt, *a):
        pass

    def reply(self, code, body, kind="application/json"):
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
        try:
            if u.path == "/":
                with open(UI, "rb") as f:
                    return self.reply(200, f.read(), "text/html; charset=utf-8")
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

    def do_PUT(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path not in ("/api/file", "/api/check"):
            return self.reply(404, {"error": "not found"})
        text = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
        try:
            name = q.get("name")
            safe_path(self.directory, name)
            problems = check(self.directory, name, text) if u.path == "/api/check" else save(self.directory, name, text)
        except ValueError as e:
            return self.reply(400, {"error": str(e)})
        self.reply(200 if not problems else 422, {"saved": u.path == "/api/file" and not problems,
                                                  "problems": problems})


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--content", default=CONTENT)
    a = ap.parse_args()
    Handler.directory = os.path.abspath(a.content)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Content editor on http://127.0.0.1:{a.port}  (editing {Handler.directory}; Ctrl+C stops)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
