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

- **Settings:** client 0xb6 `{eid64 master looter, i32 mode, wstr rarity, bool8 split coin, bool8 cash loot}` from the leader → 0x6c8 (same layout) to every member, also sent to new members. The client prints "The group loot mode has been changed to: …". The rarity travels as the popup's colored string (`grouploot.RARITIES`, best first); items.json `rarity` is a name (mundane, common, uncommon, rare, heroic, fabled, legendary; default mundane), which also sets the item's name colour (ITEM_FIELDS.md field 99). 0xb5 `{wstr name}` promotes a master looter → 0x6a5 to them, 0x6cc `{eid64}` to the others.
- **Roll:** 0x6ab (first item) / 0x6ad (next) `{wstr next item, i32 0, i32 0, i32 seconds, bool8 need allowed}` + the item's 0x1f2 bytes opens the client's Loot Roll popup (Need / Greed / Pass). Answers: 0xb9 `{bool8 need}`, 0xba pass. Each answer gets 0x6af `{i32 roll, bool8 need}`; when everyone answered (or after 30 s; silence = pass) 0x6ae `{wstr winner, bool8 need, i32 roll}` goes to the group ("Winner: Ranger 59 (NEED)"; roll 0 = "Everyone PASSED. Open loot!"), the item goes to the winner's bags and 0x696 `{eid64, wstr item, i32 qty}` prints "Ranger has looted Tattered Cloth." After the last item 0x6b0 ("No more items to be randomed!", the popup counts down) and 0x6ac hides it. Items in a roll can't be taken from the window (0x0e code 0xef). The leader's /groupcancelrollsession (0x1e6) stops a roll.
- **Master Looter (verified live):** the client prints "The group loot mode has been changed to: Master Looter with master looter Ranger" and "Ranger is now the master looter."; another member pressing U gets "You don't have permission to loot that corpse."
- **Round Robin (verified live):** the turn is picked when a group kill is first opened, before the rights check; the others see "It is Justins's turn to loot." and a member whose turn it isn't gets 0x0e code 0xf6, which the client prints as "You don't have permission to loot that corpse."
- **Coin (verified live):** every corpse carries copper (mobs.json `coin` [min, max], default 2-6 per level, `combat.corpse_coin`). The first allowed looter to open it collects it with 0x1aa ("You receive 38 copper."). With Coin Split on (0xb6 split flag) it is divided between the online members (the remainder to the looter) and the others see 0x6ce `{eid64 member, wstr amount}` "Ranger receives 10 copper due to cash loot sharing." Sending 0x6ce about the receiver's own share prints a client "Programmer error", so it is only sent about other members.
- **Give loot (verified live 2026-10-13, two clients):** the master looter types `/giveplayerlootitem <player> <item>` with the corpse targeted; the client sends **0x3dc** MsgEntityIDAndTwoStrings `{eid64 corpse, wstr player, wstr item}` (FUN_00605440 -> FUN_00522490; a soulbound item gets a confirm popup first). The client splits arguments at spaces, so "Tattered Cloth" arrives as "Tattered": the server matches the item by handle, full name or part of the name (`grouploot.match_loot`). The item goes into the member's bags; the group sees "Justins has looted 3 x Tattered Cloth." and the member "Ranger gives you 3 Tattered Cloth.". Only the master looter in Master Looter mode may do it (else 0x0e 0xf6).
- **Not done:** the rarity of real items (server data).
- **Loot window buttons (verified live 2026-10-14, two clients):** the client keeps "Share Loot Rights" and "Start Item Rolling" hidden until **0x6ca** / **0x6c9** `{bool8}` show them (VGUILoot.xml visibility game vars). The server sends both when a corpse is opened: Share Loot Rights for whoever may loot in Round Robin or Master Looter (until shared), and Start Item Rolling in Random For Magical (`grouploot.loot_buttons`). Pressing Share Loot Rights sends 0xb7: the looter gets 0x684 `{bool8 1, wstr "", bool8 0}` ("The corpse is now unlocked for everyone that is allowed to loot it.", seen live 2026-10-15), the other members 0x685 `{wstr looter, wstr corpse}` ("Ranger has unlocked the Canyon Widow to you."), and the button hides. 0x684 with a name says "unlocked to %1 for looting" (or "to %1's group" with the last bool set); with the first bool 0, "CorpseYouCannotUnlock". Pressing Start Item Rolling sends 0xb8, the other member gets the Loot Roll popup, and the button hides.
- Test: `loottest.sh` in the scratchpad, or by hand: group two characters, leader types `!lootmode 4 6` (Need Before Greed, threshold Mundane), `!target Canyon Widow`, `!kill`, U on the corpse; answer in the popups (or `!roll need|greed|pass`).

## Encounter ownership

The first player (or group) to hurt an NPC owns it until it respawns: the server sets `npc.owner` (the group id when grouped, else the player id) and sends **0x567** MsgTwoEntityIdsAndBool `{eid64 npc, eid64 owner, bool8 damaged by an NPC}` to everyone in the chunk (FUN_00549da0). Each client records the owner; the owner's client prints "You have established ownership." or "Your group has established ownership." (the bool selects the "...but the NPC has been significantly damaged by another NPC. No loot or experience rewards will be granted." wording, unused here). What ownership changes for loot and experience beyond the existing loot rights is not decided yet. The message goes out (checked in-process), but in a live fight on 2026-10-14 the ownership line was not seen in the Chat or Combat tab; it may print to a channel neither tab shows.

## Loot sparkle (2026-10-15)

The client's loot effect on a corpse (`FXspells_Loot001fx`, FUN_005240f0) is driven by three zone events in the sub-dispatcher FUN_005249b0:

- **0x564** `{eid64}` (FUN_00524920 -> FUN_00524870) starts the sparkle on the entity, once per entity.
- **0x565** `{eid64}` (FUN_00523f20 -> FUN_00523cb0) stops it. docs/ZONE_MESSAGES.md does not list 0x565 or 0x566, but this dispatcher handles them.
- **0x566** (no payload, FUN_00523e30) walks every sparkle in the list (inferred: clears them all; not used).

The server sends 0x564 to the whole chunk with the death of any NPC that has coin or items (`login_stub.corpse_lootable`; not props, merchants or tombstones). It sends 0x565 when the last coin and item come off (`corpse_emptied`). If the bag is full the items stay, and so does the sparkle. Checked live with tools/winbreak.py: FUN_00524870 runs with the corpse's entity id when a Canyon Widow dies, and FUN_00523cb0 runs when the corpse is looted empty. The effect itself was not clearly visible in screenshots (the quest-node particles behave the same; docs/QUESTS.md).
