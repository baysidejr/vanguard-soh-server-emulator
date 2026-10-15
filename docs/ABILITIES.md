**Status:** verified live on 2026-10-11. Four warrior abilities appear in the Adventuring book with icons (`server/zone.py` `ability_messages`, `server/vgmsg.py` `ability_info`), and clicking one sends zone event `0xd0` with the ability handle, which the server logs.

# Vanguard client: ability book (MsgAbilityInfo 0x215) report

Static analysis of `C:\Vanguard EMU\bin\VGClient.exe` (Ghidra via REA). [O] = observed in code, [I] = inferred.

## 1. Wire format: field types and order

- [O] Registrar `FUN_0041e2b0` is called once from the `MsgAbilityInfo` constructor `FUN_0041ebc0`. It registers 68 fields. The generic deserializer `FUN_00cd9da0` walks the field table in registration order and reads sequentially. Type codes:
  - 0 = i32, 4 bytes (`FUN_00cca810`)
  - 1 = f32, 4 bytes (`FUN_00cca900`). The client uses these as floats (MOVSS in `FUN_0041f5d0`, float compares in `FUN_0042c5b0` and `FUN_00c59af0`).
  - 2 = wstr: UTF-16LE with a NUL terminator; an empty string is 2 bytes (`FUN_00cca950`)
  - 4 = bool8, 1 byte (`FUN_00ccaa90`)
  - 7 = u8, 1 byte (`FUN_00ccaae0`)
- [O] If the payload runs short, the deserializer stops at that point (`FUN_00cd9c00`) and the remaining fields keep stack garbage. Always send all 68 fields.
- [O] The handler `FUN_00432570` builds the client ability object (0x1d4 bytes, ctor `FUN_0041f0b0`). `FUN_0041f5d0` copies the message fields into it; the assembly was used to confirm the mapping between message offsets and object offsets.

"obj" below means the client ability object. Meanings are [O] when a named UI string or explicit logic uses the field.

| # | type | msg off | obj off | meaning |
|---|------|--------|---------|---------|
| 1 | wstr | 0x14 | +0x00 | **Name**. [O] List entry text, sort key (`FUN_0042f7a0`), `_ability_examine_name`, `/cast "%s"` text. Must be unique: cast looks the ability up by name. |
| 2 | wstr | 0x30 | +0x1c | **Description**. [O] `_ability_examine_desc`, run through `FUN_006b1c60` (likely token expansion). Also the slot's 2nd string (`FUN_006adff0`) |
| 3 | wstr | 0x4c | +0x38 | [O] `_ability_examine_special_desc` |
| 4 | wstr | 0x68 | +0x54 | [O] `_ability_examine_special_desc_2` |
| 5 | i32 | 0x84 | +0x70 | **Ability handle** (instance id). [O] Sent back in the use-ability request 0xd0; 0x219 (remove from tome) matches on it (`FUN_0042b610`) |
| 6 | bool | 0x154 | +0x74 | [O] **Requires memorization**. If nonzero, use fails with "You need to memorize that ability to cast it." → send 0 |
| 7 | bool | 0x155 | +0x75 | unknown |
| 8 | u8 | 0x156 | +0x76 | [O] Flags byte. `&6` = chain/finisher-type (Adventuring list, special handling); bit0 also used. Copied to slot. Send 0 |
| 9 | wstr | 0x88 | +0x84 | [O] **Command/macro text**. If non-empty, activating the ability runs this text as a slash command instead of casting (`FUN_0042ca80`) → send "" |
| 10 | wstr | 0xa4 | +0xa0 | [O] **Type label** (`_ability_examine_type`, e.g. "Melee") |
| 11 | wstr | 0xc0 | +0xbc | [O] "Add weakness" text; its icon shows when non-empty |
| 12 | wstr | 0xdc | +0xd8 | [O] "Exploit weakness" text; its icon shows when non-empty |
| 13 | i32 | 0xf8 | +0xf8 | [O] **Book / list selector**: 0 = Adventuring, 2 = Diplomacy, anything else = General (`FUN_00431be0`) |
| 14 | i32 | 0xfc | +0xfc | unknown |
| 15 | i32 | 0x100 | +0x108 | unknown |
| 16 | i32 | 0x104 | +0x100 | unknown |
| 17 | i32 | 0x108 | +0x104 | [O] Slot mode: 0 → slot field 0x94=2, else 1. Meaning unknown |
| 18 | i32 | 0x10c | +0x7c | unknown (copied to slot data) |
| 19 | i32 | 0x110 | +0x80 | [O] **Level** ("Level: %d" in examine) |
| 20 | i32 | 0x134 | +0x10c | [O] **Ability id / book key**. The book is a map keyed on this; a second 0x215 with an existing key is **silently ignored** (`FUN_00431be0` → `FUN_004273b0`/`FUN_004251d0`) |
| 21 | i32 | 0x138 | +0x110 | [O] **Icon id**. Formatted `%05d` and looked up in the icon skin (`FUN_00c4b020`); falls back to "00443", and the slot uses "00233" if lookup fails (`FUN_006aace0`) |
| 22 | f32 | 0x13c | +0x118 | [O] **Cast time** in seconds ("Instant" if ≤0) |
| 23 | f32 | 0x140 | +0x134 | [O] **Recovery time** (examine "Recovery:" when obj+0x1d1 is set) |
| 24 | f32 | 0x144 | +0x11c, +0x120 | [O] **Refresh (cooldown) duration** ("Refresh: %s"; slot cooldown total `FUN_00c59b30`) |
| 25 | f32 | 0x148 | +0x124 | [O] **Refresh time remaining**. If >0, use is blocked ("You can't do that yet.") → send 0 |
| 26 | bool | 0x157 | +0x114 | [O] Copied to slot (+0xb1); meaning unknown |
| 27 | wstr | 0x114 | — | [O] Registered but **never copied** (ignored) |
| 28 | i32 | 0x130 | — | [O] Ignored |
| 29 | i32 | 0x14c | +0x138 | [O] **Min range** (examine "%i - %i") |
| 30 | i32 | 0x150 | +0x13c | [O] **Max range** |
| 31 | u8 | 0x158 | +0x14c | [O] **Ability kind** (0xff→-1). 10 = bard song (goes to Song*List); 1 = "On Next Swing"; kinds 0/1/3 skip the global-cooldown block (`FUN_0041ea30`) |
| 32 | u8 | 0x159 | +0x150 | [O] Song part when kind == 10: 0 Melody, 1 Verse, 2 Embellishment, 3 Bridge, 4 Lyric, 5 Chorus, 6 Coda, 7 Rest (0xff→-1) |
| 33 | bool | 0x15a | +0x154 | unknown |
| 34 | bool | 0x160 | +0x164 | [O] **Force General list** (checked before every other rule) |
| 35 | bool | 0x161 | +0x165 | unknown |
| 36 | bool | 0x162 | +0x166 | unknown |
| 37 | u8 | 0x15b | +0x158 | [O] Requirement; 0xff = any, else must equal player state at +0xdf8 (`FUN_005f3e80`) → send 0xff |
| 38 | i32 | 0x15c | +0x15c | [O] Requirement; -1 = any, else must equal player state at +0xdfc → send -1 |
| 39 | bool | 0x163 | +0x16c | [O] **Ground-targeted** (diverts to the ground-target flow) |
| 40 | bool | 0x164 | +0x16d | unknown |
| 41 | i32 | 0x168 | +0x170 | unknown |
| 42 | bool | 0x16c | +0x174 | [O] Adventuring sub-flag (sets a book-level flag) |
| 43 | bool | 0x16d | +0x175 | [O] Adventuring sub-flag (same as #42) |
| 44 | bool | 0x16e | +0x176 | [O] Adventuring sub-flag (also uses kind==2) |
| 45 | bool | 0x16f | +0x177 | [O] Adventuring sub-flag |
| 46 | bool | 0x171 | +0x178 | unknown |
| 47 | bool | 0x172 | — | [O] Ignored |
| 48 | bool | 0x173 | +0x183 | unknown |
| 49 | bool | 0x174 | +0x184 | [O] Subject to global cooldown even for kinds 0/1/3; examine shows "Instant" |
| 50 | u8 | 0x175 | +0x188 | unknown |
| 51 | u8 | 0x176 | +0x18c | [O] **Target type** (0xff→-1), shown as `_ability_examine_target` via `FUN_00d05570` |
| 52 | u8 | 0x177 | +0x190 | unknown (0xff→0) |
| 53 | i32 | 0x198 | +0x1b4 | [O] Health cost (red) |
| 54 | i32 | 0x19c | +0x1b8 | [O] Health per second |
| 55 | i32 | 0x1a0 | +0x1bc | [O] **Energy cost**; use is blocked if the player has less (stat 0xee) |
| 56 | i32 | 0x1a4 | +0x1c0 | [O] Energy per second |
| 57 | i32 | 0x1a8 | +0x1c4 | [O] **Endurance cost** (stat 0xe0) |
| 58 | i32 | 0x1ac | +0x1c8 | [O] Endurance per second |
| 59 | i32 | 0x1b0 | +0x1cc | [O] Special-points cost (Virtue, Jin, Phenomena, etc. depending on class) |
| 60 | bool | 0x1b4 | +0x1d0 | unknown |
| 61–68 | i32 ×8 | 0x178..0x194 | +0x194..0x1b0 | [O] **Allowed combat forms**. All -1 skips the form check. Otherwise the current form must be in the list, or the client tries to switch forms via event 0x13e (`FUN_005f3e80`) → send 8 × -1 |

## 2. Which list the ability lands in

[O] `FUN_00431be0` checks these rules in order:

1. If #34 is true → **GeneralAbilityList**.
2. Else if #31 == 10 → one of the Song lists, chosen by #32.
3. Else if #13 == 0 → **AdventuringAbilityList**. Several branches depend on #8, #42–#45 and #31, but they all go to the Adventuring list.
4. Else if #13 == 2 → **DiplomacyAbilityList**.
5. Else → GeneralAbilityList.

These names match the `gameVarLink`s in `VGUIAssets\Shells\Default\Windows\VGUIAbilities.xml`: `abilities_general` → GeneralAbilityList and `abilities_adventuring` → AdventuringAbilityList. Each entry is the `abilities_entry` component: an AbilitySlot (icon) plus a `_name` TextField.

## 3. Required preceding events

- [O] The UI list game-vars (GeneralAbilityList, AdventuringAbilityList, DiplomacyAbilityList, the Song lists, Chain/Finisher/Counter/Rescue/Sympathetic) are created **client-side**. This happens in `FUN_00423810`, called from the ability-book ctor `FUN_0042f090` and from the UI rebuild `FUN_005e1f40`. Unlike inventory, **no server reset is needed to create the containers**.
- [O] 0x21b (`FUN_0042bd80`, no payload) clears the book map and empties every ability list. Use it as an optional "reset before full resend".
- [O] 0x21d (no payload) only sets book byte[0] = 1. That byte is passed (inverted) as the last argument of the list insert (`FUN_0042f7a0` → `FUN_006af550`).
  - [I] It means "initial ability list complete" (it changes how later additions are inserted or notified).
- [I] Suggested sequence after zone-in, once the UI is up: `0x21b`, then N × `0x215`, then `0x21d`.
- [O] If the UI game-var does not exist yet (`FUN_00c2ff70` returns 0), the ability is stored in the book but no list row is added.
  - [I] Send the abilities after world/UI init, or resend with 0x21b first.

## 4. Minimal example: "Strike" in the Adventuring list

Field values:

- Name "Strike", description "A basic melee attack.", type label "Melee"
- handle = 1, ability id = 1001, icon = 20001, level = 1
- book (#13) = 0
- refresh duration 5.0, remaining 0
- range 0–5
- kind 0xff, target type 0xff, #37 = 0xff, #38 = -1
- all costs 0, forms 8 × -1

Icon 20001 is defined in `iconsTK.xml` with texture MNDIcons01.tga. [I] That it is an ability-style icon is a guess; any id present in `iconsTK.xml` renders.

The full message is a 10-byte header (u16 2, u32 0x215, u32 len = 0xf3 = 243) plus a 243-byte payload. The generator is `mk_ability.py` in the same scratchpad.

```
02 00 15 02 00 00 f3 00 00 00 53 00 74 00 72 00
69 00 6b 00 65 00 00 00 41 00 20 00 62 00 61 00
73 00 69 00 63 00 20 00 6d 00 65 00 6c 00 65 00
65 00 20 00 61 00 74 00 74 00 61 00 63 00 6b 00
2e 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00
00 4d 00 65 00 6c 00 65 00 65 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 01 00 00 00 e9 03 00
00 21 4e 00 00 00 00 00 00 00 00 00 00 00 00 a0
40 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
05 00 00 00 ff ff 00 00 00 00 ff ff ff ff ff 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 ff ff
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 ff ff ff
ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff
ff ff ff ff ff ff ff ff ff ff ff ff ff
```

Rules for a visible, usable ability:

- Unique #20 and unique #1.
- #6 = 0 and #9 = "".
- #25 = 0.
- Forms #61–68 = -1.
- #37 = 0xff and #38 = -1.
- Costs within the player's stats. A missing stat passes the check.

## 5. How the client uses an ability (client → server)

- [O] Clicking or activating an AbilitySlot (`FUN_00c5c480`) builds the text `/cast "<name>"` and runs it through the slash-command system. It does not send a message directly.
- [O] The /cast handler `FUN_00440ea0` resolves the name:
  - first against ability memory (`FUN_0043d460`, memorized spells);
  - then against the book (`FUN_0042ba30` → handle → `FUN_00427c30` → `FUN_0042ca80`).
- [O] `FUN_0042ca80` runs these client-side checks in order:
  1. Command string #9: if non-empty, run it as a command instead of casting.
  2. Memorize flag #6.
  3. Forms and requirements (`FUN_005f3e80`).
  4. Ground target #39.
  5. Fear.
  6. Readiness (`FUN_0042c5b0`): global cooldown, #25, energy, endurance, points.
- [O] If all checks pass, the client sends **event 0xd0** with **MsgSingleInt**: `u16 2, u32 0xd0, u32 4, i32 abilityHandle` (field #5). Send path: `FUN_004cfb00(0xd0, msg)` → `FUN_00409210`. MsgSingleInt has a single i32 field (`FUN_00422cd0`).
- [O] Related sends:
  - 0x13e is the form-change request: MsgTwoInt-like `{form id, book #13}`, sent from `FUN_005f3e80`.
  - Ground-target abilities go through `MsgClientAbilityCastGroundTarget` (`FUN_0043fa80`; not decoded).
- [I] Drag to hotbar is handled by the UI (`ABILITYSLOT_DRAG`). The hotbar most likely stores the name/handle and triggers the same `/cast` path; no server message is needed to drag. Not traced.

## Key addresses

| Address | Role |
|---------|------|
| `FUN_00432600` | Ability-book dispatcher |
| `FUN_00432570` | Handler for 0x215 |
| `FUN_0041ebc0` / `FUN_0041e2b0` | MsgAbilityInfo ctor / field registrar |
| `FUN_00cd9da0` | Generic deserializer |
| `FUN_0041f5d0` | Copies message fields into the ability object |
| `FUN_00431be0` | Chooses the list |
| `FUN_0042f7a0` / `FUN_006af550` | List insert |
| `FUN_006adff0` / `FUN_006aace0` | Slot data / slot icon |
| `FUN_006b4df0` | Examine window (field meanings) |
| `FUN_0042bd80` | Handler for 0x21b |
| `FUN_00423810` | Creates the list game-vars |
| `FUN_00c5c480` | Slot activation → `/cast` |
| `FUN_00440ea0` | /cast handler |
| `FUN_0042ca80` | Use checks and send of 0xd0 |
| `FUN_0042c5b0` | Readiness check |
| `FUN_005f3e80` | Form check |

## Starting abilities per class

`server/class_abilities.py` gives each adventuring class four starting abilities taken from the client's own `Assets/Abilities/<PREFIX>_ABILITIES.aby` (WAR, PAL, DRK, RNG, ROG, BRD, MNK, DSC, CLR, SHM, DRU, SOR, NEC, PSI, BMG). Each export is named `<PREFIX>_ABILITIES_<id>` and ends with a tag such as `BLADE_WINTER_I`, which becomes the ability's name. The id is also MsgAbilityInfo field 20 and the visual id sent in `0x3d1`, so using the ability plays its real animation. Costs, levels, damage and icons were server-side data and are placeholders. Run `python class_abilities.py` to list the picks.

## Defensive target panel (verified live 2026-10-15)

Picking a defensive target (F1, clicking a player, /targetself) shows a small panel under the portrait with the target's name, but its health bar stays empty until the server sends **0x3e2** `{eid64 entity, u8 health 0-255}` (FUN_005eaa00, game var DefTargetLifePoints). The client only applies it when the entity is its current defensive target. The server sends it once a second whenever the defensive target or its health changes (`login_stub.def_target_sync`). Seen: Ranger with himself as defensive target, full bar, then `!hurt 250` lowered both his own bar and the panel's. The level shield on the panel still shows 1 (DefTargetLevel comes from elsewhere, not found yet).

## Reactions: chains and finishers (verified live 2026-10-13)

Implemented in `server/reactions.py` and `login_stub` (`chain_next`, `activate_reaction`, `reactions_tick`); chains are content (`server/content/chains.json`, per class: opener → up to 4 steps → finisher, by ability name).

- **Ability records** (0x215): wire field #8 (flags, `vgmsg.ability_info(flags=)`): 0x03 = chain opener, 0x02 = chain step / finisher. The client puts chain-type abilities in the Reactions window lists and **locks** steps and finishers: using one directly prints "This ability is not available until the proper reaction is triggered." (server: 0x242 `{0x2a}`). Field #18 is the ability **line** id (ranks of one ability share it; the client picks the best learned rank of the line for a reaction), now sent as the ability id. #42/#43 rescue, #44 counter, #45 sympathetic (not used yet).
- **Chain definitions** at login, after the ability book: 0x26a (forget all), then one 0x268 per chain: 14 × i32 `{0, 0, 5 × (step ability id, step line id), finisher id, finisher line id}` (step 0 = opener, -1 unused). The client deserializes it (FUN_004203b0) as two ids, five (step, line) pairs and the finisher pair, and keys each chain on the **finisher ability id**: a 0x268 whose finisher is already known replaces that chain (FUN_00432260), and **0x269** `{i32 finisher ability id}` forgets it (FUN_00428060) [O]. The server doesn't need 0x269: it resends every chain.
- **Opening a reaction:** when an ability of a chain goes off, the server sends **0x391** `{eid64 target, i32 reaction id, i32 ability id, f32 seconds, i32 type, bool8 0, i32 0, i32 0}` (33 bytes; type 0 chain step, 8 finisher, 2 counter, 3 rescue). A chain button with a link icon pops up above the hotbar, the ability unlocks with a countdown sweep, and the client closes it itself when the time runs out.
- **Activation:** pressing the unlocked hotbar ability (or the Reactions window button) makes the client send **0x145** `{i32 reaction id}` instead of the normal 0xd0 use. The server answers 0x39a `{u8 0}` ("You successfully activated a combat reaction."; 1 = timed out), closes it with 0x392 `{i32 id}`, uses the ability and opens the next step. 0x396 closes all (sent on death).
- Verified with Justins (Warrior): Brutal Strike → (3) Savage Cut → (`!react`) Decimate. `!react` activates the newest open reaction.
- Reaction lists in the client's combat manager [O]: chain/finisher windows at +0xda4 (0x394 and 0x395 clear them), counters at +0xdb4 (0x398), rescues at +0xdc4 (0x397); 0x396 / 0x399 clear every list. 0x392 {i32 id} closes one window. 0x39a {u8} prints the result: 0 activated, 1 timed out, 2 queue full, 3 resting, 4 invalid target, 5 target dead, 6 changing forms, 7 can't meet the cost (FUN_005f4190).
- The server closes a window when it expires or its enemy dies, and answers activating one on a dead enemy with 0x39a code 5 (code change, not yet checked live).
- 0x393 `{i32 ability id}` (FUN_005f40f0 -> FUN_00427c90 picks the best rank the player's level allows -> FUN_0042f2b0) only rebuilds that ability's rows in the Chain/Finisher book lists; it changes no combat state, so the server has no need to send it [O]. Counters and rescues are in the sections below.

## Enemy casts and counters (counters verified live 2026-10-13)

The client has no cast bar for an enemy's spell (`castbars_report` research): an enemy cast is shown as an "in-flight ability" icon by the target frame (0x3a5) and a chat line (0x248). NPCs with mobs.json `spells` (`[{name, cast, damage, chance, icon}]`; the Canyon Widow has Venom Spit, a 5 s cast) may start a cast after a melee swing (`login_stub.npc_cast`) and don't swing while casting:

- 0x248 `{eid64 caster}` ("<name> begins to cast a spell."), 0x3a5 `{i32 in-flight id, i32 icon, wstr name, f32 seconds}` (one icon at a time), and, if the player has a counter ability (`content/counters.json`: Warrior Riposte I, Ranger Parry I), a counter reaction 0x391 type 2 on the caster for the cast time. Counter abilities have ability record wire #44 = 1: locked except during a counter window; a direct use gets 0x242 `{0x01}` (only as a reaction).
- Activating the counter (0x145) cancels the cast: 0x3a7 `{i32 id, i32 3 (Countered), i32 0, i32 0, bool8 0}` removes the icon, 0x3b2 `{0, 2, 0, 0, 0}` shows "Countered" in the incoming attacks queue, and "You counter Canyon Widow's Venom Spit!" (verified live with Justins and `!react`). A cast that finishes hits for its damage (combat text) and closes the counter window; 0x3a8 clears the icons.
- The 0x248 line shows in the **Combat** chat tab ("Canyon Widow begins to cast a spell.", verified live). Not seen yet: the 0x3a5 icon did not show in our tests (the Target Display window is the target frame; toggling it with `!ui` hides the frame). Interrupts (result 13) and the anti-group rows (0x3b5/0x3bc/0x3bd) are not used.

## Rescues (verified live 2026-10-13, two clients)

Rescue abilities per class are in `server/content/rescues.json` (Warrior: Taunt I) and are flagged in the ability record (wire #42 = 1; listed with the rescues, not locked). When an NPC hits a grouped player, every groupmate with a rescue ability gets a rescue reaction: 0x391 type 3 on the NPC for 6 s (`login_stub.offer_rescues`). The client never times rescues out, so the server closes them (0x392) when the window ends. Activating it (0x145) turns the NPC on the rescuer: "You rescue Ranger from Canyon Widow!" / "Justins rescues you from Canyon Widow!", then the ability itself is used.

## Heals on others (verified live 2026-10-13)

A heal (abilities.json `kind: heal`) lands on the targeted player if they are alive and in the same chunk (`login_stub.heal_target`), else on the caster: their HUD gets the health update, both get the combat text plus "You heal Justins for 30." / "Ranger heals you for 30.". Healing adds half the amount as hate on every NPC that hates the healed player (`heal_hate`). `!target <player name>` targets an online player (defensive target, 0x3e0). Regrowth I (Ranger) is now a heal in abilities.json. Buffs work the same way (the target gets the effect icon, stat bonus and expiry; "You cast X on Justins."), except stances (names with "Style") and abilities.json entries with `"self": true`, which always land on the caster (buff targeting not yet tried in game).

## Resists (2026-10-13)

A harmful NPC effect (Venom Bite) is resisted 15% of the time (`effects.RESIST_CHANCE_PLAYER`) and a player's damage over time 10% (`RESIST_CHANCE_NPC`). The server sends MsgPCResistedAbilityEffect `{eid64 other, wstr ability, wstr effect}`: **0x278** when you resisted ("YouResistedAbilityEffect"), **0x279** when your target did ("EnemyResistedAbilityEffect"), and the effect isn't applied. Verified live in the Combat chat tab: "You resist the Rending Bite effect from Ashen Wolf's Rending Bite!" (the client fills a localized string; channel 0x1f).
