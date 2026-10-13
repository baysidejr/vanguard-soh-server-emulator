"""Ability trainers (docs/TRAINERS.md; client dispatcher FUN_005d0d40).

Dialogue option 0x2b1 (type 0, "teach") -> client 0x168 (no payload)
  -> 0x492 start training (gamevar Training = 1, closes the dialogue)
     0x493 {i32 n, n x {wstr name, wstr description, i32 ability id, i32 icon, f32 cost copper}}
client 0x16a {i32 ability id} train -> coins 0x1aa, ability 0x215, 0x495 {i32 id, u8 result}
   results: 0 ok (the client drops the entry), 1 not training, 2 not available,
   3 can't afford, 5 inventory locked, 6 too powerful, 0xff failed
client 0x169 stop -> 0x496 {u8 reason} (5 = "Training ended."; frees both lists)
0x493 appends to the client's list, so a new session is always ended with 0x496 first."""
import struct

START, TRAIN, STOP = 0x168, 0x16A, 0x169
CLIENT_EVENTS = (START, TRAIN, STOP)
OPTION = 0x2B1
OK, NOT_TRAINING, NOT_AVAILABLE, CANT_AFFORD, TOO_POWERFUL = 0, 1, 2, 3, 6
ENDED = 5


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def begin(offers):
    """offers: [(ability id, name, description, icon, cost copper)]."""
    data = struct.pack("<i", len(offers))
    for aid, name, desc, icon, cost in offers:
        data += _w(name) + _w(desc) + struct.pack("<iif", aid, icon, float(cost))
    return [_event(0x492), _event(0x493, data)]


def result(aid, code):
    return _event(0x495, struct.pack("<iB", aid, code))


def end(reason=ENDED):
    return _event(0x496, struct.pack("<B", reason))


# Recipe trainers (client dispatcher FUN_005af590). Same flow as ability trainers:
# dialogue option 0x2b2 (type 1, "I'd like to learn recipes from you.") -> client 0x16b
#   -> 0x497 start (gamevar RecipeTraining), then one 0x498 per recipe (appended, no count):
#      {wstr name, wstr description, i32 recipe id, i32 icon, f32 cost copper} (FUN_005af140)
# client 0x16d {i32 recipe id} train -> 0x499 {i32 id, u8 result} (codes as 0x495)
# client 0x16c stop -> 0x49a {u8 reason} (as 0x496: 5 = "Training ended.")
RECIPE_START, RECIPE_STOP, RECIPE_TRAIN = 0x16B, 0x16C, 0x16D
RECIPE_EVENTS = (RECIPE_START, RECIPE_STOP, RECIPE_TRAIN)
RECIPE_OPTION = 0x2B2
RECIPE_TRAINER = 0x80                # EntityTypes bit


def recipe_begin(offers):
    """offers: [(recipe id, name, description, icon, cost copper)]."""
    return [_event(0x497)] + [_event(0x498, _w(name) + _w(desc) + struct.pack("<iif", rid, icon, float(cost)))
                              for rid, name, desc, icon, cost in offers]


def recipe_result(rid, code):
    return _event(0x499, struct.pack("<iB", rid, code))


def recipe_end(reason=ENDED):
    return _event(0x49A, struct.pack("<B", reason))
