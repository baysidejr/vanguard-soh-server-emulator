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
# Field map from the handler FUN_005e8260 (see docs/MSGSCORE.md).
SCORE_FIELDS = {
    # 0-4: bind (respawn) point, shown only as strBindLocationSelf.
    "bind_x": 0, "bind_y": 1, "bind_z": 2, "bind_chunk_x": 3, "bind_chunk_y": 4,
    "race": 5, "gender": 6, "adv_class": 7,
    "adv_level": 8, "adv_exp": 9, "adv_rest_exp": 10,
    "craft_class": 11, "craft_level": 12, "craft_exp": 13, "craft_rest_exp": 14,
    "dip_class": 15, "dip_level": 16, "dip_exp": 17, "dip_rest_exp": 18,
    "adv_exp_debt_frac": 19, "adv_exp_recovery_frac": 20,
    "adv_exp_amount": 21, "adv_exp_amount_next": 22,
    "harvest_class": 23, "harvest_level": 24,
    "aa_points": 25, "aa_spent": 26, "aa_exp": 27,
    "movement_mode": 28,          # 1 walking, 2 running
    "move_speed": 29,
    "is_gm": 30, "is_dev": 31, "is_test": 32, "invulnerable": 33, "can_aggro": 34,
    "adv_exp_frac": 35, "adv_rest_frac": 36, "craft_exp_frac": 37, "craft_rest_frac": 38,
    "dip_exp_frac": 39, "dip_rest_frac": 40, "aa_exp_frac": 41,
    "armor_class": 42, "craft_trade": 43,
    # Attack block: the window shows -field (send negative values).
    "attack": 45, "attack_max": 46, "offhand_frac": 47, "spell_attack": 50, "ranged": 52,
    "defense_input": 63,          # AdvDefense = 100 * (10 * x) ** 0.7
    "melee_mitigation": 64, "spell_mitigation": 65,
    "melee_evasion": 69, "spell_evasion": 70, "block": 71, "dodge": 72, "parry": 73,
    "energy_regen": 74, "flurry_resist": 75, "rampage_resist": 76,
    "energy_regen_s": 102, "hp_regen_s": 103, "endurance_regen_s": 104,
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
    # Breath: the HUD's Breath bar (StatusBreathSelf) shows while current < max
    # (FUN_005763b0 sets bIsDrowning = current != max).
    "breath": 0x50,
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
    "icon": 13, "capacity": 14, "container": 15, "slot": 16,
    # 71 (item +0x650): the item's handle; equip/move messages look items up by
    # it (FUN_004fa970) and a bag's slots are InventoryContainerID_<handle>.
    "handle": 71,
    "location": 92, "quality": 99,
}


# Equipment slot ids (FUN_0050cc10, the slot-tag table the paper doll uses).
EQUIP_SLOTS = {
    "HEAD": 0, "EYES": 1, "FACE": 2, "NECK": 3, "LEFTEAR": 4, "RIGHTEAR": 5, "CHEST": 6,
    "CLOAK": 7, "LEFTSHOULDER": 8, "RIGHTSHOULDER": 9, "LEFTARM": 10, "RIGHTARM": 11,
    "CONTAINER1": 12, "LEFTWRIST": 15, "RIGHTWRIST": 16, "LEFTFINGER": 19,
    "RIGHTFINGER": 20, "WAIST": 21, "FEET": 26, "CONTAINER2": 27, "PRIMARYHAND": 28,
    "SECONDARYHAND": 29, "LEGS": 32, "HANDS": 33, "WRISTS": 34, "SHOULDERS": 35,
    "TWOHANDS": 36, "CONTAINER3": 38, "MOUNT": 39, "RANGED": 42, "AMMO": 43,
    "HARVESTTOOL": 0x35,
    # Crafting gear (FUN_0050cc10 tag table): 66 tool, 67-69 the three toolbelts.
    "TACKLEBOX": 54, "CRA_HEAD": 55, "CRA_APRON": 56, "CRA_CHEST": 57, "CRA_LEGS": 58, "CRA_HANDS": 59,
    "CRA_FEET": 60, "CRA_TOOL": 66, "CRA_WAIST1": 67, "CRA_WAIST2": 68, "CRA_WAIST3": 69,
}


# Items inside a bag keep one int "slot": BAG_SLOT_BASE + bag handle * 100 + slot in the bag
# (the main grid uses 0..49), so the server's 5-element item tuples need no container field.
BAG_SLOT_BASE = 1000000


def bag_slot(container, n):
    return n if container == -1 else BAG_SLOT_BASE + container * 100 + n


def split_slot(slot):
    """(container, slot in it): container -1 = the main grid."""
    return (-1, slot) if slot is None or slot < BAG_SLOT_BASE else divmod(slot - BAG_SLOT_BASE, 100)


# Item modifiers ("+5 Strength", "+12 Armor Class"): MsgItemMod records appended after the
# item record, counted by item field 17 (parser FUN_005147c0, schema FUN_004f6270, tooltip
# FUN_006b5d80 -> FUN_006afce0, names FUN_00d02df0). Wire: i32 stat id, i32 value, i32 max
# value (= value: a range is printed when they differ), i32 mod type, i32 0, u8 0 (1 = the
# off-hand set), 4 x i32 0, wstr, wstr. A record with max value 0 is not shown.
MOD_STAT = 0               # "+N <stat name>" by stat id (attributes); 1 = crafting AP cost, 0x2f = instrument
MOD_TYPES = {
    "Tool Accuracy": 2, "Tool Effectiveness": 3, "Healing Focus": 5, "Spell Damage Focus": 6,
    "Accuracy Rating": 7, "Damage Rating": 8, "Evasion Rating": 9, "Mitigation Rating": 10,
    "Melee Accuracy Rating": 0x1A, "Melee Damage Rating": 0x1B, "Melee Evasion Rating": 0x1C,
    "Melee Mitigation Rating": 0x1D, "Ranged Accuracy Rating": 0x1E, "Ranged Damage Rating": 0x1F,
    "Spell Accuracy Rating": 0x20, "Spell Damage Rating": 0x21, "Spell Evasion Rating": 0x22,
    "Spell Mitigation Rating": 0x23, "Mount Stability": 0x24, "Endurance Regeneration": 0x25,
    "Energy Regeneration": 0x26, "Health Regeneration": 0x27, "Melee Haste": 0x28,
    "Spell Haste": 0x29, "Mount Speed (Ground)": 0x2A, "Armor Class": 0x2C, "Weapon Damage": 0x2D,
    "Weapon Delay": 0x2E, "Debate Effectiveness": 0x30, "General Critical Hit Rating": 0x34,
    "Melee Critical Hit Rating": 0x35, "Ranged Critical Hit Rating": 0x36,
    "Spell Critical Hit Rating": 0x37, "Harvesting Speed": 0x43, "Heal Critical Chance": 0x48,
    "Heal Effectiveness": 0x4A, "Global Recovery Haste": 0x4F, "Critical Hit Evasion": 0x50,
    "Critical Hit Mitigation": 0x51, "AOE Mitigation": 0x55, "Critical Damage Bonus": 0x59,
}


def item_mod(mod_type, value, stat=0):
    return pack("iiiiib" + "iiii" + "ww", (stat, value, value, mod_type, 0, 0, 0, 0, 0, 0, "", ""))


def item_mods(stats=None, mods=None):
    """MsgItemMod records for items.json "stats" {attribute: n} and "mods" {mod name: n}."""
    out = [item_mod(MOD_STAT, int(v), STAT_IDS[k]) for k, v in (stats or {}).items() if k in STAT_IDS]
    out += [item_mod(MOD_TYPES[k], int(v)) for k, v in (mods or {}).items() if k in MOD_TYPES]
    return out


def inventory_item(item_id, name, slot, icon=443, quantity=1, description="",
                   container=-1, quality=1, equip_slot=-1, default_slot=-1, allowed_slots=(),
                   raw=None, mods=None):
    """An item in a bag: equip slot -1, container -1 = the main grid
    (gamevar InventoryContainerID_-1, 50 slots), slot 0..49. Icon is a
    number formatted %05d in the client icon map (443 = the client's fallback). A slot of
    BAG_SLOT_BASE or more is a slot inside a bag (bag_slot)."""
    f = ITEM_FIELDS
    if container == -1:
        container, slot = split_slot(slot)
    return item_info({f["id"]: item_id, f["name"]: name, f["description"]: description,
                      f["quantity"]: quantity, f["equip_slot"]: equip_slot, f["icon"]: icon,
                      f["container"]: container, f["slot"]: slot, 81: 1.0,
                      f["handle"]: item_id,
                      f["quality"]: quality,
                      # Field 8 (item +0x5c): the slot right-click equips to (-1 = none).
                      # Fields 18-21 (+0x78..+0x84): bit mask of allowed equip slots
                      # (FUN_004fd590 tests bit `slot`); right-click needs the default set.
                      8: default_slot, **slot_mask(allowed_slots),
                      # 94 usable (0 = red icon), 100 = 255 (not a graft), 106 durability %.
                      94: 1, 100: 255, 106: 100, **(raw or {}),
                      **({17: len(mods)} if mods else {})}) + b"".join(mods or [])


def slot_mask(slots):
    words = [0, 0, 0, 0]
    for s in slots:
        words[s // 32] |= 1 << (s % 32)
    return {18 + i: (w - (1 << 32) if w >= 1 << 31 else w) for i, w in enumerate(words)}


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


# MsgAbilityInfo (zone 0x215 adds an ability to the book; handler FUN_00432570,
# registrar FUN_0041e2b0). 68 fields; see docs/ABILITIES.md. The client sends
# zone event 0xd0 (i32 handle) when the player uses it.
ABILITY_TYPES = ("wwww" "i" "oob" "wwww" "iiiiiii" "ii" "ffff" "o" "w" "iii" "bbo" "ooo"
                 "bi" "oo" "i" + "o" * 8 + "bbb" + "i" * 7 + "o" + "i" * 8)
assert len(ABILITY_TYPES) == 68, len(ABILITY_TYPES)
ABILITY_BOOK_ADVENTURING, ABILITY_BOOK_DIPLOMACY, ABILITY_BOOK_GENERAL = 0, 2, 1


def ability_info(handle, ability_id, name, icon, description="", level=1, book=0,
                 type_text="Melee", cast=0.0, recovery=0.0, refresh=5.0, max_range=5,
                 flags=0, line=None, counter=False, rescue=False, raw=None):
    """flags (wire #8): 0x03 chain opener, 0x02 chain step / finisher (locked until a
    reaction opens it); line (#18): the ability line, ranks of one ability share it
    (default: the ability id)."""
    v = [0] * 68
    v[7] = flags
    v[17] = ability_id if line is None else line
    v[43] = int(counter)          # wire #44: counter ability (locked until a counter window)
    v[41] = int(rescue)           # wire #42: rescue ability (listed with the rescues, not locked)
    for n, t in enumerate(ABILITY_TYPES):
        if t == "w":
            v[n] = ""
    v[0], v[1], v[4] = name, description, handle
    v[9] = type_text
    v[12] = book
    v[18], v[19], v[20] = level, ability_id, icon
    v[21], v[22], v[23], v[24] = cast, recovery, refresh, 0.0
    v[29] = max_range
    v[30] = v[31] = 0xFF          # ability kind / song part: none
    v[36], v[37] = 0xFF, -1       # requirements: any
    v[50] = v[51] = 0xFF          # target type
    for n in range(60, 68):
        v[n] = -1                 # allowed combat forms: any
    for n, x in (raw or {}).items():
        v[n] = x                  # {value index (wire # - 1): value}
    return pack(ABILITY_TYPES, v)


# MsgHotkeyAdd (registrar FUN_00682aa0): one hotbar slot. Zone 0x54e = i32 count
# + records (replaces the bars), 0x54f = add one, 0x550 = {wstr bank, i32 slot}
# removes one. The client sends 0x54b (same layout) / 0x54c when the player
# changes a slot. Bank "m_wb" is the main bar (12 slots per page).
HOTKEY_TYPES = "wiiiwwi"


def hotkey(slot, ability_id=-1, item_instance=-1, bank="m_wb"):
    """An ability slot (ability_id = MsgAbilityInfo ability id) or an item slot."""
    return pack(HOTKEY_TYPES, [bank, slot, ability_id, item_instance, "", "", 0])


def hotkey_list(records):
    return struct.pack("<i", len(records)) + b"".join(records)
