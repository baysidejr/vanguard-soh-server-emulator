# MsgScore (zone event 0x3de): what each field means

Sources: registrar `FUN_005db5d0`, handler `FUN_005e8260`, and the helpers the handler calls:
`FUN_00557b10` (attack), `FUN_00559250` (defense), `FUN_00572790` (focus), `FUN_00572500` (AC), `FUN_005582d0` (PCAdv* stats, which takes a pointer to the whole message), plus `FUN_00d02c70`.

How I worked out the stack offsets: inside `FUN_005e8260` the message object sits at `[ESP+0x74]` whenever no arguments are pushed. The exception-state writes `[ESP+0x330]` are always at that depth (190 of them), so I used them as anchors. Every field read was translated with *field offset = ESP disp − 0x74 − 4·(pending pushes)*.

Ghidra's pseudocode stack-variable names are 8 bytes off in the second half of the function, so I used the asm, not the pseudocode.

**Evidence levels:**
- **O** = observed: the read of that offset is in the asm, and it feeds a named game variable or helper.
- **P** = also confirmed by the in-game probe.
- **I** = inferred meaning.

The probe filled fields 35 and up with their own index and confirms several formulas exactly:
- Defense 9110 = 100·(10·63)^0.7, so field 63.
- Attack −45.00 = −field 45.
- Ranged −52.00 = −field 52.
- The two icons show 75 and 76 (flurry and rampage resistance).

Corrections to the "already known" list:
- Fields 0–4 are used only to build **strBindLocationSelf** ("<chunk name> (x, y, z)") and a debug string. They are the *bind (respawn) location*, not the live position.
- Field 10 is adventuring **rest XP**, not class.
- Field 14 is **crafting rest XP**. Harvesting level is field 24.
- Field 21 is **AdvExpAmountSelf** and field 22 is **AdvExpAmountNextLevel**.

Game variables shown as "bar(max N)" are `SGOUIGameVarDataStatusInfo{max=N, value=FUN_00abf240(x)}`, meaning value = x rounded, on a scale of 0..N.

## Field table

| wire | type | struct off | game var(s) / meaning | formula / notes | ev | UI |
|---|---|---|---|---|---|---|
| 0 | f32 | 0x14 | bind location x | "%f" inside strBindLocationSelf; also a debug string at UI+0xfc ("ChunkX: .. x,y,z: (..)") | O | strBindLocationSelf: no XML user found |
| 1 | f32 | 0x18 | bind location y | same | O | |
| 2 | f32 | 0x1c | bind location z | same | O | |
| 3 | i32 | 0x20 | bind chunk X | `FUN_00b70e80(chunkX, chunkY)` → chunk/area name, the prefix of strBindLocationSelf | O | |
| 4 | i32 | 0x24 | bind chunk Y | same | O | |
| 5 | u8 | 0x28 | race id | strRaceSelf = raceName(`FUN_00d02540`). Also used in str{Adv,Cra,Har,Dip}LevelRaceClass | O | VGUICharacter (inside the *LevelRaceClass strings) |
| 6 | u8 | 0x29 | gender id | strGenderSelf = `FUN_00d02a80`(g) | O | (no XML) |
| 7 | u8 | 0x2a | adventuring class id | strAdvClassSelf = `FUN_00d07120`(c); nAdventureClassType = `FUN_00d00730`(c); class 0x0f → player+0x8a8=1, class 0x1b → player+0x8a8=2 (`0x5ea64f`) | O | PlayerStatus, Pet, EncounterDisplay |
| 8 | i32 | 0x2c | adventuring level | nAdvLevelSelf; also `[DAT_01463a40+0xc]`; strAdvLevelRaceClass = "Level %i - %s %s"(lvl, race, class). Other helpers read nAdvLevelSelf back (AC mitigation, focus potential) | O | PlayerStatus, Character |
| 9 | i32 | 0x30 | adventuring XP (amount) | nAdvExpSelf | O | (no XML) |
| 10 | i32 | 0x34 | adventuring rest XP | nAdvRestExpSelf | O | (no XML) |
| 11 | u8 | 0x38 | crafting class id | strCraftTitleSelf = `FUN_00d07120`(id) | O | (no XML) |
| 12 | i32 | 0x3c | crafting level | nCraftLevelSelf; strCraLevelRaceClass = "Level %i - %s Crafter" if field 43 is 0xff, else "Level %i - %s %s"(lvl, race, tradeName(field 43)) | O | Character |
| 13 | i32 | 0x40 | crafting XP | nCraftExpSelf | O | |
| 14 | i32 | 0x44 | crafting rest XP | nCraftRestExpSelf | O | |
| 15 | u8 | 0x48 | diplomacy class id | strDiplomatClassSelf = `FUN_00d07120`(id) | O | |
| 16 | i32 | 0x4c | diplomacy level | nDipLevelSelf; strDipLevelRaceClass = "Level %i - %s Diplomat"(lvl, race) | O | Character |
| 17 | i32 | 0x50 | diplomacy XP | nDipExpSelf | O | |
| 18 | i32 | 0x54 | diplomacy rest XP | nDipRestExpSelf | O | |
| 19 | f32 | 0x9c | adventuring XP **debt** fraction | AdvExpDebtPctSelf = bar(max 2000) of clamp01(field 19 + field 35)·2000; bRestGTDebt = field 36 > field 19 | O/I | Character, PlayerStatus |
| 20 | f32 | 0xa0 | adventuring XP **recovery** fraction | AdvExpRecoveryPctSelf = bar(2000) of (field 35 + field 20)·2000 | O/I | PlayerStatus |
| 21 | i32 | 0x60 | XP amount (current) | AdvExpAmountSelf | O | PlayerStatus |
| 22 | i32 | 0x64 | XP amount for next level | AdvExpAmountNextLevel | O | PlayerStatus |
| 23 | i32 | 0x58 | harvesting class id | strHarvClassSelf = `FUN_00d07120`(id); class name in strHarLevelRaceClass ("Skill %i - %s %s", where the skill number comes from the client skill table id 0xc4, not this message) | O | Character |
| 24 | i32 | 0x5c | harvesting level | nHarvLevelSelf; also `[DAT_0146393c+0xf0]` | O | |
| 25 | i32 | 0x68 | AA points available | nAAPointsAvailableSelf | O | AlternateAdvancementWnd |
| 26 | i32 | 0x6c | AA points spent | nAAPointsSpentSelf | O | AlternateAdvancementWnd |
| 27 | i32 | 0x70 | AA XP | nAAExpSelf | O | |
| 28 | u8 | 0x74 | movement mode | strPositionSelf = `FUN_00d02c70`: 1="walking", 2="running", else "UNKNOWN" | O | (no XML) |
| 29 | f32 | 0x78 | movement speed | fMovementSpeedSelf (raw); fMovementSpeedSelfPct = "%.2f" of field 29·0.18018018 (= field 29/5.55) | O | Character |
| 30 | bool | 0x7c | is GM | bIsGMSelf | O | |
| 31 | bool | 0x7d | is Dev | bIsDevSelf; also passed to `FUN_00b70c00` | O | |
| 32 | bool | 0x7e | is Test | bIsTestSelf | O | |
| 33 | bool | 0x7f | invulnerable | bIsInvulSelf (bHasAllAbilitiesSelf is always set to 0) | O | |
| 34 | bool | 0x80 | can be aggro'd | bCanBeAggrodOnSelf | O | |
| 35 | f32 | 0x84 | adventuring XP fraction 0..1 | AdvExpPctSelf = bar(2000) of field 35·2000; AdvExpPctSelf100 = "%.2f" of field 35·100 | O | Character, PlayerStatus (XP bar) |
| 36 | f32 | 0x88 | adventuring rest-XP fraction | AdvRestExpPctSelf = bar(2000) of field 36·2000; bRestGTDebt | O | Character, PlayerStatus |
| 37 | f32 | 0x8c | crafting XP fraction | CraftExpPctSelf = bar(100) of field 37·100 | O | Character |
| 38 | f32 | 0x90 | crafting rest-XP fraction | CraftRestExpPctSelf = bar(100) of field 38·100 | O | Character |
| 39 | f32 | 0x94 | diplomacy XP fraction | DipSkillPctSelf = bar(100) of field 39·100 | O | Character |
| 40 | f32 | 0x98 | diplomacy rest-XP fraction | DipRestExpPctSelf = bar(100) of field 40·100 | O | Character |
| 41 | f32 | 0xa4 | AA XP fraction | AAExpPctSelf = bar(500) of field 41·500; nAAExpPctSelf = int(field 41·100) | O | AlternateAdvancementWnd |
| 42 | i32 | 0xa8 | armor class | nArmorClass; `FUN_00572500`: AdvArmorClass="%i"; AdvACMeleeMitigation = K·AC/(120·lvl) soft-capped at K (K = `[DAT_01463978+0x78]`); AdvACSpellMitigation = 10·AC/(120·lvl) soft-capped at 10 | O | Character (nArmorClass) |
| 43 | u8 | 0xac | crafting trade | 0xff=none; tradeName=`FUN_00d05180`; CraTradeBlacksmith=(field 43==0), CraTradeArtificer=(==2), CraTradeOutfitter=(==4) | O | Character |
| 44 | u8 | 0xad | unknown | copied only to UI+0x264; not shown | O(store)/? | |
| 45 | f32 | 0xb0 | melee damage (min) | Simple mode: AdvMeleeAtk = "%.2f" of −field 45. Range mode: main = round(field 45·(1−field 47))..round(field 46·(1−field 48)) as "%d-%d" negated | O,P | Character "Attack" |
| 46 | f32 | 0xb4 | melee damage (max) | range mode only (see field 45) | O/I | |
| 47 | f32 | 0xb8 | off-hand share (of min) | bDualWielding = (field 47≠0) (range mode); simple mode: AdvMeleeAtkOffhand = "%.1f" of field 47·100 | O | Character (offhand row, shown when bDualWielding) |
| 48 | f32 | 0xbc | off-hand share (of max) | range mode: offhand = round(field 45·field 47)..round(field 46·field 48); DPS = (lo+hi)/2 ÷ weapon delay (or ·0.25) → AdvMeleeAutoAttackDPS / AdvMeleeOffhandAutoAttackDPS | O/I | |
| 49 | i32 | 0xc0 | melee accuracy | AdvMeleeAcc = "%i" of field 49 − 5 | O | (no XML) |
| 50 | f32 | 0xc4 | spell attack | AdvSpellAtk = "%.2f" of −field 50 | O | |
| 51 | i32 | 0xc8 | spell accuracy | AdvSpellAcc = field 51 − 5 | O | |
| 52 | f32 | 0xcc | ranged damage (min) | simple: AdvRangedAtk = "%.2f" of −field 52; range mode: "%d-%d" of round(field 52)..field 53 | O,P | Character "Ranged" |
| 53 | i32 | 0xd0 | ranged damage (max) | range mode only | O/I | |
| 54 | i32 | 0xd4 | ranged accuracy | AdvRangedAcc = field 54 − 5 | O | |
| 55 | f32 | 0xd8 | healing focus (100-based) | AdvHealingFocusBonus = "%.1f " of field 55 − 100 | O | |
| 56 | f32 | 0xdc | spell damage focus (all) | AdvSpellDamageFocusBonus = field 56 − 100 | O | |
| 57 | f32 | 0xe0 | fire focus | AdvSpellDamageFocusBonusFire = field 57 − 100 | O | |
| 58 | f32 | 0xe4 | cold focus | …BonusCold = field 58 − 100 | O | |
| 59 | f32 | 0xe8 | physical focus | …BonusPhysical = field 59 − 100 | O | |
| 60 | f32 | 0xec | mental focus | …BonusMental = field 60 − 100 | O | |
| 61 | f32 | 0xf0 | arcane focus | …BonusArcane = field 61 − 100 | O | |
| 62 | f32 | 0xf4 | spiritual focus | …BonusSpiritual = field 62 − 100 | O | |
| 63 | f32 | 0xf8 | defense rating input | **AdvDefense = "%.0f" of 100·(10·field 63)^0.7** (`FUN_00abf260` = pow, exponent 0.7) | O,P (63→9110) | Character "Defense" |
| 64 | f32 | 0xfc | melee mitigation fraction | AdvMitigationMelee = "%.2f%%" of field 64·100 | O | Character |
| 65 | f32 | 0x100 | spell mitigation fraction | AdvMitigationSpell = field 65·100 % | O | Character |
| 66 | f32 | 0x124 | AoE mitigation % | PCAdvAOEMitigation "%.2f%%" | O | Character |
| 67 | f32 | 0x128 | crit mitigation % | PCAdvCritMitigation | O | Character |
| 68 | f32 | 0x12c | crit evasion % | PCAdvCritEvasion | O | Character |
| 69 | f32 | 0x104 | melee evasion fraction | AdvEvasionMelee = field 69·100 % | O | Character |
| 70 | f32 | 0x108 | spell evasion fraction | AdvEvasionSpell = field 70·100 % | O | Character |
| 71 | f32 | 0x10c | block chance % | AdvBlockChance "%.2f%%" (raw) | O | Character |
| 72 | f32 | 0x110 | dodge chance % | AdvDodgeChance (raw) | O | Character |
| 73 | f32 | 0x114 | parry chance % | AdvParryChance (raw) | O | Character |
| 74 | f32 | 0x118 | energy regen/sec | EnergyRegenPerSecond "%.2f" | O | (no XML) |
| 75 | f32 | 0x11c | flurry resistance | AdvFlurryResistance / AdvFlurryResistanceMelee "%.2f"; AdvFlurryResistanceInt "%d" (int) | O,P (icon 75) | Character bottom icon |
| 76 | f32 | 0x120 | rampage resistance | AdvRampageResistance(/Melee) "%.2f"; AdvRampageResistanceInt "%d" | O,P (icon 76) | Character bottom icon |
| 77 | f32 | 0x130 | general crit chance % | PCAdvGeneralCriticalChance | O | Character |
| 78 | f32 | 0x134 | spell crit chance % | PCAdvSpellCriticalChance | O | Character |
| 79 | f32 | 0x138 | ranged crit chance % | PCAdvRangedCriticalChance | O | Character |
| 80 | f32 | 0x13c | melee crit chance % | PCAdvMeleeCriticalChance | O | Character |
| 81 | f32 | 0x148 | melee crit damage % | PCAdvMeleeCriticalDamage | O | Character |
| 82 | f32 | 0x140 | spell crit damage % | PCAdvSpellCriticalDamage | O | Character |
| 83 | f32 | 0x144 | ranged crit damage % | PCAdvRangedCriticalDamage | O | Character |
| 84 | f32 | 0x14c | strikethrough chance % | PCAdvStrikethroughChance | O | Character |
| 85 | f32 | 0x150 | strikethrough amount % | PCAdvStrikethroughAmount | O | Character |
| 86 | f32 | 0x154 | spell strikethrough chance % | PCAdvSpellStrikethroughChance | O | Character |
| 87 | f32 | 0x158 | spell strikethrough amount % | PCAdvSpellStrikethroughAmount | O | Character |
| 88 | f32 | 0x15c | crit heal chance % | PCAdvCriticalHealChance | O | Character |
| 89 | f32 | 0x160 | crit heal amount % | PCAdvCriticalHealAmount | O | Character |
| 90 | f32 | 0x164 | melee damage % (abilities) | PCAdvMeleeDamageAbil = field 90 + field 92; PCAdvMeleeDamage = field 94 + field 92 + field 90 | O | Character (PCAdvMeleeDamage) |
| 91 | f32 | 0x168 | ranged damage % (abilities) | PCAdvRangedDamageAbil = field 91 + field 92; PCAdvRangedDamage = field 95 + field 92 + field 91 | O | Character |
| 92 | f32 | 0x16c | general damage % (abilities) | PCAdvGeneralDamageAbil = field 92; added to every *Damage total | O | |
| 93 | f32 | 0x170 | spell damage % (abilities) | PCAdvSpellDamageAbil = field 93 + field 92; PCAdvSpellDamage = field 93 + field 97 + field 92 | O | Character |
| 94 | f32 | 0x174 | melee damage % (items) | PCAdvMeleeDamageItems | O | |
| 95 | f32 | 0x178 | ranged damage % (items) | PCAdvRangedDamageItems | O | |
| 96 | f32 | 0x17c | general damage % (items) | PCAdvGeneralDamageItems; PCAdvGeneralDamage = field 96 + field 92 | O | Character |
| 97 | f32 | 0x180 | spell damage % (items) | PCAdvSpellDamageItems | O | |
| 98 | f32 | 0x184 | general accuracy % | PCAdvGeneralAccuracy | O | Character |
| 99 | f32 | 0x188 | spell accuracy % | PCAdvSpellAccuracy | O | Character |
| 100 | f32 | 0x18c | melee accuracy % | PCAdvMeleeAccuracy | O | Character |
| 101 | f32 | 0x190 | ranged accuracy % | PCAdvRangedAccuracy | O | Character |
| 102 | f32 | 0x194 | energy regen /s | PCAdvEnergyRegen "%.2f/s" | O | Character |
| 103 | f32 | 0x198 | HP regen /s | PCAdvHPRegen "%.2f/s" | O | Character |
| 104 | f32 | 0x19c | endurance regen /s | PCAdvEnduranceRegen "%.2f/s" | O | Character |
| 105 | f32 | 0x1a0 | heal effectiveness % | PCAdvHealEffectivness | O | Character |
| 106 | f32 | 0x1a4 | global refresh haste % | PCAdvGlobalRefreshHaste | O | Character |
| 107 | f32 | 0x1a8 | spell haste % | PCAdvSpellHaste | O | Character |
| 108 | f32 | 0x1ac | melee haste % | PCAdvMeleeHaste | O | Character |
| 109 | f32 | 0x1b0 | spell refresh haste | PCAdvSpellRefreshHaste = "%.2f%%" of **−field 109** | O | Character |
| 110 | f32 | 0x1b4 | melee refresh haste | PCAdvMeleeRefreshHaste = **−field 110** | O | Character |

## Details on the computed values

- **Attack display mode** (`FUN_00557b10`) depends on the global flag `[DAT_01463a58+0x334]`.
  - When the flag is 0 (the probe case), the values are simple and negated: "−45.00".
  - When the flag is non-zero, the window shows min-max ranges ("%d-%d" of negated ints, or "0") and the DPS game variables. DPS divides by the delay of the equipped item in slot 0x1c or 0x1d (`FUN_004fac20`, item+0x54c). With no item it uses (lo+hi)·0.25 instead.
  - The negation suggests the server sends damage as negative health deltas. So send the attack, ranged, spell-attack and refresh-haste values (fields 45, 46, 50, 52, 109, 110) **negative** to display positive numbers. This is inferred.
- **Accuracy** fields 49, 51 and 54 are displayed as value − 5.
- **Focus fields 55–62** are 100-based multipliers (100 = +0.0). The other AdvSpellDamageFocus* and AdvHealingFocus* variables come from equipped items (`FUN_004faea0`) and from the level-based potential: lvl·10, or lvl·20 − 500 above level 50.
- **Spell attack** (field 50) and the **accuracy** values (fields 49, 51, 54) are set as game variables but have no gameVarLink in the XML I searched.
- **Variables that do not come from this message:**
  - strNameSelf and strNameFullSelf come from the local player name.
  - HarSkillPctSelf (bar max 500) and the "Skill %i" number come from the client skill table (`FUN_0055e410(0xc4,3)`).
  - The PCAdvRes* resists, the attributes (PCAdvStrength…), PCAdvHitpointsMax, PCAdvEnergyMax, PCAdvEnduranceMax and PCAdv*Focus in VGUICharacter.xml are not set by this handler. They must come from another message.

## Where the game variables are shown (XML under VGUIAssets/Shells/Default/Windows)

| Window | Game variables from MsgScore |
|---|---|
| **VGUICharacter.xml** | strNameFullSelf, the four strXxxLevelRaceClass strings, the CraTrade* toggles, fMovementSpeedSelfPct, the XP/rest/debt bars for every sphere, nArmorClass, AdvDefense, AdvMitigation*/Evasion*/Block/Dodge/Parry, AdvFlurry/RampageResistanceInt (bottom icons), bDualWielding, AdvMeleeAtk(+Offhand), AdvRangedAtk, and all 53 PCAdv* links (crit, strikethrough, damage, accuracy, regen, haste, AOE/crit mitigation) |
| **VGUIPlayerStatus.xml** (HUD player bar) | strNameSelf, strAdvClassSelf, nAdvLevelSelf, AdvExpPctSelf, AdvExpPctSelf100, AdvExpAmountSelf, AdvExpAmountNextLevel, AdvRestExpPctSelf, AdvExpDebtPctSelf, AdvExpRecoveryPctSelf, bRestGTDebt |
| **VGUIAlternateAdvancementWnd.xml** | nAAPointsAvailableSelf, nAAPointsSpentSelf, AAExpPctSelf, nAAExpPctSelf |
| **VGUIPet.xml, VGUIEncounterDisplay.xml** | strAdvClassSelf |
| **VGUIMainBar.xml, VGUIParley.xml** | strNameSelf |

These variables are set but no XML file links to them: strBindLocationSelf, strRaceSelf, strGenderSelf, nAdvExpSelf, nAdvRestExpSelf, all the craft/harvest/diplomacy n* and str*Class variables, strPositionSelf, the bIs* flags, EnergyRegenPerSecond, AdvArmorClass/ACMitigation, the Acc variables, the Focus variables, the DPS variables, and AdvFlurry/Rampage non-Int.

## Evidence addresses (handler `FUN_005e8260`)

| What | Address(es) |
|---|---|
| Message base at ESP+0x74 | 0x5e82a4 (ctor 0x5df2f0) and 0x5e82c6 (deserialize 0xccf860) |
| Copies into UI members | 0x5e861a–0x5e894d |
| strBindLocationSelf build | 0x5e898a–0x5e8b6b |
| Race / gender / class strings | 0x5e8d35–0x5e8ef6 |
| Crafting | 0x5e8f50–0x5e92f3 |
| Harvesting / diplomacy | 0x5e9319–0x5e9492 |
| Levels and XP numbers | 0x5e9553–0x5e9aad |
| bRestGTDebt | 0x5e9ac3 |
| Movement and flags | 0x5e9b1f–0x5e9dc9 |
| XP bars | 0x5e9e04–0x5ea417 |
| nArmorClass and `FUN_00572500` | 0x5ea42d–0x5ea48f |
| `FUN_00572790` (args w56, w55, w57..w62) | 0x5ea494 |
| `FUN_00557b10` (args w45, w47, w46, w48, w49, w50, w51, w52, w53, w54) | 0x5ea4f9 |
| EnergyRegenPerSecond | 0x5ea5a2 |
| `FUN_00559250` (args w63, w64, w65, w69, w70, w71, w73, w72, w75, w76) | 0x5ea5c4 |
| `FUN_005582d0(&msg)` | 0x5ea63f |
| Class check 0x0f / 0x1b | 0x5ea64f |

## Crafting and diplomacy levels (verified live 2026-10-13)

Crafting XP (recipes, work orders) and diplomacy XP (parleys) now accumulate per sphere (`zone.gain_sphere_xp`, saved as the character's `spheres`): 1000 XP a level, up to 50. A level-up sends **0x713** `{i32 level, i32 sphere}` (sphere 0 adventuring, 1 crafting, 2 diplomacy; FUN_005e68f0), which prints "Your Crafting level is now 2." (0x723, same layout, prints "You lost a level, your %s level is now %d."). MsgScore then carries craft_level / craft_exp / craft_exp_frac and dip_level / dip_exp / dip_exp_frac. `!spherexp <1|2> <amount>` grants sphere XP for testing.

## Attribute points (verified live 2026-10-15)

The Attributes tab of the character window shows "Allocation Points" and a **+** and a **Max** button per attribute. They are enabled only while `bCanSpendAdvAllocPoints` is true.

- **0x2da** `{i32 points, i32 pool}` (pool 0 adventuring, 1 crafting, 2 diplomacy; FUN_0055dda0) sets the number and enables the buttons when points > 0. The server sends it at spawn and on every level up, together with **0x2db** `{u8 0}` ("You have gained new adventuring attribute points!" and a gold banner).
- **+ / Max** send **0xe4** `{i32 stat instance id, i32 mode, i32 category}`: mode 1 is one point, mode 3 is as many as allowed; category 0 is adventuring, 1 crafting (FUN_0056eeb0). The instance id is the stat record's field 1, which this server sets to the stat id.
- **0x2d9** `{i32 result, i32 stat instance id, i32 category, i32 new base, i32 points left}` (FUN_00575100) prints the result and updates the pool. The shown value only changes with a following 0x2d4. Result codes:

| Code | Meaning |
|---|---|
| 0-5 | raised Strength, Constitution, Dexterity, Vitality, Wisdom, Intelligence |
| 6-11 | "can not raise ... any more" (same order) |
| 12-23 | lowered / can't lower |
| 28-35 | crafting attributes raised / can't raise |
| 36 | "You may not increase or decrease that attribute." |
| 37 | "You have no points in your allocation pool." |
| 38-39 | refund pool messages |
| 255 | unknown failure |

- The shipped UI has no undo, reset or refund buttons; the `PCRefundPool*` game vars are never set. Diplomacy has a pool variable but no buttons.
- **Server** (`server/attributes.py`, `login_stub.handle_allocate`): 2 points per level after the first, and at most 1 point per level into one attribute (placeholders). Only the spent points are saved (`attr_alloc`); the pool is points earned minus points spent, so existing characters get their points back. Allocated points are added to the attributes like the gear and race bonuses, so health and the pools follow them.
- Seen live with Ranger (level 13, 24 points): + on Strength 50 → 51, then Max on Vitality 30 → 43 (capped at 13), 10 points left, "You successfully add to your strength.". Another + on Vitality: "You can not raise your vitality any more.". The values and the pool were kept after a relog.
- Crafting attributes (Problem Solving 42, Reasoning 151, Ingenuity 234, Finesse 239, category 1) work the same way in the client; the server doesn't grant crafting points yet.
