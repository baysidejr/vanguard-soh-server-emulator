# Loot window: how the client fills it

> **Verified live (2026-10-12):** U on a dead NPC → `0x1ed`, `0x1e8`, three `0x1f2`, `0x1ef` shows the items; Take All sends `0xbd` (-1) and the server's `0x197` + `0x1f6` per item + `0x1ed` moves them into the bag and closes the window. Implemented in `server/combat.py` (`loot_messages`, `take_loot`).


[O] = read directly from the decompiled client. [I] = inferred.

## Loot state object (ECX in every loot handler)
- +0x08 bool LootIsPending, +0x09 bool LootIsLooting, +0x0a bool (group/master-loot flag, skips no-drop prompts), +0x0b bool "auto loot-all when list arrives", +0x0c bool "loot-all in progress", +0x0d SafeLoot test flag. [O]
- +0x10 std::vector<Item*> (begin +0x14, end +0x18, cap +0x1c) is the **loot item vector**. [O] (FUN_005230c0 does `LEA ECX,[ESI+0x10]; CALL FUN_0045dd40` = push_back)

## Q1: what fills "LootItemList"
- 0x1f2 (FUN_005230c0) only parses the item (FUN_00516610(msg,len,0,-1) -> FUN_00514ff0) and push_backs the Item* into the vector. It does **not** touch the UI, and it does not call FUN_00512430, so the item never goes into an inventory container. [O]
- The UI rows are added only in **FUN_005207e0**: it walks the vector and calls FUN_0051fe80(item,0) for each one (it adds a row to the "LootItemList" gamevar list via FUN_006ac940), then refreshes with FUN_0051fe00. [O]
- FUN_005207e0 is called only from the **0x1ef** handler FUN_00521370. [O]
- => The list is empty because the server never sends 0x1ef. [O/I]
- Item fields: no container/slot/flag check is done for the loot list. Fields 15 (container), 16 (slot) and 7 (equip slot) are ignored. [O] The item's key is **wire field 71 (item+0x650)**: 0x1f6 removal (FUN_005206f0/FUN_00522920) and the click handler FUN_00521f40 find the item by +0x650. [O] So field 71 must be unique per item in the loot list; using the item id is fine. Byte +0x589 (wire byte at msg+0x5b7) bit0 = No-Drop and bit3 = Soulbound. These only trigger confirmation popups, so keep them 0. [O] Field 0x1c3 (msg+0x8c, quantity) >= 2 makes the chat use the "LootNotifyMeStack" text. [O]

## Q2: message meanings and order
| id | handler | meaning |
|---|---|---|
| 0x1e8/0x1ea MsgEntityIDAndBool | FUN_00520be0 | Begin looting: LootFrom = corpse name, pending=0, looting=1, opens the "_loot" window. Does NOT clear the vector. [O] |
| 0x1f2 MsgSingleItemInfo | FUN_005230c0 | Add one item to the loot vector (no UI change). [O] |
| 0x1ef (no payload) | FUN_00521370 | **Loot list complete**: FUN_005207e0 fills the LootItemList UI from the vector. If +0x0b is set, it auto-sends loot-all (FUN_00520520(-1)). Then +0x0b=0. If the vector is empty it calls FUN_00521100 (end looting: clears flags and sends 0xbe). [O] |
| 0x1f6 MsgIntAndBool {i32 handle, bool notify} | FUN_00522f90 -> FUN_00522920 | One item was looted: find the item by +0x650==handle, print "You loot X" (LootNotifyMe / LootNotifyMeStack) if notify && !+0x0a, remove the UI row (FUN_0051fcd0) and erase it from the vector. [O] |
| 0x1f7 wstr | FUN_00520ea0 | Show the text as a chat/system message (channel 0x26), e.g. loot errors. [O] |
| 0x1f8 (no payload) | FUN_0051fd60 | Loot-all finished / refresh: clears +0x0c,+0x0b and refreshes the InventoryList and LootItemList gamevars. It does NOT add rows. [O] |
| 0x1ed (no payload) | FUN_00521270 | Loot session ended: clears the vector and the UI list (FUN_0051fc40), and sets pending/looting/+0x0b to 0. [O] |
| 0x63c (no payload) | FUN_0051fe00 | Refresh LootItemList only. [O] |

Recommended order on loot open [I]:
1. (optional) 0x1ed, to clear any old vector.
2. 0x1e8 {u64 corpse eid, bool 1}, which opens the window.
3. 0x1f2 x N (unique field 71 per item).
4. **0x1ef** (empty payload), which fills the rows.
Sending 0x1ef before 0x1f2, or sending 0x1ef with 0 items, ends the session right away. 0x1f8 is not needed when the window opens.

## Q3: client -> server
- **0xbb** (FUN_005203d0): loot request on corpse, payload {u64 corpse eid} (MsgEntityID-style, FUN_00417870). It sets pending=1. This is what U sends. [O]
- **0xbc** MsgSingleInt {i32 handle} (FUN_00521f40, UI actions 0x14c/0x14d, `/lootbyhandle %i`): take one item. The handle equals wire field 71. The client checks it against the vector first ("Invalid item number." otherwise). [O]
- **0xbd** MsgSingleInt {i32 -1} (FUN_00520520, UI action 0x96 = "Take All" button, also the auto-loot timer): loot all. It sets +0x0c=1. [O]
- **0xbe** no payload (FUN_00521100 via FUN_004cfb50): stop looting / window closed. [O]
- 0x3dc: give-player-loot-item (master looter). Not needed. [O]
- MsgSingleInt layout: `u16 2, u32 id, u32 4, i32 value`. This matches 0xd0 in docs/ABILITIES.md. [O]

## Server reply recipe [I]
- On 0xbc h: add the item to the bag (0x197 inventory item with container -1 and a free slot; the handle can be the same id). Then send 0x1f6 {i32 h, bool 1}. If no items are left, send 0x1ed (or wait for the client's 0xbe).
- On 0xbd -1: for each item, add it to the bag and send 0x1f6 {h,1}. Then send 0x1f8 (clears the loot-all flag and refreshes the lists). Then send 0x1ed to close.
- On 0xbe: end the session server side. Sending 0x1ed is harmless.

## Group loot (verified live 2026-10-13, two clients)

Implemented in `server/grouploot.py` (message builders and rules, unit-tested in `test_systems.py`) and `login_stub` (`open_loot`, `group_loot_*`, `start_roll` / `present_roll` / `answer_roll` / `finish_roll`, `handle_grouploot_event`). The killer of an NPC is recorded (`npc.killer`); a solo kill can only be looted by its killer, a group kill by the killer's group according to the loot mode.

| Mode | Value | Who may loot |
|---|---|---|
| Free For All | 0 | any member |
| Round Robin | 1 | the member whose turn it is (picked when the corpse is first opened; the others get 0x6cd), or anyone after 0xb7 "allow group to loot" |
| Master Looter | 2 | the master looter, or anyone after 0xb7 |
| Random For Magical | 3 | any member; 0xb8 "start randoming" rolls the items at or above the rarity threshold |
| Need Before Greed | 4 | any member; opening the corpse starts the roll automatically (the client's options popup can't pick this mode) |

- **Settings:** client 0xb6 `{eid64 master looter, i32 mode, wstr rarity, bool8 split coin, bool8 cash loot}` from the leader → 0x6c8 (same layout) to every member, also sent to new members. The client prints "The group loot mode has been changed to: …". The rarity travels as the popup's colored string (`grouploot.RARITIES`, best first); items.json `rarity` is an index into that list (default 5 Common). 0xb5 `{wstr name}` promotes a master looter → 0x6a5 to them, 0x6cc `{eid64}` to the others.
- **Roll:** 0x6ab (first item) / 0x6ad (next) `{wstr next item, i32 0, i32 0, i32 seconds, bool8 need allowed}` + the item's 0x1f2 bytes opens the client's Loot Roll popup (Need / Greed / Pass). Answers: 0xb9 `{bool8 need}`, 0xba pass. Each answer gets 0x6af `{i32 roll, bool8 need}`; when everyone answered (or after 30 s; silence = pass) 0x6ae `{wstr winner, bool8 need, i32 roll}` goes to the group ("Winner: Ranger 59 (NEED)"; roll 0 = "Everyone PASSED. Open loot!"), the item goes to the winner's bags and 0x696 `{eid64, wstr item, i32 qty}` prints "Ranger has looted Tattered Cloth." After the last item 0x6b0 ("No more items to be randomed!", the popup counts down) and 0x6ac hides it. Items in a roll can't be taken from the window (0x0e code 0xef). The leader's /groupcancelrollsession (0x1e6) stops a roll.
- **Not done:** coin split (0x6ce), /giveplayerlootitem (0x3dc), the rarity of real items (server data).
- Test: `loottest.sh` in the scratchpad, or by hand: group two characters, leader types `!lootmode 4 6` (Need Before Greed, threshold Mundane), `!target Canyon Widow`, `!kill`, U on the corpse; answer in the popups (or `!roll need|greed|pass`).
