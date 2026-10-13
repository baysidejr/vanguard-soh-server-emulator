"""Social features (docs/SOCIAL.md): /who, friends, ignore, AFK/anon/LFG flags,
/random and /inspect.

World connection, packet type 5 (social channel: u16 5, u32 id, u32 len, payload;
client handler FUN_00625350):
  client 0x44 /who: a raw 0x160-byte struct (chunk x/y filter at 4/8, -999999 = all;
     min/max level at 0xc/0x10; 32 class ids at 0x14; name filter wchar at 0x9e)
  -> 0x501 clear, 0x500 MsgWhoInfo per player, 0x502 {i32 count, i32 mode, i32 trial, bool8 cut}
     (the client prints the lines and "N player(s) found.")
  client 0x4f7 {wstr name, bool8} /friend  -> 0x4f2 added / 0x4f3 removed (MsgFriendInfo)
  client 0x4f8 {wstr name, bool8} /ignore  -> 0x4f4 added / 0x4f5 removed
  0x4f9 / 0x4fa {i32 n, n x MsgFriendInfo} friend / ignore lists; 0x4f6 status change
     ("X is now online." / "X has gone offline.")
Zone events: 0x505 {bool8} /afk, 0x5a6 {i32, bool8} /anon (toggle), 0x503 {bool8} /lfg,
  0x15a {i32 min, i32 max} /random, 0x48c {wstr name} /inspect
  -> 0x48d begin, 0x490 {wstr name, wstr class, i32 level}, 0x48f item per equipped item, 0x48e show."""
import struct

WHO, FRIEND, IGNORE = 0x44, 0x4F7, 0x4F8
WORLD_EVENTS = (WHO, FRIEND, IGNORE)
AFK, ANON, LFG, RANDOM, INSPECT = 0x505, 0x5A6, 0x503, 0x15A, 0x48C
ZONE_EVENTS = (AFK, ANON, LFG, RANDOM, INSPECT)
ALL_CHUNKS = -999999
NO_CRAFT_CLASS = 0xFF


def _social(event_id, data=b""):
    return struct.pack("<HII", 5, event_id, len(data)) + data


def _zone(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def parse_who(data):
    """The /who request struct -> dict of filters."""
    data = data.ljust(0x160, b"\0")
    cx, cy, lo, hi = struct.unpack_from("<iiii", data, 4)
    classes = [c for c in struct.unpack_from("<32i", data, 0x14) if c != -1]
    name = data[0x9E:0x160].decode("utf-16-le", "replace").split("\0")[0]
    return {"chunk": None if cx == ALL_CHUNKS else (cx, cy), "min": lo, "max": hi,
            "classes": classes, "name": name.lower(), "lfg": data[0x98]}


def who_matches(f, p):
    """p: dict with name, level, klass, chunk, lfg."""
    if f["chunk"] is not None and tuple(p["chunk"]) != f["chunk"]:
        return False
    if f["min"] and p["level"] < f["min"]:
        return False
    if f["max"] and p["level"] > f["max"]:
        return False
    if f["classes"] and p["klass"] not in f["classes"]:
        return False
    if f["name"] and f["name"] not in p["name"].lower():
        return False
    if f["lfg"] and not p.get("lfg"):
        return False
    return True


def who_info(p, uid):
    data = (struct.pack("<i", uid) + _w(p["name"]) + _w(p.get("guild", ""))
            + struct.pack("<ii", p["level"], p["klass"]) + struct.pack("<ii", 0, 0)
            + struct.pack("<ii", p.get("craft_level", 0), p.get("craft_class", NO_CRAFT_CLASS))
            + struct.pack("<i", p.get("diplomacy_level", 1))
            + struct.pack("<iii", p["chunk"][0], p["chunk"][1], 0)
            # The second byte (find-list entry +0x62): set = looking for members, so the Find
            # window offers "Request to Join" instead of "Invite to Group" (FUN_0057fba0).
            + struct.pack("<BBBB", int(p.get("lfg", False)), int(p.get("lfm", False)), int(p.get("afk", False)),
                          int(p.get("anon", False)))
            + _w("") * 23 + struct.pack("<96i", *[0] * 96))
    return _social(0x500, data)


def who_messages(players, mode=0):
    """mode 0 = /who list, 1 = the Find window's LFG page, 2 = its LFM page."""
    out = [_social(0x501)]
    out += [who_info(p, n + 1) for n, p in enumerate(players)]
    out.append(_social(0x502, struct.pack("<iiiB", len(players), mode, 0, 0)))
    return out


# The Find window (world social): 0x503 LFG / 0x504 LFM {u8 search, u8 flag, 32 x (i32 class,
# i32 dungeon, i32 quest)}; search = 1 is the Search button, 0 the /lfg or /lfm toggle.
FIND_LFG, FIND_LFM = 0x503, 0x504


def friend_info(p, uid):
    """p: dict (name, level, klass, chunk, online, anon); unknown/offline -> -1 fields."""
    online = p.get("online", False)
    level, klass = (p["level"], p["klass"]) if online else (-1, -1)
    cx, cy = p["chunk"] if online else (-1, -1)
    return (struct.pack("<i", uid) + _w(p["name"]) + struct.pack("<iBiii", level, int(online), klass, 0,
                                                                 NO_CRAFT_CLASS)
            + struct.pack("<iiIB", cx, cy, 0, int(p.get("anon", False))))


def friend_added(p, uid):
    return _social(0x4F2, friend_info(p, uid))


def friend_removed(p, uid):
    return _social(0x4F3, friend_info(p, uid))


def friend_status(p, uid):
    return _social(0x4F6, friend_info(p, uid))


def ignore_added(p, uid):
    return _social(0x4F4, friend_info(p, uid))


def ignore_removed(p, uid):
    return _social(0x4F5, friend_info(p, uid))


def friend_list(entries):
    return _social(0x4F9, struct.pack("<i", len(entries)) + b"".join(friend_info(p, p.get("uid", n + 1))
                                                                     for n, p in enumerate(entries)))


def ignore_list(entries):
    return _social(0x4FA, struct.pack("<i", len(entries)) + b"".join(friend_info(p, p.get("uid", n + 1))
                                                                     for n, p in enumerate(entries)))


def read_name(data):
    return data.decode("utf-16-le", "replace").split("\0")[0]


def inspect_messages(name, class_name, level, item_records):
    return ([_zone(0x48D), _zone(0x490, _w(name) + _w(class_name) + struct.pack("<i", level))]
            + [_zone(0x48F, r) for r in item_records] + [_zone(0x48E)])
