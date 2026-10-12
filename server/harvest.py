"""Harvesting resource nodes (docs/HARVESTING.md; client dispatcher FUN_004f54d0).

A node is an SGONPCPawn with EntityTypes bit 0x800 (harvest cursor; interacting
sends client 0x109). The server runs the harvest on a timer:
  0x2dc {u64 node, f32, u8 quantity, u8 skill stat}  open the harvest window
  0x2dd                                              "Harvesting has begun."
  0x3d1 strike visual (player -> node) + 0x2df {f32 qty, f32 progress, f32 max}
  0x2e1 {i32 n, n x {i32 item id, i32 qty, u8 rare}}, 0x2e2 item record, 0x2e3
  0x197 the item into the bag, 0x2de "Harvesting has ended."
client 0x10a = stop. Errors: 0x0e {i16}: 0x77 already harvesting, 0x7a already
harvested, 0x159 can't attack a resource."""
import struct

BEGIN, STOP = 0x109, 0x10A
CLIENT_EVENTS = (BEGIN, STOP)
HARVESTABLE = 0x800                 # EntityTypes bit
SKILLS = {"mining": 0x0F, "quarrying": 0x32, "lumberjacking": 0x4B, "reaping": 0x59,
          "skinning": 0x76, "gathering": 0x79}
STRIKE_VISUALS = {"mining": 20084, "lumberjacking": 20083, "quarrying": 20085,
                  "reaping": 20086, "skinning": 20087, "gathering": 20088}
NODE_DEPLETED_VISUAL = 20004
STRIKES = 4                         # progress steps (the bar max is 18)
STRIKE_SECONDS = 1.5
ERR_ALREADY, ERR_HARVESTED, ERR_CANT_ATTACK = 0x77, 0x7A, 0x159


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def open_window(node, kind):
    return _event(0x2DC, struct.pack("<QfBB", node.entity_id, 0.0, 1, SKILLS.get(kind, 0x0F)))


def begun():
    return _event(0x2DD)


def progress(quantity, current, maximum=18.0):
    return _event(0x2DF, struct.pack("<fff", quantity, current, maximum))


def rewards(item_id, qty, item_record):
    return [_event(0x2E1, struct.pack("<iiiB", 1, item_id, qty, 0)),
            _event(0x2E2, item_record), _event(0x2E3)]


def ended():
    return _event(0x2DE)


def error(code):
    return _event(0x0E, struct.pack("<h", code))


def consider(node):
    """0x3da kind 3: con 11 = "easy for you to start harvesting", + tool line."""
    tool = node.harvest.get("tool", "Mining")
    data = struct.pack("<iiii", 3, 11, 0, 1)
    data += (node.name + "\0").encode("utf-16-le") + (tool + "\0").encode("utf-16-le")
    return _event(0x3DA, data)
