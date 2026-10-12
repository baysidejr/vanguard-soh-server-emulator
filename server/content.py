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
        if not q.get("kill"):
            problems.append(f"quest {qid}: needs a kill objective (the only kind supported)")
        for mob in q.get("kill", {}):
            if mob not in c.mobs:
                problems.append(f"quest {qid}: unknown kill target {mob}")
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
