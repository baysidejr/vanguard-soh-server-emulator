"""VGMessages: SGO message objects carried in type-2 event envelopes.

Fields are packed little-endian in their registration order with no tags
(deserializer FUN_00cd9da0). Type codes: f = f32, i = i32, b = u8, o = bool8,
q = i64/entity id, w = UTF-16 string with NUL.
"""

import struct

_FMT = {"f": "<f", "i": "<i", "b": "<B", "o": "<B", "q": "<q"}


def pack(types, values):
    out = bytearray()
    for t, v in zip(types, values):
        if t == "w":
            out += (str(v) + "\0").encode("utf-16-le")
        else:
            out += struct.pack(_FMT[t], v)
    return bytes(out)


# MsgScore (zone event 0x3de, handler FUN_005e8260, registrar FUN_005db5d0):
# the character sheet. 111 fields; meanings below are inferred from the UI
# variables the handler sets right after reading each field.
SCORE_TYPES = ("fff" "ii" "bbb" "iii" "b" "iii" "b" "iii" "ff" "ii" "ii" "iii" "b" "f"
               "ooooo" "ffffff" "f" "i" "bb" "ffff" "i" "f" "i" "f" "ii" + "f" * 56)
SCORE_FIELDS = {
    "x": 0, "y": 1, "z": 2, "chunk_x": 3, "chunk_y": 4,
    "race": 5, "gender": 6, "class_byte": 7,
    "adv_level": 8, "adv_exp": 9, "adv_class": 10,
    "craft_level": 12, "craft_exp": 13, "harvest_level": 14,
    "dip_level": 16, "dip_exp": 17, "aa_points": 18,
    "adv_exp_next": 21, "aa_spent": 25, "aa_exp": 26, "move_speed": 29,
    # Verified with a probe (each field = its own index): the XP bar shows
    # field 35 x 100 %, the character window's Armor Class shows field 42.
    "adv_exp_frac": 35, "armor_class": 42,
}
assert len(SCORE_TYPES) == 111, len(SCORE_TYPES)


def score(probe=False, **kw):
    values = [0] * len(SCORE_TYPES)
    if probe:
        # Every float/int from field 35 on gets its own index, to map UI slots.
        for i in range(35, len(SCORE_TYPES)):
            values[i] = i if SCORE_TYPES[i] in "if" else 0
    for name, v in kw.items():
        values[SCORE_FIELDS[name]] = v
    return pack(SCORE_TYPES, values)


# MsgSingleStatInfo (zone 0x2d3 one stat, 0x2d5 = i32 count + records; handler
# FUN_00577790). Wire order (inferred from where the handler stores each field):
# 0 stat id (+0x5c), 1 instance id (+4), 2 category (+0x4c; 0 adventuring,
# 1 crafting, 3 harvesting), 3 base (+0x28), 4 (+0x30), 5 (+0x2c), 6 current (+0x34),
# 7 (+0x3c), 8 max (+0x40), 9 (+0x38), 10 kind (+8; 1 attribute, 5 special),
# 11 (+0x44), 12 subtype (+0x48, UI hook), 13 (+0x50), 14 (+0x54)
STAT_TYPES = "iib" "iiiiiii" "bbb" "ii"


def stat_info(stat_id, value, category=0, subtype=0, base=None, kind=0, raw=None,
              maximum=None):
    """kind (wire field 10, stat +8): for category 0, 1 = attribute, 2/4 = skill,
    5 = expendable, 6 = absorption (FUN_00556c50)."""
    v = [0] * len(STAT_TYPES)
    v[0], v[2], v[3], v[6], v[12] = stat_id, category, value if base is None else base, value, subtype
    v[1] = stat_id        # instance id (+4); 0x2d4 updates find the stat by it
    if maximum is not None:
        v[8] = maximum    # +0x40: bar maximum (current/max drive the HUD bars)
    v[10] = kind
    for i, x in (raw or {}).items():
        v[i] = x
    return pack(STAT_TYPES, v)


# Stat ids (wire field 0, stat +0x5c) the character window looks up by name
# (FUN_00573070: category 0 -> PCAdv*/Stat* UI vars).
STAT_IDS = {
    "strength": 0x03, "constitution": 0x6F, "dexterity": 0x73, "vitality": 0x9A,
    "intelligence": 0x9E, "wisdom": 0xAA,
    "hit_points": 0xD2, "endurance": 0xE0, "energy": 0xEE,
    "res_fire": 0x37, "res_physical": 0x72, "res_mental": 0x89, "res_arcane": 0xA3,
    "res_cold": 0xBA, "res_spiritual": 0xBD, "res_shadow": 0x100, "res_holy": 0x101,
    "res_planar": 0x102,
}
ATTRIBUTES = ("strength", "constitution", "dexterity", "vitality", "intelligence", "wisdom")


# MsgStatUpdate (zone 0x2d4, handler FUN_00576c90): changes a stat created by
# 0x2d3/0x2d5, found by (instance id, category). Only this path refreshes the
# character window's attribute values (FUN_00573070). Field order inferred from
# the handler's stack layout:
# 0 instance id, 1 category, 2 base (+0x28), 3 (+0x30), 4 (+0x2c), 5 current (+0x34),
# 6 (+0x3c), 7 max (+0x40), 8 (+0x38), 9 byte (+0x44), 10 (+0x50), 11 (+0x54), 12 stat id
STAT_UPDATE_TYPES = "ib" "iiiiiii" "b" "iii"


def stat_update(stat_id, value, category=0, base=None, maximum=None, raw=None):
    v = [0] * len(STAT_UPDATE_TYPES)
    v[0], v[1], v[2], v[5], v[12] = stat_id, category, value if base is None else base, value, stat_id
    v[7] = value if maximum is None else maximum
    for i, x in (raw or {}).items():
        v[i] = x
    return pack(STAT_UPDATE_TYPES, v)


def stat_list(records):
    return struct.pack("<i", len(records)) + b"".join(records)


# MsgSingleItemInfo (zone 0x197 add to inventory; 0x1a6/0x1b7/0x1d4... other
# containers; handler FUN_00512d40 -> FUN_00516610). Field meanings are being
# mapped with the !item dev command; see item_info().
ITEM_TYPES = ("o" "i" "wwww" "iii" "ii" "ii" "iiiii" "iiii" "wwww" "ww" "wwwww" "iii"
              + "wwwi" * 3 + "ii" + "www" * 3 + "i" + "www" * 3 + "ww" + "iiiiiii" + "b"
              + "ii" + "ff" + "iiiiii" + "ff" + "bbbb" + "iiii" + "bbbbbb" + "iiiiii" + "f"
              + "ooo" + "www" + "i")


# Field indexes (see scratchpad inventory report; FUN_00514ff0 / FUN_00512430).
ITEM_FIELDS = {
    "id": 1, "name": 2, "description": 3, "quantity": 6, "equip_slot": 7,
    "icon": 13, "capacity": 14, "container": 15, "slot": 16, "provides_container": 71,
    "location": 92, "quality": 99,
}


def inventory_item(item_id, name, slot, icon=443, quantity=1, description="",
                   container=-1, quality=1):
    """An item in a bag: equip slot -1, container -1 = the main grid
    (gamevar InventoryContainerID_-1, 50 slots), slot 0..49. Icon is a
    number formatted %05d in the client icon map (443 = the client's fallback)."""
    f = ITEM_FIELDS
    return item_info({f["id"]: item_id, f["name"]: name, f["description"]: description,
                      f["quantity"]: quantity, f["equip_slot"]: -1, f["icon"]: icon,
                      f["container"]: container, f["slot"]: slot, 81: 1.0,
                      f["quality"]: quality})


def item_info(raw=None, probe=False):
    """Pack an item record. raw: {field index: value}. probe fills every field
    with something recognisable (strings 'S<index>', ints the index)."""
    values = []
    for n, t in enumerate(ITEM_TYPES):
        if t == "w":
            values.append(f"S{n}" if probe else "")
        elif t in "if":
            values.append(n if probe else 0)
        else:
            values.append(0)
    for n, x in (raw or {}).items():
        values[n] = x
    return pack(ITEM_TYPES, values)
