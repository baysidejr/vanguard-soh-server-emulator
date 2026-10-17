"""Archive spawns that are probably in the wrong chunk.

Archive positions are chunk-local (docs/ARCHIVE_COORDINATES... see memory notes), and the chunk
comes from the page's zone label, which is sometimes wrong: Tracker Nok's quest pages give
"-22572, 88588, 553 in Wildgrowth Forest (-20,12)", where that point is open sea 5,383 units
below him, while one page puts the same coordinates "in Martok (-20,13)", where the terrain there
is 590, within 40 units of his recorded height (seen live 2026-10-17: the Wildgrowth spot is
underwater).

A spawn is reported when its recorded z is far from its own chunk's terrain (more than FAR) with
no obstacle top near it (so it isn't standing on a building or rock), while a neighbouring chunk's
terrain at the same local x, y is within NEAR of z. That is evidence for the neighbour, not proof.

    python tools/chunk_audit.py           # report
    python tools/chunk_audit.py --apply   # move the reported spawns (marked "_moved_from")

Uses the client's own maps (terrain heights, obstacles). Standard library only.
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import content as content_mod  # noqa: E402
import obstacles  # noqa: E402

CONTENT = os.path.join(ROOT, "server", "content")
FAR = 1000.0       # recorded z this far from the chunk's terrain needs an explanation
NEAR = 150.0       # ... and a neighbour's terrain this close to z is one
ON_MESH = 400.0    # an obstacle top within this of z: standing on a building or rock


def chunk_xy(level):
    a, b = level[len("chunk_"):].split("_")
    return tuple(-int(v[1:]) if v.startswith("n") else int(v) for v in (a, b))


def level_name(cx, cy):
    return "chunk_" + "_".join(f"n{-v}" if v < 0 else str(v) for v in (cx, cy))


def candidates(c, client_dir=ROOT, content=CONTENT):
    """[(path, index, spawn, own level, own terrain z, better level, its terrain z)]."""
    out = []
    for path in sorted(glob.glob(os.path.join(content, "spawns", "*.json"))):
        level = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            spawns = json.load(f).get("spawns", [])
        obs = None
        for i, s in enumerate(spawns):
            if not str(s.get("mob", "")).startswith("arch_") or s.get("z") is None:
                continue
            x, y, z = s["x"], s["y"], s["z"]
            own = c.ground_z(level, x, y, client_dir)
            if own is None or abs(z - own) <= FAR:
                continue
            if obs is None:
                obs = obstacles.obstacles(level)
            if any((o[0] - x) ** 2 + (o[1] - y) ** 2 <= o[2] ** 2 and abs(o[4] - z) <= ON_MESH for o in obs):
                continue                         # on a building or rock: fine
            cx, cy = chunk_xy(level)
            best = None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                other = level_name(cx + dx, cy + dy)
                if not os.path.exists(os.path.join(client_dir, "Assets", "Maps", other + ".vgr")):
                    continue
                g = c.ground_z(other, x, y, client_dir)
                if g is not None and abs(z - g) <= NEAR and (best is None or abs(z - g) < abs(z - best[1])):
                    best = (other, g)
            if best:
                out.append((path, i, s, level, own, best[0], best[1]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="move the reported spawns to the better chunk")
    a = ap.parse_args(argv)
    c = content_mod.Content()
    mobs = c.mobs
    rows = candidates(c)
    for path, i, s, level, own, other, g in rows:
        name = mobs.get(s["mob"], {}).get("name", s["mob"])
        print(f"{name}: {level} terrain {own:.0f} vs recorded z {s['z']} -> {other} terrain {g:.0f}")
    print(f"{len(rows)} spawn(s) probably in the wrong chunk")
    if a.apply and rows:
        moves = {}
        for path, i, s, level, own, other, g in rows:
            moves.setdefault(path, []).append((i, other, level, own, g))
        for path, items in moves.items():
            with open(path, encoding="utf-8") as f:
                raw = f.read()
            doc = json.loads(raw)
            for i, other, level, own, g in sorted(items, reverse=True):
                s = doc["spawns"].pop(i)
                s["_moved_from"] = (f"{level}: recorded z {s['z']} is {abs(s['z'] - own):.0f} from that chunk's "
                                    f"terrain and {abs(s['z'] - g):.0f} from {other}'s at the same x, y "
                                    f"(tools/chunk_audit.py)")
                s.pop("_uncertain", None)
                target = os.path.join(os.path.dirname(path), other + ".json")
                tdoc = {"spawns": []}
                if os.path.exists(target):
                    with open(target, encoding="utf-8") as f:
                        tdoc = json.load(f)
                tdoc.setdefault("spawns", []).append(s)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(json.dumps(tdoc, indent=2, ensure_ascii=False) + "\n")
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(doc, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else ""))
        print("moved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
