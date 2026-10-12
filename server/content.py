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
        """[(name, icon, quantity)] dropped from a loot table."""
        drops = []
        for entry in self.loot.get(table_id, []):
            if rng.random() <= entry.get("chance", 1.0):
                lo, hi = entry.get("quantity", [1, 1])
                drops.append((entry["name"], entry.get("icon", 443), rng.randint(lo, hi)))
        return drops


def validate(directory=CONTENT_DIR):
    """Problems found in the content files (empty list = all good)."""
    problems = []
    c = Content(directory)
    for mid, m in c.mobs.items():
        for key in ("name", "pawn_class", "race", "health"):
            if key not in m:
                problems.append(f"mob {mid}: missing {key}")
        if m.get("merchant") and m["merchant"] not in c.merchants:
            problems.append(f"mob {mid}: unknown merchant list {m['merchant']}")
        if m.get("loot") and m["loot"] not in c.loot:
            problems.append(f"mob {mid}: unknown loot table {m['loot']}")
        for g in m.get("gear", []):
            if len(g) != 3:
                problems.append(f"mob {mid}: gear entry {g} needs [type, mesh, slot]")
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
    for mid, m in c.mobs.items():
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
    spawn_dir = os.path.join(directory, "spawns")
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
