"""Travel journal: the Adventure Journal's Locations tab and its map markers (docs/TRAVEL.md;
client handlers FUN_005d86d0 / FUN_005d83a0).

  0x2ae {wstr name, i32 category id, i32 0}: add a category under "All Locations". The first one
        also creates the built-in categories -3 All Locations, -2 Corpses, -4 Player Housing.
  0x382 MsgSingleTravelJournalEntryToClient {i32 id, i32 0, f32 x, y, z, wstr name, i32 chunk x,
        i32 chunk y, i32 0, u8 type, wstr description, i32 category id, bool8 track, i32 0}: add a
        location (dropped unless its category exists). Type 1 is the tombstone icon; type 0 also
        prints "The locations section of your Adventure Journal has changed."; other types are a
        plain point of interest on the map.
  0x383 {i32 id}: remove a location. 0x2aa (same layout as 0x382) updates an existing one."""
import math
import struct

# Locations tab: Remove > Yes (location_remove_confirm_yes, FUN_005d3580 -> FUN_005d3410) sends
# 0x138 {i32 entry id}. The server answers 0x383 {id} and keeps it out of the journal.
REMOVE_REQUEST = 0x138
POI, TOMBSTONE, NEW_POI = 2, 1, 0
ALL, CORPSES, HOUSING = -3, -2, -4
ENTRY_ID_BASE = 0x7300000
HOUSE_ENTRY_ID = ENTRY_ID_BASE + 0xFFFF

# Journal categories for the town services a chunk's spawns provide (mobs.json keys).
CATEGORIES = [
    (101, "Merchants", ("merchant", "broker")),
    (102, "Trainers", ("trainer", "recipe_trainer", "assembly_trainer")),
    (103, "Services", ("banker", "mailbox", "altar", "task_master", "repairs")),
    (104, "Crafting Stations", ("station",)),
    (105, "Riftways", ("riftway",)),
    (106, "Quest Givers", ("quests",)),
]


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def category(name, cid):
    return _event(0x2AE, _w(name) + struct.pack("<ii", cid, 0))


def entry(eid, loc, name, chunk, cat, desc="", kind=POI, track=False):
    x, y, z = loc
    return _event(0x382, struct.pack("<iifff", eid, 0, float(x), float(y), float(z)) + _w(name)
                  + struct.pack("<iiiB", chunk[0], chunk[1], 0, kind) + _w(desc)
                  + struct.pack("<iBi", cat, int(track), 0))


def remove(eid):
    return _event(0x383, struct.pack("<i", eid))


def category_of(template):
    for cid, _, keys in CATEGORIES:
        if any(template.get(k) for k in keys):
            return cid
    if template.get("assembly_bench") or template.get("title") == "Assembly Station":
        return 104
    return None


DISCOVER_RANGE = 1500.0           # walking this close to a service location adds it to the journal


def chunk_sites(spawns):
    """[(entry id, category id, (x, y, z), name, description)] for the chunk's NPCs and objects
    that offer a service; ids are stable per spawn index."""
    out = []
    for n, (s, t) in enumerate(spawns):
        cid = category_of(t)
        if cid is not None:
            out.append((ENTRY_ID_BASE + n, cid, (s["x"], s["y"], s.get("z") or 0.0),
                        t.get("name", s["mob"]), t.get("title") or ""))
    return out


def chunk_locations(spawns, chunk, known=None):
    """Journal entries for a chunk's spawns: [(category id, entry message)]; known (a set of
    entry ids) keeps only the discovered ones."""
    return [(cid, entry(eid, loc, name, chunk, cid, desc)) for eid, cid, loc, name, desc in chunk_sites(spawns)
            if known is None or eid in known]


def discover(sites, known, pos, rng=DISCOVER_RANGE):
    """The sites within rng of pos (x, y) that are not in known yet."""
    return [s for s in sites if s[0] not in known and math.hypot(s[2][0] - pos[0], s[2][1] - pos[1]) <= rng]


def login_messages(spawns, chunk, house=None, known=None):
    """Categories, then the chunk's (discovered) locations, then the player's house (category -4)."""
    found = chunk_locations(spawns, chunk, known)
    used = {cid for cid, _ in found} or {CATEGORIES[0][0]}   # one 0x2ae creates the built-ins
    out = [category(name, cid) for cid, name, _ in CATEGORIES if cid in used]
    out += [m for _, m in found]
    if house is not None:
        name, loc, hchunk = house
        out.append(entry(HOUSE_ENTRY_ID, loc, name, hchunk, HOUSING, "Your house"))
    return out
