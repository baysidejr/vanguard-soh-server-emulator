# Duels and caravans

> **Duels, verified live with two clients (2026-10-13):** Ranger selects Justins as the defensive target (0x5c; the `!deftarget Justins` dev command stands in for clicking him) and types `/duel` (0x3fd). Ranger sees "You challenge Justins to a duel." (0x3fe mode 0) and Justins gets the client's "Duel challenge" popup (0x3fe mode 1). Accept sends 0x3ff {0}; both get the "Duel countdown" window ("Duel with Justins beginning in 10 seconds", 0x400), then 0x401 {opponent eid} and the server sets each duelist's target (0x3e0 with the opponent's health). Ranger's auto-attack (`/autoattacktoggle`) then hits Justins: "You hit Justins for 12 damage." / "Ranger hits you for 12 damage." in the Combat tabs, and Justins' health drops on Ranger's target window. At 1 HP the server stops both auto-attacks and sends 0x405 {1} to the winner and {0} to the loser. The client's own "You have defeated %s" line was not seen in either chat tab (it may be a short on-screen message).
>
> **Caravans, verified live with two clients:** `/caravaninvite Justins` (0x4ae) shows Justins the client's "Caravan invite" popup; Accept (0x4b0 {"Ranger"}) prints "You have joined a caravan." (0x0e 0x62). The Social window's Caravan tab lists Ranger (Ranger, Leader) and Justins (Warrior, Must Logout, 02:59:33, counted down by the client) with "Destination: Sundering Wastelands" (0x4bc role, 0x4ba rows, 0x4bb leader location). The leader's Remove Member button sends 0x4b6 {member id}; Justins gets "You have left the caravan." and the two-person caravan disbands ("You do not belong to a caravan."). Caravans are saved in `server/caravans.json`; each logout saves `last_logout` and the caravan location. Dev command `!ui Social` opens the Social window.
>
> **Caravan travel (verified live):** with Justins in Ranger's caravan and offline for over 3 hours, pressing Play (mode 0) makes the server answer world 0x55 {wchar[64] name, i32 chunk x, i32 chunk y, i32 seconds left} instead of the zone connect, and the client shows its "Caravan options" dialog ("Go to caravan's last location in Sundering Wastelands", "Go to character's last location ... and leave the caravan", "Cancel"). The first sends Play with mode byte 3 (+136): Justins logs in at the caravan location (-31100, -5300) instead of his own (-28000, -3900). Mode 2 removes him from the caravan and logs in normally. Mode 3 before the 3 hours are up logs in normally.
>
> **Abilities (verified live):** damaging abilities hit the duel opponent: "Your Blade Winter I hits Justins for 15 damage." (0x27b kind 1).
>
> **Challenge timeout and cancel (verified live 2026-10-13):** an unanswered challenge expires after 30 s: the challenger gets 0x403 ("Duel challenge timed out") and the target's offer is cleared. A second /duel or /duelcancel (the same 0x3fd) before an answer cancels the challenge and tells the target "<name> has cancelled the duel challenge."; 0x3fd during a duel forfeits.

Server: `server/duel.py`, `login_stub.handle_duel_event/duel_tick/duel_strike/end_duel`; `combat.tick` returns ("pvp", opponent) for duel swings.

The rest is the client analysis (static, by a research agent).


Static analysis only (Ghidra via REA plus the scratchpad tools). [O] means read directly in code. [I] means inferred.
Wire format: VGMessages fields packed little-endian in registration order (see ZONE_MESSAGES.md).
Both send helpers `FUN_004cfb00(id,msg)` and `FUN_004cfb50(id)` end in `FUN_00409210`, which is the **zone** send ([net+0xa0cc] -> FUN_006eb1b0). The world send is `FUN_00409200` (FUN_006ee8b0).

**Correction to the brief:** a caravan is **not** a raid. Raids use `/raidinvite`, which sends the group invite `0xb0` (see GROUPS.md; the client allows 24 members in a raid). A caravan is an offline-travel feature. The VGClient.int text `TrialFeatureCaravan` says: "Caravans are a method of allowing players to travel with you while offline. After joining a caravan, the next time you login you will have the option to spawn at the caravan leader's current bind location, or spawn at your bind location. You must be offline for a minimum of 3 hours to use the caravan feature."

---------------------------------------------------------------------------------------------------

## A. Duels

**Slash commands** (table at 0x13f0354; no `/yield` or any surrender command exists in this client):

| Cmd | Handler | Sends | Payload | Notes |
|---|---|---|---|---|
| `/duel` | 0x5fccd0 | zone **0x3fd** | none [O] | Takes no argument. The server must use the sender's **defensive target**. The error texts confirm this: `NeedDefensiveTargetToDuel`, `DefTargetOtherPlayer`, `DefTargetNotLevFive`. |
| `/duelcancel` | 0x5fcce0 | zone **0x3fd** | none [O] | Its code is byte-identical to `/duel`, so the server cannot tell the two apart. Treat 0x3fd as "challenge, or cancel my pending challenge" (see the flow below). |
| `/duelaccept` (popup Accept) | 0x5fdea0 | zone **0x3ff** | MsgSingleInt `{i32 0}` [O] | |
| `/dueldecline` (popup Decline) | 0x5fdf10 | zone **0x3ff** | MsgSingleInt `{i32 1}` [O] | Also closes the "Duel challenge" popup locally. |

There is no context-menu "Challenge to duel" entry. The UI command list has only caravan and PvP-death-release items.

**Targeting the client sends** (needed because `/duel` uses the defensive target):
- `0x5c {u64 eid}` sets the **defensive** target (-1 clears it). It is sent by `FUN_004cfb90` [O].
- `0x5d {u64 eid}` sets the **offensive** target. It is sent by `FUN_004cfd00` [O].
- Clicking a pawn runs `FUN_004d01d0` [O]. For a player pawn (EntityTypes 0x20):
  - If the pawn is in my group (`FUN_004d5160`), it becomes my defensive target.
  - Otherwise, if the PvP ruleset says the pawn is hostile (`FUN_0058bf00`, see 0x408/0x409), it becomes my offensive target.
  - Otherwise, if its eid equals the **duel opponent** stored by 0x401, it becomes my offensive target.
  - Otherwise it becomes my defensive target.
  - So on a PvE server, clicking another player selects them as the defensive target, and `/duel` can then challenge them.
- For pets and charmed pawns (EntityTypes 0x1000): if the pawn's eid is in the duel list (0x406/0x407), it becomes my offensive target. Otherwise the PvP rules decide.

**Server -> client** (dispatcher `FUN_004ca200`, manager `[0x1463a3c]`, all zone):

| Id | Class / layout | Meaning |
|---|---|---|
| **0x3fe** | MsgStringAndInt `{wstr name, i32 mode}` | mode **1** (to the challenged player): prints `<color=yellow>%s challenges you to a duel.`, plays UISounds.DuelChallenge, and opens the "Duel challenge" popup with Accept=`/duelaccept` and Decline=`/dueldecline`. mode **0** (echo to the challenger): prints `<color=yellow>You challenge %s to a duel.` [O] |
| **0x400** | MsgStringAndInt `{wstr opponentName, i32 seconds}` | Accepted. Plays UISounds.DuelAccept, closes the challenge popup and opens the "Duel countdown" popup: "Duel with %s beginning in" / "%d seconds.". The client counts down locally (`FUN_004c9490`, UISounds.DuelCount below 6 s). It **stores the opponent name** (mgr+0xc), and 0x405 uses that name. Send it to both duelists [O]. |
| **0x401** | MsgSingleEntityId `{eid64 opponent}` | Duel begins. Stores the opponent at mgr+0x28, makes the opponent the local offensive target (`FUN_004cff30`, which sends **no** 0x5d), closes the countdown popup and plays UISounds.DuelStart [O]. The opponent is now attackable: clicking them selects them offensively. |
| **0x402** | none | Closes the popup and prints "Duel declined." [O] |
| **0x403** | none | Closes the popup and prints "Duel challenge timed out" [O]. |
| **0x404** | none | Closes the popup and prints "The person you challenged is already engaged in a duel or unable to accept your challenge at this time." [O] |
| **0x405** | MsgSingleByte `{u8 result}` | End of duel. **1** prints `<color=gold><18><p> You have defeated %s </p>` with the win sound. **0** prints "You have been defeated by %s" with the lose sound. Any other value prints nothing. In every case the client clears the opponent (-1), empties the duel list and resets the countdown [O]. |
| **0x406** | `{i32 n, n x eid64}` | Replaces the duel list: extra entities (pets or charmed pawns) that may be targeted offensively during the duel [O mechanics, I meaning]. |
| **0x407** | `{eid64}` | Appends one entity to the duel list [O]. |
| 0x0e | `{i16 code}` | Duel errors and notices: 0xb2 LevelFiveToDuel, 0xb3 AlreadyDueling, 0xb4 CantDuelHere, 0xb5 NeedDefensiveTargetToDuel, 0xb6 CantDuelSelf, 0xb7 DefTargetOtherPlayer, 0xb8 DefTargetNotLevFive, 0xb9 NoPendingDuel, 0xba DuelDeclined, 0xbb-0xc0 protocol errors (wrong or invalid entity), 0xc1 DuelEndedWithOpponentRealDeath, 0xc2 DuelEndedWithMyRealDeath [O, texts in VGClient.int]. |

**PvP ruleset messages** (dispatcher `FUN_0058cd90`, object `[0x1463a40]`, zone). These are optional for duels.
- **0x408** MsgPVPRulesetToClient `{bool8 pvpEnabled(+0), bool8 allHostile(+2), i32 minLevel(+4), i32 levelRange(+8), bool8 ignoreRange(+0x10), bool8 (+0x11), bool8 (+0x12)}` [O for the stores, I for the names]. Hostility (`FUN_0058bf00`) needs +0 or +1 to be set. If +2 is set, everyone is hostile. Otherwise the client looks the player up in the 0x409 table. The level gate (`FUN_0058bfa0`) needs both players at or above minLevel and a level difference within the range (or ignoreRange set). It uses the target's m_GameplayLevel and my level at +0xc.
- **0x409** `{i32 n, n x {i32 key, bool8 hostile}}`. The key is the player pawn's +0xb18 (PC vfunc 0x3d4). By field order this is most likely `m_OriginalRaceId`, so this is a race-vs-race hostility table [I].
- **0x5a8** `{bool8 inPvpArea}` sets +1 and prints "You have entered/left a PVP ENABLED area!" [O].
- If the server never sends these, every flag stays 0 and only the duel opponent can be targeted offensively. That is the right state for a PvE server.

**Sword cursor:** the hover code `FUN_00418060` shows the attack cursor only for EntityTypes 0x10000000 and a faction standing below -7999 (NPC logic) [O]. A duel does not change the cursor. Attackability comes only from the targeting route above. Nothing on the pawn needs to be replicated.

### Recommended duel flow (all zone)
1. A sends `0x5c {B}` (selecting B), then `/duel`, which sends `0x3fd`. The server checks:
   - A has a defensive target, and it is a player (else 0x0e 0xb5 or 0xb7) and not A (0xb6).
   - Both players are level 5 or higher (0xb2 or 0xb8).
   - A is not dueling (0xb3).
   - The zone allows duels (0xb4).
   - B is free: if not, A gets `0x404`.
   - If A already has a pending outgoing challenge, `0x3fd` cancels it: send `0x403` to both (or 0x402 to B).
2. Store pending(A->B) with a timer (about 30 s). A gets `0x3fe {B.name, 0}`. B gets `0x3fe {A.name, 1}`.
3. B sends `0x3ff {0}` (accept) or `{1}` (decline). If there is no pending duel, send 0x0e 0xb9.
   - Decline: send `0x402` to both (or 0x0e 0xba to A).
   - Timeout: send `0x403` to both.
4. On accept: A gets `0x400 {B.name, N}` and B gets `0x400 {A.name, N}` (N about 10). After N seconds, A gets `0x401 {B.eid}` and B gets `0x401 {A.eid}`. Optionally send `0x406` with each opponent's pets. Set server-side `duel_opponent` for both. Combat code must allow damage only between the two, and confirm offensive targets with `0x3e0` because the client sent no 0x5d.
5. End:
   - When a duelist's HP would reach 0, clamp it to 1, stop autoattack on both sides, and send `0x405 {1}` to the winner and `0x405 {0}` to the loser.
   - If either is killed by a third party: send 0x0e 0xc1 or 0xc2 plus `0x405 {2}` (clears state silently).
   - If either zones, logs out or moves far away: send `0x405 {2}`.
   - Suggested "yield" (server choice, [I]): treat `0x3fd` from a player who is already dueling as a forfeit, so the sender gets 0 and the opponent gets 1.

---------------------------------------------------------------------------------------------------

## B. Caravans

**Client -> server** (all **zone**; manager `[0x1463954]`, list at +4/+8, role at +0x10):

| Cmd / UI | Handler | Id | Payload | Notes |
|---|---|---|---|---|
| `/caravaninvite <name>` and the player context menu "Invite to Caravan" (`mo_caravan_invite` 0x185 -> FUN_00698c80 -> "/caravaninvite %s") | 0x60d490 | **0x4ae** | MsgSendSingleSGOString `{wstr name}` [O] | Uses the first token, run through the name-alias map (`FUN_00600a90`). Nothing is sent when the name is empty. There is no target fallback. |
| `/caravanaccept <inviter>` (popup Accept) | 0x60d650 | **0x4b0** | `{wstr inviterName}` [O] | Closes the "Caravan invite" popup. |
| `/caravandecline <inviter>` (popup Decline) | 0x60d770 | **0x4b4** | `{wstr inviterName}` [O] | Prints "You have declined %s's caravan invite." locally and closes the popup. |
| `/caravanleave`, and the "Leave Caravan" button (UI 0x71 -> runs `/caravanleave`) | 0x5fca30 | **0x4b5** | none [O] | No client-side confirm. |
| `/caravanremove <name>` | 0x60d8c0 | (popup) | - | With no second argument, it opens "Remove From Caravan?" ("Are you sure you want to remove %s from your caravan?..."). The buttons are `/caravanremove %s true` and `/caravanremove %s false` [O]. |
| `/caravanremove <name> true` | 0x60d8c0 -> FUN_00487c50 | **0x4b6** | MsgSingleInt `{i32 memberId}` [O] | The name is looked up (exact match) in the local member list, so ids must match 0x4ba. `false` sends nothing. |
| "Remove" button (UI 0x72, visible to the leader only) | FUN_00687330 -> FUN_00487150 | **0x4b6** | `{i32 memberId}` of the selected row [O] | No confirm popup. |

There are no promote or leader-change commands. Unused ids in the range: 0x4af, 0x4b1-0x4b3, 0x4b8, 0x4b9.

**Server -> client** (zone):

| Id | Layout | Meaning |
|---|---|---|
| **0x4ae** | `{wstr inviterName}` | Invite popup "Caravan invite": "%s is inviting you to join a caravan." (also printed in channel 0x2a) with buttons `/caravanaccept %s` and `/caravandecline %s`. Dropped **silently** if the inviter is on the ignore list. Unlike groups, the client does not auto-decline [O]. |
| **0x4bc** | MsgSingleInt `{i32 role}` | Stored at mgr+0x10. **0** = not in a caravan: clears the member list, the destination and the location, and sets CaravanMember=0, CaravanLeader=0, CaravanNotActive=1. **1** = **leader** (Member=1, Leader=1, NotActive=0). **2** = **member** (Member=1, Leader=0, NotActive=0) [O]. These gamevars show or hide the Leave and Remove buttons and the "You do not belong to a caravan." text. |
| **0x4ba** | MsgCaravanMemberInfo `{wstr name, i32 memberId, i32 classId, f32 timeRemainingSec, i32 state}` | Adds a row or updates the row with the same memberId (gamevar list `CaravanMemberList`) [O]. Columns: Name; Class (`FUN_00d07120(classId)`, adventuring class names); **State**: 0 "Unknown", 1 "Must Logout", 2 "Traveling", 3 "Can Login", 4 "Leader", other "Invalid"; **Time** = TimeRemainingStr `HH:MM:SS` from the float seconds, shown only when the state is 1 or 2 [O]. |
| **0x4b7** | MsgSingleInt `{i32 memberId}` | Removes that row [O]. |
| **0x4bb** | MsgCaravanLocationInfo `{i32 chunkX, i32 chunkY, i32 chunkZ, f32 x, f32 y, f32 z, i32 unused}` | Leader or caravan location. Sets CaravanChunkX/Y/Z and CaravanLocX/Y/Z, and sets **CaravanDestination** = chunk name of (chunkX, chunkY) (`FUN_00b70e80`), shown as "Destination:" in the window. The last i32 is never read [O]. |
| 0x0e | `{i16}` | 0x62 JoinedCaravan "You have joined a caravan.", 0x63 LeftCaravan, 0x64 NotInCaravan, 0x65 CantCaravanWithYourself, 0x66 CantCaravanWithDead [O]. |

**Window:** `VGUIAssets/Shells/Default/Windows/VGUISocialWnd.xml`, component `_caravan_list` (a Social window page). It has columns Name, Class, Status, Time, bound to `CaravanMemberList` members ID/Name/Class/State/TimeRemainingStr. It also shows "Destination: <CaravanDestination>" (or "None" when not active). `_leave_caravan_button` is visible when CaravanMember is set, and `_remove_from_caravan_button` when CaravanLeader is set.

**Character select (WORLD connection):**
- **World S->C 0x55**, raw struct `{wchar[64] charName, i32 chunkX(+0x80), i32 chunkY(+0x84), i32 secondsUntilAllowed(+0x88)}` -> `FUN_00631270` opens `_charsel_caravan_options` [O offsets, I for the name field]:
  - If seconds <= 0: "Go to caravan's last location in <chunk name>".
  - Otherwise: "You must be offline for <time> to go to caravan."
  - Plus "Go to character's last location in <zone>, and leave the caravan".
  - (World 0x53 is the same idea for vehicles: `_charsel_vehicle_options`.)
- The player's choice re-sends **Play** (world `0x19`: wchar[64] name, u32 0xffff0001, u32 0xffff0001, **u8 mode**; FUN_0060aaf0 builds it from `/select "name" <mode> ...`):
  - UI 0x233 `csco_last_caravan_loc` -> **mode 3** (spawn at the caravan).
  - UI 0x234 `csco_last_character_loc` -> **mode 2** (own last location and leave the caravan).
  - Normal Play is mode 0 (this matches the observed `...00 00 00 00`) [O].

### Recommended caravan flow
State lives at the server or world level (members can be offline). It is keyed by `caravanId` with a leader, a member list `{charId(=memberId), name, classId, lastLogout}` and the leader's location/bind.
1. A sends `/caravaninvite B`, which arrives as zone `0x4ae {"B"}`. Check that B is online (else 0x0e 4 PlayerNotFound), not A (0x65), alive (0x66), and not already in a caravan. Send B `0x4ae {A.name}`. Keep pending(B) = A.
2. B sends `0x4b0 {A.name}` (accept). If A has no caravan, create one with A as leader. Add B, send B 0x0e 0x62, then send the full state to every online member:
   - `0x4bc` with 1 for the leader and 2 for members;
   - one `0x4ba` per member, with state 4 for the leader, 1 "Must Logout" for online members, 2 "Traveling" with the seconds left until 3 h offline, and 3 "Can Login" after that;
   - `0x4bb` with the leader's current or bind location.
   - `0x4b4 {A.name}` (decline): clear pending and optionally tell A in chat.
3. `0x4b5` (leave): remove the member, send them `0x4bc {0}` and 0x0e 0x63, and send the others `0x4b7 {id}`. If the leader leaves, promote someone or disband. A caravan with only one member left is disbanded (send 0x4bc {0} to all).
4. `0x4b6 {memberId}`: leader only. Same as leave, for the target member.
5. Push timers and location: resend `0x4ba` when a member logs in or out (state 1 <-> 2), with the f32 seconds left. Resend `0x4bb` when the leader changes chunk or bind. At login, send `0x4bc` + `0x4ba` x n + `0x4bb` after the HUD is up.
6. Character select: when a caravan member presses Play (mode 0) and has been offline long enough, or always so the window can show the countdown, answer with world `0x55 {name, chunkX, chunkY, secondsLeft}` instead of event 8. Mode 3 means spawn at the leader's (bind) location. Mode 2 means spawn normally and remove the player from the caravan.

### Comparison with groups and brotherhoods
- **Same id in both directions**, like brotherhoods (0x4bd invite C->S {wstr target} / S->C {wstr inviter}). Caravans use 0x4ae the same way.
- **Accept and decline carry the inviter name** (wstr). Brotherhood 0x4be/0x4bf and group 0xb1/0xb2 carry nothing.
- **Role message:** 0x4bc {0,1,2} plays the role of brotherhood 0x6ef, but the order is different: caravan 1 = leader and 2 = member; brotherhood 1 = member and 2 = leader.
- **Member rows** are keyed by an i32 id, like brotherhood 0x6ea / 0x6e7. Removal uses the id (0x4b6), like brotherhood 0x4c1.
- **No group-style member bars:** caravans have no health or position updates, only the list in the Social window. The client checks no size limit, so the maximum size is a server-only gap; log it in CONTENT_EDITOR.md.
- **Connection:** all in-game caravan and duel traffic goes over the **zone** connection (unlike guild and social chat, which use the world connection). Only the character-select caravan option (world 0x55 plus the Play mode byte) uses the **world** connection.

## Key addresses
- Duel: dispatcher FUN_004ca200; manager [0x1463a3c] (+0 countdown f32, +4 countdown active, +8 seconds, +0xc opponent name, +0x28 opponent eid64, +0x30 list); handlers FUN_004c9690/9a90/92a0/9230/9e00/a180/a0f0; tick FUN_004c9490; list check FUN_004c9390; click routing FUN_004d01d0; offensive target FUN_004cfd00 (0x5d); defensive target FUN_004cfb90 (0x5c).
- PvP: FUN_0058cd90 (0x408 FUN_0058be50, 0x409 FUN_0058ccc0, 0x5a8 FUN_0058bda0); checks FUN_0058bf00 / FUN_0058bfa0.
- Caravan: dispatcher FUN_00488ff0, manager [0x1463954]; 0x4b7 FUN_00487e70, 0x4ba FUN_00488c90, 0x4bb FUN_00487250, 0x4bc FUN_00488460 (reset FUN_00488060); invite popup FUN_005ecdd0 (dispatcher FUN_005ef9e0); row gamevar VGUIGameVarDataCaravanMember (vtable 0x10b9244, binds FUN_00673b40, state FUN_006736f0, time FUN_00673900); remove by name FUN_00487c50, by row FUN_00487150; charselect FUN_00631270 (world 0x55), Play FUN_0060aaf0 and FUN_0051ca70.

**Defensive targets (verified live 2026-10-14):** the client only accepts a pawn as a defensive target when its EntityTypes has 0x20 (player) or 0x1000 (FUN_004cfb90). Player pawns now send EntityTypes 0x20, so clicking another player, `/targetself` and F1 work (the client sends 0x5c {u64 id}); `!deftarget` is no longer needed.
