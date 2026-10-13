"""Fishing (docs/FISHING.md; client dispatcher FUN_004cf940, manager DAT_014639d8).

The client checks the gear (pole in the primary hand and bait in the secondary hand, both
item type 26 "Fishing"), throws the bobber and plays the animations; the server runs the bite
and the minigame.
Client -> server: 0x59d /fishing (cast request); 0x599 {f32 x, y, z} bobber in water (then
  every 2 s); 0x59b {i32 dir} minigame key (0 forward, 1 right, 2 back, 3 left);
  0x59a {i32 0} stop.
Server -> client: 0x59d cast; 0x59a {i32 state} (0 stop, 4 "Fish on!", 5 reel);
  0x59c {eid64, i32 event, i32 dir}: 9 the fish pulls (dir), 3 "Good", 4 "Oops",
  5 "Fish caught!", 6 "The fish got away!", 11 "You scared the fish!"."""
import random
import struct

CAST, BOBBER, KEY, STATE = 0x59D, 0x599, 0x59B, 0x59A
CLIENT_EVENTS = (CAST, BOBBER, KEY, STATE)
FISH_ON, STOP = 4, 0
PULL, GOOD, OOPS, CAUGHT, GOT_AWAY, SCARED = 9, 3, 4, 5, 6, 11
SKILL = 0x5B                       # Fishing skill stat id
NEEDED, MISSES = 4, 2              # good answers to land the fish, misses before it escapes
PULL_SECONDS = 2.5                 # time to answer each pull
LAND_TIMEOUT = 15.0                # the bobber must reach water within this


def _w(text):
    return (text + "\0").encode("utf-16-le")


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def cast():
    return _event(CAST)


def state(s):
    return _event(STATE, struct.pack("<i", s))


def event(eid, ev, direction=0):
    return _event(0x59C, struct.pack("<Qii", eid, ev, direction))


# Fishing achievements (the Quests window's Achievements tab, "Fishing" page; zone dispatcher
# FUN_00449300): 0x5a1 MsgAchievementInfo {wstr fish, wstr biggest catch location, i32 type 0,
# i32 fish id, i32 total caught, f32 total weight, f32 heaviest, bool8 fresh water, wstr only
# bait, wstr favorite bait, u8 combo[4]} adds a row (fish id -2 clears the list, -3 redraws it);
# 0x5a2 (same layout) updates one row and redraws.
NO_DIRECTION = 0xFF


def record(name, rec, fresh=False, row_id=None):
    return (_w(name) + _w(rec.get("where", "")) + struct.pack("<ii", 0, rec["id"] if row_id is None else row_id)
            + struct.pack("<iffB", rec.get("caught", 0), rec.get("total", 0.0), rec.get("best", 0.0), int(fresh))
            + _w(rec.get("only_bait", "")) + _w(favorite_bait(rec)) + bytes([NO_DIRECTION] * 4))


def favorite_bait(rec):
    baits = rec.get("baits", {})
    return max(baits, key=baits.get) if baits else "None"


def achievement_list(records, fresh=lambda name: False):
    """0x5a1: clear, one row per fish, redraw."""
    empty = {"id": 0}
    out = [_event(0x5A1, record("", empty, row_id=-2))]
    out += [_event(0x5A1, record(name, rec, fresh(name))) for name, rec in sorted(records.items(), key=lambda kv: kv[1]["id"])]
    out.append(_event(0x5A1, record("", empty, row_id=-3)))
    return out


def achievement_update(name, rec, fresh=False):
    return _event(0x5A2, record(name, rec, fresh))


def add_catch(records, name, weight, where, bait):
    """Count a catch; returns (record, new personal best)."""
    rec = records.setdefault(name, {"id": len(records) + 1, "caught": 0, "total": 0.0, "best": 0.0, "baits": {}})
    rec["caught"] += 1
    rec["total"] = round(rec["total"] + weight, 2)
    best = weight > rec["best"]
    if best:
        rec["best"], rec["where"] = weight, where
    if bait:
        rec["baits"][bait] = rec["baits"].get(bait, 0) + 1
    return rec, best


def bite_delay(rng=random):
    return rng.uniform(4.0, 10.0)
