# Ability effects: buffs, damage over time, heals, cooldowns

**Verified live (2026-10-12, Ranger):**
- Ferocity I (a buff) puts an icon with a countdown ("26s", then "9s") in the player's effects area. Expiry was watched live: after 30 s Evasive Style I's icon goes away and "Evasive Style I wears off." prints.
- Deadly Shot I (a DoT) hits once, then shows a "Deadly Shot I" debuff icon in the target window. It ticks 4 times every 3 s ("Your Deadly Shot I hits Ashen Wolf for 4 damage.") and the wolf's health bar drops.
- Reusing an ability before its refresh time is refused.

**NPC special attacks (verified live):** after a melee swing, a mob template's `abilities` may fire, for example the Canyon Widow's Venom Bite: "Canyon Widow uses Venom Bite on you!". This adds a harmful effect icon with a countdown (`0x23a` harmful=1). It ticks "Canyon Widow's Venom Bite hits YOU for 5 damage.", and `0x23b` removes the icon at the end. A reapply refreshes the tick count.

The code is in `server/effects.py` and `login_stub.use_ability` / `apply_buff` / `apply_dot` / `effects_tick`. The dev commands `!learn <ability>` and `!use <ability>` help with testing.

## What an ability does

Real ability data (costs, damage, durations) was server-side. The emulator guesses an ability's kind from its name (`effects.KEYWORDS`):
- **dot** if the name contains words like rend, venom or decimate
- **heal** for heal, mend or restore
- **buff** for might, ward, style, shield and similar words
- **strike** (direct damage) for everything else

`server/content/abilities.json` overrides the guess per ability name: `kind`, with `damage/ticks/interval`, `amount`, or `stat/bonus/duration`, plus `icon`.

## Messages (static analysis; the starred ones are verified live)

| Id | Payload | Meaning |
|---|---|---|
| `0x23a`* | `i32 id, wstr name, wstr desc, u8, i32 icon, u8, i32 seconds left, bool8 show, bool8 no expiry, bool8 harmful, bool8 short list, f32 duration` | adds an effect to the player's effects window (dispatcher `FUN_00467f80`) |
| `0x23b`* | `i32 id` | removes it (the client never expires effects itself) |
| `0x23c` | `i32 id, i32 left, i32 duration, bool8` | timer update (sent every 5 s) |
| `0x24a` (C->S) | `i32 effect id` | the client's effect timer ran 2 s (and again 12 s) past the end and the effect is still shown (effects tick FUN_00463bd0, manager DAT_0146399c). The server answers 0x23b if the effect is gone, or 0x23c with the time left. Unit-tested |
| `0x3c5`* | `i32 id, wstr name, wstr desc, i32 icon, bool8 show, bool8 debuff, eid64 caster` | adds an effect to the target window (the current target's list: `0x3c9` clears it, and the server resends on retarget) |
| `0x3c6` | `eid64 target, i32 id` | removes a target effect |
| `0x2d4`* | MsgStatUpdate with current = base + bonus | stat buff shown in the character window |
| `0x259` | `i32 ability id, f32 left, f32 total` | hotbar cooldown sweep |
| `0x242` | `u8 code` | ability failure sound (7 = too soon, 3 = too far, 0x22 = no energy, 0x24 = no endurance) |
| `0x241`* | `u8 code` | ability failure with the client's own chat line and screen text (FUN_0043e610; codes below). Used for "not refreshed" (7), stunned (0x0d, "You cannot do that while stunned.", verified live 2026-10-14) and "requires a chain" (0x2a) |
| `0x25c`* / `0x260`* | `wstr name, f32 seconds` / none | cast bar / interrupted. An ability with `cast` seconds in abilities.json shows the bar ("You begin to cast Deadly Shot I.") and goes off when the time is up. Moving during the cast interrupts it ("Your Deadly Shot I is interrupted."). Verified live |
| `0x27b` | `eid64 source, eid64 target, i32 instance, bool8 heal, u8 kind, i32 amount, i32 bonus, u8 outcome, u8 type, u8, wstr ability, bool8, bool8` | client-built combat sentence, shown in the **Combat** tab (verified live: "Your Test Strike heals you for 12 hit points.", "Canyon Widow's Venom Bite hits you for 6 damage."; kind 0 gives the weapon form "You slash yourself for 12 damage."). Used for heals, DoT ticks and every melee hit both ways (auto-attack and NPC swings use kind 0 with damage type 3, giving "You hit Canyon Widow for 8 damage." / "Canyon Widow hits you for 7 damage."; abilities use kind 1 with the ability name). `!ctext [kind] [heal] [self]` sends a test line |

## Hotbar cooldown sweep (fixed, verified live 2026-10-13)

0x259 is keyed by the **ability id** (MsgAbilityInfo field 20, e.g. 1001), not the handle (field 5): FUN_00427c30 searches the ability-book map that FUN_00431be0 keys on obj+0x10c. With the handle the lookup missed and nothing was drawn. Sending the ability id darkens the hotbar slot and the client runs the sweep from its own clock (slot +0x9f4 total, +0x9f8 left). The update reaches the hotbar through the ability-book row the slot is linked to (FUN_006ad020 -> FUN_00c2bf90 -> FUN_006aace0). 0x25b {f32} is the optional global cooldown; MsgAbilityInfo field 36 must stay 0 or the per-frame tick stops.

## Stances and maintained abilities (verified live 2026-10-13)

Abilities with abilities.json `"stance": true` (the Ranger's Offensive / Precision / Evasive Style) are maintained stances: no timer, one at a time (assuming another takes the old one off: "You assume Evasive Style I." / "Offensive Style I wears off."), always on the caster. The server keeps the stat bonus as a buff internally but shows the stance only in the **Effects Maintained** window (`VGUIMaintainedAbilities.xml`, a frameless icon row): **0x23e** `{i32 id, wstr name, wstr desc, u8 0, i32 icon, bool8 0, f32 0}` adds it (resending the id replaces it), **0x23f** `{i32 id}` removes it, 0x24f clears all. Right-clicking the icon (or `/cancelmaintained <name>`) sends **0x24e** `{i32 id}` and the server ends the stance. The timed buff icon (0x23a) is removed for stances so it doesn't show "3650d". Right-clicking an ordinary buff icon sends **0x249** `{i32 id}` and the server ends it ("Adamant Foeman I wears off.", verified live). Not done: 0x254 ability-failure reasons.

## Fear (verified live 2026-10-13)

abilities.json `"kind": "fear", "duration": s` (Necromancer "Fear I": 1.5 s cast, 8 s): the targeted NPC runs straight away from the caster at 80% speed and doesn't swing until it wears off; it keeps its hate and comes back afterwards. Chat: "Canyon Widow flees in terror!". Server: `combat.chase_step` / `combat.npc_turns` check `npc.feared_until`.

## Stuns and roots on players (verified live 2026-10-13)

The client moves its own pawn, so the server holds a player still by replicating the pawn's **GroundSpeed = 0** and restores it (with the mount bonus) when the effect ends. mobs.json abilities with `"kind": "stun"` or `"root"` and `"duration"` (the Robed Wanderer's Dazing Blow: 15%, 3 s) put a harmful effect icon up and print "Robed Wanderer's Dazing Blow stuns you!"; "You can move again." when it wears off. A stun also blocks abilities ("You are stunned!") and interrupts a playing Bard song. Measured with `!cc root 8` (dev): holding W moved 1008 units in 3 s before, 0 while rooted, 1009 after.

**Fear on players (verified live 2026-10-13):** kind `"fear"` roots the pawn like a stun and moves it 250 units a second away from the NPC with server teleports (0x3e5 MsgForceLocationSet, facing away), because the client can't be steered. `!cc fear 5` with Garret Holm targeted pushed Ranger from (-31000, -5800) to (-31205, -7030); chat: "Garret Holm's Test Fear terrifies you!". Fear also blocks abilities and interrupts songs. Movement is in one-second hops.

## Avoidance and critical hits (verified live 2026-10-13)

The 0x27b outcome byte (FUN_004368b0) picks the sentence: **0/1 miss** ("Timber Wolf misses you!", "You miss Rat!"; for spell damage types 7-12 it is a resist), **2 hit**, **3 critical hit**, **4 block**, **5 dodge** ("You dodge Timber Wolf's attack.", "Rat dodges your attack."), **6 parry**. Every melee swing both ways rolls one outcome (`combat.roll_outcome`, placeholder numbers): miss 6% + 2% per level the defender is above the attacker; dodge 4% + 0.1% per Dexterity above 30; parry 4% when the defender holds a weapon (players with a primary or two-handed weapon; NPCs of the playable races, not creatures); block 6% with a shield; critical 5% + 0.1% per attacker Dexterity above 30, for 1.5x damage. Avoided swings do no damage.

The character sheet's Dodge, Parry and Block show these chances (parry only with a weapon in hand, block only with a shield).

## Kill experience (verified live 2026-10-13)

A kill gives 150 XP at the player's own level, +15% per level the NPC is above and -15% per level below; NPCs 6 or more levels below give nothing (`combat.kill_xp`, placeholder curve). Level 13 Ranger killing a level 9 Timber Wolf: "You gain 60 adventuring experience!". Group sharing and the group bonus apply on top. Each level needs 12% more experience than the one before (`zone.xp_for_level`: 1000 for level 1, 3900 at 13, 8610 at 20; cap 50; placeholder curve); the XP bar shows progress toward it (level 13 Ranger with 878 XP: 22.51%).

## Ability power (verified live 2026-10-13)

Ability damage, damage over time and heals scale with the caster (`combat.power`, placeholder): +8% per level above 1, and +1% per point of the class's main attribute above its default (Strength for fighters, Intelligence for spellcasters' damage, Wisdom for heals). At level 13 Ranger's Deadly Shot I (3-7 a tick) ticked for 7 and 13.

## Ability failure codes (0x241)

From the client's switch (byte table 0x43f980, jump table 0x43f86c). The first text is the chat line (a localization key where it is one word), the second the screen flash.

| Code | Message |
|---|---|
| 0x01 | You may only activate that ability as a reaction. (with a DEBUG note) |
| 0x02 | Your combat queue is full. (with a DEBUG note) |
| 0x03 | TooFarAway / Target too far away. |
| 0x04 | That agenda ability does not match your current parley task. |
| 0x05 | Your target is of the wrong type for that ability. |
| 0x06 | You can't meet the cost of that ability. |
| 0x07 | That ability has not refreshed. / Not ready to do that yet. |
| 0x08 | You can't execute abilities while you are memorizing. |
| 0x09 | You can't execute abilities while you are resting. / You are resting! |
| 0x0b | Please select a valid target for that ability. / Invalid target. |
| 0x0c | NotAttackable / Invalid target. |
| 0x0d | NotWhileStunned / You are stunned! |
| 0x0e | NotWhileDazed / You are dazed! |
| 0x0f | You may not use an ability from that sphere on your current target. |
| 0x10 | You must already be parleying with an NPC to use that ability. |
| 0x11 | You are not wielding the proper weapon type to use that ability. |
| 0x12 | You cannot cast a spell communally without a defensive target. |
| 0x14 | Your level is not high enough to use this ability. |
| 0x15 | Your skill level is not high enough to use this ability. |
| 0x16 | You need to wield a harvesting tool to use this ability. |
| 0x17 | You cannot use this ability right now. |
| 0x18 | You are missing a flag that is required to use this ability. |
| 0x19 | You can't use that right now because you are casting it and it requires time to refresh. |
| 0x1b / 0x1c | focused bond limits |
| 0x1e / 0x1f | corpse consumed / you must have a corpse targeted |
| 0x20 | You do not have enough %s to use this ability. |
| 0x21 | FailBardSong / Bard song only. |
| 0x22 / 0x23 / 0x24 | not enough energy / stamina / endurance |
| 0x25 / 0x26 / 0x32 / 0x33 | not enough inspire / reason / flatter / demand (diplomacy) |
| 0x28 | You are missing the ammo needed to use this ability. |
| 0x29 / 0x2b | You can't do that yet. |
| 0x2a | You may only use that once it is unlocked as part of a chain. / That requires a chain. |
| 0x2c-0x2f, 0x31 | corpse or target too powerful, too high level, not an NPC, was a pet |
| 0x30 | You're already looting something. |
| 0x34-0x37 | must dodge / parry / block / feint first |
| 0x39 / 0x3a | missing reagent / reagent not equipped |
| 0x3c | TooClose / Target too close. |
| 0x3d | FailPassive / Passive only. |
| 0x3e | CantSeeTarget / Can't see target. |
| 0x3f / 0x40 / 0x41 | wrong mount type / not while flying / wrong ammunition |
| 0x42-0x44 | invalid raid target (cannot help raid, raid target full, lockout) |
| 0x45 | Your level is too high to use this ability. |
| 0x46 | FailCastClassOrRaceLocked |
| 0xff | You fail to cast for an unknown reason. |

## Wounds (verified live 2026-10-15)

**0x44b** MsgWoundsUpdate `{5 x u8}` (FUN_005ef110) gives the severity of each body part in the order head, torso, left arm, right arm, legs: 0 Unwounded, 1 Minor, 2 Mid, 3 Major, 4 Incapacitated (client strings). The client compares with what it had and prints the changes: "Your head was just wounded! The severity of the wound is up to Minor" as screen text, plus "You have been wounded!" / "Right Arm - Mid" and "Some of your wounds have been cured!" / "Right Arm - Unwounded" in chat. It also sets the game vars nWoundsHead, nWoundsTorso, nWoundsLeftArm, nWoundsRightArm and nWoundsLeg.

The server's rules are placeholders:
- An NPC's critical hit wounds a random part one level, half the time (`combat.wound`).
- While sitting out of combat, the worst wound heals one level every 20 s (`login_stub.wounds_tick`).
- Releasing after death clears all wounds.
- Wounds are saved (`wounds`) and sent at login. They have no effect on stats yet.

Seen live from real hits 2026-10-15 (an Ashen Wolf with mobs.json `"crit": 1.0`): "You have been wounded!" / "Legs - Major", "Head - Incapacitated". `!wound <part 0-4> <severity 0-4>` sets one for testing. Seen live: "Right Arm - Mid", then Minor and Unwounded after sitting.
