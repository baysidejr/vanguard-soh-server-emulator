# How the server makes the client play ability visuals (VGClient.exe)

> **Verified live (2026-10-12):** sending `0x3d1` with ability 570015 (WAR SHOUT_FURY_I) plays the shout animation on the player; 570001 plays the strike and the target reacts. Implemented in `server/combat.py` (`display_ability`).

> **Particle and material effects (verified live 2026-10-15):** the FX_ Actions in the lists (FX_IMPACT_BODY_..., FX_RIGHT_WIELD_...) only play since the server announces the client's FX* packages in the package map (docs/PROTOCOL.md); before that only the animations showed. Ranger Blade of Winter on a Canyon Widow now tints the spider red, then frost blue.


[O] = observed in code/data, [I] = inferred.

## TL;DR
Send zone event **0x3d1 MsgDisplayAbility** (or 0x3d3, same layout) with caster eid, target eid,
**ability id = the Ability export number** (e.g. 610004, 0 = generic auto attack), and an
**outcome/phase byte** (0 miss, 1 crit-miss, 2 hit, 3 crit, 4 block, 5 dodge, 6 parry).
The client loads `<PKG>_<id>` from `Assets/Abilities/<PKG>.aby` and plays the caster's Action list
and, when a target is given, the target's reaction Action list for that phase. The ability does
NOT have to be in the ability book.

## 1. Ability lookup / loader
- [O] `FUN_007f3640(int abilityId)` maps the id range to a package name and builds the object name
  with `"%s_%d"`. Then it calls `FUN_00405610(0, name, pkg, 0x2002, 0)` (load object), `FUN_00ae1f30`,
  and `FUN_007ec6e0` (cast). It returns the UAbility* or 0, and returns 0 when id < 0.
  Ranges [O]: <10000 MELEE_ABILITIES, <20000 SPELL_, <30000 HARVESTING_, <40000 CRAFTING_,
  <50000 DIPLOMACY_, 60000-69999 ITEM_, 70000-79999 WEAPON_PROC_, 80000-89999 TRAP_,
  200000-209999 NPC_ABILITIES, 210000-389999 ABILITIES_<element> (one band per 10000:
  FIRE, ICE, WATER, EARTH, AIR, POISON, DISEASE, ARCANE, DIVINE, MYSTICAL, NATURE, PSIONIC,
  NECROMANCY, ELECTRIC, SMOKE, PHYSICAL, UNDEAD, then GENERAL),
  400001-409999 SOCIAL_, 500000-669999 class packages (one per 10000: BMG, CLR, DSC, SHM, INQ, DRK,
  PAL, WAR, BRD, BSK, MNK, RNG, ROG, DRU, NEC, PSI, SOR), 900000-999999 RAID_.
- [I] Caveat: NPC_BASE_ABILITIES.aby exports are named `NPC_BASE_ABILITIES_2100xx`, but ids in
  210000-219999 map to `ABILITIES_FIRE_<id>`. Those NPC base abilities are probably unreachable
  through this path. Ids 50000-59999 and 90000-199999 have no package, so the name gets an empty
  prefix and the lookup fails.
- [O] Ability export body (decoded with upackage). The layout is `00 01 00 00 00`, then i32 id,
  then 7 records. Each record is `{i32 phaseIdx, u8, i32 nA, nA x compactIndex (caster Actions),
  i32 nB, nB x compactIndex (target Actions)}`. The record is followed by zero padding and an
  FString display tag (for example "BLADE_WINTER_I"). The Actions are imports from `*_ACTIONS`
  (.acn).
- [O] Runtime: in FUN_0080dbf0, `param_5` (phase) selects `ability + 0x38 + 0x20*phase`
  (switch for 0..6, default 0). Array A is at +8/+0xc and is played on the caster
  (FUN_0080a020). Array B is at +0x14/+0x18 and is played in a second display object for the
  target.
- Phase meaning, [O] from the asset contents and [I] for the naming:
  - 0: miss / fail (GENERIC_ATTACK_FAIL)
  - 1: critical fail (GENERIC_ATTACK_FAIL_CRIT)
  - 2: hit (GENERIC_ATTACK_SUCCESS, ANIM_IMPACT)
  - 3: critical hit (…SUCCESS_CRIT, ANIM_IMPACT_CRITICAL). The handler downgrades 3 to 2 when the
    caster's vfunc +0x324 flag has 0x10 and the target's has 0x20 [O].
  - 4: block
  - 5: dodge
  - 6: parry

  Phase 3 also sets `local_43c = 1` (crit flag) [O].

## 2. Event that plays the ability: 0x3d1 / 0x3d3 MsgDisplayAbility
- Dispatcher FUN_00439a60 [O]:
  - 0x3d1 calls `FUN_00439510(msg, len, 0)`.
  - 0x3d3 calls `FUN_00439510(msg, len, 1)`.
  - Related events on the same dispatcher: 0x3d2 EndPhaseEarly (FUN_00433a50) and 0x3d4 AddChatText
    (FUN_00435eb0).
- Message ctor is FUN_004337f0 and the field schema is FUN_00432ad0 [O]. Wire order is the
  schema order (offsets are in-object). All fields are little-endian, packed, with no padding on
  the wire. Types come from the existing ZONE_MESSAGES decoding of
  cca8b0=eid64, cca810=i32, ccaae0=u8, ccaa90=bool8, cca900=f32.

| # | obj off | type | meaning |
|---|---|---|---|
| 1 | 0x18 | eid64 | **caster**. Must resolve to an existing actor (FUN_00b7e3c0/FUN_00b73430), or nothing is played [O] |
| 2 | 0x20 | eid64 | **target**. -1 = none [O]. Target reactions (array B) only play when it resolves [I] |
| 3 | 0x28 | i32 | **ability id**: export number, e.g. 610004. Passed to FUN_007f3640 [O] |
| 4 | 0x2c | i32 | display id: per-message unique id, stored at display+0x30 [O]. Use an incrementing counter [I] |
| 5 | 0x30 | i32 | ability instance / use id, stored at display+0x34. Links the phases of one use [O]. Chat text from 0x3d4 is queued against it (FUN_007eefa0) [O/I] |
| 6 | 0x34 | i32 | previous display id to stop. When type==0 and value != -1, FUN_007f3ad0(this, 1) removes that display [O]. Send -1 |
| 7 | 0x38 | u8 | display type [O]: 3 = add the target to an existing instance (FUN_007f3cc0) and stop; 4 = instant (durations 0.1/0); 0 = normal (honors #6); 1/2/other = durations 10/0. A value of 1 skips the "pending/looping" flag (display+0x3c) [O] |
| 8 | 0x39 | u8 | stored at display+0xa8 and compared as a sequence/priority (`<=`) against existing displays [O]. Send 0 |
| 9 | 0x3a | bool8 | adds flag 0x10 (FUN_00432dc0) and the +/- sign in the AntiGroup counter (FUN_004aa140) [O]. Send 0 |
| 10 | 0x3b | u8 | ability kind/delivery [O]: 0 gives flags 0x81; 2/9/10/11/15 give 0x100 (forces 1.5 s timing, likely projectile/ranged [I]); 1/3/7/8/14 give 0x80. Values 0/1/5/14 with a time below 1.5 use 1.6 s |
| 11 | 0x3c | i32 | stored at display+0x64 [O], meaning unknown. Send 0 |
| 12 | 0x40 | i32 | stored at display+0x68 [O], meaning unknown. Send 0 |
| 13 | 0x44 | u8 | **phase / outcome** 0..6 (see above) [O] |
| 14 | 0x45 | u8 | stored at display+0xac when inheriting [O]. Send 0 |
| 15 | 0x46 | u8 | not used in the handler that was read. Send 0 |
| 16 | 0x47 | bool8 | when set, the display also gets display+0xa0=1 and +0xa4. The handler calls FUN_00439310(target) and flushes queued chat text (FUN_00435470 / FUN_007eefa0 / FUN_004cfb70) [O]. Probably means "final/landing" [I] |
| 17 | 0x48 | u8 | delta for the caster's AntiGroup in-flight counter (FUN_004aa140) [O]. Send 0 |
| 18 | 0x4c | f32 | duration / cast time in seconds. Used to build the timing doubles: +1.0 for 0x3d1, +0.2 for 0x3d3. It is also rounded into a byte at display+0xad [O] |
| 19 | 0x50 | i32 | if a target exists and the value is not 0 or -1: FUN_007ef130(target, instanceId, value) [O], meaning unknown. Send 0 |

Payload size is 2x8 + 4x4 + 4x1 + 2x4 + 5x1 + 4 + 4 = **57 bytes**.

- 0x3d1 vs 0x3d3 [O]: with param 0 (0x3d1), FUN_0080dbf0 first calls FUN_0080dad0(instanceId).
  That stops the caster's other still-pending displays that belong to a different instance.
  0x3d3 skips this step and uses shorter timing (+0.2 instead of +1.0).
  [I] So 0x3d3 is an additional/overlapping display, and 0x3d1 is the primary one.
- Call chain [O]: FUN_00439510 → FUN_007f6710 (ECX = caster pawn) → FUN_007f3640(abilityId) →
  FUN_0080dbf0(instanceId, isAlt, displayId, UAbility*, phase, f3c, f40, targetPawn, flags, f39,
  f47, f45.., f48, dur1, dur2, dur3, type, -1.0).
- Ability book [O]: the 0x3d1 path never consults the ability book (VGClientAbilityBook). Any id
  that resolves to an Ability object plays.
- Minimal melee swing that hits [I], from assets plus code:
  0x3d1 {caster=attackerEid, target=victimEid, abilityId=0 (MELEE_ABILITIES_0 GENERIC_AUTO_ATTACK;
  9 = GENERIC_NPC_AUTO_ATTACK for NPCs), displayId=N++, instanceId=M++, prevDisplay=-1, type=0,
  0, 0, kind=0, 0, 0, phase=2, 0, 0, 0, 0, dur=0.0 (or the swing time), 0}.
  For a class ability such as RNG "BLADE_WINTER_I" use abilityId=610004. Use phase=5 for dodge,
  and so on.

## 3. Combat text
- **0x3d4 MsgDisplayAddChatText**, handler FUN_00435eb0 [O]. Layout:
  {eid64 source, eid64 target, bool8, u8, i32 instanceId, wstr text}. Both entities must resolve.
  The chat channel is computed by FUN_00432f20(src, tgt, bool, u8).
  FUN_007eefa0(instanceId, text, chan) queues the text on the matching ability display. If there
  is no match (it returns 0), the text is printed immediately via FUN_004cfb70(text, chan) [O].
  [I] So the server sends 0x3d1 and then 0x3d4 with the same instance id, and the
  "You hit X for N damage" line appears when the hit lands (field #16 flush).
- 0x27b MsgDisplayAbilityGenText (FUN_004382d0) {eid64, eid64, i32, bool8, u8, i32, i32, u8, u8, u8,
  wstr, bool8, bool8}: client-side generated ability text. Not analyzed.
- 0x248 {eid64}: "You begin to cast …" / "%s begins to cast a spell." (FUN_004350b0), chat only.
- No separate floating-combat-text event was identified in this pass.

## Fireworks (2026-10-15, not visible yet)

The client ships fireworks as item abilities ITEM_ABILITIES_60002-60022 (FIREWORKS_ROCKET_BLUE, FIREWORKS_FOUNTAIN_YELLOW, FIREWORKS_SPARKLER_RED, ...). Every phase holds one caster Action from ITEM_ACTIONS.acn (FIREWORK_ROCKET_BLUE_60002), which uses FXspells_FireworksCast..._P001fx / FXfire_Fireworks001fx emitters and Firework1-3 sounds. items.json `"fireworks": <ability id>` (Blue Rocket, Yellow Fountain, Red Sparkler) plays it with 0x3d1 for the chunk and uses one up. The client resolves the ability (FUN_007f3640 hit with 60002) and starts the display (FUN_0080dbf0), but nothing showed in screenshots with the hit phase or a 3 s duration. The FX packages are announced, so the item Actions may need ITEM_ACTIONS loaded some other way, or a cast phase. Spawning `FXfire.FXfire_Fireworks001fx` directly with 0x553 creates the actor but also shows nothing. Retried 2026-10-15 with the camera zoomed out on the player (the earlier tests were in first person): the sparkler (60018) with target self or none, display type 0 or 4, phase 2 or 3, and 0 or 5 s duration still showed nothing on or around the character. Narrowed 2026-10-15: the emitter classes exist (FXspells.u has FXspells_FireworksCastSparklerARed_P001fx and the rest, FXfire.u FXfire_Fireworks001fx, and ITEM_ACTIONS.acn imports them), and FXspells / FXfire are among the announced packages. Emitters placed in the level do render (the fireplace flame in a Bordinar's Cleft hall), so the gap is specific to emitters spawned at runtime (fireworks, the loot sparkle, quest-node particles, 0x553 spawns): next step is breaking in the spawned emitter's setup with tools/winbreak.py.
