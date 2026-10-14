"""Turn a crowdsourced batch (raw/<batch>/*.jsonl, see AGENT_INSTRUCTIONS.md) into proposed
server content (the formats of server/content/*.json) plus a report of everything that could
not be mapped. The live content is never touched: the output goes to
reviewed/<batch>/proposed/<file>.json, to be checked and merged by hand.

    python crowdsourced/convert.py raw/2026-10-14-wastelands-quests

Mapping rules (docs/CONTENT_EDITOR.md):
- names become keys by slugging ("Ashen Wolf" -> "ashen_wolf"); records link by name;
- creature_kind / race -> a client race id from docs/CREATURES.md (exact name, then the
  mesh package name, then a word match) or a playable race from races_classes.RACES;
- item slots -> vgmsg.EQUIP_SLOTS names, item types -> zone.ITEM_TYPE_IDS keys;
- money stays in copper; low-confidence records are skipped unless --include-low.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))

import races_classes  # noqa: E402
import vgmsg  # noqa: E402

SLOTS = {"head": "HEAD", "chest": "CHEST", "legs": "LEGS", "hands": "HANDS", "feet": "FEET",
         "waist": "WAIST", "cloak": "CLOAK", "shoulders": "SHOULDERS", "wrists": "WRISTS",
         "neck": "NECK", "ear": "LEFTEAR", "finger": "LEFTFINGER", "primary": "PRIMARYHAND",
         "secondary": "SECONDARYHAND", "two-hand": "TWOHANDS", "ranged": "RANGED", "ammo": "AMMO"}
ITEM_TYPES = {"weapon": "weapon", "armor": "armor", "shield": "shield", "jewelry": "jewelry",
              "container": "container", "fishing": "fishing", "tool": "harvest_tool"}
RARITIES = ("mundane", "common", "uncommon", "rare", "heroic", "fabled", "legendary")
SERVICES = {"merchant": None, "banker": "banker", "trainer": "trainer", "repair": "repair",
            "task master": "task_master", "mailbox": "mailbox", "altar": "altar"}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def existing_keys(path=os.path.join(ROOT, "server", "content", "mobs.json")):
    """{in-game name: mob key} of the server's current mobs, so records update them in place."""
    try:
        mobs = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {m["name"]: k for k, m in mobs.items() if not k.startswith("_") and isinstance(m, dict) and "name" in m}


KEYS = existing_keys()


def key(name):
    """The mob key for an NPC or creature name: the existing one, else a slug."""
    return KEYS.get(name) or slug(name)


def creature_races(path=os.path.join(ROOT, "docs", "CREATURES.md")):
    """{lowercase name or package: race id} from the race table in CREATURES.md."""
    out = {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\|\s*(\d+)\s*\|\s*0x[0-9A-Fa-f]+\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|", line)
        if m:
            rid, name, pkg = int(m.group(1)), m.group(2).lower(), m.group(3).lower()
            out.setdefault(name, rid)
            if pkg:
                out.setdefault(pkg, rid)
    for rid, name in races_classes.RACES.items():
        out[name.lower()] = rid
    return out


def find_race(races, text):
    if not text:
        return None
    t = text.lower().replace(" ", "")
    if t in races:
        return races[t]
    for k, v in races.items():
        if k.replace(" ", "") == t:
            return v
    words = [w for w in re.split(r"[^a-z]+", text.lower()) if len(w) > 2]
    for w in reversed(words):                     # "giant black widow spider" -> spider
        for k, v in races.items():
            if k.startswith(w) or w in k:
                return v
    return None


class Batch:
    def __init__(self, folder, include_low=False):
        self.folder = folder
        self.records = {}
        self.issues = []
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".jsonl") or fn == "gaps.jsonl":
                continue
            for n, line in enumerate(open(os.path.join(folder, fn), encoding="utf-8"), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError as e:
                    self.issues.append(f"{fn}:{n}: bad JSON ({e})")
                    continue
                if not r.get("name") or not r.get("type"):
                    self.issues.append(f"{fn}:{n}: missing name or type")
                    continue
                if not r.get("sources"):
                    self.issues.append(f"{fn}:{n}: {r['name']}: no sources, skipped")
                    continue
                if r.get("confidence") == "low" and not include_low:
                    self.issues.append(f"{fn}:{n}: {r['name']}: low confidence, skipped")
                    continue
                self.records.setdefault(r["type"], []).append(r)

    def of(self, kind):
        return self.records.get(kind, [])

    def named(self, kind, name):
        return next((r for r in self.of(kind) if r["name"] == name), None)


# Which server constant each formula topic would replace (AGENT_INSTRUCTIONS.md "formula").
FORMULA_TARGETS = {
    "race starting attributes": "zone.RACE_ATTRIBUTES",
    "attribute gain per level": "zone.CLASS_ATTRIBUTES / zone.innate_bonus",
    "hit points per level": "zone.HP_BASE, CON_HP, HP_PER_LEVEL",
    "armor class mitigation": "combat.mitigate",
    "dodge/parry/block chance": "combat.BASE_DODGE, BASE_PARRY, BASE_BLOCK, DODGE_PER_DEX",
    "critical hit chance and damage": "combat.BASE_CRIT, CRIT_PER_DEX, CRIT_MULT",
    "experience per kill by level difference": "combat.KILL_XP (kill_xp)",
    "experience needed per level": "zone.xp_for_level",
    "endurance/energy pools": "zone.POOL_BASE, POOL_PER_POINT",
    "regeneration rates": "combat regeneration constants",
    "ability damage scaling": "combat.POWER_PER_LEVEL, POWER_PER_POINT",
}


def convert(batch, races):
    out = {"mobs.json": {}, "items.json": {}, "loot.json": {}, "merchants.json": {}, "quests.json": {},
           "dialogs.json": {}, "factions.json": {}, "recipes.json": {}, "spawns_unplaced.json": []}
    issue = batch.issues.append

    for r in batch.of("creature"):
        race = find_race(races, r.get("creature_kind") or r["name"])
        if race is None:
            issue(f"creature {r['name']}: no client race for {r.get('creature_kind')!r}")
            continue
        level = r.get("level") or (r.get("level_range") or [None])[0]
        m = {"name": r["name"], "pawn_class": "SGONPCPawn", "race": race, "level": level}
        if r.get("health"):
            m["health"] = r["health"]
        if isinstance(r.get("damage"), list):
            m["damage"] = r["damage"]
        if str(r.get("aggressive", "")).lower() == "yes":
            m["aggro_radius"] = r.get("aggro_range") or 600
        if r.get("loot_ref") or batch.named("loot", r["name"]):
            m["loot"] = slug(r.get("loot_ref") or r["name"])
        m["_source"] = r["sources"][0]["url"]
        out["mobs.json"][key(r["name"])] = m

    for r in batch.of("npc"):
        race = find_race(races, r.get("race"))
        m = {"name": r["name"], "pawn_class": "SGONPCPawn", "race": race if race is not None else 14,
             "level": r.get("level") or 10, "health": 300, "damage": [0, 0]}
        if race is None:
            issue(f"npc {r['name']}: race {r.get('race')!r} unknown, using Thestran (14)")
        if r.get("title"):
            m["title"] = r["title"]
        for s in r.get("services") or []:
            if s == "merchant":
                m["merchant"] = slug(r["name"])
            elif SERVICES.get(s):
                m[SERVICES[s]] = True
            elif s not in ("quest giver",):
                issue(f"npc {r['name']}: service {s!r} needs a manual setup")
        m["_source"] = r["sources"][0]["url"]
        out["mobs.json"][key(r["name"])] = m

    for r in batch.of("item"):
        it = {}
        t = r.get("item_type")
        if t in ITEM_TYPES:
            it["type"] = ITEM_TYPES[t]
        slot = r.get("slot")
        if slot == "bag":
            it["bag"] = r.get("bag_slots") or 8
        elif slot:
            if slot in SLOTS:
                it["slot"] = SLOTS[slot]
            else:
                issue(f"item {r['name']}: slot {slot!r} unknown")
        if r.get("rarity") in RARITIES:
            it["rarity"] = r["rarity"]
        for src, dst in (("level_required", "level"), ("armor", "armor"), ("description", "description")):
            if r.get(src) is not None:
                it[dst] = r[src]
        if isinstance(r.get("damage"), list):
            it["damage"] = r["damage"]
            it["delay"] = r.get("delay_seconds") or 2.0
        stats, mods, other = {}, {}, {}
        for k, v in (r.get("stats") or {}).items():
            low = k.lower()
            if low in vgmsg.ATTRIBUTES:
                stats[low] = v
            elif next((m for m in vgmsg.MOD_TYPES if m.lower() == low), None):
                mods[next(m for m in vgmsg.MOD_TYPES if m.lower() == low)] = v
            else:
                other[k] = v
        if stats:
            it["stats"] = stats
        if mods:
            it["mods"] = mods
        if other or r.get("effects"):
            it["_unsupported"] = {"stats": other or None, "effects": r.get("effects")}
            issue(f"item {r['name']}: {sorted(other) + (['effects'] if r.get('effects') else [])} kept in _unsupported")
        it["icon"] = 443                              # icons need the client id: set by hand
        it["_source"] = r["sources"][0]["url"]
        out["items.json"][r["name"]] = it

    for r in batch.of("loot"):
        drops = []
        for d in r.get("drops") or []:
            chance = d.get("chance")
            if isinstance(chance, str):
                m = re.search(r"([\d.]+)\s*%", chance)
                chance = float(m.group(1)) if m else {"common": 50, "uncommon": 20, "rare": 5}.get(chance.lower())
            if chance is None:
                issue(f"loot {r['name']}: {d.get('item')} has no usable chance")
                continue
            drops.append({"name": d["item"], "icon": 443, "quantity": d.get("quantity") or [1, 1],
                          "chance": round(chance / 100 if chance > 1 else chance, 3)})
        out["loot.json"][slug(r.get("source") or r["name"])] = drops

    for r in batch.of("merchant"):
        out["merchants.json"][slug(r.get("npc") or r["name"])] = [
            {"item": s["item"], "price": s.get("price_copper")} for s in r.get("sells") or []]

    next_id = 6000
    for r in batch.of("quest"):
        steps = []
        for s in r.get("steps") or []:
            k = s.get("kind")
            step = {"objective": s.get("objective") or ""}
            if k == "kill":
                step["kill"] = {key(s.get("target")): s.get("count") or 1}
            elif k == "collect":
                step["collect"] = {s.get("target"): s.get("count") or 1}
            elif k == "talk":
                step["talk"] = key(s.get("target"))
            else:
                issue(f"quest {r['name']}: step kind {k!r} needs a manual setup")
                continue
            steps.append(step)
        rw = r.get("rewards") or {}
        q = {"id": next_id, "name": r["name"], "level": r.get("level"), "giver": key(r.get("giver")),
             "greeting": r.get("start_text") or "", "description": r.get("description") or "",
             "summary": r.get("summary") or "", "accept_text": "", "steps": steps,
             "reward": {k: v for k, v in (("xp", rw.get("xp")), ("coin", rw.get("coin_copper")),
                                          ("items", rw.get("items") or None),
                                          ("choice", rw.get("choice") or None)) if v}}
        if r.get("turn_in"):
            q["turn_in"] = key(r["turn_in"])
        if r.get("prerequisites"):
            q["requires"] = [slug(p) for p in r["prerequisites"]]
        q["_source"] = r["sources"][0]["url"]
        out["quests.json"][slug(r["name"])] = q
        next_id += 1

    # Dialogue: [{"npc_says", "responses": [{"player_says", "leads_to", "requires", "reward"}]}]
    # -> dialogs.json {start, nodes: {id: {text, responses: [{text, goto}]}}}.
    for r in batch.of("dialogue"):
        conv = r.get("conversation") or r.get("tree") or []
        ids = {n.get("npc_says"): f"n{i}" for i, n in enumerate(conv)}
        nodes = {}
        for i, n in enumerate(conv):
            responses = []
            for resp in n.get("responses") or []:
                e = {"text": resp.get("player_says") or ""}
                target = resp.get("leads_to")
                if target and target != "end":
                    if target in ids:
                        e["goto"] = ids[target]
                    else:
                        issue(f"dialogue {r['name']}: reply {e['text']!r} leads to text not in the tree")
                if resp.get("requires") or resp.get("reward"):
                    e["_manual"] = {"requires": resp.get("requires"), "reward": resp.get("reward")}
                    issue(f"dialogue {r['name']}: reply {e['text']!r} has a condition or reward to set by hand")
                responses.append(e)
            nodes[f"n{i}"] = {"text": n.get("npc_says") or "", "responses": responses or [{"text": "Farewell."}]}
        if nodes:
            out["dialogs.json"][key(r.get("npc") or r["name"])] = {"start": "n0", "nodes": nodes,
                                                                    "_source": r["sources"][0]["url"]}

    # Factions -> factions.json with new ids (2001+); allies/enemies resolved by name.
    fids = {r["name"]: str(2001 + i) for i, r in enumerate(batch.of("faction"))}
    for r in batch.of("faction"):
        f = {"name": r["name"], "start": 0}
        for rel in ("allies", "enemies"):
            names = r.get(rel) or []
            ids = [int(fids[n]) for n in names if n in fids]
            if ids:
                f[rel] = ids
            if len(ids) < len(names):
                issue(f"faction {r['name']}: {rel} {[n for n in names if n not in fids]} are not in this batch")
        if r.get("changes"):
            f["_changes"] = r["changes"]
            issue(f"faction {r['name']}: standing changes need numbers set by hand")
        f["_source"] = r["sources"][0]["url"]
        out["factions.json"][fids[r["name"]]] = f

    # Recipes: inputs and output; the craft steps need client action ids, so they are left
    # for a person (see recipes.json for the stage format).
    for n, r in enumerate(batch.of("recipe")):
        output = r.get("output")
        out_name = output.get("item") if isinstance(output, dict) else output
        rec = {"id": 7001 + n, "name": r["name"], "description": r.get("description") or "",
               "icon": 475, "inputs": {i["item"]: i.get("count") or 1 for i in r.get("ingredients") or []},
               "output": out_name or r["name"], "xp": None, "stages": [],
               "_craft": r.get("craft"), "_level": r.get("level"), "_station": r.get("station"),
               "_tools": r.get("tools"), "_steps": r.get("steps"), "_source": r["sources"][0]["url"]}
        out["recipes.json"][slug(r["name"])] = rec
        issue(f"recipe {r['name']}: stages, actions and xp must be filled in by hand")

    # Spawns: raw locations can't be placed without a person checking the map.
    for r in batch.of("spawn"):
        out["spawns_unplaced.json"].append({"what": r.get("what") or r["name"], "zone": r.get("zone"),
                                            "chunk": r.get("chunk"), "location": r.get("location"),
                                            "count": r.get("count"), "movement": r.get("movement"),
                                            "respawn_time": r.get("respawn_time"),
                                            "_source": r["sources"][0]["url"]})

    # Formulas: written to FORMULAS.md next to the constants they would replace.
    batch.formulas = [dict(r, _target=FORMULA_TARGETS.get((r.get("topic") or "").lower(), "?"))
                      for r in batch.of("formula")]

    for kind in batch.records:
        if kind not in ("creature", "npc", "item", "loot", "merchant", "quest", "dialogue", "faction",
                        "recipe", "spawn", "formula"):
            issue(f"{len(batch.of(kind))} {kind} record(s) not converted automatically yet")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("batch", help="batch folder, e.g. raw/2026-10-14-wastelands-quests")
    ap.add_argument("--include-low", action="store_true", help="also convert low-confidence records")
    a = ap.parse_args(argv)
    folder = a.batch if os.path.isabs(a.batch) else os.path.join(HERE, a.batch)
    batch = Batch(folder, a.include_low)
    out = convert(batch, creature_races())
    dest = os.path.join(HERE, "reviewed", os.path.basename(folder.rstrip("/\\")), "proposed")
    os.makedirs(dest, exist_ok=True)
    for fn, data in out.items():
        if data:
            with open(os.path.join(dest, fn), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    if getattr(batch, "formulas", None):
        with open(os.path.join(dest, "FORMULAS.md"), "w", encoding="utf-8") as f:
            f.write("# Game formulas found\n\nEach one would replace a placeholder in the server code "
                    "(the target column). Check the sources before changing anything.\n\n"
                    "| Topic | Applies to | Values / formula | Target | Source | Confidence |\n|---|---|---|---|---|---|\n")
            for r in batch.formulas:
                vals = r.get("formula") or json.dumps(r.get("values"), ensure_ascii=False)
                f.write(f"| {r.get('topic')} | {r.get('applies_to') or ''} | {str(vals).replace('|', '/')} | "
                        f"{r['_target']} | {r['sources'][0]['url']} | {r.get('confidence')} |\n")
    with open(os.path.join(dest, "ISSUES.md"), "w", encoding="utf-8") as f:
        f.write("# Conversion issues\n\n" + ("\n".join(f"- {i}" for i in batch.issues) or "None.") + "\n")
    counts = {fn: len(d) for fn, d in out.items() if d}
    print(f"{dest}: {counts}, {len(batch.issues)} issue(s)")


if __name__ == "__main__":
    main()
