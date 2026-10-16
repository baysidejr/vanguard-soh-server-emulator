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


def blockers(quest, world, chunks):
    """The objectives of a quest whose giver is placed that can't be done yet: [(objective, why)]."""
    chunk = chunks.get(quest.get("zone"))
    names, drops = world.get(z.level_name(*chunk), ({}, {})) if chunk else ({}, {})
    out = []
    for s in quest.get("candidate_steps") or []:
        t = objective_target(s.get("objective") or "")
        if s.get("kind") != "kill" and t in drops:
            continue
        if s.get("kind") != "collect" and any(n in names for n in singulars(t)):
            continue
        why = {"kill": "no such creature placed in the zone",
               "collect": "no placed creature in the zone drops it"}.get(s.get("kind"), "nothing placed matches it")
        out.append((s.get("objective") or "", why))
    return out


def report(quests, world, chunks):
    """For the editor: {"totals": {status: n}, "zones": [{"zone", counts, "ready": [names],
    "blocked": [{"quest", "giver", "objectives": [[objective, why]]}]}]} sorted by zone."""
    totals, zones = collections.Counter(), {}
    for q in quests.values():
        status = readiness(q, world, chunks)
        totals[status] += 1
        zinfo = zones.setdefault(q.get("zone") or "?", {"zone": q.get("zone") or "?", "counts": collections.Counter(),
                                                         "ready": [], "blocked": []})
        zinfo["counts"][status] += 1
        if status == "ready":
            zinfo["ready"].append(q["name"])
        elif status == "giver":
            zinfo["blocked"].append({"quest": q["name"], "giver": q.get("giver"),
                                     "objectives": [list(b) for b in blockers(q, world, chunks)]})
    out = sorted(zones.values(), key=lambda zi: zi["zone"])
    for zi in out:
        zi["counts"] = dict(zi["counts"])
        zi["ready"].sort()
        zi["blocked"].sort(key=lambda b: b["quest"])
    return {"totals": dict(totals), "zones": out}


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
             for s in steps if "talk" not in s for name, n in (s.get("collect") or s.get("kill")).items()]
    tasks += [s["objective"] for s in steps if "talk" in s]          # "Speak with ..." (delivery_plan)
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


def apply(ready, world, chunks, content=z.CONTENT, steps_for=None):
    """Add ready quests (and their collect items) to content. steps_for: {quest name: steps}
    to use instead of plan_steps (delivery_plan). Returns (quests added, items added)."""
    qpath, ipath = os.path.join(content, "quests.json"), os.path.join(content, "items.json")
    quests, items = z.load(qpath, {}), z.load(ipath, {})
    names = {q.get("name", "").lower() for q in quests.values() if isinstance(q, dict)}
    next_id = max([QUEST_ID_BASE - 1] + [q.get("id", 0) for q in quests.values() if isinstance(q, dict)]) + 1
    added_q = added_i = 0
    for rec in ready:
        key = "arch_" + z.key_for(rec["name"])[5:]
        if key in quests or rec["name"].lower() in names:
            continue
        if steps_for and rec["name"] in steps_for:
            steps = steps_for[rec["name"]]
        else:
            status, steps = plan_steps(rec, world, chunks)
        quests[key] = to_quest(rec, steps, next_id, content)
        if steps_for and rec["name"] in steps_for:
            quests[key]["turn_in"] = steps[0]["talk"]
            quests[key]["_placeholder_steps"] = ("the archive records no objectives; played as a delivery to "
                                                 "the hand-in NPC")
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


def delivery_plan(quests, world, chunks, content=z.CONTENT):
    """{quest name: steps} for quests whose giver is placed, whose archive page records no
    objectives, and whose hand-in NPC is someone else who is placed: played as "speak with the
    hand-in NPC" (a placeholder; some are real deliveries, others had objectives the archive did
    not record). Returns also the records, as (records, steps_for)."""
    placed = {s["mob"] for fn in glob.glob(os.path.join(content, "spawns", "*.json"))
              for s in z.load(fn, {}).get("spawns", [])}
    recs, steps_for = [], {}
    for q in quests.values():
        if readiness(q, world, chunks) != "no steps":
            continue
        turn_in = (q.get("turn_in") or "").strip()
        if not turn_in or turn_in.lower() in ((q.get("giver") or "").lower(), "unknown"):
            continue
        key = z.key_for(turn_in)
        if key in placed:
            recs.append(q)
            steps_for[q["name"]] = [{"objective": f"Speak with {turn_in}", "talk": key}]
    return recs, steps_for


PLACEHOLDER_DISTANCE = 1500     # how far from the quest giver an invented camp stands
_WATER, _GROUND = {}, []


def _wet(level, x, y, height=None):
    """True when the ground at (x, y) lies inside one of the chunk's WaterVolumes (server/water.py;
    no water known = dry). The ground, not `height`: a neighbour's height can hang over the sea
    (Seawatch Coast's whole sea is one volume below z 1)."""
    sys.path.insert(0, os.path.join(z_root(), "server"))
    if level not in _WATER:
        try:
            import water
            _WATER[level] = water.water_boxes(level, os.path.join(z_root(), "Assets", "Maps"))
        except Exception:
            _WATER[level] = []
    if not _WATER[level]:
        return False
    if True:                    # the ground decides: a height from a neighbour can hang in the air over the sea
        if not _GROUND:
            import content as server_content
            _GROUND.append(server_content.Content(z.CONTENT))
        height = _GROUND[0].ground_z(level, x, y, z_root())
    return any(lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1] and lo[2] <= height + 20 <= hi[2] for _n, lo, hi in _WATER[level])


def _ground(level, x, y):
    if not _GROUND:
        import content as server_content
        _GROUND.append(server_content.Content(z.CONTENT))
    return _GROUND[0].ground_z(level, x, y, z_root())


def z_root():
    return z.ROOT


def placeholder_camps(quests, world, chunks, creatures, content=z.CONTENT):
    """For quests whose giver is placed and whose only missing objectives are kills of creatures the
    archive knows (same zone, a level) but doesn't locate: a camp of three of each such creature
    PLACEHOLDER_DISTANCE from the giver, on the terrain (the giver's height in a city off the
    terrain). Every spawn is marked "_placeholder": the position is invented, for the content
    editor to correct. Returns {level: [(template key, template, [spawns])]}."""
    import hashlib
    import math
    by_name = {n.lower(): r for n, r in creatures.items()}
    out, done = {}, set()
    for q in quests.values():
        if readiness(q, world, chunks) != "giver":
            continue
        targets = []
        for objective, _why in blockers(q, world, chunks):
            t = objective_target(objective)
            rec = next((by_name[s] for s in singulars(t) if s in by_name), None)
            if rec is None or rec.get("zone") != q.get("zone") or not rec.get("level") or z.is_object(rec):
                targets = []
                break
            targets.append(rec)
        if not targets:
            continue
        level = z.level_name(*chunks[q["zone"]])
        giver = next((s for s in z.existing_spawns(level, content)
                      if s["mob"] == world[level][0].get((q.get("giver") or "").lower())), None)
        if giver is None:
            continue
        for rec in targets:
            key = z.key_for(rec["name"])
            if key in done:
                continue
            done.add(key)
            a0 = int(hashlib.md5(rec["name"].encode()).hexdigest(), 16) % 360 * math.pi / 180
            camp = None
            for k in range(8):                            # the first direction whose camp is not under water
                a = a0 + k * math.pi / 4
                cx, cy = giver["x"] + PLACEHOLDER_DISTANCE * math.cos(a), giver["y"] + PLACEHOLDER_DISTANCE * math.sin(a)
                trial = []
                for i in range(3):
                    b = 2 * math.pi * i / 3
                    trial.append({"mob": key, "x": round(cx + 250 * math.cos(b)), "y": round(cy + 250 * math.sin(b)),
                                  "yaw": 0, "wander": 200, "_placeholder": f"position invented for the quest {q['name']}"})
                if giver.get("z") is not None and abs(giver["z"] - _ground(level, giver["x"], giver["y"])) > 400:
                    for sp in trial:              # the giver is in a city or underground: its floor
                        sp["z"] = giver["z"]
                if not any(_wet(level, sp["x"], sp["y"], sp.get("z")) for sp in trial):
                    camp = trial
                    break
            if camp is None:
                continue
            out.setdefault(level, []).append((key, z.creature_template(rec, None), camp))
    return out


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
