"""Attribute points: the character window's Allocation Points and the + / Max buttons on the
Attributes tab (decoded from the client, docs/MSGSCORE.md "Attribute points").

client -> zone:
  0xe4 {i32 stat instance id, i32 mode (1 = one point, 3 = as many as allowed), i32 category
       (0 adventuring, 1 crafting)}: the + (UI attribute_gain_inc) and Max (attribute_gain_max)
       buttons, only enabled while bCanSpendAdvAllocPoints is true (FUN_0056eeb0)
server -> client:
  0x2da {i32 points, i32 pool (0 adventuring, 1 crafting, 2 diplomacy)}: sets PCPotentialPool*
       (the Allocation Points number) and bCanSpend*AllocPoints = points > 0 (FUN_0055dda0)
  0x2d9 {i32 result, i32 stat instance id, i32 category, i32 new base value, i32 points left}
       (FUN_00575100): prints the result and updates the pool; the shown value needs a 0x2d4
  0x2db {u8 0 adventuring / 1 crafting}: "You have gained new %s attribute points!" and a banner

Points are placeholders: POINTS_PER_LEVEL each level after the first, at most CAP_PER_LEVEL per
level into one attribute. Only spent points are saved; the pool is earned minus spent.
"""
import struct

ALLOCATE = 0xE4
SET_POOL, RESULT, GAINED = 0x2DA, 0x2D9, 0x2DB
ONE, MAX = 1, 3
ADVENTURING = 0
POINTS_PER_LEVEL = 2
CAP_PER_LEVEL = 1
# Result codes 0-5 (raised) and 6-11 (can't raise) run in this order (FUN_00575100).
ORDER = ("strength", "constitution", "dexterity", "vitality", "wisdom", "intelligence")
RAISE_FAILED = 6
NOT_ALLOWED, NO_POINTS = 36, 37


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def earned(level):
    return POINTS_PER_LEVEL * max(0, level - 1)


def pool(level, alloc):
    return max(0, earned(level) - sum(alloc.values()))


def cap(level):
    return CAP_PER_LEVEL * level


def set_pool(points):
    return _event(SET_POOL, struct.pack("<ii", points, ADVENTURING))


def gained():
    return _event(GAINED, bytes([ADVENTURING]))


def result(code, stat_id, new_value, points):
    return _event(RESULT, struct.pack("<iiiii", code, stat_id, ADVENTURING, new_value, points))


def allocate(name, mode, level, alloc):
    """(points added, result code) for a + (ONE) or Max (MAX) press on attribute name."""
    if name not in ORDER:
        return 0, NOT_ALLOWED
    left = pool(level, alloc)
    if left <= 0:
        return 0, NO_POINTS
    room = cap(level) - alloc.get(name, 0)
    if room <= 0:
        return 0, RAISE_FAILED + ORDER.index(name)
    n = min(left, room) if mode == MAX else 1
    alloc[name] = alloc.get(name, 0) + n
    return n, ORDER.index(name)
