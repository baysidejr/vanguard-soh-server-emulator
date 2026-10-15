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
