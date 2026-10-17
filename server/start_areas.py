"""Where a new character starts (backlog B-017).

The character-create request (event 0x139) carries the starting chunk the player picked: i32 x,
i32 y at raw +9 / +13 after the three names (docs/PROTOCOL.md). Six of seven saved characters
sent (-26, 1), the Isle of Dawn in ChunkNames.txt; one sent (-65535, -65535), taken here to mean
"the race's own starting area" [I]. Each race's intro text in bin/VGClient.int (RI<race>) names
that area: Tursh Village in Thestra, Shang Village near Tanvu in Kojan, or Karibasa Village on
the Cliffs of Ghelgad near Khal in Qalia.

Where in the chunk: the maps' PlayerStart actors are not real spawn points (zone.spawn_location),
so a character stands next to the NPC its intro tells it to report to when there is one (Master
Rahlsu in Shang Village), else at the densest cluster of the area's archive NPCs, i.e. the
village [I: an approximation; the original spawn spots were server data].

Off unless the server runs with --start-areas.
"""
import struct

ISLE_OF_DAWN, TURSH, SHANG, KARIBASA = (-26, 1), (-27, 27), (-19, 7), (-13, -8)
STARTS = {ISLE_OF_DAWN: "Isle of Dawn", TURSH: "Tursh Village", SHANG: "Shang Village",
          KARIBASA: "Karibasa Village"}
RACIAL = -65535                 # the create request's "no island" value [I]

# Race id (races_classes.RACES) -> starting area, from each race's intro text (RI<race>).
RACE_START = {
    14: TURSH, 2: TURSH, 10: TURSH, 4: TURSH, 18: TURSH, 9: TURSH, 21: TURSH,
    12: SHANG, 5: SHANG, 8: SHANG, 11: SHANG, 7: SHANG, 17: SHANG,
    13: KARIBASA, 6: KARIBASA, 3: KARIBASA, 22: KARIBASA, 15: KARIBASA, 20: KARIBASA,
}
# The NPC an area's intro text names ("report to Master Rahlsu").
NAMED_NPC = {SHANG: "Master Rahlsu"}
CLUSTER_RADIUS = 3000.0
BESIDE = 120.0                  # stand this far from the anchor, not inside it


def requested_chunk(raw):
    """(x, y) of the starting chunk in a create request's bytes after the names, or None."""
    if len(raw) < 17:
        return None
    return struct.unpack_from("<ii", raw, 9)


def start_chunk(raw):
    """The chunk a new character starts in, or None to keep the server's default."""
    req = requested_chunk(raw)
    if req is None:
        return None
    if req in STARTS:
        return req
    if req == (RACIAL, RACIAL):
        return RACE_START.get(raw[7])
    return None


def anchor(spawns, chunk):
    """(x, y) to stand beside in a starting chunk, from its [(spawn, template)] list; None if
    the chunk has no NPCs."""
    name = NAMED_NPC.get(tuple(chunk))
    for s, t in spawns:
        if name and t.get("name") == name:
            return s["x"], s["y"]
    # Only peaceful people count: creatures have a damage block (or an aggro radius), and a new
    # character must not appear beside a pack of them.
    people = [(s["x"], s["y"]) for s, t in spawns if not t.get("damage") and not t.get("aggro_radius")]
    if not people:
        return None
    r2 = CLUSTER_RADIUS ** 2
    return max(people, key=lambda p: sum((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 <= r2 for q in people))


def start_position(content, chunk, level, client_dir, lift):
    """Saved-position triple (pawn centre, as the client reports it) beside the anchor, or None."""
    a = anchor(content.spawns(level, client_dir), chunk)
    if a is None:
        return None
    x, y = a[0] + BESIDE, a[1]
    z = content.ground_z(level, x, y, client_dir)
    if z is None:
        return None
    return [x, y, z + lift]
