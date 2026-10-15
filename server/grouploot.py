"""Group loot: loot modes, master looter, round robin and the need/greed lottery
(docs/LOOT.md "Group loot"; decoded from the client's group manager).

client -> zone:
  0xb6 set loot mode {eid64 master looter, i32 mode, wstr rarity, bool8 split coin, bool8 cash loot}
       (leader, loot options popup)
  0xb5 promote master looter {wstr name}
  0xb7 allow the group to loot {eid64 corpse}, 0xb8 start randoming {eid64 corpse}
  0xb9 {bool8 need} need (1) / greed (0), 0xba pass
  0x1e6 /groupcancelrollsession {eid64 target}
server -> client:
  0x6c8 loot mode (same layout as 0xb6), 0x6a5 you are master looter, 0x6cc {eid64} another is
  0x6cd {eid64} round robin: someone else's turn, 0x696 {eid64, wstr item, i32 qty} "X looted Y"
  0x6ab / 0x6ad roll popup {wstr next, i32 0, i32 0, i32 seconds, bool8 need allowed} + item (0x1f2
  bytes); 0x6ab clears the list first. 0x6af {i32 roll, bool8 need} your roll (< 1 = passed),
  0x6ae {wstr winner, bool8 need, i32 roll} the result (roll < 1 = everyone passed),
  0x6b0 no more items, 0x6ac hide the popup."""
import random
import struct

FREE_FOR_ALL, ROUND_ROBIN, MASTER_LOOTER, RANDOM_FOR_MAGICAL, NEED_BEFORE_GREED = range(5)
MODE_NAMES = ("Free For All", "Round Robin", "Master Looter", "Random For Magical", "Need Before Greed")

# The rarity threshold travels as the popup's colored string (best first).
RARITIES = ("<color=red>Legendary+</color>", "<color=purple>Fabled</color>",
            "<color=orange>Heroic</color>", "<color=c00ffff37>Rare</color>",
            "<color=blue>Uncommon</color>", "<color=ltgreen>Common</color>",
            "<color=white>Mundane</color>")
DEFAULT_RARITY = RARITIES[4]
# items.json "rarity" names, best first (same order as RARITIES), and the item record's
# rarity byte (wire field 99, item +0x61c) that colours the name (client colour table
# FUN_006d0ee0: 1 red, 10 purple, 2 orange, 4 yellow, 6 blue, 7 green, 8 white).
RARITY_NAMES = ("legendary", "fabled", "heroic", "rare", "uncommon", "common", "mundane")
RARITY_WIRE = {"legendary": 1, "fabled": 10, "heroic": 2, "rare": 4, "uncommon": 6, "common": 7,
               "mundane": 8}
DEFAULT_ITEM_RARITY = "mundane"
COMMON = RARITY_NAMES.index("common")


def rarity_index(name):
    """Index into RARITIES of an items.json rarity name (unknown/missing: mundane)."""
    name = name or DEFAULT_ITEM_RARITY
    return RARITY_NAMES.index(name) if name in RARITY_NAMES else len(RARITY_NAMES) - 1


def rarity_wire(name):
    return RARITY_WIRE.get(name or DEFAULT_ITEM_RARITY, RARITY_WIRE[DEFAULT_ITEM_RARITY])

SET_MODE, PROMOTE_ML, ALLOW_GROUP, START_RANDOM, NEED_GREED, PASS, CANCEL_ROLLS = (
    0xB6, 0xB5, 0xB7, 0xB8, 0xB9, 0xBA, 0x1E6)
# /giveplayerlootitem <player> <item> (FUN_00605440 -> FUN_00522490; the client first asks to
# confirm a soulbound item): 0x3dc MsgEntityIDAndTwoStrings {eid64 corpse (the target),
# wstr player, wstr item}. The master looter hands an item on the corpse to a group member.
GIVE_LOOT = 0x3DC
CLIENT_EVENTS = (SET_MODE, PROMOTE_ML, ALLOW_GROUP, START_RANDOM, NEED_GREED, PASS, CANCEL_ROLLS, GIVE_LOOT)


def parse_give_loot(data):
    """(corpse eid, player name, item text) from a 0x3dc payload."""
    corpse = struct.unpack_from("<Q", data, 0)[0]
    words = data[8:].decode("utf-16-le", "replace").split("\0")
    return corpse, words[0].strip(), (words[1] if len(words) > 1 else "").strip()


def match_loot(loot, text):
    """The corpse item a /giveplayerlootitem argument names: its handle, or (part of) its name."""
    text = text.strip().lower()
    if text.lstrip("-").isdigit():
        return next((i for i in loot if i[0] == int(text)), None)
    return next((i for i in loot if i[1].lower() == text), None) or \
        next((i for i in loot if text and (text in i[1].lower() or i[1].lower() in text)), None)
ROLL_SECONDS = 30

# 0x0e result codes.
MUST_BE_LEADER, NO_PERMISSION, PENDING_RANDOM, INVALID_MODE = 0xC4, 0xF6, 0xEF, 0xD3


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def _rstr(data, pos):
    end = pos
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
        end += 2
    return data[pos:end].decode("utf-16-le", "replace"), end + 2


# Loot window buttons (VGUILoot.xml): 0x6ca {bool8} shows "Share Loot Rights" (sends 0xb7),
# 0x6c9 {bool8} shows "Start Item Rolling" (sends 0xb8); the client keeps them hidden until told.
SHOW_SHARE, SHOW_START_ROLLING = 0x6CA, 0x6C9


def loot_buttons(group, npc):
    """[0x6ca, 0x6c9] for someone who may loot npc: share rights in Round Robin and Master
    Looter (until shared), start rolling in Random For Magical."""
    mode = settings(group)["mode"] if group is not None else None
    share = mode in (ROUND_ROBIN, MASTER_LOOTER) and not getattr(npc, "open_to_group", False)
    return [loot_button(SHOW_SHARE, share), loot_button(SHOW_START_ROLLING, mode == RANDOM_FOR_MAGICAL)]


def loot_button(event_id, shown):
    return _event(event_id, bytes([int(bool(shown))]))


def settings(group):
    """The group's loot settings (created with defaults)."""
    if not hasattr(group, "loot"):
        group.loot = {"mode": FREE_FOR_ALL, "ml": group.leader.char_id, "rarity": DEFAULT_RARITY,
                      "split": False, "cash": False, "turn": 0}
    return group.loot


def parse_set_mode(data):
    """0xb6 -> (master looter eid, mode, rarity string, split coin, cash loot)."""
    ml, mode = struct.unpack_from("<Qi", data, 0)
    rarity, pos = _rstr(data, 12)
    split, cash = (data[pos], data[pos + 1]) if len(data) >= pos + 2 else (0, 0)
    return ml, mode, rarity, bool(split), bool(cash)


def mode_message(group):
    s = settings(group)
    return _event(0x6C8, struct.pack("<Qi", s["ml"], s["mode"]) + _w(s["rarity"])
                  + struct.pack("<BB", s["split"], s["cash"]))


def you_master_looter():
    return _event(0x6A5)


def other_master_looter(eid):
    return _event(0x6CC, struct.pack("<Q", eid))


def other_turn(eid):
    return _event(0x6CD, struct.pack("<Q", eid))


def looted(member, item, qty):
    return _event(0x696, struct.pack("<Q", member.char_id) + _w(item) + struct.pack("<i", qty))


def roll_popup(item_bytes, next_name="", first=True, seconds=ROLL_SECONDS, need_allowed=True):
    return _event(0x6AB if first else 0x6AD, _w(next_name) + struct.pack("<iiiB", 0, 0, seconds, need_allowed)
                  + item_bytes)


def your_roll(roll, need):
    return _event(0x6AF, struct.pack("<iB", roll, need))


def roll_result(winner, need, roll):
    return _event(0x6AE, _w(winner) + struct.pack("<Bi", need, roll))


def rolls_over():
    return _event(0x6B0)


def hide_popup():
    return _event(0x6AC)


def coin_share(member, text):
    """0x6ce {eid64 member, wstr amount}: "CashLootShare(Yours)" coin split line."""
    return _event(0x6CE, struct.pack("<Q", member.char_id) + _w(text))


def coin_text(copper):
    """12345 -> "1 gold, 23 silver, 45 copper" (100 copper a silver, 100 silver a gold,
    100 gold a platinum)."""
    parts = []
    for name, size in (("platinum", 1000000), ("gold", 10000), ("silver", 100), ("copper", 1)):
        n, copper = divmod(copper, size)
        if n:
            parts.append(f"{n} {name}")
    return ", ".join(parts) or "0 copper"


def split_coin(total, n):
    """Shares of total for n members: equal parts, the remainder to the first (the looter)."""
    share, rest = divmod(total, max(1, n))
    return [share + rest] + [share] * (n - 1)


def threshold(rarity):
    """Index of a rarity string (unknown -> Uncommon)."""
    return RARITIES.index(rarity) if rarity in RARITIES else 4


def qualifies(item_rarity, rarity):
    """True when an item (rarity index, 0 best) is at or above the group's threshold."""
    return item_rarity <= threshold(rarity)


def next_turn(group):
    """Round robin: the member whose turn it is, then advance."""
    s = settings(group)
    member = group.members[s["turn"] % len(group.members)]
    s["turn"] = (s["turn"] + 1) % max(1, len(group.members))
    return member


def may_loot(player, npc):
    """None when player may loot the corpse, else a 0x0e result code. The killer's group
    shares the corpse by its loot mode; a corpse nobody killed (or a solo kill) belongs to
    the killer only."""
    killer = getattr(npc, "killer", None)
    if killer is None or killer is player:
        g = getattr(player, "group", None)
        if killer is None or g is None:
            return None
    g = getattr(killer, "group", None)
    if g is None or player not in g.members:
        return NO_PERMISSION
    s = settings(g)
    if getattr(npc, "open_to_group", False) or s["mode"] in (FREE_FOR_ALL, RANDOM_FOR_MAGICAL, NEED_BEFORE_GREED):
        return None
    if s["mode"] == ROUND_ROBIN:
        owner = getattr(npc, "loot_owner", None)
        return None if owner is None or owner is player else NO_PERMISSION
    return None if player.char_id == s["ml"] else NO_PERMISSION        # master looter


def resolve(answers):
    """answers: {name: None (pass) or (need, roll)} -> (winner, need, roll), or None when
    everyone passed. Need beats greed, then the higher roll (1-100, rolled on answering)."""
    rolls = {n: a for n, a in answers.items() if a is not None}
    if not rolls:
        return None
    name, (need, roll) = max(rolls.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    return name, need, roll
