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
import math
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
RECORD_TYPES = set("npc creature spawn item loot merchant quest ability recipe diplomacy faction dialogue mount fish zone".split())


def record_errors(r):
    """Validate collection records before conversion; never coerce uncertain values."""
    errors = []
    if r["type"] not in RECORD_TYPES:
        errors.append("unknown record type")
    if not isinstance(r.get("notes"), str):
        errors.append("notes must be a string")
    for field in ("level", "health", "aggro_range", "bag_slots", "armor", "level_required",
                  "delay_seconds", "value_copper"):
        value = r.get(field)
        if value is not None and (type(value) not in (int, float)
                                  or not math.isfinite(value) or value < 0):
            errors.append(f"{field} must be a finite nonnegative number or null")
    for field in ("race", "creature_kind", "slot", "item_type", "rarity", "giver", "turn_in",
                  "loot_ref", "source", "npc", "title", "description", "start_text", "summary"):
        if r.get(field) is not None and not isinstance(r[field], str):
            errors.append(f"{field} must be a string or null")
    for field in ("damage", "level_range"):
        value = r.get(field)
        if value is not None and (not isinstance(value, list) or len(value) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in value)
                or value[0] > value[1]):
            errors.append(f"{field} must be an ordered pair of nonnegative numbers")
    for field in ("services", "prerequisites", "quests_given", "class_restrictions", "race_restrictions"):
        value = r.get(field)
        if value is not None and (not isinstance(value, list)
                                 or any(not isinstance(v, str) or not v.strip() for v in value)):
            errors.append(f"{field} must be a list of names or null")
    stats = r.get("stats")
    if stats is not None and (not isinstance(stats, dict) or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in stats.values())):
        errors.append("stats must contain finite numbers")
    rewards = r.get("rewards")
    if r["type"] == "quest" and rewards is not None:
        if not isinstance(rewards, dict):
            errors.append("quest rewards must be an object or null")
        else:
            for field in ("items", "choice"):
                value = rewards.get(field)
                if value is not None and (not isinstance(value, list) or any(
                        not isinstance(v, str) or not v.strip() for v in value)):
                    errors.append(f"reward {field} must be a list of names")
            for field in ("xp", "coin_copper"):
                value = rewards.get(field)
                if value is not None and (type(value) is not int or value < 0):
                    errors.append(f"reward {field} must be a nonnegative integer")
    for field, target in (("steps", "target"), ("drops", "item"), ("sells", "item")):
        value = r.get(field)
        if value is None:
            continue
        if not isinstance(value, list):
            errors.append(f"{field} must be a list or null")
            continue
        for entry in value:
            if not isinstance(entry, dict):
                errors.append(f"{field} entries must be objects")
                continue
            if entry.get(target) is not None and not isinstance(entry[target], str):
                errors.append(f"{field} {target} must be a string or null")
            for numeric in ("count", "price_copper"):
                n = entry.get(numeric)
                if n is not None and (type(n) is not int or n < (1 if numeric == "count" else 0)):
                    errors.append(f"{field} {numeric} has an invalid value")
            quantity = entry.get("quantity")
            if quantity is not None and (not isinstance(quantity, list) or len(quantity) != 2
                    or any(type(n) is not int or n < 1 for n in quantity)
                    or quantity[0] > quantity[1]):
                errors.append(f"{field} quantity must be an ordered positive integer pair")
    return errors


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def existing_keys(path=os.path.join(ROOT, "server", "content", "mobs.json")):
    """{in-game name: mob key} of the server's current mobs, so records update them in place."""
    try:
        with open(path, encoding="utf-8") as f:
            mobs = json.load(f)
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
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
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
    # Ambiguous substring matches are not evidence of a client model.
    return None


class Batch:
    def __init__(self, folder, include_low=False):
        self.folder = folder
        self.records = {}
        self.issues = []
        self.validation_issues = []
        seen, duplicates = {}, set()
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".jsonl") or fn == "gaps.jsonl":
                continue
            with open(os.path.join(folder, fn), encoding="utf-8") as f:
                lines = f.readlines()
            for n, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError as e:
                    self.issues.append(f"{fn}:{n}: bad JSON ({e})")
                    continue
                if not isinstance(r, dict):
                    self.issues.append(f"{fn}:{n}: record must be a JSON object")
                    continue
                if not all(isinstance(r.get(k), str) and r[k].strip() for k in ("name", "type")):
                    self.issues.append(f"{fn}:{n}: missing name or type")
                    continue
                if not r.get("sources"):
                    self.issues.append(f"{fn}:{n}: {r['name']}: no sources, skipped")
                    continue
                sources = r["sources"]
                if not isinstance(sources, list) or not all(
                    isinstance(s, dict)
                    and isinstance(s.get("url"), str)
                    and s["url"].startswith(("https://", "http://"))
                    and isinstance(s.get("title"), str) and s["title"].strip()
                    and "date" in s and (s["date"] is None or isinstance(s["date"], str))
                    for s in sources
                ):
                    self.issues.append(f"{fn}:{n}: {r['name']}: invalid sources, skipped")
                    continue
                if r.get("confidence") not in ("high", "medium", "low"):
                    self.issues.append(f"{fn}:{n}: {r['name']}: invalid confidence, skipped")
                    continue
                if r.get("confidence") == "low" and not include_low:
                    self.issues.append(f"{fn}:{n}: {r['name']}: low confidence, skipped")
                    continue
                errors = record_errors(r)
                if errors:
                    self.issues.extend(f"{fn}:{n}: {r['name']}: {e}, skipped" for e in errors)
                    continue
                identity = (r["type"], r["name"])
                if identity in seen:
                    duplicates.add(identity)
                    self.issues.append(f"{fn}:{n}: duplicate {identity!r}: all matching records withheld")
                    continue
                seen[identity] = r
                self.records.setdefault(r["type"], []).append(r)
        for kind, name in duplicates:
            self.records[kind] = [r for r in self.records[kind] if r["name"] != name]
        destinations = {}
        for kind, records in self.records.items():
            for r in records:
                if kind in ("npc", "creature"):
                    dest = ("mobs", key(r["name"]))
                elif kind in ("quest", "loot", "merchant"):
                    dest = (kind, slug(r.get("source" if kind == "loot" else "npc") or r["name"]))
                else:
                    continue
                destinations.setdefault(dest, []).append((kind, r["name"]))
        for dest, identities in destinations.items():
            if len(identities) > 1:
                self.issues.append(f"output key collision {dest!r}: {identities!r}; all withheld")
                for kind, name in identities:
                    self.records[kind] = [r for r in self.records[kind] if r["name"] != name]
        self.validation_issues = list(self.issues)

    def of(self, kind):
        return self.records.get(kind, [])

    def named(self, kind, name):
        return next((r for r in self.of(kind) if r["name"] == name), None)


def quest_ids():
    """Reserve live and previously proposed IDs; reuse IDs for the same quest key."""
    import glob
    paths = [os.path.join(ROOT, "server", "content", "quests.json")]
    paths += sorted(glob.glob(os.path.join(HERE, "reviewed", "*", "proposed", "quests.json")))
    ids, used = {}, set()
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            quests = json.load(f)
        for name, q in quests.items():
            if isinstance(q, dict) and type(q.get("id")) is int:
                used.add(q["id"])
                ids.setdefault(name, q["id"])
    return ids, used


def reference_issues(out):
    """Check proposed references against proposals and live content without modifying either."""
    known = {fn: set(records) for fn, records in out.items()}
    issues = []
    for fn in known:
        path = os.path.join(ROOT, "server", "content", fn)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                known[fn].update(json.load(f))

    def check(owner, filename, name):
        if name not in known[filename]:
            issues.append(f"{owner}: unresolved {filename} reference {name!r}; manual setup required")

    for name, mob in out["mobs.json"].items():
        for field, filename in (("loot", "loot.json"), ("merchant", "merchants.json")):
            if field in mob:
                check(f"mob {name}", filename, mob[field])
    for name, drops in out["loot.json"].items():
        for drop in drops:
            check(f"loot {name}", "items.json", drop["name"])
    for name, stock in out["merchants.json"].items():
        check(f"merchant {name}", "mobs.json", name)
        for sale in stock:
            check(f"merchant {name}", "items.json", sale["item"])
    for name, q in out["quests.json"].items():
        for field in ("giver", "turn_in"):
            if field in q:
                check(f"quest {name}", "mobs.json", q[field])
        for prerequisite in q.get("requires", []):
            check(f"quest {name}", "quests.json", prerequisite)
        for step in q["steps"]:
            for target in step.get("kill", {}):
                check(f"quest {name}", "mobs.json", target)
            for target in step.get("collect", {}):
                check(f"quest {name}", "items.json", target)
            if "talk" in step:
                check(f"quest {name}", "mobs.json", step["talk"])
        for field in ("items", "choice"):
            for item in q["reward"].get(field, []):
                check(f"quest {name}", "items.json", item)
    return list(dict.fromkeys(issues))


def convert(batch, races):
    out = {"mobs.json": {}, "items.json": {}, "loot.json": {}, "merchants.json": {}, "quests.json": {}}
    issue = batch.issues.append

    for r in batch.of("creature"):
        race = find_race(races, r.get("creature_kind"))
        if race is None:
            issue(f"creature {r['name']}: no client race for {r.get('creature_kind')!r}")
            continue
        level = r.get("level") or (r.get("level_range") or [None])[0]
        if level is None or r.get("health") is None:
            issue(f"creature {r['name']}: unknown level or required health, skipped")
            continue
        m = {"name": r["name"], "pawn_class": "SGONPCPawn", "race": race, "level": level}
        if r.get("health"):
            m["health"] = r["health"]
        if isinstance(r.get("damage"), list):
            m["damage"] = r["damage"]
        if str(r.get("aggressive", "")).lower() == "yes":
            if r.get("aggro_range") is not None:
                m["aggro_radius"] = r["aggro_range"]
            else:
                issue(f"creature {r['name']}: aggressive but aggro range unknown; no radius invented")
        if r.get("loot_ref") or batch.named("loot", r["name"]):
            m["loot"] = slug(r.get("loot_ref") or r["name"])
        m["_source"] = r["sources"][0]["url"]
        out["mobs.json"][key(r["name"])] = m

    for r in batch.of("npc"):
        race = find_race(races, r.get("race"))
        if race is None or r.get("level") is None or r.get("health") is None:
            issue(f"npc {r['name']}: unknown client race, level or required health, skipped; no defaults invented")
            continue
        m = {"name": r["name"], "pawn_class": "SGONPCPawn", "race": race,
             "level": r["level"], "health": r["health"]}
        if r.get("damage") is not None:
            m["damage"] = r["damage"]
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
        elif t is not None:
            it.setdefault("_unsupported", {})["item_type"] = t
            issue(f"item {r['name']}: type {t!r} requires manual mapping")
        slot = r.get("slot")
        if slot == "bag":
            if r.get("bag_slots") is not None:
                it["bag"] = r["bag_slots"]
            else:
                issue(f"item {r['name']}: bag capacity unknown; no capacity invented")
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
            if r.get("delay_seconds") is not None:
                it["delay"] = r["delay_seconds"]
            else:
                issue(f"item {r['name']}: weapon delay unknown; no delay invented")
        stats, mods, other = {}, {}, {}
        normalize = lambda name: re.sub(r"[^a-z0-9]", "", name.lower())
        stat_names = {normalize(name): name for name in vgmsg.STAT_IDS}
        mod_names = {normalize(name): name for name in vgmsg.MOD_TYPES}
        mapped = {}
        for k, v in (r.get("stats") or {}).items():
            if isinstance(v, float) and not v.is_integer():
                other[k] = v
                issue(f"item {r['name']}: fractional {k} cannot be encoded without verified scaling; kept unsupported")
                continue
            normalized = normalize(k)
            canonical = stat_names.get(normalized) or mod_names.get(normalized)
            if canonical is None:
                other[k] = v
                continue
            target = stats if normalized in stat_names else mods
            identity = ("stat" if target is stats else "mod", canonical)
            if identity in mapped and mapped[identity][1] != v:
                old_name, old_value = mapped[identity]
                other[old_name], other[k] = old_value, v
                target.pop(canonical, None)
                issue(f"item {r['name']}: contradictory aliases for {canonical}; values withheld")
            elif not any(normalize(name) == normalized for name in other):
                target[canonical] = v
                mapped[identity] = (k, v)
        if stats:
            it["stats"] = stats
        if mods:
            it["mods"] = mods
        if other or r.get("effects"):
            it.setdefault("_unsupported", {}).update({"stats": other or None, "effects": r.get("effects")})
            issue(f"item {r['name']}: {sorted(other) + (['effects'] if r.get('effects') else [])} kept in _unsupported")
        for field in ("class_restrictions", "race_restrictions", "bind", "no_drop", "quest_item",
                      "stack_size", "value_copper"):
            if r.get(field) is not None:
                it.setdefault("_unsupported", {})[field] = r[field]
                issue(f"item {r['name']}: {field} retained in _unsupported; manual mapping required")
        it["icon"] = 443                              # icons need the client id: set by hand
        it["_source"] = r["sources"][0]["url"]
        out["items.json"][r["name"]] = it

    for r in batch.of("loot"):
        drops = []
        incomplete = False
        for d in r.get("drops") or []:
            chance = d.get("chance")
            if isinstance(chance, str):
                m = re.fullmatch(r"\s*(\d+(?:\.\d+)?|\.\d+)\s*%\s*", chance)
                chance = float(m.group(1)) if m else None
            if (type(chance) not in (int, float) or not math.isfinite(chance)
                    or not 0 <= chance <= 100):
                issue(f"loot {r['name']}: {d.get('item')} has no usable chance")
                incomplete = True
                continue
            if not d.get("item") or d.get("quantity") is None:
                issue(f"loot {r['name']}: unknown item or quantity, entire table withheld")
                incomplete = True
                continue
            drops.append({"name": d["item"], "icon": 443, "quantity": d["quantity"],
                          "chance": chance / 100})
        if not incomplete and drops:
            out["loot.json"][slug(r.get("source") or r["name"])] = drops

    for r in batch.of("merchant"):
        if not r.get("npc") or not r.get("sells") or any(
                not s.get("item") or s.get("price_copper") is None for s in r["sells"]):
            issue(f"merchant {r['name']}: unknown NPC, inventory or price; inventory withheld")
            continue
        out["merchants.json"][slug(r.get("npc") or r["name"])] = [
            {"item": s["item"], "price": s.get("price_copper")} for s in r.get("sells") or []]

    known_ids, used_ids = quest_ids() if batch.of("quest") else ({}, set())
    next_id = 6000
    for r in batch.of("quest"):
        if not r.get("giver") or r.get("level") is None or not r.get("steps"):
            issue(f"quest {r['name']}: unknown giver, level or objectives; quest withheld")
            continue
        steps = []
        unsupported = False
        for s in r.get("steps") or []:
            k = s.get("kind")
            if not s.get("target") or (k in ("kill", "collect") and s.get("count") is None):
                issue(f"quest {r['name']}: unknown step target or count")
                unsupported = True
                continue
            step = {"objective": s.get("objective") or ""}
            if k == "kill":
                step["kill"] = {key(s["target"]): s["count"]}
            elif k == "collect":
                step["collect"] = {s["target"]: s["count"]}
            elif k == "talk":
                step["talk"] = key(s.get("target"))
            else:
                issue(f"quest {r['name']}: step kind {k!r} needs a manual setup")
                unsupported = True
                continue
            steps.append(step)
        if unsupported:
            issue(f"quest {r['name']}: skipped to avoid exporting incomplete requirements")
            continue
        quest_key = slug(r["name"])
        while next_id in used_ids:
            next_id += 1
        quest_id = known_ids.get(quest_key, next_id)
        used_ids.add(quest_id)
        known_ids[quest_key] = quest_id
        rw = r.get("rewards") or {}
        q = {"id": quest_id, "name": r["name"], "level": r.get("level"), "giver": key(r.get("giver")),
             "greeting": r.get("start_text") or "", "description": r.get("description") or "",
             "summary": r.get("summary") or "", "accept_text": "", "steps": steps,
             "reward": {k: v for k, v in (("xp", rw.get("xp")), ("coin", rw.get("coin_copper")),
                                          ("items", rw.get("items") or None),
                                          ("choice", rw.get("choice") or None)) if v is not None}}
        if r.get("turn_in"):
            q["turn_in"] = key(r["turn_in"])
        if r.get("prerequisites"):
            q["requires"] = [slug(p) for p in r["prerequisites"]]
        q["_source"] = r["sources"][0]["url"]
        out["quests.json"][quest_key] = q

    for kind in batch.records:
        if kind not in ("creature", "npc", "item", "loot", "merchant", "quest"):
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
    batch.issues.extend(reference_issues(out))
    dest = os.path.join(HERE, "reviewed", os.path.basename(folder.rstrip("/\\")), "proposed")
    os.makedirs(dest, exist_ok=True)
    for fn, data in out.items():
        with open(os.path.join(dest, fn), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(dest, "PROVENANCE.json"), "w", encoding="utf-8") as f:
        json.dump({kind: {r["name"]: {k: r[k] for k in ("sources", "confidence", "notes")}
                          for r in records} for kind, records in batch.records.items()},
                  f, indent=2, ensure_ascii=False)
    with open(os.path.join(dest, "ISSUES.md"), "w", encoding="utf-8") as f:
        f.write("# Conversion issues\n\n" + ("\n".join(f"- {i}" for i in batch.issues) or "None.") + "\n")
    counts = {fn: len(d) for fn, d in out.items() if d}
    print(f"{dest}: {counts}, {len(batch.issues)} issue(s)")


if __name__ == "__main__":
    main()
