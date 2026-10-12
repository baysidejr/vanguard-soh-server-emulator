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
