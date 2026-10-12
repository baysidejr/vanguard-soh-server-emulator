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
