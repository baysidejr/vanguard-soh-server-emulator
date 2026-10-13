# Pets

> **Verified live (2026-10-13):** right-clicking a "Wolf Whistle" (items.json `"pet": {name, race, model, level, health, damage}`; sold at the camp merchant) spawns Ashfang, a wolf (race 119) next to Ranger: "Ashfang answers your call.". The server sends 0x419 {pet eid, name, type 8, 0} and 0x41d {health}, and the client shows its Pet Commands bar. Ashfang follows Ranger (server-side movement, 450 units/s, 150 units behind). With an Ashen Wolf targeted, `/pet attack` (0x79) gets "Ashfang says "Yes, Master."" (0x41b 0) and the pet runs in and bites: "Your Ashfang hits Ashen Wolf for 10 damage." in the Combat tab. Right-clicking the whistle again, or `/pet dismiss` (0x7f), sends 0x41b 5 and 0x41a and removes the pet; logging out removes it too.
>
> **Pet combat (verified live):** the enemy the pet bites turns on the pet ("Ashen Wolf hits Ashfang for 4 damage.", written by the server because the client only writes 0x27b combat text that involves the player) and ignores the owner while it fights the pet. The pet health bar (paw icon under the player bars) follows 0x41d. At 0 health "Ashfang has been slain!" and the pet is removed.
>
> **Pet abilities (2026-10-13):** a pet item's `pet.abilities` ([{name, icon, damage, refresh}]; the Wolf Whistle's Ashfang has Savage Bite) are sent on summon as 0x429 (MsgAbilityInfo, ability ids from 990000), which adds them to the pet's ability list; a pet bar with the ability icon appears beside the paw button. Using one sends **0x88** `{i32 ability id}`: the pet attacks its target (or yours) with it, the cooldown starts (0x42c `{i32 id, f32 remaining, f32 total, f32 0}`): "Your Ashfang's Savage Bite hits Robed Wanderer for 24 damage." (verified by clicking the pet bar slot; the pet runs in first when its target is up to 3000 units away). `!pet <item>` summons an item's pet without the item.

> **Minions (verified live 2026-10-13):** right-clicking a minion item (items.json `"minions": {name, race, model, level, health, damage, count, seconds}`; the test item is the "Bone Charm": two Bone Servants, skeleton race 101, for 60 s) spawns that many NPCs and sends 0x419 type 6 per minion with the timer, plus 0x41e {eid64, u8 hp}. The client opens the "Minions" window with one entry per minion (name, health bar) and the command row. Minions follow and fight like the pet (`companion_tick`, shared with the pet), at most 4 at once. They return to dust when their time runs out (0x41f {eid64}). The window's buttons are the /minions commands (0x85 attack, 0x81 back off, 0x82 follow, 0x83 resume, 0x84 dismiss; no payload, all minions): Dismiss gave "Your minions return to dust." and closed the window.

> **Pets from class abilities (verified live 2026-10-13):** abilities.json `"kind": "pet"` with a `"pet"` spec (same fields as a pet item) summons the companion when the ability resolves. The client's ability packages have Necromancer "Awakenabomination I" (640009) and Shaman "Summonattendantofhayatet/rakurr/tuurgin I"; casting Awakenabomination I (3 s) printed "Abomination answers your call." and showed the pet bar. The pet specs are placeholders (CONTENT_EDITOR.md). Dev: `!learn <name>` now also finds other classes' abilities.
>
> **Not done:** minion abilities.

Server: `server/pets.py`, `login_stub.summon_pet/dismiss_pet/handle_pet_event/pet_tick`.

The rest is the client analysis (static, by a research agent).


[O] means observed in code. [I] means inferred.

All pet logic in the client lives in one manager object, the global `*(0x14639ac)`. The S->C dispatcher is `FUN_0057ca30`, which handles 0x418-0x435. The client never runs pet AI. Following, attacking and staying are all done by the server. The client only shows UI state and sends commands.

## Pet categories (MsgPetNew u8 `type`, stored at manager+0x24)

| type | meaning | UI effect [O] |
|---|---|---|
| 6 | **automatic pet / minion** | Not stored as "the pet". It is appended to the minion vector (+0x74). It appears in `PetAutoList` with Name, HP and Timer. `bHaveAutomaticPet` becomes 1, which shows the "Minions" window (VGUIMinions.xml). |
| 8, 0xb | **persistent / controllable pet** | `bHavePet`=1 and `bHaveControllablePet`=1. This shows the Pet Commands bar and the Pet Abilities bar (VGUIPet.xml). `PetType`="Persistent". 0x435 is accepted only for these types. |
| 0, 1 | basic pet | `bHavePet`=1 (health bar and dismiss X in VGUIPlayerStatus.xml). No command bar. `PetType`="BasicCommands". |
| other | general pet | Same as 0/1, but `PetType`="General". |

For type != 6, manager state is: +0 hasPet=1, +4 std::wstring name, +0x20 health byte (set to 0xFF on new), +0x24 type, +0x30/+0x34 pet eid. The client then refreshes the game vars PetType, PetName, bHavePet/bHaveControllablePet and PetStatus.

## S->C messages (zone_event id, payload)

| id | layout | meaning |
|---|---|---|
| **0x419** MsgPetNew | `eid64 pet, wstr name, u8 type, f32 timer` | [O] "You have a pet". If type==6, adds a minion record: eid, name, hp=0xFF, timer total=remaining=f32 (default 100.0); that record is shown in the minion entry's "Timer" column. Otherwise sets the main pet; the f32 is ignored. `FUN_0057c6a0` |
| **0x41a** | none | [O] Pet gone. Clears hasPet, name, type(=0xff) and health, and clears the pet ability list (`FUN_0057be60`). Refreshes all vars, so the windows hide. `FUN_0057c5e0` |
| 0x418 | `wstr name` | [O] Pet renamed. Updates the name and prints "Pet's name changed: <name>". Reply to C->S 0x80. |
| **0x41b** | `u8 result` | [O] Pet command reply. 0: `"<name> says "Yes, Master.""` (or "Pet command succeeded."). 1: "You don't have a pet.". 2/3/4/7: `"<name> says "I'm afraid I can't do that, Master.""` / "Pet command failed.". 5: `"<name> returns to dust."` and clears hasPet and name. 5 does not refresh UI vars, so follow it with 0x41a. |
| **0x41d** | `u8 health` | [O] Pet health, 0..255. Stored at +0x20 and pushed to `PetStatus` as StatusInfo(max 0xFF, value). This is the pet health bar in the player status window. |
| 0x41e | `eid64 minion, u8 hp` | [O] Minion HP, 0..255, for the matching record in `PetAutoList`. |
| 0x41f | `eid64 minion` | [O] Removes a minion from the list (bHaveAutomaticPet is recomputed). |
| 0x429 | MsgAbilityInfo (same as 0x215, docs/ABILITIES.md) | [O] Adds an ability to `PetAbilityList`, sorted by name. Handle is at +0x70 and ability id at +0x10c. `FUN_0057c810` |
| 0x42b | `i32 handle` | [O] Removes the pet ability with that handle (+0x70). |
| 0x42c | `i32 abilityId, f32 a, f32 b, f32 c` | [O]/[I] Pet ability timer. `a` goes to +0x124/+0x11c when it is >= the current value; the client blocks 0x88 while +0x124 > 0 ("That is not done refreshing yet."). So `a` is the remaining cooldown [I]. `b` goes to +0x134 and `c` is passed to `FUN_005792f0` [I]. |
| 0x42e | `i32 abilityId, f32 frac` | [I] Sets ability +0x128/+0x12c = frac*100 (a progress percent). |
| 0x434 | `i32 n` | [O] `PetNumGraftsAllowed` (Pet "Grafts" inventory window). Related: 0x1d2/0x1d3 graft add and remove (VGClientInventory). |
| 0x435 | `i32 abilityId` | [O] For pet types 8/0xb only. Marks that ability as the pet's default/auto attack (+0x17a=1, `FUN_0057b920`). |
| 0x242 code 0x2f | `u8` | [O] Ability failure "AbilityCorpseWasPet" ("The corpse you have targeted was a pet and can't be used for that."). Related codes: 0x1e CorpseAlreadyConsumed, 0x1f MustHaveCorpseTarget, 0x2c ToPowerful, 0x2d ToHighLvl, 0x2e CorpseNotNPC (necro corpse abilities). |

## C->S messages

`/pet <cmd>` (`FUN_0060b8c0` -> `FUN_0057a510`) checks hasPet locally. If there is no pet it prints "You don't have a pet." and sends nothing. All commands are `FUN_004cfb50`, with no payload [O]:

| id | /pet arg | UI button |
|---|---|---|
| 0x76 | FOLLOW | PetFollowMe |
| 0x77 | STAY | PetStay |
| 0x79 | ATTACK | PetAttack (attack the player's current target [I]) |
| 0x7a | BACKOFF | PetBackoff |
| 0x7b | ASSISTME | PetAssistMe |
| 0x7c | ASSISTMEALWAYS | PetAssistMe (toggle) |
| 0x7d | GUARD | PetGuard |
| 0x7e | TOGGLEDEFENDSELF | defend-self toggle |
| 0x7f | DISMISS | PetDismiss and the X button by the pet health bar |

Anything else prints "Invalid pet command.". There is no 0x78 sender.

`/minions <cmd>` (`FUN_0057a710`) does no local check and sends no payload [O]: 0x85 ATTACK, 0x81 BACKOFF, 0x82 FOLLOW, 0x83 RESUMEBEHAVIOR, 0x84 DISMISS. Anything else prints "Invalid minion command.".

`/petname <name>` (`FUN_0057b4c0`) requires hasPet and sends **0x80** `wstr name` (MsgSendSingleSGOString) [O].

Pet ability bar [O]:
- **0x88** `i32 handle`: activate a pet ability (`FUN_00579710` sends the list entry's +0x70 handle, not the +0x10c ability id; the server sends handle = id so either works). It is suppressed client-side while that ability's cooldown is > 0.
- **0x86** / **0x87** `i32 abilityId` (the +0x10c id): toggle the pet default/auto attack on or off (`_pet_default_attack`, `FUN_0057bd??`, around 0x57bdb0). The client flips +0x17a locally.

## Replicated pawn properties (SGONPCPawn, own NetFields 118-123)

`m_bShowIOParticle`(118), `m_LockoutTimerId`(119), **`m_OwnerEntityIDHighInt`(120)**, **`m_OwnerEntityIDLowInt`(121)**, `m_bIsAggro`(122), `m_FactionId`(123).

- Source (SGOUnrealAbstractionLayer.u script text): `reliable if (bNetDirty && Role==ROLE_Authority) m_FactionId, m_bIsAggro, m_OwnerEntityIDLowInt, m_OwnerEntityIDHighInt, ...`.
- Native offsets [O]: FactionId +0xb04, bIsAggro +0xb08 bit0, OwnerLow +0xb0c, OwnerHigh +0xb10 (nativereplication `FUN_00bf3360`; setter `0xbcd2b0`; 64-bit getter `0xbcd2d0`, vtable slot 0x117b8f0).
- I found no client consumer of the owner id outside replication. There are no direct callers of the getter, and no script uses it. Sending it is harmless and correct, but **the client does not need it** to show the pet window. There is no `bIsPet` or `m_PetOwner` property. "This NPC is your pet" is conveyed only by 0x419.

## Minimal recipe: summon a controllable pet that follows

1. Spawn the pet NPC as a normal world NPC (`zone.open_npc` / `npc_bunch`). Use a new entity id and a pet race/mesh. Set `npc.props |= {"m_OwnerEntityIDLowInt": eid & 0xffffffff, "m_OwnerEntityIDHighInt": eid >> 32, "m_FactionId": <friendly>, "m_bIsAggro": False}`, where eid is the owner player's entity id. Broadcast it to everyone in the zone like any NPC.
2. To the owner: `zone_event(0x419, vgmsg.pack("qwbf", (pet_eid, "Skeleton", 8, 100.0)))`. This gives a health bar, dismiss X, the Pet Commands bar and the Pet Abilities bar. Use type 0 for a health bar only, or 6 for a minion-list entry.
3. `zone_event(0x41d, bytes([255]))` sets full health. Re-send it as `round(255*hp/max)` whenever the pet's HP changes.
4. Optional: send 0x429 MsgAbilityInfo per pet ability (built with vgmsg.ability_info), plus `0x435 i32 id` for the default attack.
5. Server pet AI, per tick, with mode starting at FOLLOW:
   - FOLLOW (0x76): `combat.chase_step(pet, owner)`. Stop within about 2-3 m; do not attack.
   - STAY (0x77): stop.
   - ATTACK (0x79): target = owner's current target; chase_step and swing using the NPC combat code.
   - BACKOFF (0x7a): drop the target, then FOLLOW.
   - GUARD (0x7d): hold position and attack aggressors.
   - ASSISTME / ASSISTMEALWAYS (0x7b / 0x7c): attack the owner's target, once or each time.

   Reply to each command with `0x41b 0` (prints `"<name> says "Yes, Master.""`). Reply `0x41b 1` if there is no pet, or 2 if the command is impossible.
6. Rename (0x80 wstr) -> store it and send `0x418 wstr`.
7. Dismiss (0x7f), or pet death: send `0x41b 5` ("returns to dust"), then `0x41a`, then close or despawn the actor for all clients. For minions, send `0x41f eid`.
8. Re-send 0x419 and 0x41d on zone-in or reconnect. The client keeps no pet state across sessions.
