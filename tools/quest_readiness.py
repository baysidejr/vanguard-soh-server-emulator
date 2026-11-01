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
    for extra in (singular_name(name),):
        if extra not in out:
            out.append(extra)
    return out


def _single(word):
    if len(word) < 4 or not word.endswith("s") or word.endswith(("ss", "'s")):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("shes", "ches", "xes", "sses")):
        return word[:-2]
    return word[:-1]


def singular_name(name):
    """The singular creature name of a plural objective target: every word before an "of" made
    singular ("hobgoblins overseers" -> "hobgoblin overseer", "eyes of pain" -> "eye of pain")."""
    words = name.split()
    cut = words.index("of") if "of" in words else len(words)
    return " ".join([_single(w) for w in words[:cut]] + words[cut:])


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
             for s in steps if "talk" not in s and "use" not in s for name, n in (s.get("collect") or s.get("kill")).items()]
    tasks += [s["objective"] for s in steps if "talk" in s or "use" in s]   # "Speak with ...", "Portals Closed"
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


# Owner decision B-007 (2026-10-17): a quest the archive records no objectives for is only played
# as a delivery when something points to one. The only evidence there is so far is the quest's
# own title ("A Message For Fayalas", "Report To Officer Yu", "Potion Delivery"); others are
# kept in quests.json but switched off ("disabled", quest.offerable).
DELIVERY_TITLE = re.compile(r"\b(message|messages|letter|letters|delivery|deliver|delivering|note|missive|"
                            r"package|parcel|word to|summons|report to|correspondence|dispatch|courier|"
                            r"orders for|news for|tidings|introduction|send word|errand)\b", re.I)
DELIVERY_EVIDENCE = ("the archive's quest title names a delivery or a report to the hand-in NPC (inferred "
                     "from the title; the archive records no objectives)")
NO_DELIVERY_EVIDENCE = ("B-007 (owner decision C, 2026-10-17): the archive records no objectives and nothing "
                        "points to a delivery; not offered. Remove \"disabled\" to play it as a delivery again.")


# Zones whose evidence-less delivery placeholders are offered anyway, marked (owner decision
# 2026-10-31, B-019: the Isle of Dawn start would otherwise have almost nothing to do).
DELIVERY_PLACEHOLDER_ZONES = ("Isle of Dawn",)
MARKED_DELIVERY = ("PLACEHOLDER (owner decision 2026-10-31, B-019): the archive records no objectives; offered as "
                   "a delivery to the hand-in NPC until real objectives are found")


def mark_delivery(q, zone=None):
    """Keep a delivery placeholder playable only with title evidence (or in a zone where the owner
    wants them offered, marked); switch it off otherwise."""
    if zone in DELIVERY_PLACEHOLDER_ZONES:
        q["_placeholder_delivery"] = MARKED_DELIVERY
        q.pop("disabled", None)
        q.pop("_disabled", None)
    elif DELIVERY_TITLE.search(q.get("name", "")) and q.get("giver") != q.get("turn_in"):
        q["_delivery_evidence"] = DELIVERY_EVIDENCE
        q.pop("disabled", None)
        q.pop("_disabled", None)
    else:
        q["disabled"] = True
        q["_disabled"] = NO_DELIVERY_EVIDENCE
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
            quests[key]["turn_in"] = steps[-1]["talk"]
            quests[key]["_placeholder_steps"] = ("the archive records no objectives; played as a delivery to "
                                                 "the hand-in NPC")
            mark_delivery(quests[key], rec.get("zone"))
            if carried_items(rec) and "_placeholder_delivery" in quests[key]:
                note = ("the archive records only the item carried from the giver; played as a delivery to the "
                        "hand-in NPC")
                quests[key]["_placeholder_steps"] = note
                quests[key]["_placeholder_delivery"] = MARKED_DELIVERY.split(":")[0] + ": " + note
            reward = quests[key].setdefault("reward", {})
            if reward.get("xp") == 100 * int(rec.get("level") or 1):     # the placeholder, not the archive's
                reward["xp"] = 25 * int(rec.get("level") or 1)              # one conversation: a quarter
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


def enable_zone_deliveries(do_apply, chunks, content=z.CONTENT):
    """Switch back on the delivery placeholders B-007 switched off whose giver stands in a
    DELIVERY_PLACEHOLDER_ZONES zone (marked). Returns the quest names."""
    qpath = os.path.join(content, "quests.json")
    quests = z.load(qpath, {})
    givers = set()
    for zone in DELIVERY_PLACEHOLDER_ZONES:
        if zone in chunks:
            givers |= {sp["mob"] for sp in z.existing_spawns(z.level_name(*chunks[zone]), content)}
    names = []
    for q in quests.values():
        if isinstance(q, dict) and q.get("_disabled") == NO_DELIVERY_EVIDENCE and q.get("giver") in givers:
            q["_placeholder_delivery"] = MARKED_DELIVERY
            q.pop("disabled", None)
            q.pop("_disabled", None)
            names.append(q.get("name"))
    if names and do_apply:
        z.write(qpath, quests)
    return sorted(names)


def link_chains(archive_quests, content=z.CONTENT):
    """Archive quests that follow another quest in quests.json ("previous" on the archive page)
    require it (quests added in the same refresh missed the link). Never closes a loop. Returns
    the number of links added."""
    path = os.path.join(content, "quests.json")
    quests = z.load(path, {})
    by_name = {q["name"].lower(): k for k, q in quests.items() if isinstance(q, dict) and "name" in q}

    def needs(key, target, seen=()):
        """True when `key` (directly or further back) requires `target`."""
        for r in quests.get(key, {}).get("requires", []):
            if r == target or (r not in seen and needs(r, target, seen + (r,))):
                return True
        return False
    added = 0
    for key, q in quests.items():
        if not key.startswith("arch_") or not isinstance(q, dict) or q.get("requires"):
            continue
        prev = (archive_quests.get(q.get("name")) or {}).get("chain_previous")
        pkey = by_name.get((prev or "").lower())
        if pkey and pkey != key and not needs(pkey, key):
            q["requires"] = [pkey]
            added += 1
    if added:
        z.write(path, quests)
    return added


def delivery_plan(quests, world, chunks, content=z.CONTENT):
    """{quest name: steps} for quests whose giver is placed, whose archive page records no
    objectives, and whose hand-in NPC is someone else who is placed: played as "speak with the
    hand-in NPC" (a placeholder; some are real deliveries, others had objectives the archive did
    not record). Returns also the records, as (records, steps_for)."""
    placed = {s["mob"] for fn in glob.glob(os.path.join(content, "spawns", "*.json"))
              for s in z.load(fn, {}).get("spawns", [])}
    recs, steps_for = [], {}
    for q in quests.values():
        status = readiness(q, world, chunks)
        turn_in = (q.get("turn_in") or "").strip()
        if not turn_in or turn_in.lower() in ((q.get("giver") or "").lower(), "unknown"):
            continue
        key = z.key_for(turn_in)
        carried = carried_items(q) if status == "giver" and q.get("zone") in DELIVERY_PLACEHOLDER_ZONES else None
        if carried and key in placed:
            # "Lix Luckkin's Report (0/1)" from the giver to someone else: carry it over (marked).
            recs.append(q)
            steps_for[q["name"]] = [{"objective": f"Deliver {', '.join(carried)} to {turn_in}", "talk": key}]
            continue
        if status != "no steps":
            continue
        if key in placed:
            recs.append(q)
            steps = [{"objective": f"Speak with {turn_in}", "talk": key}]
            # "items needed" that drop in the quest's zone: gather them first (closer to the quest)
            chunk = chunks.get(q.get("zone"))
            drops = world.get(z.level_name(*chunk), ({}, {}))[1] if chunk else {}
            need = [i.strip() for i in (q.get("archive_fields") or {}).get("items needed") or [] if i.strip()]
            if need and all(i.lower() in drops for i in need):
                steps = [{"objective": drops[i.lower()][0], "collect": {drops[i.lower()][0]: 1}} for i in need] + steps
            steps_for[q["name"]] = steps
    return recs, steps_for


def carried_items(q):
    """The item names when every recorded objective is a single item ("Lix Luckkin's Report (0/1)")
    rather than kills or a count to gather; else None."""
    names = []
    for s in q.get("candidate_steps") or []:
        o = (s.get("objective") or "").strip()
        m = re.fullmatch(r"(.+?)\s*\(0/1\)", o)
        if not m or s.get("kind") == "kill" or re.search(r"\b(slain|killed|closed|rescued|poisoned)\b", o, re.I):
            return None
        names.append(m.group(1).lstrip("*").strip())
    return names or None


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


def placeholder_camps(quests, world, chunks, creatures, content=z.CONTENT, invent_zones=()):
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
                rec = invented_creature(objective, q) if q.get("zone") in invent_zones else None
            if rec is None:
                targets = []
                break
            need = next((int(st.get("count") or 1) for st in q.get("candidate_steps") or []
                         if st.get("objective") == objective), 1)
            targets.append((rec, 3 if need > 1 else 1))        # one named foe, or a camp of three
        if not targets:
            continue
        level = z.level_name(*chunks[q["zone"]])
        giver = next((s for s in z.existing_spawns(level, content)
                      if s["mob"] == world[level][0].get((q.get("giver") or "").lower())), None)
        if giver is None:
            continue
        for rec, size in targets:
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
                for i in range(size):
                    b = 2 * math.pi * i / 3
                    r = 250 if size > 1 else 0
                    trial.append({"mob": key, "x": round(cx + r * math.cos(b)), "y": round(cy + r * math.sin(b)),
                                  "yaw": 0, "wander": 200, "_placeholder": f"position invented for the quest {q['name']}"})
                if giver.get("z") is not None and abs(giver["z"] - _ground(level, giver["x"], giver["y"])) > 400:
                    for sp in trial:              # the giver is in a city or underground: its floor
                        sp["z"] = giver["z"]
                if not any(_wet(level, sp["x"], sp["y"], sp.get("z")) for sp in trial):
                    camp = trial
                    break
            if camp is None:
                continue
            tpl = invented_template(rec) if rec.get("_invented") else z.creature_template(rec, None)
            out.setdefault(level, []).append((key, tpl, camp))
    return out


# Zones where a kill target with no archive page at all becomes a placeholder creature named from the
# quest objective (owner decision 2026-10-31, B-019: the Isle of Dawn's common creatures have no pages).
INVENT_ZONES = ("Isle of Dawn",)
# Stand-in looks where no client race carries the creature's name (placeholders, like the rest).
STAND_IN_LOOKS = {"gataro": "lizardman", "imp": "fireelemental", "eye": "wingedeye", "dervish": "rockdervish"}


def invented_creature(objective, quest):
    """A record for a kill target the archive has no page for: its name from the objective
    ("Gataro Podlings Slain (0/5)" -> "Gataro Podling"), the quest's level; None when the
    objective is not a plain "<creatures> Slain" ("Ulvari Slain at Hobgoblin Camp")."""
    if not re.search(r"\b(slain|killed|defeated|destroyed)\s*(\([^)]*\))?\s*$", objective.strip(), re.I):
        return None
    t = objective_target(objective)
    if not re.fullmatch(r"[a-z' -]+", t) or set(t.split()) & {"slain", "in", "at", "inside", "from", "near"}:
        return None
    name = " ".join(w if w == "of" else w[:1].upper() + w[1:] for w in singular_name(t).split())
    return {"name": name, "level": int(quest.get("level") or 1), "zone": quest.get("zone"), "_invented": quest["name"]}


def invented_race(name):
    """A client race for an invented creature: a race named like the whole name or one of its
    words ("Hobgoblin Overseer" -> hobgoblin), else a stand-in look; else the default."""
    if not z._RACES:
        z.creature_race({}, None)
    convert, races = z._RACES[0]
    words = [w.lower() for w in name.split() if w.lower() != "of"]
    for text in [name] + words[::-1]:
        race = convert.find_race(races, text)
        if race is not None:
            return race
    for w in words[::-1]:
        if w in STAND_IN_LOOKS and STAND_IN_LOOKS[w] in races:
            return races[STAND_IN_LOOKS[w]]
    return z.DEFAULT_RACE


def invented_template(rec):
    """A placeholder mob for an invented creature: the quest's level, health and damage scaled as
    for archive creatures of two dots, not aggressive (a newcomer's first fights)."""
    level = rec["level"]
    return {"name": rec["name"], "pawn_class": "SGONPCPawn", "race": invented_race(rec["name"]), "level": level,
            "health": 100 + 40 * level, "damage": [max(1, level), max(2, 2 * level)],
            "_placeholder": f"creature invented from an objective of the quest {rec['_invented']} (owner decision "
                            "2026-10-31): the archive has no page for it; look, level and stats are guesses"}


# Objectives the archive names but nothing places ("Portals Closed (0/3)", "Lumber (1)",
# "Villagers Rescued (0/5)"): in INVENT_ZONES (owner decision 2026-10-31, "get the Isle of Dawn
# complete") a placeholder object of that name near the giver is used (right-click) instead.
PERSON_WORDS = {"villager", "refugee", "logger", "supporter", "citizen", "prisoner", "captive", "worker"}
OBJECT_LOOKS = {"portal": 767, "food": 1087, "fire": 1087, "flame": 1087, "banner": 631}   # prop races
OBJECT_LOOK = 1072                                                                        # a crate / chest
PLACEHOLDER_OBJECTIVES = ("objectives the archive names but nothing places are played with placeholder objects "
                          "and creatures near the giver (owner decision 2026-10-31)")


def _title(text):
    return " ".join(w if w in ("of", "from", "to", "the") else w[:1].upper() + w[1:] for w in text.split())


def object_name(objective, need):
    """'Portals Closed (0/3)' -> 'Portal', 'Convince 4 Magistrate Supporters to Stop (4)' ->
    'Magistrate Supporter', "*Ring of Zalaz (0/1)" -> 'Ring of Zalaz'."""
    t = re.sub(r"\s*\([^)]*\)\s*$", "", objective).strip().lstrip("*").strip()
    t = re.sub(r"^(convince|collect|gather|find|recover)\s+\d+\s+", "", t, flags=re.I)
    t = re.sub(r"\s+to stop$", "", t, flags=re.I)
    t = re.sub(r"\s+(closed|rescued|poisoned|found|collected|recovered|destroyed|captured)$", "", t, flags=re.I)
    words = t.split()
    if need > 1:            # the head noun only, as written: "Tentrees Tools" -> "Tentrees Tool"
        cut = next((i for i, w in enumerate(words) if w.lower() in ("of", "from")), len(words))
        if cut:
            words[cut - 1] = _single(words[cut - 1])
    return " ".join(w if w.lower() in ("of", "from", "to", "the") else w[:1].upper() + w[1:] for w in words)


def qualified_kill(objective, quest):
    """'Hobgoblins slain in Gai's Nousa (0/5)' / 'Hobgoblins in Farmlands Slain (0/8)' -> a record
    for an invented "Gai's Nousa Hobgoblin" at the quest's level; else None."""
    t = re.sub(r"\s*\([^)]*\)\s*$", "", objective).strip()
    m = (re.fullmatch(r"(.+?)\s+(?:slain|killed)\s+(?:at|in|inside)\s+(.+)", t, re.I)
         or re.fullmatch(r"(.+?)\s+(?:at|in|inside)\s+(.+?)\s+(?:slain|killed)", t, re.I))
    if not m:
        return None
    name = _title(f"{m.group(2).lower()} {singular_name(m.group(1).lower())}")
    return {"name": name, "level": int(quest.get("level") or 1), "zone": quest.get("zone"), "_invented": quest["name"]}


def object_template(name, quest, person_race=None):
    low = name.lower().split()
    person = bool(PERSON_WORDS & set(low))
    t = {"name": name, "pawn_class": "SGONPCPawn", "level": int(quest.get("level") or 1), "health": 100, "damage": [0, 0],
         "_placeholder": f"object invented for an objective of the quest {quest['name']} (owner decision 2026-10-31): "
                         "the archive names it but places nothing; used with a right-click"}
    if person:
        t["race"] = person_race or z.ZONE_RACE.get(quest.get("zone")) or z.DEFAULT_RACE
    else:
        t["race"] = next((r for w, r in OBJECT_LOOKS.items() if w in low), OBJECT_LOOK)
        t["prop"] = True
    return t


def _ring(level, giver, name, size, quest_name, radius):
    """size spawns of name in a ring PLACEHOLDER_DISTANCE from the giver, the first direction not under
    water (marked "_placeholder"); None when every direction is wet."""
    import hashlib
    import math
    key = z.key_for(name)
    a0 = int(hashlib.md5(name.encode()).hexdigest(), 16) % 360 * math.pi / 180
    for k in range(8):
        a = a0 + k * math.pi / 4
        cx, cy = giver["x"] + PLACEHOLDER_DISTANCE * math.cos(a), giver["y"] + PLACEHOLDER_DISTANCE * math.sin(a)
        trial = []
        for i in range(size):
            b = 2 * math.pi * i / max(size, 1)
            r = radius if size > 1 else 0
            trial.append({"mob": key, "x": round(cx + r * math.cos(b)), "y": round(cy + r * math.sin(b)), "yaw": 0,
                          "_placeholder": f"position invented for the quest {quest_name}"})
        if giver.get("z") is not None and abs(giver["z"] - _ground(level, giver["x"], giver["y"])) > 400:
            for sp in trial:
                sp["z"] = giver["z"]
        if not any(_wet(level, sp["x"], sp["y"], sp.get("z")) for sp in trial):
            return trial
    return None


def placeholder_objectives(quests, world, chunks, content=z.CONTENT, zones=INVENT_ZONES):
    """Quests in zones whose giver is placed but some objectives aren't: every such objective gets a
    placeholder (an invented creature to kill, else an object to use). Returns
    ({level: [(template key, template, spawns)]}, {quest name: steps}, [quest records])."""
    mobs = z.load(os.path.join(content, "mobs.json"), {})
    have = {v.get("name", "").lower() for v in z.load(os.path.join(content, "quests.json"), {}).values()
            if isinstance(v, dict)}
    out, steps_for, recs, made = {}, {}, [], set()
    for q in sorted(quests.values(), key=lambda r: r["name"]):
        if q.get("zone") not in zones or readiness(q, world, chunks) != "giver" or q["name"].lower() in have:
            continue
        level = z.level_name(*chunks[q["zone"]])
        names, drops = world[level]
        giver = next((s for s in z.existing_spawns(level, content) if s["mob"] == names.get((q.get("giver") or "").lower())), None)
        if giver is None:
            continue
        steps, entries = [], []
        for s in q.get("candidate_steps") or []:
            objective = (s.get("objective") or "").strip()
            label = re.sub(r"\s*\([^)]*\)\s*$", "", objective.lstrip("- ")).strip()
            need = int(s.get("count") or 1)
            t = objective_target(objective)
            mob = next((names[n] for n in singulars(t) if n in names), None)
            if s.get("kind") != "kill" and t in drops:
                steps.append({"objective": label, "collect": {drops[t][0]: need}})
                continue
            if s.get("kind") != "collect" and mob and t != (q.get("giver") or "").lower():
                steps.append({"objective": label, "kill": {mob: need}})
                continue
            rec = invented_creature(objective, q) or qualified_kill(objective, q)
            if rec is not None:
                key = z.key_for(rec["name"])
                tpl, size, radius = invented_template(rec), 3, 250
                steps.append({"objective": label, "kill": {key: need}})
            else:
                name = object_name(objective, need)
                key, tpl, size, radius = (z.key_for(name), object_template(name, q, mobs.get(giver["mob"], {}).get("race")),
                                          min(need, 5), 150)
                steps.append({"objective": label, "use": {key: need}})
            if key not in mobs and key not in made and key not in names.values():
                camp = _ring(level, giver, tpl["name"], size, q["name"], radius)
                if camp is None:
                    steps = None
                    break
                entries.append((key, tpl, camp))
                made.add(key)
        if not steps:
            continue
        steps_for[q["name"]] = steps
        recs.append(q)
        out.setdefault(level, []).extend(entries)
    return out, steps_for, recs


# Givers the archive names two ways, the placed spelling (zone, quest page's name) -> placed name.
GIVER_ALIASES = {("Isle of Dawn", "Kimaso Blackleaf"): "Veteran Kimaso Blackleaf"}   # "Veteran" is a title


def alias_givers(quests):
    """Use the placed spelling of a giver named two ways (GIVER_ALIASES), in place."""
    for q in quests.values():
        alias = GIVER_ALIASES.get((q.get("zone"), (q.get("giver") or "").strip()))
        if alias:
            q["giver"] = alias
    return quests


def conversation_plan(quests, world, chunks, content=z.CONTENT, zones=DELIVERY_PLACEHOLDER_ZONES):
    """The quests in zones that record no objectives and no other placed hand-in NPC (delivery_plan
    takes those): "speak with" the giver of the next quest in the chain when that one is placed,
    else with the giver again (a conversation placeholder). Returns (records, {name: steps})."""
    have = {v.get("name", "").lower() for v in z.load(os.path.join(content, "quests.json"), {}).values()
            if isinstance(v, dict)}
    taken = set(delivery_plan(quests, world, chunks, content)[1])
    recs, steps_for = [], {}
    for q in sorted(quests.values(), key=lambda r: r["name"]):
        if q.get("zone") not in zones or q["name"] in taken or q["name"].lower() in have \
                or readiness(q, world, chunks) != "no steps":
            continue
        names = world[z.level_name(*chunks[q["zone"]])][0]
        giver = (q.get("giver") or "").strip()
        nxt = quests.get(q.get("chain_next") or "") or {}
        to = (nxt.get("giver") or "").strip()
        if to and to.lower() != giver.lower() and to.lower() in names:
            steps = [{"objective": f"Speak with {to}", "talk": names[to.lower()]}]
        else:
            steps = [{"objective": f"Hear {giver} out", "talk": names[giver.lower()]}]
        recs.append(q)
        steps_for[q["name"]] = steps
    return recs, steps_for


def add_placeholder_quests(recs, steps_for, world, chunks, content=z.CONTENT):
    """Add the quests placeholder_objectives planned (never overwrites). Returns how many."""
    qpath = os.path.join(content, "quests.json")
    quests = z.load(qpath, {})
    names = {q.get("name", "").lower() for q in quests.values() if isinstance(q, dict)}
    next_id = max([QUEST_ID_BASE - 1] + [q.get("id", 0) for q in quests.values() if isinstance(q, dict)]) + 1
    level_names = {lv: n for lv, (n, _d) in world.items()}
    added = 0
    for rec in recs:
        key = "arch_" + z.key_for(rec["name"])[5:]
        if key in quests or rec["name"].lower() in names:
            continue
        q = to_quest(rec, steps_for[rec["name"]], next_id, content)
        placed = level_names.get(z.level_name(*chunks[rec["zone"]]), {})
        turn_in = placed.get((rec.get("turn_in") or "").strip().lower())
        if turn_in:
            q["turn_in"] = turn_in
        elif q.get("turn_in") not in placed.values():
            q.pop("turn_in", None)                     # hand back to the giver
            q.pop("_turn_in_name", None)
        q["_placeholder_steps"] = PLACEHOLDER_OBJECTIVES
        quests[key] = q
        next_id += 1
        added += 1
    if added:
        z.write(qpath, quests)
    return added


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
