"""Where the server's content came from: a count per content file of records that cite an archive
page ("_source"), records explicitly marked as invented ("_placeholder", "_placeholder_steps",
"_archive_placeholder"), and records with neither (hand-made test content or placeholder values
that carry no mark). Nothing in server/content is original game data unless it cites a source,
and even sourced records carry placeholder values (stats, prices) that the archive doesn't record.

    python tools/provenance.py            # the table
    python tools/provenance.py --unmarked mobs.json   # list one file's unmarked keys

Read-only. Uses only the Python standard library.
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "server", "content")
PLACEHOLDER_MARKS = ("_placeholder", "_placeholder_steps", "_archive_placeholder")


def classify(rec):
    """'placeholder', 'sourced' or 'unmarked' for one record (a dict)."""
    if any(rec.get(k) for k in PLACEHOLDER_MARKS):
        return "placeholder"
    if rec.get("_source"):
        return "sourced"
    return "unmarked"


def records(path):
    """(key, record) pairs of a content file: top-level entries, or each spawn of a spawn file."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if isinstance(doc, dict) and isinstance(doc.get("spawns"), list):
        return [(f"{i}:{s.get('mob')}", s) for i, s in enumerate(doc["spawns"]) if isinstance(s, dict)]
    if isinstance(doc, dict):
        out = []
        for k, v in doc.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict):
                out.append((k, v))
            elif isinstance(v, list):          # loot tables, merchant lists: rows of one entry
                out.append((k, {"_source": next((r.get("_source") for r in v if isinstance(r, dict) and r.get("_source")), None)}
                            if not k.startswith(("arch_", "archive_")) else {"_source": "archive import"}))
        return out
    return []


def report(content=CONTENT):
    """{file: {'sourced': n, 'placeholder': n, 'unmarked': n}}; spawn files summed as 'spawns/'."""
    out = {}
    files = sorted(glob.glob(os.path.join(content, "*.json")))
    for fn in files:
        counts = {"sourced": 0, "placeholder": 0, "unmarked": 0}
        for _k, r in records(fn):
            counts[classify(r)] += 1
        out[os.path.basename(fn)] = counts
    spawns = {"sourced": 0, "placeholder": 0, "unmarked": 0}
    for fn in glob.glob(os.path.join(content, "spawns", "*.json")):
        for _k, sp in records(fn):
            if sp.get("_placeholder"):
                spawns["placeholder"] += 1
            elif str(sp.get("mob", "")).startswith("arch_"):
                spawns["sourced"] += 1         # placed by the archive importer from a cited page
            else:
                spawns["unmarked"] += 1
    out["spawns/*.json"] = spawns
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--unmarked", metavar="FILE", help="list the unmarked keys of one content file")
    a = ap.parse_args(argv)
    if a.unmarked:
        for k, r in records(os.path.join(CONTENT, a.unmarked)):
            if classify(r) == "unmarked":
                print(k)
        return 0
    rows = report()
    print(f"{'file':28} {'sourced':>8} {'placeholder':>12} {'unmarked':>9}")
    for name, c in rows.items():
        if sum(c.values()):
            print(f"{name:28} {c['sourced']:>8} {c['placeholder']:>12} {c['unmarked']:>9}")
    print("\nsourced: cites an archive page (values the archive lacks are still placeholders); "
          "placeholder: marked invented; unmarked: hand-made test content or placeholder values without a mark.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
