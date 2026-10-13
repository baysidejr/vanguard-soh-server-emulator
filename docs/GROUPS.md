# Group (party) protocol: VGClient.exe static analysis

> **Verified live with two clients (2026-10-12):** `/invite Ranger` (0xb0) → 0x6b3 popup on the invitee; `/groupacceptinvite` (0xb1) → 0x6b2 + 0x6bb rows and 0x6cb leader: both group windows show the other member with bars, leader star, "You have formed the group" / "You have joined the group". Group chat (`gsay` via the world server) arrives, but channel 8 prints "[???]" (open). Implemented in `server/group.py` and `login_stub.handle_group_event`.


Tags: [O] = observed in decompile/bytes, [I] = inferred.
Zone event framing: `u16 2, u32 id, u32 len, payload`. wstr = UTF-16LE + 0x0000. eid64 = u64 LE. bool8/u8 = 1 byte.
Group manager object = global `DAT_0146394c` (ecx of all group fns). S->C group dispatcher = `FUN_004e2910` [O].

## 1. Client -> server (zone connection, sent via FUN_004cfb00 / FUN_004cfb50)

Slash command table at 0x13ee4b0 (UTF-16 names, 24-byte entries {-1, handler, name, 0, flags, 0}) [O].

| Command(s) | Handler | Event | Payload | Notes |
|---|---|---|---|---|
| `/invite`, `/groupinvite`, `/raidinvite` [name] | FUN_006070a0 -> FUN_004d8fb0 | **0xb0** | wstr target name (MsgSendSingleSGOString) [O] | No name -> uses current target's name (FUN_00b73400/FUN_004d2250); self -> "CantGroupInviteSelf" locally. Client prints "TryInviteFormGroup"/"TryInviteGroup" locally; no server echo required. Client-side checks: GroupFull at 6 members (24 raid), must be leader if grouped. |
| `/groupacceptinvite` (also popup "Accept" button) | 0x5fc2c0 -> FUN_004d91f0 | **0xb1** | none (len 0) [O] | Only sent if an invite is pending (mgr+4 flag set by 0x6b3); clears bGroupInvitePendingSelf. |
| `/groupdeclineinvite` (popup "Decline") | 0x5fc2d0 -> FUN_004d92d0 | **0xb2** | none [O] | Also auto-sent by 0x6b3 handler if inviter is on ignore list (FUN_0057f7d0). |
| `/groupleave` | 0x5fc2e0 -> FUN_004d17d0 | **0xae** | none [O] | Only when grouped. |
| `/groupdisband`, `/raiddisband` | 0x5fc320 -> code at 0x4d1800 | **0xaf** | none [O] | Only when grouped and leader (else "NotInGroup"/"MustBeGroupLeader" locally). |
| `/groupboot` [name] | FUN_00607370 -> FUN_004d93b0 | **0xb3** | wstr name [O] | leader/raid-assistant only |
| `/grouppromote`, `/groupleader` [name] | FUN_00607580 -> FUN_004d94e0 | **0xb4** | wstr name [O] | leader only |

## 2. Group chat (/g, /gsay, /groupsay, /partysay) [O]

Handler 0x5fce20: `swprintf("gsay %s", text)` then `FUN_00409240(0x14, buf, bytelen)` ->
FUN_006ee6d0 on **ClientWorldConnectionManager** (subobject +0xa4 of the net root; zone mgr is +0x130, RTTI-confirmed) -> **PacketSGOChatMessage, app-message type 6**:

```
u16 6 | u32 0x14 | u32 byteLen | UTF-16LE "gsay <text>" + 0x0000   (byteLen = 2*chars+2)
```
Goes over the **WORLD** server connection (UDP 10100), NOT the zone connection [O].
Same packet carries `/raidsay` ("rsay %s", 0x5fcdf0) and `/join` (raw text, 0x5fc6a0). `/say` is unchanged (zone event 0x74).

Display back to clients (zone conn):
- **0x0f** {wstr text, wstr speaker, i32 channel} with **channel 8 = "GroupSay"** (FUN_0041af60 switch: 3 Say, 4 Shout, 5 Emote, 8 GroupSay, 9 RaidSay, 0xb GuildSay, 0xf Tell, 0x11 Mindsay, 0x27 Broadcast, 0x5d LFG) [O for switch, I that 0x0f feeds it — matches verified 3/5].
- Alternative: **0x68a** {wstr} prints the string into chat with channel 8 (group colour), no speaker formatting (FUN_004d7dd0 -> FUN_004cfb70(text, 8)) [O].

## 3. Server -> client events (all via FUN_004e2910)

### Invite
- **0x6b3 MsgGroupSendInvite** -> invitee. Handler FUN_004d9840 [O]. Registration FUN_004d0f00 [O]. Wire order:
  `eid64 inviterEid, wstr inviterName, i32 unk(0), i32 memberCount, bool8 isRaid, 24 x wstr memberNames, 24 x i32 memberLevels, 24 x i32 memberClassIds`
  Shows "_group_invite_confirm" popup (name + "<color=cyan>Name</color> Level N Class" lines for memberCount entries), prints "InvitedYouToGroup", sets pending flag. Ignored silently if the invitee is already grouped. If the "auto accept group invites" option is on, client immediately sends 0xb1.
- **0x6b5 MsgSingleByte** -> inviter on failure: 1 MustBeGroupLeader, 2/4 PersonAlreadyGrouped, 3 GroupFull (FUN_004d49d0) [O].
- **0x6b9 MsgStringAndTwoInts** -> inviter on decline: {wstr name, i32 ?, i32 reason} reason 0 ClientInit (normal decline), 1 AlreadyGrouped, 2 PendingInvite, 3 WrongRace, 4 LeftGame (FUN_004d7c70) [O switch; which int is the reason = I, the second].
- **0x6b7 MsgSingleInt** -> invitee: clears pending invite; value 0 prints "GroupInviteTimedOut" (FUN_004d9c90) [O].

### Forming / joining
- **0x6b2 MsgSingleEntityId {eid64 groupId}** -> the inviter when a NEW group forms (FUN_004e1bc0) [O]. Stores groupId (mgr+0x58), creates the SELF row from local player data, sets grouped + leader-self, prints "YouFormedGroup".
- **0x6bb MsgGroupMemberAdded** -> add one other member row (FUN_004e1fa0) [O]. If receiver is not yet grouped, it ALSO creates the self row, sets grouped (not leader) and prints "YouJoinedGroup"; otherwise prints "OtherJoinedGroup". Registration FUN_004d0bc0 [O], copy into row FUN_004dad50 [O], row UI FUN_006d4be0 [O]. Wire order:

| # | type | row off | meaning |
|---|---|---|---|
| 1 | wstr | +0x10 | Name [O] |
| 2 | eid64 | +0x00 | member entity id (key for all updates) [O] |
| 3 | i64 | +0x08 | second id; self row uses player-info +0x10 -> send character id (= eid here) [I] |
| 4 | i32 | +0x2c,+0x60 | UI list row handle/ID; must be unique per member (self uses player-info +8). Use e.g. low 32 bits of eid [I] |
| 5 | i32 | +0x30 | sub-group number; row only shown if == mgr+0x60 (0 for normal groups) -> send **0** [O] |
| 6 | u8 | +0x48 | HP bar value, bar max 255 (255 = full) [O] |
| 7 | i32 | +0x4c | unknown; self uses -1 -> send -1 [I] |
| 8 | i32 | +0x50 | class id (AdvClass, FUN_00d07120 -> class name) [O] |
| 9 | i32 | +0x54 | level [O] |
| 10 | u8 | +0x58 | Endurance bar 0..255 [O] |
| 11 | u8 | +0x59 | Energy bar 0..255 [O] |
| 12 | u8 | +0x5c | "phy_sta" bar 0..255 (send 255) [O] |
| 13-15 | f32 x3 | +0x34..+0x3c | world position x,y,z (map/minimap blip) [O] |
| 16-17 | i32 x2 | +0x40,+0x44 | chunk X, chunk Y (map bounds check, FUN_0052fde0) [O/I] |
| 18 | bool8 | +0x70 | flag (cleared on leader change) [I: main assist?] |
| 19 | bool8 | +0x6e | flag [I] |
| 20 | bool8 | +0x6f | flag [I] |

  Distance/direction columns are computed locally (+0x64/+0x68), not on the wire.
- **0x6cb MsgSingleEntityId {eid64 leaderEid}** -> mark another member as leader (+0x6c IsLeader icon), prints "OtherGroupLeader", clears leader-self (FUN_004df910) [O].
- **0x6a4** (no payload) -> you are leader ("YouGroupLeader") [O].
- **0x6d7 MsgGroupMemberGroupInfoPreJoin {eid64 groupId, eid64 leaderEid, i32 subGroup, bool8 isRaid}** -> sets mgr fields only, no UI (FUN_004d4aa0) [O fields; order I]. Optional before 0x6bb.
- **0x6a0** (no payload) "YouJoinedGroup" sets flags but does NOT add the self row -> prefer the 0x6bb auto-join path [O].

### Periodic member updates (key = eid64)
- **0x695 MsgGroupMemberPositionUpdate {eid64, f32 x, f32 y, f32 z, i32 chunkX, i32 chunkY}** (FUN_004d60d0) [O].
- **0x68b {eid64, u8}** HP 0..255 (+0x48) [O]
- **0x68c {eid64, u8}** Endurance (+0x58) [O]
- **0x68d {eid64, u8}** Energy (+0x59) [O]
- **0x68e {eid64, u8}** phy_sta (+0x5c) [O]
- **0x68f {eid64, i32}** level (+0x54) [O]
- **0x690 {eid64 old, eid64 new}** member entity id changed (zoning) [O]
- **0x691 {eid64}** "%s died!!" [O per doc]

### Removal / disband
- **0x6bc MsgEntityIDAndInt {eid64, i32}** -> other member left: "OtherLeftGroup", row removed (FUN_004df780) [O].
- **0x6bd {eid64, i32}** -> other member booted [O per doc strings].
- **0x6a1** (none) -> you left: "YouLeftGroup", clears group (FUN_004df720) [O].
- **0x6a2** (none) -> you were booted [O doc].
- **0x6be** (none) -> "GroupDisbanded", clears group (FUN_004e0b40) [O].

## 4. Minimal server recipe (2 players A invites B)
1. A: `/invite B` -> zone C->S 0xb0 {wstr "B"}. Look up B by name (case-insens.). If B grouped -> A: 0x6b5 {u8 2}.
2. B <- 0x6b3 {A.eid, "A", 0, n, 0, names[24], levels[24], classes[24]} (n=1 with A's own entry if A ungrouped; pad unused with empty wstr / 0).
3. B accepts -> 0xb1 (empty). Decline -> 0xb2 -> A: 0x6b9 {"B", 0, 0}.
4. On accept, if A ungrouped: A <- 0x6b2 {groupId} (A becomes leader; self row). Then:
   - A <- 0x6bb(member=B)
   - B <- 0x6bb(member=A) (B auto-joins, self row), then B <- 0x6cb {A.eid} (leader icon).
   For later joiners: new member gets 0x6bb for every existing member then 0x6cb leader; every existing member gets 0x6bb(new).
5. Every ~1 s per member: 0x695 position to the others; 0x68b/0x68c/0x68d on vital changes (value = cur*255/max).
6. 0xae leave -> leaver 0x6a1; others 0x6bc {eid, 0}; if 1 left -> 0x6be to the remaining one. 0xaf disband (leader) -> all 0x6be.
7. 0xb4 promote {name} -> all 0x6cb {newLeader} and new leader 0x6a4. 0xb3 boot {name} -> booted 0x6a2, others 0x6bd {eid,0}.
8. Group chat: WORLD conn type 6 {u32 0x14, u32 len, "gsay <text>"} -> strip "gsay ", send each member (zone) 0x0f {text, speakerName, 8}.

## Raids (verified live with two clients, 2026-10-13)

With Justins in Ranger's group, `/raidcreate` (0xac) makes the server send 0x6c2 to every member: both get "You have joined the raid.". `/readycheck` (0xa8) sends the leader 0x6c4 ("You have requested a raid ready check.") and the others 0x6c5 {leader row id}, which opens the client's "Ready Check" popup ("Ranger has requested a ready check. Are you ready?"). The answer 0xa9 {initiator row, status} is passed to the leader as 0x6c6 {row, status}: when nobody clicks, the client answers AFK after 15 s and the leader sees "Justins is afk!". The limit is 24; new raid members get 0x6d7 and a free raid group (0x6bb field 5). Moving members between raid groups (0xaa -> 0x6c1) and raid roles (0xab -> 0x6a6, toggled) are coded but untested; `/raidalert` (0xa7 -> 0x551 on-screen text) showed nothing in the one test.

The rest of this section is the client analysis (static, by a research agent), including mentoring and the Find (LFG/LFM) window, which are not implemented yet.


[O] = read in code. [I] = inferred. Wire = SGO fields packed LE in registration order (see ZONE_MESSAGES.md).
"rowId" = the i32 member key that the server assigns in 0x6bb field #4 (row+0x2c). Every raid i32 message
uses it. The client looks rows up with FUN_004d4ef0(rowId) over mgr+0xf4 (mgr = DAT_0146394c) [O].

### Which connection to use
- **Group/raid S->C** (all ids handled by FUN_004e2910): this function is called from zone FUN_00622350 (0x6224a5) AND
  from world-social FUN_00625350 (0x625415) [O]. Both connections work. Use **zone**, like the existing group code.
- **0x500/0x501/0x502** (FUN_00588c50): called from zone (0x6230fd) and world-social (0x625955) [O]. Use **world type 5**,
  because the request arrives there.
- **0x5ca mentor popup, 0x551 screen alert** (FUN_005ef9e0): world-social routes only 0x508 and 0x509..0x514 to it, and
  world FUN_0062aaf0 routes only 0x5e2. So these are **zone only** [O].

### A. RAIDS

### C->S (zone, FUN_004cfb00/FUN_004cfb50 unless noted)
| Cmd / UI | Id | Payload | Client-side checks |
|---|---|---|---|
| /raidcreate (FUN_004d1760), Raid window `_raid_create` button | **0xac** | none | Must be grouped ("NotInGroup"), not already a raid ("GroupAlreadyRaid"), and leader ("NotGroupLeader") [O] |
| /raidinvite = /invite (FUN_006070a0) | **0xb0** | wstr name | Same as group invite. Group-full limit is 24 when in a raid [O, GROUPS.md] |
| /raiddisband = /groupdisband | **0xaf** | none | Leader only [O] |
| /raidalert text (FUN_00606d80 -> FUN_004dc040) | **0xa7** | wstr text | Empty text -> "RaidAlertNeedText". Must be in a raid ("MustBeInRaid") and be leader or raid assistant ("RaidNoPermission") [O] |
| /readycheck (FUN_004dc120), `_raid_ready_check` button | **0xa8** | wstr "" (empty, 2 bytes 00 00) | Must be grouped and be leader or raid assistant. Raid is NOT required [O] |
| Ready-check popup answer (FUN_004d51e0) | **0xa9** | i32 initiatorRowId (mgr+0xdc, from 0x6c5), i32 status | Status comes from the button value (1 ready / 0 not ready [I]). The client sends **3 (AFK)** automatically after 15 s [O] |
| /raidassistant [name\|target] (FUN_00606ba0 -> FUN_004d68c0) | **0xab** | i32 rowId, i32 **2** | In a raid and leader (mgr+3) only [O] |
| Menu: promote main tank (FUN_004d6920) | 0xab | i32 rowId, i32 **3** | In a raid, leader or raid assistant [O] |
| Menu: promote main assist (FUN_004d6990) | 0xab | i32 rowId, i32 **1** | Grouped, leader or raid assistant [O] |
| Menu `mo_raid_move_to_group_1..4` (FUN_004d6740) | **0xaa** | i32 rowId, i32 groupIndex 0..3 | In a raid, leader or raid assistant [O] |
| /raidsay, /rsay (0x5fcdf0) | WORLD type 6, 0x14 | "rsay <text>" | Same path as gsay [O, GROUPS.md] |
| (/mark-style target marker, FUN_0060c150) | 0x592 | eid64 self, eid64 target, i32 mark (0 STAR..7 PLUS, -1 CLEAR) | Leader or assistant. Not raid-specific [O] |

### S->C (zone recommended; dispatcher FUN_004e2910)
| Id | Layout | Meaning |
|---|---|---|
| **0x6c2** | none | Group becomes a raid. Prints "JoinedRaid", sets mgr+2 isRaid and the UI var `IsRaid`, and adds every row to the raid lists [O]. Send it to all members in reply to 0xac. |
| **0x6d7** PreJoin | eid64 groupId, eid64 leaderEid [I], i32 subGroup, bool8 isRaid | Sets mgr+0x58 (group id), mgr+0x28 (second eid), mgr+0x60 (**my sub-group**) and mgr+2 (isRaid) [O]. Send it to a new raid member BEFORE its 0x6bb rows, so that its group window shows the right sub-group and it prints "YouJoinedRaid". |
| 0x6b3 invite | (as GROUPS.md) with bool8 isRaid=1 | Popup text "InvitedYouToRaid" [O]. Lists up to 24 members. |
| **0x6bb** member row | (as GROUPS.md) | **Field #5 i32 = raid group 0..3** (row+0x30) [O]. The Raid tab puts the row into `RaidGroupMemberList%02d` (00..03, VGUIRaidManagement.xml) using that value. The group window shows only rows whose value equals mgr+0x60. **Flags #18 = raid assistant (+0x70), #19 = main assist (+0x6e), #20 = main tank (+0x6f)** [O, from the 0x6a6 handler]. Prints "OtherJoinedRaid"/"YouJoinedRaid" when isRaid is set. |
| **0x6c1** | i32 rowId, i32 unused(0), i32 newSubGroup | Moves a member to another raid group (FUN_004dc640) [O]. If rowId is self: sets mgr+0x60 and rebuilds the group window and map blips. Otherwise it moves the row between lists. |
| **0x6a6** | i32 unused(0) [I], i32 rowId, i32 role | **Toggles** the role flag: 1 main assist, 2 raid assistant, 3 main tank (FUN_004de1b0) [O]. Prints "YouRaidAssistant"/"YouNoRaidAssistant"/"OtherRaidAssistant"... When rowId is self, sets mgr+0xea (raid assistant permission) and the UI var `bIsGroupRaidAssistantSelf`. |
| 0x6cb {eid64} / 0x6a4 (none) | | Leader. Prints "OtherRaidLeader"/"YouRaidLeader" when a raid [O]. |
| 0x6bc / 0x6bd / 0x6a1 / 0x6a2 / 0x6be | | Leave/boot/disband. Raid variants print "OtherLeftRaid", "YouBootedFromRaid", "RaidDisbanded" [O]. |
| **0x6c4** | none | To the ready-check initiator: prints "You have requested a raid ready check." and fills `RaidNotReadyList` with all members (FUN_004d5a00) [O]. |
| **0x6c5** | i32 initiatorRowId | To the others: "You have received a raid ready check.", the `RaidReadyCheckPopup`/`_ready_check_confirm` popup, a sound, and a 15 s timer. Stores the rowId in mgr+0xdc [O]. |
| **0x6c6** | i32 responderRowId, i32 status | To the initiator: 0 RaidMemberNotReady, 1 RaidMemberReady (moves the row to `RaidReadyList`), 2 RaidMemberTooFarAway, 3 RaidMemberAfk (FUN_004d5c90) [O]. |
| 0x0f chat | wstr text, wstr speaker, i32 **9** | RaidSay display "[Raid][speaker]: text" [O, CHAT.md]. |
| 0x551 | wstr text, u8 soundIdx | On-screen alert (FUN_005e7470 -> FUN_005e58f0; the u8 selects a UISounds entry). **Zone only.** Recommended for /raidalert [I]. 0x556 {eid64} is the built-in "<name> calls for help!" alert [O]. |

### Recommended server flow (raid)
1. Leader sends 0xac. Check: grouped, leader, not a raid. Set raid=True. Send **0x6c2** to every member. Existing members keep sub-group 0.
2. 0xb0 invite while in a raid: send 0x6b3 with isRaid=1 (limit 24). On 0xb1 accept, choose the first sub-group with fewer than 6 members (0..3). Send the joiner **0x6d7 {raidId, leaderEid, sg, 1}**, then 0x6bb for every member (each with its own field #5 group and role flags), then 0x6cb {leader}. Send every existing member 0x6bb(new member, field #5 = sg).
3. 0xaa {rowId, g}: leader or assistant only. Update the member and send **0x6c1 {rowId, 0, g}** to all members (including the moved member).
4. 0xab {rowId, role}: role 2 needs the leader; roles 1/3 need the leader or an assistant. Flip the flag on the server and send **0x6a6 {0, rowId, role}** to all members (the client toggles, so send exactly once per change).
5. 0xa8 ready check: initiator <- 0x6c4. Each other member <- 0x6c5 {initiatorRowId}. On 0xa9 {initRowId, status}, send the initiator **0x6c6 {responderRowId, status}**. The server may itself send status 2 (too far).
6. 0xa7 {text}: in a raid, leader or assistant. Send every member, on zone, 0x551 {"<color=red> <18> <p> " + text, 7} [I format]. Alternatively send 0x0f on channel 9.
7. World type 6 "rsay <text>": strip "rsay ", then send all raid members 0x0f {text, speaker, 9}.
8. 0xaf disband: all members <- 0x6be.

### B. MENTORING
| Dir | Conn | Id | Layout | Meaning |
|---|---|---|---|---|
| C->S | zone (FUN_00409210 -> FUN_006eb1b0) | **0x5c8** | wstr targetName | Context menu "Request Mentor" (`mo_request_mentor`, menu id 0x18d -> FUN_00691270 -> FUN_0063d510) on a **group member** row. The option is shown only when the requester's level (player+0xae8) is > 10 [O]. |
| S->C | **zone only** | **0x5ca** | wstr requesterName | The target gets "<name> has requested that you mentor them. Would you like to accept?" in chat, plus a "Mentor Request" popup whose buttons run /mentoraccept and /mentordecline (FUN_005eb2b0) [O]. |
| C->S | zone | **0x5c9** | bool8 accept (1 = /mentoraccept, 0 = /mentordecline) | Closes the popup. No pending-state check on the client [O]. |
| C->S | zone | **0x5cb** | none (len 0) | "Stop Mentoring" (`mo_stop_mentoring`, id 0x18e -> FUN_00692c70 -> FUN_00639a70) [O]. |

No dedicated mentor S->C message (level change, mentor icon) was found. There are no "mentor" strings beyond the ones above.
The level change must go through the existing level messages [I]: group 0x68f {eid, level} to the group, the
character-sheet/level update for the player (0x713 "Your %s level is now %d" or a MsgScore 0x3de resend), and /who level.
Server flow [I]: on 0x5c8, check that both players are in the same group and the target is online, then send the target
0x5ca {requesterName}. On 0x5c9=1, the higher-level member mentors down to the lower member's level: update the levels,
then send 0x68f to the group and the level update to the mentor. Report the result with a chat line (0x0f channel 0 /
FUN_004cfb70 text). On 0x5c9=0, send the requester a text line saying the request was declined. On 0x5cb, restore the real
level.

### C. LFG / LFM / Find window

### C->S (WORLD type 5 via FUN_00409300). Both requests use the same struct, MsgLfg (fields FUN_0057cdd0) [O]
```
u8  bSearch        1 = Find-window "Search" (FUN_00584620 / FUN_00584e10); 0 = flag/preference update (toggle)
u8  bFlag          0x503: my LFG flag (social mgr DAT_01463a30 +3); 0x504: my LFM flag (+4)
32 x { i32 classId, i32 dungeonId, i32 questId }   interleaved per index; -1 = empty   (total 2 + 384 = 386 bytes)
```
- **0x503** = LFG (I want a group). Preferences come from `_find_lfg_preferred_classes/_dungeons/_quests` (FUN_00583ed0).
  The search is sent from the "Find a group to join (LFG)" page. A captured "01 ff ff..." is bSearch=1 followed by the
  arrays; byte 2 is the LFG flag (00 when off).
- **0x504** = LFM (my group wants members). Uses `_find_lfm_preferred_*` (FUN_005846c0). It is sent by /lfm (leader only,
  "LFMNotLeader"; bSearch=0) and by the "Find members for my group (LFM)" page Search (bSearch=1).
- Class ids are matched against class names 0..0x35. Dungeon names map to ids with FUN_0052d930, quest names with
  FUN_00593bb0 [O].
- /lfg also sends zone 0x503 MsgSingleBool {lfg} (FUN_00409260) [O, SOCIAL.md].
- The "Advanced Find" page only clears the list locally (FUN_005820f0). Its search is the /who request 0x44 [I].

### S->C (fills the FindList; world type 5 recommended)
1. **0x501** (none): clear the list.
2. **0x500 MsgWhoInfo** per result (layout in SOCIAL.md). The Find columns come from the record [I via binding
   FUN_00681d50]: Name = name, Level = level, Class = class id, Location = chunk X/Y (name via FUN_00b70e80; anonymous
   shows nothing). Set u8 LFG=1 on LFG players. The 32 x 3 i32 tail is that player's preference list (send their
   class/dungeon/quest ids or -1).
3. **0x502 {i32 count, i32 mode, i32 trialCount, bool8 truncated}**. When the Find window is open (FUN_0057dbf0),
   **mode 1 = "Find a group to join (LFG)" page, 2 = "Find members for my group (LFM)" page, other = "Advanced Find"**,
   and the list shows in that page (FUN_00582990) [O]. When the Find window is closed it prints /who-style chat lines.
   - Reply to 0x503 search: mode 1, listing LFM group leaders (players whose LFM flag is set).
   - Reply to 0x504 search: mode 2, listing LFG players not in a group.
   - Match preferences against each other (class/dungeon/quest overlap) if wanted.

### Request to join / invite from the Find list

> **Implemented (2026-10-13):** the server forwards world 0x58b to the leader as zone 0x58b {leader, requester, level, class}. It refuses when the requester is already grouped, the target is not a leader, or the group is full. The leader's 0x58c decline goes back to the requester as 0x58c {leader}. Verified with two clients: Ranger's Request to Join reached Justins, whose client auto-declined (no client-side LFM flag), and Ranger saw "Justins has declined your request to join the group." The leader's Invite/Decline dialog has not been seen yet; it needs a real group leader with /lfm on.
| Dir | Conn | Id | Layout | Meaning |
|---|---|---|---|---|
| C->S | world type 5 | **0x58b** | wstr leaderName | "Request to join" from the find list (FUN_0057fc1d -> FUN_004dbd90). Only sent when the player is not grouped ("AlreadyInGroup") [O] |
| S->C | zone or world (FUN_004e2910) | **0x58b** MsgRequestToJoinGroup | wstr (leader/target name [I]), wstr requesterName, i32 level, i32 classId | Goes to the leader. The leader sees "RequestingToJoinYourGroup" and a `_request_to_join_group_dialog` ("<cyan>Name</cyan> Level N Class") with Invite/Decline buttons. The client auto-declines when the group has >= 6 rows, the leader's LFM flag is off, the requester is ignored, or a dialog is already open [O] |
| C->S | world type 5 | **0x58c** | wstr requesterName | Leader declines, by button or auto-decline (FUN_004dbfa0) [O]. The Invite button sends a normal **0xb0** {name} (FUN_004d8fb0 caller 0x4dbf0e) [I]. The find-list "Invite" (LFM side) also uses 0xb0 (caller 0x582490) [I] |
| S->C | zone or world | **0x58c** | wstr leaderName | To the requester: "RequestToJoinGroupDeclined" [O] |

### Key addresses
Group manager handlers: FUN_004e2910 (dispatcher). 0x6c1 FUN_004dc640, 0x6c2 FUN_004dcd40, 0x6a6 FUN_004de1b0,
0x6c4 FUN_004d5a00, 0x6c5 FUN_004d5f40, 0x6c6 FUN_004d5c90, 0x6d7 FUN_004d4aa0, 0x58b FUN_004ddd10, 0x58c FUN_004d8220.
Senders: 0xac FUN_004d1760, 0xa7 FUN_004dc040, 0xa8 FUN_004dc120, 0xa9 FUN_004d51e0, 0xab FUN_004d5380, 0xaa FUN_004d6740,
0x592 FUN_004d5400.
Mentor: 0x5c9 FUN_005fdcc0/FUN_005fdd50, 0x5c8 FUN_0063d510, 0x5cb FUN_00639a70, 0x5ca FUN_005eb2b0.
Menu switch FUN_006a8060 (jump table 0x6aa19c, index = id-1).
LFG/LFM: FUN_00583ed0 / FUN_005846c0 (builders), FUN_00584620 / FUN_00584e10 (Search), FUN_005867f0 (LFM toggle),
FUN_00584eb0 (page router), FUN_00582990 (0x502).

## Mentoring (verified live with two clients, 2026-10-13)

Ranger (level 12) asks his group member Justins (level 20) to mentor him: 0x5c8 {wstr "Justins"} (the group window's "Request Mentor" menu; the `!mentorme Justins` dev command does the same). Justins gets 0x5ca {"Ranger"}, the client's "Mentor Request" popup ("Ranger has requested that you mentor them. Would you like to accept?"). Accept sends 0x5c9 {1}; the server lowers Justins' effective level to 12 (MsgScore level, pawn m_GameplayLevel for everyone, group 0x68f {eid, level}) and his level badge changes from 20 to 12: "You are now mentoring Ranger. Your level is 12.". Stop Mentoring (0x5cb) restores the real level. Mentoring changes only the shown level for now (no stat or experience scaling).

## Invitation timeout (verified live 2026-10-13)

An unanswered group invitation expires after 60 s (`INVITE_TIMEOUT`): the invited player gets 0x6b7 `{i32 0}`, which closes their invite popup and prints "You can no longer join that group." (GroupInviteTimedOut), and the inviter gets "Your group invitation to Justins has expired.". A member's death sends 0x691 `{eid64}` to the others ("<name> died!!", see DEATH.md).
