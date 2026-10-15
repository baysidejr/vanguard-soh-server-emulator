"""Faction standing (docs/FACTIONS.md; client dispatcher FUN_004ccc50).

Server -> client:
  0x35b MsgFactionInfo {wstr name, i32 faction id, i32 value, bool8 prestige}: adds a row to
        the Factions window (gamevar PCPlayerFactions, or PCPrestigeFactions when prestige).
  0x358 MsgClientFactionChange {i32 faction id, i32 value}: new value for a known faction.
        When the value crosses a tier the client recolours the name plates of every NPC
        whose m_FactionId is that faction (FUN_004ca8c0 / FUN_004ca950).
  0x35d MsgFactionInfo: "You've unlocked a new prestige faction: %s!"
Client -> server:
  0x18d {i32 page} /showfactions (-1 = all, or /showfactions <page>)
  0x18c {wstr name} /showfactionbyname <name>
Tiers (FUN_004ca950, string keys FactionKOS ... FactionAlly): below -8000 KOS (red),
-8000 Untrustworthy, -5000 Wary, -2000 Neutral (yellow), 2000 Sociable, 5000 Goodwill,
8000 and up Ally (green)."""
import struct

SHOW, SHOW_BY_NAME = 0x18D, 0x18C
CLIENT_EVENTS = (SHOW, SHOW_BY_NAME)
MIN, MAX = -20000, 20000
TIERS = ((-8000, "Kill on Sight"), (-5000, "Untrustworthy"), (-2000, "Wary"), (2000, "Neutral"),
         (5000, "Sociable"), (8000, "Goodwill"))


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def tier(value):
    for limit, name in TIERS:
        if value < limit:
            return name
    return "Ally"


# The client asks about a faction id it has no row for (FUN_004cc5d0, e.g. for a name plate's
# colour): 0x35e {i32 faction id}, once per id. The answer is 0x35b.
INFO_REQUEST = 0x35E


def info(fid, name, value, prestige=False):
    return _event(0x35B, _w(name) + struct.pack("<iiB", fid, value, int(prestige)))


def unlocked(fid, name, value):
    """0x35d (FUN_004cc820): "You've unlocked a new prestige faction: %s!" and the row."""
    return _event(0x35D, _w(name) + struct.pack("<iiB", fid, value, 1))


def change(fid, value):
    return _event(0x358, struct.pack("<ii", fid, value))


def clamp(value):
    return max(MIN, min(MAX, int(value)))


def read_name(data):
    return data.decode("utf-16-le", "replace").split("\0")[0]
