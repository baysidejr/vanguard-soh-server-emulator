"""Place a zone's NPCs from the crowdsourced archive at their recorded positions.

The archive's NPC locations ("-9686, -35413, 1540") are the zone chunk's own coordinates (x, y, z),
the same frame as the server's spawn files: checked 2026-10-15 by placing Khal's NPCs, and Afshin
Budjiri stood on the floor of a trainer's hall. The client's bin/Resources/Texts/ChunkNames.txt
gives each zone's chunk.

    python tools/import_zone.py "Khal"              # report; drafts in crowdsourced/drafts/<zone>/
    python tools/import_zone.py "Khal" --apply      # add to server/content (never overwrites)

Each NPC becomes a mobs.json template "arch_<name>" (name, level, its services as the title, a
placeholder race from its continent and placeholder health) with "_source" (the archive page),
and a spawn at its position in content/spawns/<chunk>.json. Existing templates and spawns of the
same key are left alone, so it can be run again as the archive grows. What the archive doesn't
have (appearance, gear, services' wares, dialogue) is left for the content editor.
Uses only the Python standard library.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "server", "content")
RAW = os.path.join(ROOT, "crowdsourced", "raw")
DRAFTS = os.path.join(ROOT, "crowdsourced", "drafts")
CHUNK_NAMES = os.path.join(ROOT, "bin", "Resources", "Texts", "ChunkNames.txt")
CONTINENT_RACE = {"Thestra": 14, "Qalia": 13, "Kojan": 12}     # placeholder look per continent
DEFAULT_RACE = 14


def read_text(path):
    data = open(path, "rb").read()
    return data.decode("utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else data.decode("latin-1")


def zone_chunks(path=CHUNK_NAMES):
    """display name -> (chunk x, chunk y) for the overland chunks (instances use 1000+ ids)."""
    out = {}
    for m in re.finditer(r'DISPLAYNAME="([^"]*)" X=(-?\d+) Y=(-?\d+)', read_text(path)):
        name, x, y = m.group(1), int(m.group(2)), int(m.group(3))
        if name and abs(x) < 1000 and abs(y) < 1000:
            out.setdefault(name, (x, y))
    return out


def level_name(x, y):
    return f"chunk_{'n' if x < 0 else ''}{abs(x)}_{'n' if y < 0 else ''}{abs(y)}"


EXTRA_RAW = []     # more raw folders (--raw), e.g. the collection branch's, read after RAW


def archive_npcs(raw=None, kind="npc"):
    """name -> newest record of that kind (each folder's batches are read in name order, later
    ones win; folders in order: raw, or RAW then EXTRA_RAW)."""
    recs = {}
    roots = [raw] if isinstance(raw, str) else (raw or [RAW] + EXTRA_RAW)
    files = [fn for root in roots for fn in sorted(glob.glob(os.path.join(root, "*", f"{kind}.jsonl")))]
    for fn in files:
        with open(fn, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("name"):
                    recs[r["name"]] = r
    return recs


def position(rec):
    loc = rec.get("location") or {}
    raw = loc.get("raw") if isinstance(loc, dict) else loc if isinstance(loc, str) else None
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", raw or "")]
    return tuple(nums[:3]) if len(nums) >= 3 else None


PARLEY_WORDS = {"gossip": "gossip", "incite": "incite", "entertain": "entertain", "convince": "convince",
                "convice": "convince", "interview": "interview"}    # "Convice" is the archive's spelling


def parley_types(rec):
    """The parley types an NPC offers, from the archive's "parley types" field
    ("[[[ Gossip ]]], , , [[[ Convice ]]], [[[ Interview ]]]"), in order, without repeats."""
    out = []
    for v in (rec.get("archive_fields") or {}).get("parley types") or []:
        for word in re.findall(r"[A-Za-z]+", v):
            t = PARLEY_WORDS.get(word.lower())
            if t and t not in out:
                out.append(t)
    return out


def parley_key(ptype, presence):
    return f"archive_{ptype}_{presence}"


def parley_setup(ptype, presence):
    """A generic diplomacy.json parley of that type (placeholder cards, lines and reward; the
    archive records only the type and the presence it asks for)."""
    return {"offer": f"I'd like to {ptype} with you." if ptype != "interview" else "May I ask you a few questions?",
            "presence": presence, "type": ptype, "npc_cards": [40100, 40101, 40102], "npc_pools": {"reason": 1},
            "lines": ["Go on.", "I'm not convinced.", "That's a fair point.", "Hmm, interesting."],
            "win_at": 17, "lose_at": 5, "reward": {"xp": 100}, "_archive_placeholder": True}


def is_object(rec):
    """Quest objects (archive type "Object": a censer, a crate) are not people; not imported."""
    return "Object" in ((rec.get("archive_fields") or {}).get("type") or [])


def key_for(name):
    return "arch_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def template(rec):
    level = int(rec.get("level") or 20)
    t = {"name": rec["name"], "pawn_class": "SGONPCPawn",
         "race": CONTINENT_RACE.get(rec.get("continent"), DEFAULT_RACE),
         "level": level, "health": 100 + 40 * level}
    if t["race"] in (12, 13, 14):         # the human races have model variants 0-3: vary the look by name
        t["model"] = zlib.crc32(rec["name"].encode("utf-8")) % 4
    services = [s for s in (rec.get("services") or []) if s and s != "quest giver"]
    if services:
        t["title"] = ", ".join(s.title() for s in services)[:40]
    role = next((r for r in (rec.get("archive_fields") or {}).get("role") or []
                 if r and r != "General NPC" and not r.startswith("Class Trainer")), None)
    if role:
        t["title"] = role[:40]            # "Light Armor Vendor" says more than "Merchant"
    # Services the server can run from what the archive says. Merchants get the shared placeholder
    # stock "general_goods" (the archive has no wares); task masters keep only the title.
    if "merchant" in services:
        t["merchant"] = "general_goods"
    if "banker" in services:
        t["banker"] = True
    if "repair" in services:
        t["repair"] = True
    if "broker" in services:
        t["broker"] = f"{rec.get('zone') or 'Local'} Market"
    types = parley_types(rec)
    if types:
        presence = next((int(p) for p in (rec.get("archive_fields") or {}).get("presence") or [] if str(p).isdigit()), 0)
        t["parley"] = [parley_key(pt, presence) for pt in types]
    if "trainer" in services and rec.get("training_classes_recorded"):
        t["trainer"] = True
        t["trainer_classes"] = sorted(set(rec["training_classes_recorded"]))
        if len(t["trainer_classes"]) == 1:          # "Warrior Trainer" rather than "Trainer"
            t["title"] = t["title"].replace("Trainer", f"{t['trainer_classes'][0]} Trainer", 1)[:40]
    src = (rec.get("sources") or [{}])[0].get("url")
    if src:
        t["_source"] = src
    return t


QUEST_LOC = re.compile(r"(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)(?:.*\((-?\d+),\s*(-?\d+)\))?")


def quest_giver_spots(zone, quests, chunk):
    """giver name -> ((x, y, z), quest record) from the zone's quest records: a quest's archive
    "location" is where it starts, i.e. where its giver stands ("33289, -95029, 2936 in Khal
    (-13, -9)"). Only spots in the zone's own chunk; the first quest of each giver wins."""
    out = {}
    for q in sorted(quests.values(), key=lambda r: r["name"]):
        if q.get("zone") != zone or not q.get("giver") or "," in q["giver"]:
            continue                      # "Kurake , Kurake Wamani": several names, which one is unclear
        for loc in (q.get("archive_fields") or {}).get("location") or []:
            m = QUEST_LOC.search(str(loc))
            if not m:
                continue
            if m.group(4) is not None and (int(m.group(4)), int(m.group(5))) != chunk:
                continue
            out.setdefault(q["giver"], (tuple(float(m.group(i)) for i in (1, 2, 3)), q))
            break
    return out


_RACES = []


def creature_race(rec, continent):
    """A client race for a creature from its archive type ("Farie", "Blob") via the converter's
    race table; else the continent's placeholder."""
    if not _RACES:
        sys.path.insert(0, os.path.join(ROOT, "crowdsourced"))
        import convert
        _RACES.append((convert, convert.creature_races()))
    convert, races = _RACES[0]
    for kind in [rec.get("creature_kind")] + list((rec.get("archive_fields") or {}).get("type") or []):
        if kind:
            race = convert.find_race(races, kind)
            if race is not None:
                return race
    return CONTINENT_RACE.get(continent, DEFAULT_RACE)


def creature_template(rec, continent):
    """A hostile mob from an archive creature record: level, aggression and difficulty from the
    archive; health and damage are placeholders scaled by level and the difficulty dots."""
    af = rec.get("archive_fields") or {}
    level = int(rec.get("level") or 10)
    dots = next((int(d[0]) for d in af.get("difficulty") or [] if d[:1].isdigit()), 2)
    t = {"name": rec["name"], "pawn_class": "SGONPCPawn", "race": creature_race(rec, continent), "level": level,
         "health": (100 + 40 * level) * dots // 2, "damage": [max(1, level), max(2, 3 * level * dots // 3)]}
    if "Aggressive" in (af.get("behaviour") or []):
        t["aggro_radius"] = 600
    src = (rec.get("sources") or [{}])[0].get("url")
    if src:
        t["_source"] = src
    return t


def creature_spot(rec, chunk):
    """(x, y, z) of a creature's archive "location" in that chunk, or None."""
    af = rec.get("archive_fields") or {}
    for loc in af.get("location") or []:
        m = QUEST_LOC.search(str(loc))
        if m and (m.group(4) is None or (int(m.group(4)), int(m.group(5))) == chunk):
            return tuple(float(m.group(i)) for i in (1, 2, 3))
    return None


def respawn_seconds(rec):
    """The archive's respawn in minutes ("20") as seconds, or None."""
    for v in (rec.get("archive_fields") or {}).get("respawn") or []:
        if str(v).strip().isdigit():
            return int(v) * 60
    return None


def plan(zone, recs, chunks, quests=None, continent=None, creatures=None):
    """(level, {key: template}, [spawn]) for a zone's NPCs that have a position, then the quest
    givers the NPC records don't place, at their quests' start locations."""
    if zone not in chunks:
        raise SystemExit(f"{zone!r} is not in ChunkNames.txt")
    level = level_name(*chunks[zone])
    mobs, spawns = {}, []
    for rec in sorted(recs.values(), key=lambda r: r["name"]):
        pos = position(rec)
        if rec.get("zone") != zone or pos is None or is_object(rec):
            continue
        key = key_for(rec["name"])
        mobs[key] = template(rec)
        spawns.append({"mob": key, "x": round(pos[0]), "y": round(pos[1]), "z": round(pos[2]), "yaw": 0})
    for giver, (pos, q) in quest_giver_spots(zone, quests or {}, chunks[zone]).items():
        key = key_for(giver)
        if key in mobs:
            continue
        rec = dict(recs.get(giver) or {"name": giver, "level": q.get("level")})
        rec.setdefault("sources", q.get("sources"))
        rec.setdefault("continent", continent)          # the zone's, for the placeholder race
        mobs[key] = template(rec)
        spawns.append({"mob": key, "x": round(pos[0]), "y": round(pos[1]), "z": round(pos[2]), "yaw": 0})
    for rec in sorted((creatures or {}).values(), key=lambda r: r["name"]):
        if rec.get("zone") != zone or is_object(rec):
            continue
        pos = creature_spot(rec, chunks[zone])
        key = key_for(rec["name"])
        if pos is None or key in mobs:
            continue
        mobs[key] = creature_template(rec, continent)
        sp = {"mob": key, "x": round(pos[0]), "y": round(pos[1]), "z": round(pos[2]), "yaw": 0}
        if respawn_seconds(rec):
            sp["respawn"] = respawn_seconds(rec)
        spawns.append(sp)
    return level, mobs, spawns


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")


def apply(level, mobs, spawns, content=CONTENT):
    """Add the templates and spawns that are not there yet; a template that is already there only
    gains the fields it lacks (a builder's edits are never changed). Returns (templates added,
    spawns added)."""
    mobs_path = os.path.join(content, "mobs.json")
    existing = load(mobs_path, {})
    new_mobs = {k: v for k, v in mobs.items() if k not in existing}
    grew = False
    for k, v in mobs.items():
        if k in existing and isinstance(existing[k], dict):
            for field, value in v.items():
                if field not in existing[k]:
                    existing[k][field] = value
                    grew = True
    spawn_path = os.path.join(content, "spawns", level + ".json")
    doc = load(spawn_path, {"spawns": []})
    have = {s.get("mob") for s in doc.get("spawns", [])}
    new_spawns = [s for s in spawns if s["mob"] not in have]
    if new_mobs or grew:
        existing.update(new_mobs)
        write(mobs_path, existing)
    # The generic parleys the templates refer to (diplomacy.json), created once.
    wanted = {k for m in existing.values() if isinstance(m, dict) and isinstance(m.get("parley"), list)
              for k in m["parley"] if k.startswith("archive_")}
    dip_path = os.path.join(content, "diplomacy.json")
    if wanted and os.path.exists(dip_path):
        dip = load(dip_path, {})
        parleys = dip.setdefault("parleys", {})
        missing = [k for k in sorted(wanted) if k not in parleys]
        for k in missing:
            _, ptype, presence = k.split("_")
            parleys[k] = parley_setup(ptype, int(presence))
        if missing:
            write(dip_path, dip)
    if new_spawns:
        doc.setdefault("spawns", []).extend(new_spawns)
        write(spawn_path, doc)
    return len(new_mobs), len(new_spawns)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("zone", help='the zone name as in ChunkNames.txt, e.g. "Khal"')
    ap.add_argument("--apply", action="store_true", help="add to server/content instead of writing drafts")
    ap.add_argument("--raw", action="append", default=[],
                    help="another folder of raw batches to read as well (e.g. one taken from the collection branch)")
    a = ap.parse_args(argv)
    EXTRA_RAW.extend(a.raw)
    zone_rec = archive_npcs(kind="zone").get(a.zone) or {}
    level, mobs, spawns = plan(a.zone, archive_npcs(), zone_chunks(), archive_npcs(kind="quest"),
                               zone_rec.get("continent"), archive_npcs(kind="creature"))
    print(f"{a.zone}: {level}, {len(spawns)} NPCs with a position in the archive (NPC records and quest start locations)")
    if not a.apply:
        out = os.path.join(DRAFTS, re.sub(r"[^A-Za-z0-9]+", "_", a.zone))
        write(os.path.join(out, "mobs.json"), mobs)
        write(os.path.join(out, "spawns", level + ".json"), {"spawns": spawns})
        print(f"drafts written to {os.path.relpath(out, ROOT)} (run again with --apply to add them)")
        return 0
    added_mobs, added_spawns = apply(level, mobs, spawns)
    print(f"added {added_mobs} templates to mobs.json and {added_spawns} spawns to spawns/{level}.json")
    if added_mobs or added_spawns:
        log = os.path.join(ROOT, "crowdsourced", "imported.md")
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"| {datetime.date.today()} | all raw batches, npc.jsonl ({a.zone}) | {added_spawns} NPCs at their "
                    f"recorded positions (placeholder race and health) | server/content/mobs.json, "
                    f"spawns/{level}.json via tools/import_zone.py |\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
