"""World content loaded from JSON (server/content/): mob templates, loot tables
and per-chunk spawns. The client has none of this data (docs/CONTENT_EDITOR.md);
these files are what a future content editor will write.

    content/mobs.json            {template id: {name, pawn_class, race, level, health,
                                  damage [min, max], gear [[type, mesh, slot]...], loot}}
    content/loot.json            {table id: [{name, icon, quantity [min, max], chance}]}
    content/spawns/<chunk>.json  {"spawns": [{mob, x, y, z?, yaw?, respawn?}]}

Keys starting with "_" are comments."""
import json
import os
import random

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
PAWN_PACKAGE = "SGOUnrealAbstractionLayer"
DEFAULT_RESPAWN = 60
COLLISION_HEIGHT = 90.0     # pawn half height: spawn this far above the terrain


def _load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")} if isinstance(data, dict) else data


class Content:
    def __init__(self, directory=CONTENT_DIR):
        self.directory = directory
        self.mobs = _load(os.path.join(directory, "mobs.json"))
        self.loot = _load(os.path.join(directory, "loot.json"))
        self.items = _load(os.path.join(directory, "items.json"))
        self.merchants = _load(os.path.join(directory, "merchants.json"))
        self.quests = _load(os.path.join(directory, "quests.json"))
        self.recipes = _load(os.path.join(directory, "recipes.json"))
        self.diplomacy = _load(os.path.join(directory, "diplomacy.json"))
        self.abilities = _load(os.path.join(directory, "abilities.json"))
        self.factions = _load(os.path.join(directory, "factions.json"))
        self.workorders = _load(os.path.join(directory, "workorders.json"))
        self.dialogs = _load(os.path.join(directory, "dialogs.json"))
        self.riftways = _load(os.path.join(directory, "riftways.json"))
        self.plots = _load(os.path.join(directory, "plots.json"))
        self.titles = _load(os.path.join(directory, "titles.json"))
        self.assembly = _load(os.path.join(directory, "assembly.json"))
        self.chains = _load(os.path.join(directory, "chains.json"))
        self.counters = _load(os.path.join(directory, "counters.json"))
        self.rescues = _load(os.path.join(directory, "rescues.json"))
        self.songs = _load(os.path.join(directory, "songs.json"))
        self.forms = _load(os.path.join(directory, "forms.json"))
        outposts_path = os.path.join(directory, "outposts.json")
        self.outposts = _load(outposts_path) if os.path.exists(outposts_path) else {}
        hints_path = os.path.join(directory, "hints.json")
        self.hints = _load(hints_path) if os.path.exists(hints_path) else {}
        aa_path = os.path.join(directory, "aa.json")
        self.aa = _load(aa_path) if os.path.exists(aa_path) else {}
        self._terrain = {}

    def spawns(self, level, client_dir=None):
        """[(spawn dict with resolved z, template dict)] for a chunk, or []."""
        path = os.path.join(self.directory, "spawns", level + ".json")
        if not os.path.exists(path):
            return []
        out = []
        for s in _load(path).get("spawns", []):
            template = self.mobs.get(s["mob"])
            if template is None:
                raise ValueError(f"{path}: unknown mob template {s['mob']!r}")
            s = dict(s)
            if s.get("z") is None:
                s["z"] = self.ground_z(level, s["x"], s["y"], client_dir)
            out.append((s, template))
        return out

    def ground_z(self, level, x, y, client_dir):
        import terrain
        if level not in self._terrain:
            path = os.path.join(client_dir or os.path.join(self.directory, "..", ".."),
                                "Assets", "Maps", level + ".vgr")
            self._terrain[level] = terrain.Terrain(path) if os.path.exists(path) else None
        z = self._terrain[level].height(x, y) if self._terrain[level] else None
        return (z if z is not None else 0.0) + COLLISION_HEIGHT

    def item(self, name):
        """Item template {icon, slot, mesh} by name ({} if unknown)."""
        return self.items.get(name, {})

    def roll_loot(self, table_id, rng=random):
        """[(name, icon, quantity)] dropped from a loot table. The icon: the row's, else the item's
        in items.json, else a sack (442; the old default 443 is a red "prohibited" sign)."""
        drops = []
        for entry in self.loot.get(table_id, []):
            if rng.random() <= entry.get("chance", 1.0):
                lo, hi = entry.get("quantity", [1, 1])
                icon = entry.get("icon", self.items.get(entry["name"], {}).get("icon", 442))
                drops.append((entry["name"], icon, rng.randint(lo, hi)))
        return drops


def validate(directory=CONTENT_DIR):
    """Problems found in the content files (empty list = all good)."""
    problems = []
    c = Content(directory)
    import songs as song_rules
    for cls, parts in c.songs.items():
        if cls.startswith("_"):
            continue
        for name, p in parts.items():
            if p.get("part") not in song_rules.PARTS:
                problems.append(f"songs {cls}/{name}: unknown part {p.get('part')!r}")
        if not any(p.get("part") == "melody" for p in parts.values()):
            problems.append(f"songs {cls}: no melody (a song needs one)")
    import races_classes
    attributes = ("strength", "constitution", "dexterity", "vitality", "intelligence", "wisdom")
    for cls, forms in c.forms.items():
        if cls.startswith("_"):
            continue
        if cls not in races_classes.ADVENTURING_CLASSES.values():
            problems.append(f"forms {cls}: not a class name (races_classes)")
        for name, f in (forms.items() if isinstance(forms, dict) else []):
            if not isinstance(f, dict):
                problems.append(f"forms {cls}/{name}: must be an object")
                continue
            if f.get("stat") not in attributes:
                problems.append(f"forms {cls}/{name}: stat must be one of {', '.join(attributes)}")
            if not isinstance(f.get("bonus", 0), (int, float)):
                problems.append(f"forms {cls}/{name}: bonus must be a number")
            if "abilities" in f and not (isinstance(f["abilities"], list) and all(isinstance(a, str) for a in f["abilities"])):
                problems.append(f"forms {cls}/{name}: abilities must be a list of ability names")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    pair = lambda v: isinstance(v, list) and len(v) == 2 and all(num(x) for x in v)
    kinds = ("strike", "dot", "heal", "buff", "fear", "pet", "sprint", "recall", "recall_house")
    for name, a in c.abilities.items():
        if name.startswith("_"):
            continue
        if not isinstance(a, dict):
            problems.append(f"ability {name}: must be an object")
            continue
        if "kind" in a and a["kind"] not in kinds:
            problems.append(f"ability {name}: kind must be one of {', '.join(kinds)}")
        for k in ("refresh", "cast", "icon", "duration", "bonus", "ticks", "interval", "speed"):
            if k in a and not num(a[k]):
                problems.append(f"ability {name}: {k} must be a number")
        for k in ("damage", "amount"):
            if k in a and not pair(a[k]):
                problems.append(f"ability {name}: {k} must be [min, max]")
        if a.get("kind") == "pet" and not isinstance(a.get("pet"), dict):
            problems.append(f"ability {name}: a pet ability needs \"pet\" {{name, race, ...}}")
    for tid, t in c.titles.items():
        if not tid.startswith("_") and not (isinstance(t, dict) and isinstance(t.get("name"), str) and t["name"]):
            problems.append(f"title {tid}: needs a name")
    for label, table in (("chains", c.chains), ("counters", c.counters), ("rescues", c.rescues)):
        for cls in table:
            if not cls.startswith("_") and cls not in races_classes.ADVENTURING_CLASSES.values():
                problems.append(f"{label} {cls}: not a class name (races_classes)")
    for oid, o in c.outposts.items():
        if oid.startswith("_"):
            continue
        if not (isinstance(o, dict) and isinstance(o.get("chunk"), str) and pair(o.get("loc")) and num(o.get("radius"))):
            problems.append(f"outpost {oid}: needs chunk, loc [x, y] and radius")
    loot_names = {e.get("name") for rows in c.loot.values() if isinstance(rows, list) for e in rows if isinstance(e, dict)}
    for pid, p in c.plots.items():
        if pid.startswith("_"):
            continue
        if not (isinstance(p, dict) and isinstance(p.get("chunk"), str) and isinstance(p.get("loc"), list)
                and len(p["loc"]) >= 2 and num(p.get("cost", 0))):
            problems.append(f"plot {pid}: needs chunk, loc [x, y, z] and a numeric cost")
            continue
        for b in p.get("buildings", []):
            for item in (b.get("materials") or {}):
                if item not in c.items and item not in loot_names:   # loot-only items count too
                    problems.append(f"plot {pid} building {b.get('name')}: unknown material {item}")
            for mob in b.get("npcs", []):
                if mob not in c.mobs:
                    problems.append(f"plot {pid} building {b.get('name')}: unknown NPC {mob}")
    for rid, r in c.assembly.items():
        if rid.startswith("_"):
            continue
        if not isinstance(r, dict) or not num(r.get("id")):
            problems.append(f"assembly {rid}: needs a numeric id")
            continue
        if r.get("reward") not in c.items:
            problems.append(f"assembly {rid}: reward {r.get('reward')} is not in items.json")
        ing = r.get("ingredients", [])
        if len(ing) > 5:
            problems.append(f"assembly {rid}: at most 5 ingredients")
        for i in ing:
            if not isinstance(i, dict) or i.get("item") not in c.items:
                problems.append(f"assembly {rid}: unknown ingredient {i.get('item') if isinstance(i, dict) else i}")
    for hid, h in c.hints.items():
        if not hid.startswith("_") and not (isinstance(h, dict) and isinstance(h.get("title"), str) and isinstance(h.get("text"), str)):
            problems.append(f"hint {hid}: needs title and text")
    for key, r in c.riftways.items():
        if key.startswith("_"):
            continue
        if not isinstance(r, dict):
            problems.append(f"riftway {key}: must be an object")
            continue
        if r.get("color") not in ("green", "blue", "yellow", "red", "purple"):
            problems.append(f"riftway {key}: color must be green, blue, yellow, red or purple")
        if r.get("chunk") and not all(isinstance(r.get(k), (int, float)) for k in ("x", "y")):
            problems.append(f"riftway {key}: an open destination (chunk set) needs x and y")
    for mid, m in c.mobs.items():
        if isinstance(m, dict) and m.get("trainer_classes") and not (
                isinstance(m["trainer_classes"], list)
                and all(x in races_classes.ADVENTURING_CLASSES.values() for x in m["trainer_classes"])):
            problems.append(f"mob {mid}: trainer_classes must be class names (races_classes)")
        # "riftway": "" is a stone you can travel from that is not itself a destination
        if isinstance(m, dict) and m.get("riftway") not in (None, "") and m["riftway"] not in c.riftways:
            problems.append(f"mob {mid}: riftway {m['riftway']} is not in riftways.json")
    for mid, m in c.mobs.items():
        for key in ("name", "pawn_class", "race", "health"):
            if key not in m:
                problems.append(f"mob {mid}: missing {key}")
        if m.get("merchant") and m["merchant"] not in c.merchants:
            problems.append(f"mob {mid}: unknown merchant list {m['merchant']}")
        if "faction" in m and str(m["faction"]) not in c.factions:
            problems.append(f"mob {mid}: unknown faction {m['faction']}")
        if m.get("loot") and m["loot"] not in c.loot:
            problems.append(f"mob {mid}: unknown loot table {m['loot']}")
        for g in m.get("gear", []):
            if len(g) != 3:
                problems.append(f"mob {mid}: gear entry {g} needs [type, mesh, slot]")
        ch = m.get("chatter")
        if ch is not None and not (isinstance(ch, list) and all(isinstance(x, str) and x.strip() for x in ch)):
            problems.append(f"mob {mid}: chatter must be a list of lines")
        if "chatter_every" in m and not (isinstance(m["chatter_every"], (int, float)) and m["chatter_every"] >= 10):
            problems.append(f"mob {mid}: chatter_every must be at least 10 seconds")
        if "difficulty" in m and m["difficulty"] not in range(6):
            problems.append(f"mob {mid}: difficulty must be 0-5 (0 slightly easier ... 5 extremely difficult)")
        if "flee_at" in m and not (isinstance(m["flee_at"], (int, float)) and 0 < m["flee_at"] < 1):
            problems.append(f"mob {mid}: flee_at must be a health share between 0 and 1")
        if "crit" in m and not (isinstance(m["crit"], (int, float)) and 0 <= m["crit"] <= 1):
            problems.append(f"mob {mid}: crit must be a chance from 0 to 1")
        if "aggro_say" in m and not isinstance(m["aggro_say"], str):
            problems.append(f"mob {mid}: aggro_say must be a line of text")
    import zone as zone_rules
    import vgmsg as vg
    import grouploot as loot_rules
    for name, it in c.items.items():
        if not isinstance(it, dict):
            continue
        if "type" in it and it["type"] not in zone_rules.ITEM_TYPE_IDS:
            problems.append(f"item {name}: unknown type {it['type']!r}")
        if "slot" in it and it["slot"] not in vg.EQUIP_SLOTS:
            problems.append(f"item {name}: unknown slot {it['slot']!r}")
        for f in it.get("flags", []):
            if f not in zone_rules.ITEM_FLAGS:
                problems.append(f"item {name}: unknown flag {f!r}")
        if "rarity" in it and it["rarity"] not in loot_rules.RARITY_NAMES:
            problems.append(f"item {name}: unknown rarity {it['rarity']!r}")
        for k in (it.get("stats") or {}):
            if k not in vg.STAT_IDS:
                problems.append(f"item {name}: unknown stat {k!r}")
        for k in (it.get("mods") or {}):
            if k not in vg.MOD_TYPES:
                problems.append(f"item {name}: unknown mod {k!r}")
        use = it.get("use")
        if use is not None and (not isinstance(use, dict) or set(use) - {"heal", "energy", "endurance"}):
            problems.append(f"item {name}: use must be {{heal, energy, endurance: n}}")
        if "cooldown" in it and not (isinstance(it["cooldown"], (int, float)) and it["cooldown"] >= 0):
            problems.append(f"item {name}: cooldown must be seconds")
        if "fireworks" in it and not (isinstance(it["fireworks"], int) and 60000 <= it["fireworks"] < 70000):
            problems.append(f"item {name}: fireworks must be an ITEM_ABILITIES id (60002-60022)")
        spy = it.get("spyglass")
        if spy is not None and not (isinstance(spy, dict) and 1 <= spy.get("fov", 20) <= 170
                                    and 0 < spy.get("seconds", 1) <= 30):
            problems.append(f"item {name}: spyglass must be {{fov: 1-170, seconds: 0-30}}")
        if "salvage_kit" in it and not isinstance(it["salvage_kit"], bool):
            problems.append(f"item {name}: salvage_kit must be true or false")
        for opt in it.get("salvage") or []:
            if not (isinstance(opt, list) and len(opt) == 2 and opt[0] in c.items and isinstance(opt[1], int) and opt[1] > 0):
                problems.append(f"item {name}: salvage entry {opt!r} needs a known item and a quantity")
        conv = it.get("convert")
        if conv is not None:
            into = conv.get("into") if isinstance(conv, dict) else None
            if not (isinstance(conv, dict) and isinstance(conv.get("count"), int) and conv["count"] > 0
                    and isinstance(into, list) and 1 <= len(into) <= 3):
                problems.append(f"item {name}: convert must be {{count: n, into: [[item, qty], ...] (1-3)}}")
            else:
                for opt in into:
                    if not (isinstance(opt, list) and len(opt) == 2 and opt[0] in c.items
                            and isinstance(opt[1], int) and opt[1] > 0):
                        problems.append(f"item {name}: convert option {opt!r} needs a known item and a quantity")
    import aa as aa_rules
    import vgmsg as vg
    aa_ids = [a.get("id") for a in c.aa.get("abilities", [])]
    if len(aa_ids) != len(set(aa_ids)):
        problems.append("aa: ability ids must be unique (0x85a train sends only the id)")
    for a in c.aa.get("abilities", []):
        if a.get("list") not in aa_rules.LISTS:
            problems.append(f"aa {a.get('id')}: unknown list {a.get('list')!r}")
        for k in (a.get("stats") or {}):
            if k not in vg.STAT_IDS:
                problems.append(f"aa {a.get('id')}: unknown attribute {k!r}")
        for r in (a.get("requires") or {}):
            if int(r) not in aa_ids:
                problems.append(f"aa {a.get('id')}: requires unknown ability {r}")
    for tid, entries in c.loot.items():
        if not isinstance(entries, list):
            problems.append(f"loot {tid}: must be a list of drops")
            continue
        for n, e in enumerate(entries):
            if not isinstance(e, dict) or not str(e.get("name", "")).strip():
                problems.append(f"loot {tid} row {n + 1}: needs an item name")
                continue
            ch = e.get("chance", 1.0)
            if not isinstance(ch, (int, float)) or not 0 <= ch <= 1:
                problems.append(f"loot {tid} row {n + 1}: chance must be 0..1")
            q = e.get("quantity", [1, 1])
            if not (isinstance(q, list) and len(q) == 2 and all(isinstance(x, int) and x >= 1 for x in q) and q[0] <= q[1]):
                problems.append(f"loot {tid} row {n + 1}: quantity must be [min, max] with 1 <= min <= max")
    for lid, entries in c.merchants.items():
        for e in entries:
            if e.get("item") not in c.items:
                problems.append(f"merchant {lid}: item {e.get('item')!r} not in items.json")
    for qid, q in c.quests.items():
        if q.get("giver") not in c.mobs:
            problems.append(f"quest {qid}: unknown giver {q.get('giver')}")
        if q.get("turn_in", q.get("giver")) not in c.mobs:
            problems.append(f"quest {qid}: unknown turn_in {q.get('turn_in')}")
        steps = q.get("steps") or [{"kill": q.get("kill")}]
        for n, step in enumerate(steps):
            kinds = [k for k in ("kill", "collect", "talk") if step.get(k)]
            if len(kinds) != 1:
                problems.append(f"quest {qid} step {n}: needs exactly one of kill, collect, talk")
            for mob in list(step.get("kill") or {}) + ([step["talk"]] if step.get("talk") else []):
                if mob not in c.mobs:
                    problems.append(f"quest {qid} step {n}: unknown mob {mob}")
            for name in step.get("collect") or {}:
                if name not in c.items:
                    problems.append(f"quest {qid} step {n}: item {name!r} not in items.json")
        for name in q.get("reward", {}).get("items", []):
            if name not in c.items:
                problems.append(f"quest {qid}: reward item {name!r} not in items.json")
        for r in q.get("requires", []):
            if r not in c.quests:
                problems.append(f"quest {qid}: requires unknown quest {r}")
    dip = c.diplomacy
    for cid in dip.get("deck", []):
        if str(cid) not in dip.get("cards", {}):
            problems.append(f"diplomacy deck: unknown card {cid}")
    for pid, p in dip.get("parleys", {}).items():
        for cid in p.get("npc_cards", []):
            if str(cid) not in dip.get("cards", {}):
                problems.append(f"parley {pid}: unknown card {cid}")
        if not p.get("npc_cards"):
            problems.append(f"parley {pid}: needs npc_cards")
        elif not any(not dip["cards"].get(str(cid), {}).get("cost") for cid in p["npc_cards"]):
            problems.append(f"parley {pid}: needs at least one npc card without a cost")
    for mid, m in c.mobs.items():
        for key in (m.get("parley") if isinstance(m, dict) and isinstance(m.get("parley"), list) else []):
            if key not in dip.get("parleys", {}):
                problems.append(f"mob {mid}: parley {key} is not in diplomacy.json")
        if isinstance(m, dict) and isinstance(m.get("parley"), str) and m["parley"] not in dip.get("parleys", {}):
            problems.append(f"mob {mid}: unknown parley {m['parley']}")
    for rid, r in c.recipes.items():
        for stage in r.get("stages", [{"steps": r.get("steps", [])}]):
            for st in stage["steps"]:
                if st.get("tool") and st["tool"] not in c.items:
                    problems.append(f"recipe {rid}: tool {st['tool']!r} not in items.json")
        for name in list(r.get("inputs", {})) + [r.get("output")]:
            if name not in c.items:
                problems.append(f"recipe {rid}: item {name!r} not in items.json")
    for mid, m in c.mobs.items():
        for key in m.get("recipe_trainer", []):
            if key not in c.recipes or "trainer_cost" not in c.recipes[key]:
                problems.append(f"mob {mid}: recipe_trainer {key} is not a recipe with a trainer_cost")
    for mid, dl in c.dialogs.items():
        if mid not in c.mobs:
            problems.append(f"dialog {mid}: unknown mob")
        if dl.get("start") not in dl.get("nodes", {}):
            problems.append(f"dialog {mid}: start node {dl.get('start')} missing")
        for nid, node in dl.get("nodes", {}).items():
            if len(node.get("responses", [])) > 5:
                problems.append(f"dialog {mid} node {nid}: more than 5 responses")
            for r in node.get("responses", []):
                if "goto" in r and r["goto"] not in dl["nodes"]:
                    problems.append(f"dialog {mid} node {nid}: goto {r['goto']} missing")
                act = r.get("action", "")
                if act.startswith("quest:") and act[6:] not in c.quests:
                    problems.append(f"dialog {mid} node {nid}: unknown quest {act[6:]}")
    for wid, w in c.workorders.items():
        if w.get("recipe") not in c.recipes:
            problems.append(f"work order {wid}: unknown recipe {w.get('recipe')}")
        if w.get("task_master") not in c.mobs:
            problems.append(f"work order {wid}: unknown task master {w.get('task_master')}")
        for name in list(w.get("supplies", {})) + list(w.get("deliver", {})):
            if name not in c.items:
                problems.append(f"work order {wid}: item {name!r} not in items.json")
    spawn_dir = os.path.join(directory, "spawns")
    for name in sorted(os.listdir(spawn_dir)):
        for s in _load(os.path.join(spawn_dir, name)).get("spawns", []):
            if any(len(p) < 2 for p in s.get("path", [])):
                problems.append(f"{name}: {s['mob']} path points need [x, y]")
    for name in sorted(os.listdir(spawn_dir)):
        data = _load(os.path.join(spawn_dir, name))
        for n, s in enumerate(data.get("spawns", [])):
            if s.get("mob") not in c.mobs:
                problems.append(f"{name} spawn {n}: unknown mob {s.get('mob')}")
            for key in ("x", "y"):
                if not isinstance(s.get(key), (int, float)):
                    problems.append(f"{name} spawn {n}: missing {key}")
    return problems


if __name__ == "__main__":
    issues = validate()
    print("\n".join(issues) if issues else "content OK")
