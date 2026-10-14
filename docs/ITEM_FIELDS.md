# MsgSingleItemInfo (0x197): tooltip and icon fields

> **Verified live (2026-10-12):** field 94 = 1 removes the red icon background; 106 = 100 shows "Durability: 100%" in green (−1 hides it); 74 sets the type line (3 = a plain item); 77/78/82/84 give weapon damage, speed and skill. Implemented in `server/zone.py` (`item_equip_fields`, `damage_encoding`) from `server/content/items.json`. Because the shown damage is symmetric around the integer field 77, a range whose ends sum to an even number shows one end off by one.


Static analysis of VGClient.exe. Tooltip builder: FUN_006b6ad0. Parser: FUN_00514ff0 (msg -> item). Icon slot: SGOUIItemSlot (ctor FUN_00c54710, draw FUN_00c54150).
[O] = observed in code. [I] = inferred.

## Why every icon is red
- SGOUIItemSlot loads "VgrdIconTintRed" into slot+0x9ac (FUN_00c54710). FUN_00c54150 draws it when `slot+0xa74 == 0 && slot+0x988 != 0`, i.e. a slot that holds an item but is not marked usable. [O]
- slot+0xa74 is set only by FUN_00c53840(byte). The item-slot updater FUN_006ae340 calls it with **item+0x668**. [O]
- item+0x668 = `(msg+0x5a3 != 0)` = **wire field 94** (u8). [O] We send 0, so every icon is tinted red.
- **Fix: field 94 = 1.**
- The server can change it later with zone event **0x1da** (FUN_00500b40: finds the item by handle +0x650 and sets +0x668 = bool, then refreshes the slot). [O] The payload layout (handle, bool) is [I].
- Neither durability, level, nor class feeds the icon tint. The client only uses them to colour tooltip text. [O]

## Why the tooltip says "Durability: 0%"
- FUN_006abf00: if item+0x664 == -1, the durability line is hidden. Otherwise pct = item+0x664 / FUN_00d07650() * 100, and FUN_00d07650 always returns 100. So **+0x664 is the durability percentage (current, 0..100), with max fixed at 100**. [O]
- item+0x664 = msg 0x5c0 = **wire field 106** (i32). [O]
- Colour bands: >90 green, >65 blue, >45 white, >25 yellow, >15 orange, >0 red, <=0 purple. [O]
- **Fix: field 106 = 100** (or -1 to hide the line).
- Event 0x1dc (FUN_00508dc0) updates +0x664 and +0x668 together with damage, AC, and level. [O]

## Second gotcha: field 100 must be 0xFF
item+0x58b = **field 100** (u8). The client treats any value other than 0xFF as a **graft** [O]:
- FUN_006b2920: the type text becomes "Graft".
- The slot line uses graft slot names (FUN_006ab760: Brain/Arms/Legs/...).
- FUN_006b10c0 prints "Graft Level: N" when the value is < 12.

Normal items need **field 100 = 255**. With 255 the client prints the slot line (FUN_006b2da0) and "Item Level: N" instead.

## Field table (wire field -> item offset)

| wire | type | item off | meaning (tooltip function) | good value (1H sword) | tag |
|---|---|---|---|---|---|
| 2 | wstr | +0x04 | name | "Rusty Sword" | O |
| 3 | wstr | +0x20 | description, appended when non-empty (checks size at +0x34) | text | O |
| 4 | wstr | +0x6f0 | "Made by: %s" crafter name (FUN_006af300). Shown as "Vehicle name:" when field 48 == 3 | "" | O |
| 8 | i32 | +0x5c | default equip slot. The slot line lists this plus the mask (FUN_006b2da0). Also feeds "Armor" type text | 28 (PRIMARYHAND) | O |
| 9 | i32 | +0x60 | race mask (& 0x77f7fc). 0 or full = no "Required Race" line (FUN_006b16a0) | 0 | O |
| 11,12 | i32 | +0x68,+0x6c | class mask (64 bits). "Required Class" is shown only when the mask is neither 0 nor the full class set for that item type (FUN_006b1270, mask from FUN_006ab450; for weapons the full set is 0x1a78c4b4 / 0x7000) | 0, 0 | O |
| 13 | i32 | +0x70 | icon | 443 | O |
| 17 | i32 | +0x1c0 | count of 0x60-byte stat/bonus records (stats list FUN_006b5d80 via +0x640). Record layout not decoded | 0 | O |
| 18-21 | i32 | +0x78..+0x84 | allowed-slot bitmask. Slots 28+29 print "Either Hand". All zero with field 8 < 0 prints "cannot be deconstructed" | bits 28,29 | O |
| 22-25 | wstr | +0x88.. | "Required Flags:" list, shown when any is non-empty (FUN_006ae6b0) | "" | O |
| 33 | i32 | +0x710 | charges remaining (FUN_006b0d30) | 0 | O |
| 34 | i32 | +0x1d0 | max charges. > 0 prints "Charges: f33/f34" | 0 | O |
| 35 | i32 | +0x1d4 | count of "Chance on Hit" effects (strings 36-47, % at +0x2d4..) | 0 | O |
| 48 | i32 | +0x2e0 | 3 = vehicle (changes "Made by") | 0 | O |
| 49 | i32 | +0x2e4 | count of "Activated Ability" entries (strings 50-58) | 0 | O |
| 59 | i32 | +0x3e4 | count of "Equipped Effect" entries (strings 60-68) | 0 | O |
| 69 | wstr | +0x4e4 | extra raw text appended to the tooltip (FUN_006ae620) | "" | O |
| 74 | i32 | +0x524 | **item type**: 0 shield/parry, 1 weapon, 2 crafting tool, 4 armor, 5/6/15 clothing, 7 crafting component, 9/21 ranged, 10/13 jewelry, 11/12/18 container, 14 focus, 16 harvest tool, 17 harvest pack, 19 instrument, 20 ammo, 22 crafting resource, 27 attachment (FUN_006b2920). Also selects the level type (FUN_00d01550: 0 = Adventuring, 1 = Crafting, 2 = Diplomacy, 3 = none) | 1 | O |
| 75 | i32 | +0x528 | debug-only comparison with float +0x530 | 0 | O |
| 76 | i32 | +0x52c | **required level / item level**. "Required Level: N Adventuring" (red if player level < N and N != 1); "Item Level: N" | 1 | O |
| 77 | i32 | +0x534/+0x538 | damage base v. min = (int)(v - v*f78/255), max = (int)(v + v*f78/255) | 8 | O |
| 78 | u8 | - | damage variance (0..255), applied to 77 and 79 | 95 (gives 5-10) | O |
| 79 | i32 | +0x540/+0x544 | second damage range. Shown as " (min-max)" only if it differs from 77's min | 8 (same as 77) | O |
| 80 | i32 | +0x53c | used by harvesting tools (FUN_006aba00) | 0 | O |
| 81 | f32 | +0x548 | unknown. Client forces 1.0 if <= 0 | 1.0 | O/I |
| 82 | f32 | +0x54c | **weapon delay / "Speed"** in seconds. DPS = ((min+max)/2) / delay | 2.0 | O |
| 84 | i32 | +0x554 | **weapon skill** (stat id, FUN_00d03670): 198 One-handed Slashing, 227 Longsword, 43 Short Sword, 109 One-handed Blunt, 17 One-handed Piercing, 250 Dagger and Knife, 84 Martial Sword (adds a parry line). Printed as the weapon type text; some ids add a "Weapon Bonus" line | 198 | O |
| 85 | i32 | +0x558 | **Armor Class**. Shown for type 0/4 or whenever non-zero (FUN_006afbe0) | 0 | O |
| 87 | i32 | +0x560 | armor class name (0 Medium, 1-2 Light, 3 Heavy, 4-5 Shield). For type 0, 5 = parrying item (Parry instead of Block) | 0 | O |
| 88 | i32 | +0x564 | ranged weapon kind name (types 9/21) | 0 | O |
| 89,90 | f32 | +0x568/+0x56c | ranged min/max range (types 9/21) | 0 | O |
| 91 | u8 | +0x714 | crafted quality grade. Shown as "Quality: Grade N" unless 0 or 1 | 0 | O |
| 94 | u8 | +0x668 (bool) | **usable by you. 0 = red icon tint** | **1** | O |
| 95 | i32 | +0x578 | required skill id (name) | 0 | O |
| 96 | i32 | +0x57c | required skill value. > 0 prints "Required Skill: N <skill95>" | 0 | O |
| 97 | i32 | +0x580 | tool tier (types 2/16) | 0 | O |
| 99 | u8 | +0x61c | rarity / name colour (0..11; colour table FUN_006d0ee0, RGB): **8 white Mundane, 7 green Common, 6 (5) blue Uncommon, 4 yellow Rare, 2 (3) orange Heroic, 10 purple Fabled, 1 red Legendary**, 0 gold 0xf3ce4b, 9 bronze 0xc89449, 11 grey. The broker's rarity filter offers 8, 7, 6, 4, 2, 10, 1 (Mundane → Legendary). items.json `rarity` names map to it (`grouploot.RARITY_WIRE`; default mundane). Also scales Block/Parry chance (0 x1.6, 1 x1.4, 2 x1.2, 6 x0.8, 7 x0.6, 8 x0.5, 9 x1.8, 10 x1.3, others x1.0) | 8 | O |
| 100 | u8 | +0x58b | **graft slot. 0xFF = not a graft** | **255** | O |
| 102 | u8 | +0x589 | flags (FUN_006ab640): 1 No Trade, 2 Unique, 4 No Rent, 8 Soulbound, 0x10 No Drop On Equip, 0x20 Quest, 0x40 No Sell, 0x80 Bind On Equip. Bit 3 also drives a slot overlay (FUN_00c53870) | 0 | O |
| 103 | u8 | +0x58a | flag byte 2. Bit 8 clear shows "(unbindable)" after Soulbound [I] | 0 | I |
| 106 | i32 | +0x664 | **durability %** (0..100, max fixed 100). -1 hides the line | **100** | O |
| 107 | i32 | +0x5e4 | passed to FUN_005009d0 -> slot FUN_00c53f30 (probably cooldown/timer) | 0 | I |
| 112 | bool | +0x5f0 | if set and flag 0x10 is set, flags become No Trade (Soulbound path) | 0 | O |
| 114 | bool | +0x649 | adds one extra tooltip line | 0 | O |
| 115-117 | wstr | +0x590.. | "Statements Unlocked" (diplomacy) | "" | O |
| 118 | i32 | +0x644 | 2 = "Gold Membership Required" (field 113 = unlocked) | 0 | O |

Not present in the tooltip: weight, price, and a "Lore" flag. The closest flag to Lore is "Unique" (bit 2 of field 102). [O]

**Item modifiers (verified live 2026-10-13).** The stat/bonus list comes from MsgItemMod records appended after the item record, counted by **field 17** (parser FUN_005147c0, schema FUN_004f6270, tooltip FUN_006b5d80 -> FUN_006afce0, mod names FUN_00d02df0). Each record on the wire: `i32 stat id, i32 value, i32 max value, i32 mod type, i32 0, u8 0 (1 = the off-hand set), 4 x i32 0, wstr, wstr` (41 bytes with empty strings). A record whose max value is 0 is skipped; when max differs from value a range is printed.
- Mod type **0** = "+N <stat name>" for the stat id (Strength, Dexterity, ...; MsgStatUpdate ids, `vgmsg.STAT_IDS`).
- Other types are ratings named by FUN_00d02df0 (`vgmsg.MOD_TYPES`): 2 Tool Accuracy, 3 Tool Effectiveness, 5 Healing Focus, 6 Spell Damage Focus, 7-10 Accuracy/Damage/Evasion/Mitigation Rating, 0x1a-0x23 melee/ranged/spell ratings, 0x25-0x27 Endurance/Energy/Health Regeneration ("per 6 seconds"), 0x28/0x29 Melee/Spell Haste, 0x2a Mount Speed (Ground), 0x2c Armor Class, 0x2d Weapon Damage, 0x2e Weapon Delay, 0x30 Debate Effectiveness, 0x34-0x37 critical hit ratings, 0x43 Harvesting Speed, 0x48-0x4a heal mods, 0x4f Global Recovery Haste, 0x50/0x51 critical hit evasion/mitigation, 0x55 AOE Mitigation, 0x59 Critical Damage Bonus. Type 1 is a crafting action-point cost decrease and 0x2f an instrument mod.
- items.json: `"stats": {"dexterity": 4}` and `"mods": {"Armor Class": 8}`. The Forester's Cloak tooltip shows "+4 Dexterity, +2 Wisdom, +2 Health Regeneration per 6 seconds, +8 Armor Class". Equipped items' `stats` are added to the character's attributes (`zone.apply_gear_stats`; Dexterity 30 -> 37 with the boots and cloak); of the mods, **Armor Class** (plus each item's base `armor`) reduces NPC melee damage by x 100 / (100 + AC) (`combat.mitigate`, placeholder curve) and **Health Regeneration** adds its value per 6 seconds to out-of-combat regeneration; the other mods are display-only for now.

## Recipe: normal undamaged 1H sword, damage 5-10, delay 2.0, level 1, all classes
Keep the current base fields (f1 id, f2 name, f3 desc, f6 = 1, f7 = -1, f13 icon, f15 = -1, f16 slot, f71 handle, f92 = 0) and set:
- f8 = 28; f18 = 0x30000000 (bits 28,29), f19-f21 = 0
- f9 = 0, f11 = 0, f12 = 0 (all races/classes)
- f74 = 1 (weapon)
- f76 = 1 (level 1)
- f77 = 8, f78 = 95, f79 = 8 (client computes 5-10; 8*95/255 = 2.98 -> (int)5.02 = 5, (int)10.98 = 10)
- f81 = 1.0, f82 = 2.0 (Speed 2.00, DPS 3.50, see note)
- f84 = 198 (One-handed Slashing)
- f94 = 1 (removes red tint)
- f99 = 1
- f100 = 255 (not a graft)
- f102 = 0
- f106 = 100 (Durability 100%, green)
- everything else 0 / empty

Note: DPS uses integer average ((5+10)/2 = 7 with integer division) / 2.0 = 3.50. [O]
