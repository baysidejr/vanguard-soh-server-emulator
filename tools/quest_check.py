"""Can every quest a player can be offered actually be finished with what is placed in the world?

content.py checks that a quest's names refer to templates that exist; this checks that those
templates are spawned somewhere and that every item a quest asks for can be obtained: dropped by a
spawned creature (its loot table), gathered from a spawned resource node, bought from a spawned
merchant, or given by another quest. Quests switched off ("disabled", backlog B-007) are skipped.

    python tools/quest_check.py            # problems, one line per quest
    python tools/quest_check.py --all      # every enabled quest with its status

Read-only. Uses only the Python standard library.
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "server", "content")


def load(name, content=CONTENT):
    with open(os.path.join(content, name), encoding="utf-8") as f:
        return json.load(f)


def spawned(content=CONTENT):
    """{template key: [chunk names]} for every spawn in spawns/*.json."""
    out = {}
    for path in glob.glob(os.path.join(content, "spawns", "*.json")):
        level = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            for s in json.load(f).get("spawns", []):
                out.setdefault(s.get("mob"), []).append(level)
    return out


def item_sources(mobs, where, loot, merchants, quests):
    """{item name: [how to get it]} from what is placed."""
    out = {}
    for key in where:
        t = mobs.get(key)
        if not isinstance(t, dict):
            continue
        for row in loot.get(t.get("loot"), []) if t.get("loot") else []:
            if isinstance(row, dict) and row.get("name"):
                out.setdefault(row["name"], []).append(f"loot of {t.get('name', key)}")
        if isinstance(t.get("harvest"), dict) and t["harvest"].get("item"):
            out.setdefault(t["harvest"]["item"], []).append(f"harvest {t.get('name', key)}")
        for row in merchants.get(t.get("merchant"), []) if t.get("merchant") else []:
            if isinstance(row, dict) and row.get("item"):
                out.setdefault(row["item"], []).append(f"sold by {t.get('name', key)}")
    for key, q in quests.items():
        if isinstance(q, dict) and not q.get("disabled"):
            reward = q.get("reward") or {}
            for name in list(reward.get("items") or []) + list(reward.get("choice") or []):
                name = name.get("name") if isinstance(name, dict) else name
                if isinstance(name, str):
                    out.setdefault(name, []).append(f"reward of {q.get('name', key)}")
    return out


def problems(q, mobs, where, sources):
    """Why a quest can't be finished (empty if it can)."""
    out = []

    def placed(key, role):
        if key not in where:
            out.append(f"{role} {mobs.get(key, {}).get('name', key)!r} is not spawned anywhere")

    placed(q.get("giver"), "giver")
    placed(q.get("turn_in", q.get("giver")), "hand-in NPC")
    for n, step in enumerate(q.get("steps", []), 1):
        for key in step.get("kill") or {}:
            placed(key, f"step {n} kill target")
        if step.get("talk"):
            placed(step["talk"], f"step {n} talk target")
        for item in step.get("collect") or {}:
            if item not in sources:
                out.append(f"step {n}: nothing placed drops, sells or gives {item!r}")
    return out


def check(content=CONTENT):
    """[(key, quest, [problems])] for every enabled quest."""
    mobs, loot = load("mobs.json", content), load("loot.json", content)
    merchants, quests = load("merchants.json", content), load("quests.json", content)
    where = spawned(content)
    sources = item_sources(mobs, where, loot, merchants, quests)
    return [(k, q, problems(q, mobs, where, sources)) for k, q in quests.items()
            if isinstance(q, dict) and not k.startswith("_") and not q.get("disabled")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="list every enabled quest, not only problems")
    a = ap.parse_args(argv)
    rows = check()
    bad = [r for r in rows if r[2]]
    for key, q, probs in rows:
        if probs or a.all:
            print(f"{key} ({q.get('name')}): " + ("; ".join(probs) if probs else "OK"))
    print(f"{len(rows) - len(bad)} of {len(rows)} enabled quests can be finished with what is placed; "
          f"{len(bad)} cannot")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
