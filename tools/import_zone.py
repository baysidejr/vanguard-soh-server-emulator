"""Place a zone's NPCs from the crowdsourced archive at their recorded positions.

The archive's NPC locations ("-9686, -35413, 1540") are the zone chunk's own coordinates (x, y, z),
the same frame as the server's spawn files: checked 2026-10-15 by placing Khal's NPCs, and Afshin
Budjiri stood on the floor of a trainer's hall. The client's bin/Resources/Texts/ChunkNames.txt
gives each zone's chunk.

    python tools/import_zone.py "Khal"              # report; drafts in crowdsourced/drafts/<zone>/
    python tools/import_zone.py "Khal" --apply      # add to server/content (never overwrites)
    python tools/import_zone.py --all --branch --apply --skip "Sundering Wastelands" --skip "Wildgrowth Forest"
                                                    # every zone, with the collection branch's newest pages

Each NPC becomes a mobs.json template "arch_<name>" (name, level, its services as the title, a
race (the archive's when it records one, else a placeholder from its continent) and placeholder health) with "_source" (the archive page),
and a spawn at its position in content/spawns/<chunk>.json. Existing templates and spawns of the
same key are left alone, so it can be run again as the archive grows. What the archive doesn't
have (appearance, gear, services' wares, dialogue) is left for the content editor.
Uses only the Python standard library.
"""
import argparse
import collections
import datetime
import glob
import json
import math
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
SOURCES = []       # how the extra folders are named in crowdsourced/imported.md


# Zone names the archive spells differently from ChunkNames.txt (checked by hand).
ZONE_ALIASES = {"Vursog Moor": "Vsurog Moor", "Infineum Plateau": "The Infineum Plateaus",
                "Skrillien Point": "Skrilien Point"}


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
    # The archive capitalises some zone names differently ("Wardship Of The Sleeping Moon"):
    # use ChunkNames.txt's spelling so they match the zone's chunk.
    try:
        canon_chunks = zone_chunks()
    except OSError:
        canon_chunks = {}
    canon = {k.lower(): k for k in canon_chunks}
    by_chunk = {v: k for k, v in canon_chunks.items()} if canon else {}
    squash = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    if kind != "zone" and canon:
        # Sub-area zone pages name their parent in "chunk" (Graystone: "Beranid Hills",
        # Oathbreaker Caves: "Bordinars Cleft", without the apostrophe).
        by_squash = {squash(k): v for k, v in canon.items()}
        for zname, zr in archive_npcs(raw, kind="zone").items():
            parent = next(iter((zr.get("archive_fields") or {}).get("chunk") or []), "")
            if parent and squash(parent) in by_squash:
                canon.setdefault(zname.lower(), by_squash[squash(parent)])
    for name, ch in ZONE_ALIASES.items():                # the archive's spelling -> the client's
        if ch.lower() in canon:
            canon.setdefault(name.lower(), canon[ch.lower()])
    if by_chunk:                                         # a map label in a zone ("Tursh", "Karibasa")
        for ch, labels in poi_labels().items():
            for label in labels:
                if ch in by_chunk:
                    canon.setdefault(label, by_chunk[ch])
                    canon.setdefault(label + " village", by_chunk[ch])
    for r in recs.values():
        zn = r.get("zone")
        if isinstance(zn, str) and zn.lower() in canon:
            r["zone"] = canon[zn.lower()]
        elif by_chunk:
            # A zone field naming a sub-area or a person ("Nerail Tharazen"), but a location
            # that says which chunk ("-80422, 84409, 17146 in Lomshir (-15, -9)"): use that.
            for loc in (r.get("archive_fields") or {}).get("location") or []:
                m = QUEST_LOC.search(str(loc))
                if m and m.group(4) is not None and (int(m.group(4)), int(m.group(5))) in by_chunk:
                    r["zone"] = by_chunk[(int(m.group(4)), int(m.group(5)))]
                    break
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
    """Quest objects (archive type "Object": a censer, a crate) are not people; not imported.
    Records typed "Object" that have services or a role (merchants such as Almari Jal in Khal)
    are mislabelled people and count as NPCs."""
    af = rec.get("archive_fields") or {}
    if rec.get("services") or af.get("role"):
        return False
    return "Object" in (af.get("type") or [])


def key_for(name):
    return "arch_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


ZONE_RACE = {}                   # zone -> the race most of its race-recorded NPCs have (zone_race)


def zone_race(zone, recs, least=3, share=0.8):
    """The race of a zone's people when at least `least` of its NPC pages record a race and
    `share` of those agree (Mekalia: Gnome, Hathor Zhi: Dark Elf), else None: the default for
    the zone's NPCs whose own page records none."""
    import collections
    races = collections.Counter()
    for r in recs.values():
        if r.get("zone") == zone and (r.get("archive_fields") or {}).get("race"):
            race = npc_race({"archive_fields": r["archive_fields"], "continent": None, "zone": None})
            if race != DEFAULT_RACE or "thestran" in str(r["archive_fields"]["race"]).lower():
                races[race] += 1
    total = sum(races.values())
    if total >= least:
        race, n = races.most_common(1)[0]
        if n >= share * total:
            return race
    return None


def npc_race(rec):
    """The client race for an NPC: the archive's recorded race ("Dwarf", "Kojani Human",
    "Half-Elf"; about 2% of NPC pages have one) through the converter's race table, else the
    continent's human race (also for a bare "Human")."""
    fallback = ZONE_RACE.get(rec.get("zone")) or CONTINENT_RACE.get(rec.get("continent"), DEFAULT_RACE)
    name = next(iter((rec.get("archive_fields") or {}).get("race") or []), "")
    name = re.sub(r"\s*\*$|\s+Human$", "", name.strip()).replace("Half-Elf", "Half Elf")
    if not name or name == "Human":
        return fallback
    if not _RACES:
        creature_race({}, None)                     # loads the converter's race table
    convert, races = _RACES[0]
    race = convert.find_race(races, name)
    return fallback if race is None else race


STATIONS = ("domestic", "soldier", "crafter", "clergy", "merchant", "noble", "academic", "outsider")


FEMALE = re.compile(r"(?<![a-z])(priestess|lady|madam|madame|sister|mother|matron|queen|duchess|baroness|countess|"
                    r"huntress|seamstress|mistress|empress|princess|grandmother|aunt|widow|wife|daughter|maiden|"
                    r"sorceress|enchantress|abbess|dame|woman|matriarch)(?![a-z])", re.I)


def clean_role(role):
    """An archive role as a title: without a location note ("Light Armor Vendor (east city walls
    outside Tavern)" -> "Light Armor Vendor"), and None when still longer than a title fits (40)
    or empty ("Up on the wall - to the north from stairs" is a direction, not a role)."""
    if not role:
        return None
    if not role.startswith("("):              # "(Peacebearer of Gloriann)" is the whole title
        role = re.sub(r"\s*\(.*$", "", role).strip()
    return role if role and len(role) <= 40 else None


def template(rec):
    level = int(rec.get("level") or 20)
    t = {"name": rec["name"], "pawn_class": "SGONPCPawn", "race": npc_race(rec),
         "level": level, "health": 100 + 40 * level}
    dots = next((int(d[0]) for d in (rec.get("archive_fields") or {}).get("difficulty") or [] if d[:1].isdigit()), None)
    if dots:
        t["difficulty"] = max(0, min(5, dots - 1))
    if FEMALE.search(rec["name"]) or FEMALE.search(" ".join((rec.get("archive_fields") or {}).get("role") or [])):
        t["gender"] = 1                   # "Priestess Aludan", "Duchess ...": the archive records no gender
    if t["race"] in (12, 13, 14):         # the human races have model variants 0-3: vary the look by name
        t["model"] = zlib.crc32(rec["name"].encode("utf-8")) % 4
    services = [s for s in (rec.get("services") or []) if s and s != "quest giver"]
    if services:
        t["title"] = ", ".join(s.title() for s in services)[:40]
    role = next((r for r in (rec.get("archive_fields") or {}).get("role") or []
                 if r and r != "General NPC" and not r.startswith("Class Trainer")), None)
    role = clean_role(role)
    if role:
        t["title"] = role                 # "Light Armor Vendor" says more than "Merchant"
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
        plevel = next((int(v) for v in (rec.get("archive_fields") or {}).get("parley level") or [] if str(v).isdigit()), None)
        if plevel:
            t["parley_level"] = plevel        # scales the generic parley's XP (login_stub.finish_parley)
    station = next(iter((rec.get("archive_fields") or {}).get("station") or []), "").strip().lower()
    if station in STATIONS:
        t["presence_station"] = station       # a won parley raises presence with it (finish_parley); not "station", the crafting-station flag
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


def has_npc_page(q):
    """Whether the quest record links its giver to an archive NPC page (/mobs/...)."""
    g = (q.get("giver") or "").strip().lower()
    return any((e.get("name") or "").strip().lower() == g and "/mobs/" in (e.get("url") or "")
               for e in q.get("referenced_entities") or [])


def quest_giver_spots(zone, quests, chunk):
    """giver name -> ((x, y, z), quest record) from the zone's quest records: a quest's archive
    "location" is where it starts, i.e. where its giver stands ("33289, -95029, 2936 in Khal
    (-13, -9)"). Only spots in the zone's own chunk; the first quest of each giver wins."""
    out = {}
    for q in sorted(quests.values(), key=lambda r: r["name"]):
        if q.get("zone") != zone or not q.get("giver") or "," in q["giver"]:
            continue                      # "Kurake , Kurake Wamani": several names, which one is unclear
        if q["giver"].strip().lower() in ("unknown", "?", "n/a", "varies", "various", "multiple", "none"):
            continue                      # the archive didn't know (or name) who gives it: "Varies"
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
    if any(d[:1].isdigit() for d in af.get("difficulty") or []):
        t["difficulty"] = max(0, min(5, dots - 1))      # /con wording: 1 dot slightly easier ... 6 extremely
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


def face(spawns, near=800.0):
    """Headings for spawns placed at yaw 0 (the archive has none): each faces its nearest
    neighbour within `near` units, as people in a town do, else a direction fixed by its key."""
    for s in spawns:
        if s.get("yaw"):
            continue
        best = None
        for o in spawns:
            if o is s:
                continue
            d = math.hypot(o["x"] - s["x"], o["y"] - s["y"])
            if 1.0 < d <= near and (best is None or d < best[0]):
                best = (d, o)
        if best:
            ang = math.atan2(best[1]["y"] - s["y"], best[1]["x"] - s["x"])
            s["yaw"] = int(math.degrees(ang) * 65536 / 360) & 0xFFFF
        else:
            s["yaw"] = zlib.crc32(s["mob"].encode("utf-8")) & 0xFFFF
    return spawns


def plan(zone, recs, chunks, quests=None, continent=None, creatures=None, zone_rec=None):
    """(level, {key: template}, [spawn]) for a zone's NPCs that have a position, then the quest
    givers the NPC records don't place, at their quests' start locations, the creatures with a
    location, and creature camps from the zone page's map (camps())."""
    if zone not in chunks:
        raise SystemExit(f"{zone!r} is not in ChunkNames.txt")
    level = level_name(*chunks[zone])
    ZONE_RACE[zone] = zone_race(zone, recs)
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
        if giver not in recs and not has_npc_page(q):
            continue          # no NPC record and no NPC page: a parsing leftover such as "Then", not a person
        if any(abs(s["x"] - pos[0]) < 50 and abs(s["y"] - pos[1]) < 50 and abs(s["z"] - pos[2]) < 100 for s in spawns):
            continue          # someone already stands there: the same person under another spelling
        rec = dict(recs.get(giver) or {"name": giver, "level": q.get("level"), "zone": zone})
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
        if "random" in ((rec.get("archive_fields") or {}).get("spawn") or []):
            sp["wander"] = 400            # the archive's "random" spawn: it roams rather than stands
        if respawn_seconds(rec):
            sp["respawn"] = respawn_seconds(rec)
        spawns.append(sp)
    for key, t, camp in camps(zone, zone_rec, creatures or {}, continent):
        if key in mobs:
            continue
        mobs[key] = t
        spawns.extend(camp)
    people = []
    for key, t, sp in map_people(zone, zone_rec, recs, continent, spawns, creatures):
        if key in mobs:
            continue
        mobs[key] = t
        people.append(sp)
    off_terrain_heights(level, spawns, people)
    spawns.extend(people)
    for key, t, sp in poi_people(zone, chunks[zone], recs, continent, spawns):
        if key in mobs:
            continue
        mobs[key] = t
        spawns.append(sp)
    spawns.extend(service_props(zone_rec, spawns, existing_spawns(level)))
    for sp in spawns:
        if sp.get("z") is not None and abs(sp["z"]) > MAX_Z:
            del sp["z"]                   # "223739": a typo on the archive; the server finds the ground
    return level, mobs, face(spawns)


MAX_Z = 150000                   # no map goes this high or low (the tree cities stand near 64000)


# Map places that are a service object: the camp's templates (Altar of Binding, Mailbox) stand there.
SERVICE_PLACES = ((re.compile(r"bind|altar|alter\b|resur+ection", re.I), "camp_altar", 3000),
                  (re.compile(r"^mailbox$", re.I), "camp_mailbox", 1000))


SHARED_PROPS = {mob for _, mob, _ in SERVICE_PLACES}


OFF_TERRAIN = 400                # a city whose NPCs stand this far from the terrain (median)
OFF_TERRAIN_REACH = 6000         # and only near the city: farther out the terrain is the better guess


def off_terrain_heights(level, placed, people, ground=None):
    """In a chunk whose positioned NPCs mostly stand well above or below the terrain (a city carved
    into a mountain like Bordinar's Cleft, or built in the trees like Tawar Galan), people with no
    height take the nearest positioned NPC's within OFF_TERRAIN_REACH: the terrain would put them on
    the surface. ground(x, y) is the terrain height (default: the server's, from the client's map)."""
    known = [s for s in placed if s.get("z") is not None and s["mob"].startswith("arch_")]
    todo = [s for s in people if s.get("z") is None]
    if len(known) < 5 or not todo:
        return
    if ground is None:
        sys.path.insert(0, os.path.join(ROOT, "server"))
        import content as server_content
        c = server_content.Content(CONTENT)
        ground = lambda x, y: c.ground_z(level, x, y, ROOT)
    diffs = sorted(s["z"] - ground(s["x"], s["y"]) for s in known)
    if abs(diffs[len(diffs) // 2]) < OFF_TERRAIN:
        return
    for s in todo:
        k = min(known, key=lambda k: math.hypot(k["x"] - s["x"], k["y"] - s["y"]))
        if math.hypot(k["x"] - s["x"], k["y"] - s["y"]) < OFF_TERRAIN_REACH:
            s["z"] = k["z"]


POI_NAMES = os.path.join(ROOT, "bin", "Resources", "Texts", "PoINames.txt")
_POIS = {}


def poi_labels(path=POI_NAMES):
    """{(chunk x, chunk y): {label lower case, without "[45-50]": (x, y, z)}} from the client's
    map labels (PoINames.txt)."""
    if path not in _POIS:
        out = {}
        try:
            text = read_text(path)
        except OSError:
            text = ""
        for m in re.finditer(r'PoIName="([^"]*)" ChunkX=(-?\d+) ChunkY=(-?\d+) X=(-?\d+) Y=(-?\d+) Z=(-?\d+)', text):
            name = re.sub(r"\s*\[[^]]*\]", "", m.group(1)).strip().lower()
            out.setdefault((int(m.group(2)), int(m.group(3))), {}).setdefault(
                name, tuple(float(m.group(i)) for i in (4, 5, 6)))
        _POIS[path] = out
    return _POIS[path]


def poi_people(zone, chunk, npcs, continent, placed, labels=None):
    """[(key, template, spawn)]: NPCs of the zone with no position whose archive "locations seen"
    names one of the chunk's map labels ("Zaraj Arena") stand at that label, spread around it."""
    labels = (labels if labels is not None else poi_labels()).get(tuple(chunk), {})
    seen = {s["mob"] for s in placed}
    groups = {}
    for rec in sorted(npcs.values(), key=lambda r: r["name"]):
        if rec.get("zone") != zone or position(rec) is not None or is_object(rec) or key_for(rec["name"]) in seen:
            continue
        spot = next((labels[p.strip().lower()] for p in (rec.get("archive_fields") or {}).get("locations seen") or []
                     if p.strip().lower() in labels and p.strip().lower() != zone.lower()), None)   # the zone name
        # labels its hub: too vague to stand someone at
        if spot is not None:
            groups.setdefault(spot, []).append(rec)
    out = []
    for (x, y, z), recs in groups.items():
        for i, rec in enumerate(recs):
            a = 2 * math.pi * i / len(recs)
            r = CROWD_RADIUS if len(recs) > 1 else 0
            rec = dict(rec)
            rec.setdefault("continent", continent)
            out.append((key_for(rec["name"]), template(rec),
                        {"mob": key_for(rec["name"]), "x": round(x + r * math.cos(a)), "y": round(y + r * math.sin(a)),
                         "z": round(z), "yaw": 0}))
    return out


def existing_spawns(level, content=CONTENT):
    return load(os.path.join(content, "spawns", level + ".json"), {}).get("spawns", [])


def service_props(zone_rec, placed, existing=()):
    """[spawn]: Altars of Binding at the zone map's "Bindstone" / "Altar" / "Resurection Altar"
    places and mailboxes at its "Mailbox" places, unless one already stands within its spacing
    (3000 units for altars, 1000 for mailboxes). Height as for map_people."""
    out = []
    for mp in (zone_rec or {}).get("map_places") or []:
        m = re.match(r"\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", str((mp.get("location") or {}).get("raw") or ""))
        if not m:
            continue
        x, y = float(m.group(1)), float(m.group(2))
        for pattern, mob, spacing in SERVICE_PLACES:
            if not pattern.search(mp.get("name") or ""):
                continue
            others = [s for s in list(existing) + out if s.get("mob") == mob]
            if any(math.hypot(s["x"] - x, s["y"] - y) < spacing for s in others):
                break
            near = [s for s in placed if s.get("z") is not None and math.hypot(s["x"] - x, s["y"] - y) < NEIGHBOUR_Z]
            sp = {"mob": mob, "x": round(x), "y": round(y), "yaw": 0}
            if near:
                sp["z"] = min(near, key=lambda s: math.hypot(s["x"] - x, s["y"] - y))["z"]
            out.append(sp)
            break
    return out


# Map place names that are a role ("Sorcerer Instructor", "Horseshoe Vendor", "Bankers"): the
# title of the people listed there, and the services the server can run.
ROLE_WORDS = re.compile(r"vendor|trader|merchant|outfitter|instructor|trainer|banker|bank|broker|registrar|"
                        r"alchemist|smith|tailor|crafter|keeper|guard|captain|priest", re.I)
# The starting areas' archetype instructors ("Heavyfighter Instructor") teach a group of classes.
ARCHETYPES = {"heavyfighter": ("Warrior", "Paladin", "Dread Knight"),
              "lightfighter": ("Rogue", "Monk", "Ranger", "Bard"),
              "spellcaster": ("Sorcerer", "Necromancer", "Psionicist", "Druid"),
              "healer": ("Cleric", "Shaman", "Blood Mage", "Disciple")}
OBJECT_WORDS = re.compile(r"cauldron|chest|crate|barrel|box|altar|stone|mailbox|pile|node|cart|banner|"
                          r"brazier|statue|totem|portal|lever|book|scroll|sign", re.I)
NEIGHBOUR_Z = 1500               # take the height of a positioned NPC this close (same floor of a city)
CROWD_RADIUS = 150               # several people at one map point stand around it


def place_services(t, place):
    """Services from a role place name, on a template that doesn't have them yet."""
    sys.path.insert(0, os.path.join(ROOT, "server"))
    import races_classes
    low = place.lower()
    if re.search(r"instructor|trainer", low):
        cls = [c for c in races_classes.ADVENTURING_CLASSES.values() if c.lower() in low]
        squashed = low.replace(" ", "")
        for word, classes in ARCHETYPES.items():
            if not cls and word in squashed:
                cls = list(classes)
        if cls:
            t.setdefault("trainer", True)
            t.setdefault("trainer_classes", cls)
    if re.search(r"\bbank", low):
        t.setdefault("banker", True)
    if "broker" in low:
        t.setdefault("broker", "Local Market")
    if re.search(r"vendor|trader|merchant|outfitter", low):
        t.setdefault("merchant", role_stock_key(place) or "general_goods")


def map_people(zone, zone_rec, npcs, continent, placed, creatures=None):
    """[(key, template, spawn)]: people a zone page's map lists at a place ("Sorcerer Instructor"
    at "-34897, -20831": Fila Azadi) who have no recorded position. They stand at the map point,
    spread around it when several share it; the height is a positioned NPC's within NEIGHBOUR_Z
    (cities have floors above and below the terrain), else left to the server (the terrain). A
    role place name becomes their title and services (place_services). Round points such as
    "-10000, -24000" are skipped as guesses."""
    out, seen = [], {s["mob"] for s in placed}
    for mp in (zone_rec or {}).get("map_places") or []:
        m = re.match(r"\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", str((mp.get("location") or {}).get("raw") or ""))
        people = [e for e in mp.get("entities") or [] if e and key_for(e) not in seen]
        if not m or not people:
            continue
        x, y = float(m.group(1)), float(m.group(2))
        if x % 1000 == 0 and y % 1000 == 0:
            continue
        near = [s for s in placed if s.get("z") is not None and math.hypot(s["x"] - x, s["y"] - y) < NEIGHBOUR_Z]
        z = min(near, key=lambda s: math.hypot(s["x"] - x, s["y"] - y))["z"] if near else None
        place = (mp.get("name") or "").strip()
        for i, name in enumerate(people):
            rec = npcs.get(name)
            if rec is not None and (is_object(rec) or rec.get("zone") not in (None, zone)):
                continue
            if rec is None and (OBJECT_WORDS.search(name) or name in (creatures or {})):
                continue          # "Boiling Cauldrons"; a creature page (named mobs are left out)
            rec = dict(rec or {"name": name})
            rec.setdefault("continent", continent)
            rec.setdefault("zone", zone)
            t = template(rec)
            if ROLE_WORDS.search(place) and place.lower() != name.lower() and "title" not in t:
                t["title"] = place[:40]
            if ROLE_WORDS.search(place):
                place_services(t, place)
            if "_source" not in t and zone_rec.get("sources"):
                t["_source"] = zone_rec["sources"][0].get("url")
            a = 2 * math.pi * i / len(people)
            r = CROWD_RADIUS if len(people) > 1 else 0
            sp = {"mob": key_for(name), "x": round(x + r * math.cos(a)), "y": round(y + r * math.sin(a)), "yaw": 0}
            if z is not None:
                sp["z"] = z
            seen.add(key_for(name))
            out.append((key_for(name), t, sp))
    return out


CAMP_RADIUS = 250
NOT_HOSTILE = re.compile(r"(injured|wounded|captive|lost|trapped|friendly) |defender|guard|sentr|soldier|citizen|villager", re.I)


def camps(zone, zone_rec, creatures, continent):
    """[(key, template, [spawn])]: the zone page's map places named after a creature of that zone
    ("Gwartak Grunts" at "-55454, 55971") become camps there. The map points are the chunk's own
    x, y (checked against NPCs the same places list: within about 100 units), with no height, so
    the spawns leave z out and the server puts them on the ground. A plural name is a camp of three
    around the point; a singular name is skipped (the archive files some people under creatures, and
    nothing in the records tells them apart). They wander a little."""
    by_name = {n.lower(): r for n, r in creatures.items()}
    out, seen = [], set()
    for mp in (zone_rec or {}).get("map_places") or []:
        m = re.match(r"\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", str((mp.get("location") or {}).get("raw") or ""))
        name = (mp.get("name") or "").strip().lower()
        if not m or not name:
            continue
        head, _, last = name.rpartition(" ")
        forms = [name] + [(head + " " if head else "") + last[: -len(p)] + s
                          for p, s in (("ies", "y"), ("ves", "f"), ("men", "man"), ("es", ""), ("s", "")) if last.endswith(p)]
        rec = next((by_name[f] for f in forms if f in by_name), None)
        if rec is None or rec.get("zone") != zone or is_object(rec) or not rec.get("level"):
            continue
        key = key_for(rec["name"])
        if key in seen:
            continue
        seen.add(key)
        x, y = float(m.group(1)), float(m.group(2))
        if forms[0] == rec["name"].lower() or NOT_HOSTILE.search(name):
            continue          # one name ("Chi Ake Threecranes") may be a person; "Injured ..." needs help
        n = 3
        camp = []
        for i in range(n):
            a = 2 * math.pi * i / n
            r = CAMP_RADIUS if n > 1 else 0
            sp = {"mob": key, "x": round(x + r * math.cos(a)), "y": round(y + r * math.sin(a)), "yaw": 0, "wander": 200}
            if respawn_seconds(rec):
                sp["respawn"] = respawn_seconds(rec)
            camp.append(sp)
        out.append((key, creature_template(rec, continent), camp))
    return out


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


def attach_loot(mobs, loot_recs, content=CONTENT):
    """Give imported creatures the archive's drops: a loot.json table per creature that has a loot
    record (editor.loot_draft: chance from the archive's percentage, icon from items.json),
    created once, and the template's "loot". Returns the number of tables added."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import editor
    path = os.path.join(content, "loot.json")
    loot = load(path, {})
    added = 0
    for key, t in mobs.items():
        rec = loot_recs.get(t.get("name"))
        if rec is None or not t.get("aggro_radius") and "damage" not in t:
            continue
        d = editor.loot_draft(rec, (rec.get("sources") or [{}])[0].get("url"), lambda n: key, content)
        if "error" in d:
            continue
        table = key + "_drops"
        if table not in loot:
            loot[table] = d["value"]
            added += 1
        t.setdefault("loot", table)
    if added:
        write(path, loot)
    return added


def moved_out_of(level, content=CONTENT):
    """Templates whose spawn tools/chunk_audit.py moved out of this chunk (its "_moved_from" names
    the chunk): they are placed, just elsewhere, so the import must not put them back."""
    out = set()
    for path in glob.glob(os.path.join(content, "spawns", "*.json")):
        for s in load(path, {"spawns": []}).get("spawns", []):
            if str(s.get("_moved_from", "")).startswith(level + ":"):
                out.add(s.get("mob"))
    return out


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
    have = {s.get("mob") for s in doc.get("spawns", [])} | moved_out_of(level, content)
    # Service props (altars, mailboxes) are shared templates: service_props already checked the
    # spacing against the file, so they're added even when the chunk has one of that kind.
    new_spawns = [s for s in spawns if s["mob"] not in have or (s["mob"] in SHARED_PROPS and not any(
        o.get("mob") == s["mob"] and o.get("x") == s["x"] and o.get("y") == s["y"] for o in doc.get("spawns", [])))]
    # Someone already stands on that exact spot under another name ("Naji" from a quest record,
    # "Naji Sevenblade" from her NPC page, same archive coordinates): the same person.
    new_spawns = [s for s in new_spawns if s["mob"] in SHARED_PROPS or not any(
        o.get("mob") != s["mob"] and abs(o.get("x", 1e9) - s["x"]) < 10 and abs(o.get("y", 1e9) - s["y"]) < 10
        for o in doc.get("spawns", []))]
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


# Merchant roles (the archive's title) -> what a role stock holds: a test on an archive item record.
# The archive records no vendor wares, so these stocks are placeholders built from archive items of
# the right kind (mundane or common, not player-crafted), spread over the levels.
def _atype(r):
    return " ".join((r.get("archive_fields") or {}).get("type") or [])


def _ranged(r):
    return "Ranged" in _atype(r) or "bow" in ((r.get("weapon_type_recorded") or "") + r["name"]).lower()


ROLE_STOCKS = {                  # first match wins: "Ranged Weapon Vendor" before "Weapon Vendor"
    "ranged": (("Ranged Weapon",), _ranged),
    "weapons": (("Weapons Vendor", "Weapon Vendor"),
                lambda r: r.get("item_type") == "weapon" and not _ranged(r)),
    "heavy_armor": (("Heavy Armor",), lambda r: _atype(r) == "Heavy Armor"),
    "medium_armor": (("Medium Armor",), lambda r: _atype(r) == "Medium Armor"),
    "light_armor": (("Light Armor",), lambda r: _atype(r) == "Light Armor"),
    "crafting": (("Crafting Equipment",), lambda r: _atype(r) == "Crafting Tool"),
    "clothing": (("Clothing",), lambda r: _atype(r) == "Clothing"),
}
STOCK_SIZE = 12
STOCK_MIN = 3                    # fewer than this and the merchant keeps general_goods
NAMED_ITEM = re.compile(r"(?<!adventurer)(?<!apprentice)(?<!initiate)(?<!apostle)'s(?![a-z])| of | tool$", re.I)  # "Basnaret's Robe", "Bow of Fighting": loot, not stock


def role_stock_key(title):
    """The role stock for a merchant title ("Merchant - Heavy Armor Vendor" -> "archive_heavy_armor")."""
    for role, (words, _) in ROLE_STOCKS.items():
        if any(w in (title or "") for w in words):
            return "archive_" + role
    return None


def item_level(r):
    for v in (r.get("level_required"), r.get("item_level")):
        try:
            return int(v)
        except (TypeError, ValueError):
            pass
    return 0


def build_role_stock(role, items_recs):
    """[(archive record, price)]: up to STOCK_SIZE items for a role, evenly over the levels. The
    archive has no prices: 25 copper per item level (required level, else item level; a placeholder)."""
    test = ROLE_STOCKS[role][1]
    pool = [r for r in items_recs.values()
            if r.get("rarity") in ("mundane", "common") and r.get("slot") and "." not in r["name"]
            and not NAMED_ITEM.search(r["name"])
            and (r.get("archive_fields") or {}).get("origin") != ["Player-crafted"] and test(r)]
    pool.sort(key=lambda r: (item_level(r), r["name"]))
    if len(pool) > STOCK_SIZE:
        pool = [pool[i * (len(pool) - 1) // (STOCK_SIZE - 1)] for i in range(STOCK_SIZE)]
    if len(pool) < STOCK_MIN:
        return []
    return [(r, 25 * max(1, item_level(r))) for r in pool]


# Placeholder icons by equipment slot (iconsTK.xml numbers, picked by eye): the archive has no icons.
# 443 is a red "prohibited" sign, so it is no placeholder.
SLOT_ICONS = {"HEAD": 437, "CHEST": 436, "HANDS": 434, "WRISTS": 432, "LEGS": 430, "FEET": 431,
              "SHOULDERS": 435, "WAIST": 473, "CLOAK": 474, "BACK": 474, "NECK": 445, "LEFTEAR": 444,
              "RIGHTEAR": 444, "LEFTFINGER": 444, "RIGHTFINGER": 444, "SECONDARYHAND": 517}
WEAPON_ICONS = ((re.compile(r"staff|rod|wand", re.I), 483), (re.compile(r"mace|hammer|club|maul", re.I), 425),
                (re.compile(r"dagger|knife|shiv|kris", re.I), 427))
NO_ICON = 442                    # a sack: anything without a slot


def slot_icon(items, slot, name=""):
    """A placeholder icon for an archive item: by slot (SLOT_ICONS), a weapon by its name, else the
    commonest icon of the hand-made items for that slot, else a sack."""
    if slot in SLOT_ICONS:
        return SLOT_ICONS[slot]
    if slot in ("PRIMARYHAND", "TWOHANDS"):
        hit = next((icon for pat, icon in WEAPON_ICONS if pat.search(name)), None)
        if hit:
            return hit
    icons = collections.Counter(it["icon"] for it in items.values() if isinstance(it, dict)
                                and slot and it.get("slot") == slot and it.get("icon") not in (None, 443)
                                and not it.get("_source"))
    return icons.most_common(1)[0][0] if icons else NO_ICON


def fix_placeholder_icons(content=CONTENT):
    """Archive items still on the old placeholder 443 get slot_icon. Returns how many changed."""
    path = os.path.join(content, "items.json")
    items = load(path, {})
    n = 0
    for name, it in items.items():
        if isinstance(it, dict) and it.get("_source") and it.get("icon") == 443:
            it["icon"] = slot_icon(items, it.get("slot"), name)
            n += 1
    if n:
        write(path, items)
    return n


def stock_merchants(content=CONTENT):
    """Give imported merchants on the shared "general_goods" (or on another role stock) the role
    stock matching their title, creating the stock (merchants.json) and its items (items.json, via
    the converter) once. Merchants a builder gave other wares are left alone.
    Returns (merchants changed, items added)."""
    sys.path.insert(0, os.path.join(ROOT, "crowdsourced"))
    import convert
    import tempfile
    mobs_path, merch_path, items_path = (os.path.join(content, n) for n in ("mobs.json", "merchants.json", "items.json"))
    mobs, merchants, items = load(mobs_path, {}), load(merch_path, {}), load(items_path, {})
    recs = archive_npcs(kind="item")
    changed = added = 0
    for key, t in mobs.items():
        if not key.startswith("arch_") or not isinstance(t, dict) or not (
                t.get("merchant") == "general_goods" or str(t.get("merchant")).startswith("archive_")):
            continue
        stock = role_stock_key(t.get("title"))
        if stock is None or stock == t["merchant"]:
            continue
        if stock not in merchants:
            chosen = build_role_stock(stock[len("archive_"):], recs)
            with tempfile.TemporaryDirectory() as d:
                with open(os.path.join(d, "all.jsonl"), "w", encoding="utf-8") as f:
                    for r, _ in chosen:
                        f.write(json.dumps(dict(r, notes=r.get("notes") or "", confidence=r.get("confidence") or "low")) + "\n")
                out = convert.convert(convert.Batch(d, include_low=True), convert.creature_races())["items.json"]
            rows = []
            for r, price in chosen:
                it = out.get(r["name"])
                if it is None:
                    continue
                if r["name"] not in items:
                    if it.get("icon") in (None, 443):        # the converter's placeholder
                        it["icon"] = slot_icon(items, it.get("slot"), r["name"])
                    items[r["name"]] = it
                    added += 1
                rows.append({"item": r["name"], "price": price})
            if not rows:
                continue
            merchants[stock] = rows
        t["merchant"] = stock
        changed += 1
    if changed:
        write(merch_path, merchants)
        write(mobs_path, mobs)
    if added:
        write(items_path, items)
    return changed, added


def branch_raw(ref):
    """The raw batches of a git ref (the scrape publishes to its own branch), extracted with git
    archive into a temporary folder (removed when the program exits); the branch is not merged.
    Returns the raw folder."""
    import atexit, shutil, subprocess, tarfile, tempfile, io
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=ROOT, check=False)
    data = subprocess.run(["git", "archive", ref, "crowdsourced/raw"], cwd=ROOT, capture_output=True, check=True).stdout
    out = tempfile.mkdtemp(prefix="vgemu-raw-")
    atexit.register(shutil.rmtree, out, True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(out, filter="data")
    return os.path.join(out, "crowdsourced", "raw")


def import_all(do_apply, skip):
    """Every zone with something to place (NPCs, quest givers, creatures), with loot."""
    chunks, npcs, quests = zone_chunks(), archive_npcs(), archive_npcs(kind="quest")
    zones, creatures, loot = archive_npcs(kind="zone"), archive_npcs(kind="creature"), archive_npcs(kind="loot")
    totals = [0, 0, 0]
    for name in sorted(chunks):
        if name in skip:
            continue
        level, mobs, spawns = plan(name, npcs, chunks, quests, (zones.get(name) or {}).get("continent"), creatures,
                                   zones.get(name))
        if not spawns:
            continue
        totals[0] += 1
        if do_apply:
            attach_loot(mobs, loot)
            added = apply(level, mobs, spawns)
            totals[1] += added[0]
            totals[2] += added[1]
    if not do_apply:
        print(f"{totals[0]} zones have something to place (run with --apply to add it)")
        return 0
    print(f"{totals[0]} zones: added {totals[1]} templates and {totals[2]} spawns")
    print("role stocks: %d merchants, %d items added" % stock_merchants())
    print("placeholder icons replaced: %d" % fix_placeholder_icons())
    if totals[1] or totals[2]:
        with open(os.path.join(ROOT, "crowdsourced", "imported.md"), "a", encoding="utf-8") as f:
            f.write(f"| {datetime.date.today()} | raw batches{' + ' + ', '.join(SOURCES) if SOURCES else ''} "
                    f"(all zones, skipping {', '.join(sorted(skip)) or 'none'}) | {totals[2]} spawns, {totals[1]} "
                    f"templates | server/content via tools/import_zone.py --all |\n")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("zone", nargs="?", help='the zone name as in ChunkNames.txt, e.g. "Khal"')
    ap.add_argument("--all", action="store_true", help="every zone in ChunkNames.txt with something to place")
    ap.add_argument("--skip", action="append", default=[], help="a zone to leave out (with --all)")
    ap.add_argument("--branch", nargs="?", const="origin/crowdsourced/archive-collection",
                    help="also read the raw batches of this git branch (default: the collection branch)")
    ap.add_argument("--apply", action="store_true", help="add to server/content instead of writing drafts")
    ap.add_argument("--raw", action="append", default=[],
                    help="another folder of raw batches to read as well (e.g. one taken from the collection branch)")
    a = ap.parse_args(argv)
    EXTRA_RAW.extend(a.raw)
    SOURCES.extend(a.raw)
    if a.branch:
        EXTRA_RAW.append(branch_raw(a.branch))
        SOURCES.append(f"branch {a.branch}")
    if a.all:
        return import_all(a.apply, set(a.skip))
    if not a.zone:
        ap.error("give a zone name or --all")
    zone_rec = archive_npcs(kind="zone").get(a.zone) or {}
    level, mobs, spawns = plan(a.zone, archive_npcs(), zone_chunks(), archive_npcs(kind="quest"),
                               zone_rec.get("continent"), archive_npcs(kind="creature"), zone_rec)
    print(f"{a.zone}: {level}, {len(spawns)} NPCs with a position in the archive (NPC records and quest start locations)")
    if not a.apply:
        out = os.path.join(DRAFTS, re.sub(r"[^A-Za-z0-9]+", "_", a.zone))
        write(os.path.join(out, "mobs.json"), mobs)
        write(os.path.join(out, "spawns", level + ".json"), {"spawns": spawns})
        print(f"drafts written to {os.path.relpath(out, ROOT)} (run again with --apply to add them)")
        return 0
    attach_loot(mobs, archive_npcs(kind="loot"))
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
