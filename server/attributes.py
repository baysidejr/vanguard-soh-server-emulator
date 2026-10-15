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
ADVENTURING, CRAFTING = 0, 1
# Crafting attributes (category 1 stat records; the crafting tab of the character window):
# stat id, and the order of their result codes 28-31 (raised) and 32-35 (can't raise).
CRAFT_STATS = {"problem_solving": 42, "reasoning": 151, "ingenuity": 234, "finesse": 239}
CRAFT_ORDER = ("reasoning", "finesse", "ingenuity", "problem_solving")
CRAFT_RAISED, CRAFT_RAISE_FAILED = 28, 32
CRAFT_BASE = 20
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


def set_pool(points, category=ADVENTURING):
    return _event(SET_POOL, struct.pack("<ii", points, category))


def gained(category=ADVENTURING):
    return _event(GAINED, bytes([category]))


def result(code, stat_id, new_value, points, category=ADVENTURING):
    return _event(RESULT, struct.pack("<iiiii", code, stat_id, category, new_value, points))


def allocate(name, mode, level, alloc, category=ADVENTURING):
    """(points added, result code) for a + (ONE) or Max (MAX) press on attribute name."""
    order, raised, failed = ((CRAFT_ORDER, CRAFT_RAISED, CRAFT_RAISE_FAILED) if category == CRAFTING
                             else (ORDER, 0, RAISE_FAILED))
    if name not in order:
        return 0, NOT_ALLOWED
    left = pool(level, alloc)
    if left <= 0:
        return 0, NO_POINTS
    room = cap(level) - alloc.get(name, 0)
    if room <= 0:
        return 0, failed + order.index(name)
    n = min(left, room) if mode == MAX else 1
    alloc[name] = alloc.get(name, 0) + n
    return n, raised + order.index(name)


# Crafting skills on the crafting Skills tab (verified live 2026-10-15): category 1, kind 2 stat
# records; the subtype (wire field 12, stat +0x48) picks the list (FUN_005570d0 jump table at
# 0x557898), the stat id the name (FUN_00573070, category 1 table at 0x574560).
# (stat id, subtype): blacksmith refining parent 5 / skills 0xa, finishing parent 6 / skills 0xb;
# artificer 0x18 / 0xe, 0x19 / 0xf; outfitter 0x1c / 0x12, 0x1d / 0x13.
CRAFT_SKILLS = (
    (231, 0x05), (40, 0x0A), (123, 0x0A), (135, 0x0A), (252, 0x0A), (228, 0x0A), (105, 0x0A),
    (148, 0x06), (180, 0x0B), (64, 0x0B),
    (120, 0x18), (100, 0x0E), (87, 0x0E), (177, 0x0E), (150, 0x0E), (35, 0x0E), (171, 0x0E), (4, 0x0E),
    (113, 0x19), (108, 0x0F),
    (126, 0x1C), (200, 0x12), (101, 0x12), (95, 0x12), (179, 0x12), (62, 0x12), (235, 0x12),
    (39, 0x1D), (26, 0x13), (130, 0x13),
)
CRAFT_SKILL_PER_LEVEL = 5          # placeholder: crafting skills follow the crafting level


# Skill direction (verified live 2026-10-15): the - / lock / + buttons on a crafting skill send
# 0xe3 {i32 stat instance id, i32 direction (1 increase, 2 decrease, 0 locked), i32 category}
# (FUN_0056ed90). The highlighted button is stat +0x44, which only the server sets: 0x2d4 field 9
# (0x2d5 field 11 at login). Increase = may gain, decrease = may give points to other skills of
# the pool, locked = neither (VGClient.int tooltips); the redistribution rules are server data.
SET_DIRECTION = 0xE3
DIRECTIONS = (0, 1, 2)


def craft_skill_value(level):
    return CRAFT_SKILL_PER_LEVEL * max(1, level)


def craft_skill_records(level, dirs=None):
    import vgmsg
    v = craft_skill_value(level)
    dirs = dirs or {}
    return [vgmsg.stat_info(sid, v, category=CRAFTING, kind=2, subtype=sub, maximum=v,
                            raw={11: dirs.get(sid, 0)}) for sid, sub in CRAFT_SKILLS]


# The answer to a skill's - / lock / + button (FUN_00574850): 0x2d8 {i32 result, i32 stat id,
# i32 category, i32 direction}. Result 0 "You successfully set the directional movement of your
# skill.", 1 "You may only set the directional movement of skills.", 2 "You don't have that
# skill.", 0xff "...failed ... for unknown reasons."; the stat's direction (+0x44) is set either way.
DIRECTION_RESULT = 0x2D8
DIRECTION_OK, DIRECTION_NOT_SKILL, DIRECTION_NO_SKILL = 0, 1, 2


def direction_result(result, sid, category, direction):
    return _event(DIRECTION_RESULT, struct.pack("<iiii", result, sid, category, direction))


def craft_skill_update(sid, level, direction):
    """0x2d4 for one crafting skill with its direction (field 9); every other field resent."""
    import vgmsg
    v = craft_skill_value(level)
    return _event(0x2D4, vgmsg.stat_update(sid, v, category=CRAFTING, maximum=v, raw={9: direction}))


def craft_records(alloc):
    """0x2d5 stat records (category 1, attribute) of the crafting attributes."""
    import vgmsg
    return [vgmsg.stat_info(sid, CRAFT_BASE + alloc.get(name, 0), category=CRAFTING, kind=1,
                            maximum=CRAFT_BASE + alloc.get(name, 0)) for name, sid in CRAFT_STATS.items()]


def craft_update(name, alloc):
    import vgmsg
    value = CRAFT_BASE + alloc.get(name, 0)
    return _event(0x2D4, vgmsg.stat_update(CRAFT_STATS[name], value, category=CRAFTING))
