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
}
assert len(SCORE_TYPES) == 111, len(SCORE_TYPES)


def score(**kw):
    values = [0] * len(SCORE_TYPES)
    for name, v in kw.items():
        values[SCORE_FIELDS[name]] = v
    return pack(SCORE_TYPES, values)
