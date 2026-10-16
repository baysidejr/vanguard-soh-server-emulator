"""How many archive quests could be played in our world today, and add the ones that can.

A quest is "ready" when its giver is placed in the quest's zone and every objective can be done
there: a kill target ("Timber Wolves Slain (12)") is a creature placed in that zone, and a collect
item ("Sprite Essence (0/8)") drops from a creature placed there. Run it after each import refresh
to see the scrape's progress.

    python tools/quest_readiness.py                   # summary and the ready quests
    python tools/quest_readiness.py --branch          # also read the collection branch's raw batches
    python tools/quest_readiness.py --branch --apply  # add ready quests to quests.json (never overwrites)

Added quests start from editor.quest_draft (the archive's text, level and rewards); what the
archive doesn't say (dialogue, most rewards) gets a plain placeholder and stays in "_needs" for the
content editor. A collect item missing from items.json is added as a plain quest item.
Uses only the Python standard library.
"""
import argparse
import collections
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import import_zone as z  # noqa: E402

QUEST_ID_BASE = 5100            # archive quests get ids from here up (hand-made ones are 5001..)


def objective_target(text):
    """'- Loamite Sludgemongers Slain (7/10)' -> 'loamite sludgemongers'."""
    t = re.sub(r"\s*\([^)]*\)\s*$", "", text.strip().lstrip("- ")).strip()
    return re.sub(r"\s+(slain|killed|defeated|destroyed)$", "", t, flags=re.I).lower()


def singulars(name):
    """The name itself and the likely singulars of its last word."""
    head, _, last = name.rpartition(" ")
    pre = head + " " if head else ""
    out = [name]
    for plural, single in (("ies", "y"), ("ves", "f"), ("men", "man"), ("es", ""), ("s", "")):
        if last.endswith(plural):
            out.append(pre + last[: -len(plural)] + single)
    return out


def zone_world(content=z.CONTENT):
    """{chunk level: ({placed name: template key}, {dropped item, lower case: (name, icon)})}."""
    mobs = z.load(os.path.join(content, "mobs.json"), {})
    loot = z.load(os.path.join(content, "loot.json"), {})
    out = {}
    for fn in glob.glob(os.path.join(content, "spawns", "*.json")):
        level = os.path.splitext(os.path.basename(fn))[0]
        names, drops = {}, {}
        for s in z.load(fn, {}).get("spawns", []):
            m = mobs.get(s.get("mob"))
            if not isinstance(m, dict) or "name" not in m:
                continue
            names[m["name"].lower()] = s["mob"]
            table = loot.get(m.get("loot"))
            for r in table if isinstance(table, list) else []:
                if isinstance(r, dict) and r.get("name"):
                    drops[r["name"].lower()] = (r["name"], r.get("icon"))
        out[level] = (names, drops)
    return out


def plan_steps(quest, world, chunks):
    """(status, steps): status 'ready', 'giver' (placed, an objective not), 'no giver' or 'no
    steps'; steps are quests.json steps when ready."""
    chunk = chunks.get(quest.get("zone"))
    names, drops = world.get(z.level_name(*chunk), ({}, {})) if chunk else ({}, {})
    giver = (quest.get("giver") or "").lower()
    if giver not in names:
        return "no giver", None
    found = quest.get("candidate_steps") or []
    if not found:
        return "no steps", None
    steps = []
    for s in found:
        t = objective_target(s.get("objective") or "")
        count = int(s.get("count") or 1)
        step = {"objective": re.sub(r"\s*\([^)]*\)\s*$", "", (s.get("objective") or "").strip().lstrip("- "))}
        mob = next((names[n] for n in singulars(t) if n in names), None)
        if t == giver:
            return "giver", None              # "read the book": the giver is the objective, an interaction
        if s.get("kind") != "kill" and t in drops:
            step["collect"] = {drops[t][0]: count}
        elif s.get("kind") != "collect" and mob:
            step["kill"] = {mob: count}
        else:
            return "giver", None
        steps.append(step)
    return "ready", steps


def readiness(quest, world, chunks):
    return plan_steps(quest, world, chunks)[0]


def coin_copper(text):
    """'1s 40c' -> 140, '55 c' -> 55, '2g' -> 20000; None when there is no unit ('17')."""
    parts = re.findall(r"(\d+)\s*([pgsc])(?![a-z])", str(text or "").lower())
    if not parts:
        return None
    return sum(int(n) * {"p": 1000000, "g": 10000, "s": 100, "c": 1}[u] for n, u in parts)


def to_quest(rec, steps, quest_id, content=z.CONTENT):
    """A quests.json entry for a ready archive quest."""
    import editor
    src = (rec.get("sources") or [{}])[0].get("url")
    q = editor.quest_draft(rec, src, z.key_for, content)["value"]
    q = {"id": quest_id, **{k: v for k, v in q.items() if not k.startswith("_") or k in ("_needs", "_source")}}
    q["steps"] = steps
    q["_needs"] = [n for n in q.get("_needs", []) if not n.startswith(("the mob to kill", "step ", "steps", "turn_in"))]
    giver_name = rec.get("giver")
    tasks = [(f"Gather {n} {name}" if "collect" in s else
              f"Slay {n} " + re.sub(r"\s+(slain|killed|defeated|destroyed)$", "", s["objective"], flags=re.I))
             for s in steps for name, n in (s.get("collect") or s.get("kill")).items()]
    q.setdefault("greeting", f"I could use some help. ({rec['name']}: the archive has no dialogue yet.)")
    q.setdefault("description", f"{giver_name} has asked you to help: " + ", then ".join(
        t[0].lower() + t[1:] for t in tasks) + ".")
    q.setdefault("summary", "; ".join(tasks) + f" for {giver_name}.")
    q.setdefault("accept_text", f"You agree to help {giver_name}.")
    if (rec.get("turn_in") or "").strip().lower() == "unknown":
        q.pop("turn_in", None)
        q.pop("_turn_in_name", None)
    coin = ((rec.get("archive_fields") or {}).get("coin reward") or [None])[0]
    reward = q.setdefault("reward", {})
    copper = coin_copper(coin)
    if copper is not None:
        reward.setdefault("coin", copper)
    elif coin and coin != "0":
        q["_needs"].append(f"coin reward (the archive says {coin!r} with no unit)")
    reward.setdefault("xp", 100 * int(rec.get("level") or 1))     # placeholder: the archive rarely says
    return q


def apply(ready, world, chunks, content=z.CONTENT):
    """Add ready quests (and their collect items) to content. Returns (quests added, items added)."""
    qpath, ipath = os.path.join(content, "quests.json"), os.path.join(content, "items.json")
    quests, items = z.load(qpath, {}), z.load(ipath, {})
    names = {q.get("name", "").lower() for q in quests.values() if isinstance(q, dict)}
    next_id = max([QUEST_ID_BASE - 1] + [q.get("id", 0) for q in quests.values() if isinstance(q, dict)]) + 1
    added_q = added_i = 0
    for rec in ready:
        key = "arch_" + z.key_for(rec["name"])[5:]
        if key in quests or rec["name"].lower() in names:
            continue
        status, steps = plan_steps(rec, world, chunks)
        quests[key] = to_quest(rec, steps, next_id, content)
        next_id += 1
        added_q += 1
        level = z.level_name(*chunks[rec["zone"]])
        for step in steps:
            for item in step.get("collect", {}):
                if item not in items:
                    icon = world[level][1][item.lower()][1]
                    items[item] = {"icon": icon or 442, "description": f"Wanted for {rec['name']}.",
                                   "_source": quests[key]["_source"]}
                    added_i += 1
    if added_q:
        z.write(qpath, quests)
    if added_i:
        z.write(ipath, items)
    return added_q, added_i


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--branch", nargs="?", const="origin/crowdsourced/archive-collection",
                    help="also read the raw batches of this git branch")
    ap.add_argument("--apply", action="store_true", help="add the ready quests to server/content")
    a = ap.parse_args(argv)
    if a.branch:
        z.EXTRA_RAW.append(z.branch_raw(a.branch))
    quests, world, chunks = z.archive_npcs(kind="quest"), zone_world(), z.zone_chunks()
    counts, ready = collections.Counter(), []
    for q in quests.values():
        r = readiness(q, world, chunks)
        counts[r] += 1
        if r == "ready":
            ready.append(q)
    ready.sort(key=lambda q: (q.get("zone") or "", q["name"]))
    print(f"{len(quests)} archive quests: " + ", ".join(f"{n} {k}" for k, n in counts.most_common()))
    print("  (giver = giver placed, some objective's creature or item not yet in the zone)")
    for q in ready:
        print(f"  ready: {q['name']} ({q.get('zone')}, {q.get('giver')}): "
              + "; ".join(s.get("objective", "") for s in q.get("candidate_steps") or []))
    if a.apply:
        print("added %d quests and %d items" % apply(ready, world, chunks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
