# VGClient inventory: what the server must send (event 0x197 MsgSingleItemInfo)

Tags: **[O]** = observed in decompiled code or assets. **[I]** = inferred.

**Status:** verified live on 2026-10-11 — the server's starter items (with stack counts) and coins show in the bag (`server/zone.py` `inventory_messages`). Icons still use the fallback 443.

## Why an item with container 0 did not appear
The bag grid is the gamevar list **`InventoryContainerID_-1`**, not `InventoryList`, and it has 50 slots.
- `VGUIAssets/Shells/Default/Windows/VGUIInventory.xml` lines 79-84: the `_inventory_list` window has `<AttachUpdater type="ItemList" gameVarLink="InventoryContainerID_-1" inventoryList="true" numPerMulti="10">`. **[O]**
- FUN_00512520 (called from the reset path FUN_00513000 -> FUN_00512bd0) runs `FUN_00510d70(-1, 0x32)`. That creates `InventoryContainerID_-1` with 50 empty slots. **[O]**
- FUN_00512430: if `item+0x58 == -1` (field 7), it calls `FUN_00510ba0(container = item+0x654 (field 15), item, slot = item+0x1bc (field 16))`. **[O]**
- FUN_00510ba0 calls FUN_004ff770(container), which looks up the gamevar named `"InventoryContainerID_" + container`. FUN_006aced0(list, slot, ItemInfo{handle=item+0x6ec}) then writes the slot. If the list is missing, or the slot index has no entry (slot >= capacity), the item goes into a pending map at manager+0x6dc. FUN_00510d70 flushes that map only when a container with that ID is created later. **[O]**

You sent **field 15 = 0**, so the client went looking for `InventoryContainerID_0`. That container does not exist, so the item was parked in the pending map and never drawn. **Fix: field 15 = -1, field 7 = -1, field 16 = slot 0..49.**

## Required messages, in order
1. **0x195 inventory reset/init** (FUN_00513170). Payload is MsgThreeIntsAndFloat, 16 bytes: `i32 spaceAvailable, i32, i32, i32/f32`. **[O]** only field 0 (+0x14) is read. FUN_00513000 clears all client inventory lists and recreates `InventoryContainerID_-1` (50 slots). It then stores (float)field0 at manager+0x64 and pushes it to gamevar `InventorySpaceAvailable` (FUN_004f7800). **[O]**
   - As an alternative, **0x1c0** has no payload and runs the same reset (FUN_00513000) but does not set space. **[O]**
   - Send this after the UI and gamevar system are up (FUN_00c2ff70 returns 0 while DAT_01925068 == 0) and **before** any items, because it wipes the lists. **[I]**
2. **0x197 MsgSingleItemInfo**, one per item (layout below).
3. Optional **0x1aa MsgSingleLong**: `i64 copper` (coins).

## Field index -> meaning (wire field n -> message struct offset -> client item offset)
Items are built in FUN_00514ff0 (copies from the message struct). Field registration is in FUN_004429a0. **[O]**

| # | type | msg off | item off | meaning |
|---|---|---|---|---|
| 0 | bool8 | 0x14 | - | not copied to item (flag) |
| 1 | i32 | 0x18 | +0x00 | server item id **[O]** |
| 2 | wstr | 0x1c | +0x04 | **name** (`_inventory_examine_name`, FUN_006b71c0) **[O]** |
| 3 | wstr | 0x38 | +0x20 | appended to the examine text when non-empty (FUN_006b6ad0 checks item+0x34). Probably the **description** **[I]** |
| 4 | wstr | 0x54 | +0x6f0 | unknown string |
| 5 | wstr | 0x70 | +0x600 | unknown string |
| 6 | i32 | 0x8c | +0x70c | **stack quantity**. FUN_00690490 shows the stack-count spinner only if > 1 **[O]**. Send 1. |
| 7 | i32 | 0x90 | +0x58 | **equip slot; -1 = in a container/bag** **[O]**. 0x1c/0x24 trigger the special path FUN_005f26e0(field 72) **[O]** |
| 8 | i32 | 0x94 | +0x5c | ? |
| 9-10 | i32 | 0x98/0x9c | +0x60/+0x64 | ? |
| 11-12 | i32 | 0xa0/0xa4 | +0x68/+0x6c | ? |
| 13 | i32 | 0xa8 | +0x70 | **icon id** (numeric, see Icons) **[O]** |
| 14 | i32 | 0xac | +0x74 | **container capacity**. If > 0, this item is a bag and FUN_00510d70(field71, field14) creates `InventoryContainerID_<field71>` **[O]**. 0 for normal items. |
| 15 | i32 | 0xb0 | +0x654 | **container ID the item sits in** (-1 = main bag grid) **[O]** |
| 16 | i32 | 0xb4 | +0x1bc | **slot index in that container** (0..49 for main) **[O]** |
| 17 | i32 | 0xb8 | +0x1c0 | count of trailing 0x60-byte records parsed by FUN_005147c0. **Keep 0** **[O]** |
| 18-21 | i32 | 0xbc..0xc8 | +0x78..+0x84 | ? |
| 22-25 | wstr | 0xcc.. | +0x88,+0xa4,+0xc0,+0xdc | ? |
| 26-27 | wstr | 0x13c,0x158 | +0xf8,+0x114 | ? |
| 28-32 | wstr | 0x174..0x1e4 | +0x130,+0x14c,+0x168,+0x184,+0x1a0 | ? |
| 33 | i32 | 0x200 | +0x710 | ? |
| 34-35 | i32 | 0x204/0x208 | +0x1d0/+0x1d4 | ? |
| 36-47 | 3x[wstr,wstr,wstr,i32] | 0x20c.. | strings +0x1d8/+0x22c/+0x280 (k=0), +0x1f4/+0x248/+0x29c, +0x210/+0x264/+0x2b8; ints +0x2d4/+0x2d8/+0x2dc | ? |
| 48-49 | i32 | 0x314/0x318 | +0x2e0/+0x2e4 | ? |
| 50-58 | 3x[wstr x3] | 0x31c.. | +0x2e8.. | ? |
| 59 | i32 | 0x418 | +0x3e4 | ? |
| 60-68 | 3x[wstr x3] | 0x41c.. | +0x3e8.. | ? |
| 69-70 | wstr | 0x518/0x534 | +0x4e4/+0x500 | ? |
| 71 | i32 | 0x550 | +0x650 | **container ID this item provides** (only meaningful with field 14 > 0). Also passed to vtbl+0x28 in FUN_00512af0 **[O]**. Use a unique positive value for bags, 0 otherwise **[I]** |
| 72 | i32 | 0x554 | +0x51c | used when field7 == 0x1c/0x24 (FUN_00512af0) |
| 73 | i32 | 0x558 | +0x520 | ? |
| 74 | i32 | 0x55c | +0x524 | passed to FUN_006ab450 in the tooltip (FUN_006b6ad0). Possibly a level requirement **[I]** |
| 75-76 | i32 | 0x560/0x564 | +0x528/+0x52c | ? |
| 77 | i32 | 0x568 | +0x534/+0x538 | value v, range v*(1 -/+ f78/255) (damage min/max?) **[O math, I meaning]** |
| 78 | u8 | 0x56c | - | variance 0..255 for fields 77/79 |
| 79 | i32 | 0x570 | +0x540/+0x544 | same treatment as 77 |
| 80 | i32 | 0x574 | +0x53c | ? |
| 81 | f32 | 0x578 | +0x548 | if <= 0 the client forces 1.0 (delay/speed?) **[O]** |
| 82 | f32 | 0x57c | +0x54c | ? |
| 83-88 | i32 | 0x580..0x594 | +0x550..+0x564 | ? |
| 89-90 | f32 | 0x598/0x59c | +0x568/+0x56c | ? |
| 91 | u8 | 0x5a0 | +0x714 | ? |
| 92 | u8 | 0x5a1 | +0x570 | **location type**: 8 = pet inventory (InventoryPetList), 10 = merchant buyback (MerchantBuybackList), 4 = ignored by the UI, anything else (**0**) = normal inventory (FUN_00512af0). 0x1ac sets it to 0 and 0x1ad sets it to 7 **[O]** |
| 93 | u8 | 0x5a2 | +0x574 | ? |
| 94 | u8 | 0x5a3 | +0x668 (bool) | ? |
| 95-98 | i32 | 0x5a4..0x5b0 | +0x578,+0x57c,+0x580,+0x584 | ? |
| 99 | u8 | 0x5b4 | +0x61c | **name colour / rarity** 0..11 (FUN_006d0f60 -> FUN_006d0ee0 colour table) **[O]** |
| 100 | u8 | 0x5b5 | +0x58b | 0xFF selects an alternative tooltip path |
| 101-104 | u8 | 0x5b6..0x5b9 | +0x588,+0x589(flags),+0x58a,+0x58c | flags |
| 105 | i32 | 0x5bc | (not copied) | - |
| 106 | i32 | 0x5c0 | +0x664 | ? |
| 107-109 | i32 | 0x5c4/0x5c8/0x5cc | +0x5e4/+0x5ec/+0x5e8 | ? |
| 110 | i32 | 0x5d4 | +0x5f4 | count of trailing 0xa4-byte records (FUN_00514980). **Keep 0** **[O]** |
| 111 | f32 | 0x5d0 | +0x1c4 | passed to FUN_004be860 |
| 112 | bool8 | 0x5d8 | +0x5f0 | ? |
| 113 | bool8 | 0x634 | +0x648 | ? |
| 114 | bool8 | 0x635 | +0x649 | adds an extra tooltip line when set |
| 115-117 | wstr | 0x5dc.. | +0x590,+0x5ac,+0x5c8 | ? |
| 118 | i32 | 0x630 | +0x644 | ? |

Notes on the item fields you asked about:
- `item+0x6ec` is **not from the wire**. It is a client-local handle. FUN_00517b60 increments a global counter DAT_013e9be4 and FUN_00513a10 stores it at +0x6ec. The UI list entries (SGOUIGameVarDataItemInfo) store this handle. **[O]**
- `item+0x654` is field 15 (parent container). `item+0x650` is field 71 (container ID the item provides). `item+0x570` is field 92. **[O]**
- FUN_00512d40 sends every 0x197 through FUN_00516610(...,0,-1). That means a resend of the same id creates a new client object, not an update. **[O]**

## Icons
Field 13 is a numeric icon ID. FUN_006ab420 -> FUN_00c4b020 formats it as `"%05d"` (e.g. 1 -> "00001") and looks up that key in the client icon map (FUN_00c4ae60). If the ID is < 0 or not found, it falls back to **"00443"**. **[O]** So any 5-digit icon key that exists in the client's icon table works. **443** is guaranteed to resolve because it is the client's own default **[O]**. Which numbers map to swords is unknown, so try small values such as 1..1000 **[I]**.

## Coins (0x1aa MsgSingleLong, i64)
The unit is **copper**. FUN_0050b6e0 stores the i64. FUN_0050a250 then sets these gamevars **[O]**:
- InventoryCoins = total
- Platinum = c / 1,000,000
- Gold = (c / 10,000) % 100
- Silver = (c / 100) % 100
- Copper = c % 100

It prints "You receive/lose %s." and plays UISounds.CoinsIn/Out from the delta. Event 0x1bb takes the same payload and handler but clears flag +0x85 first, so it sets coins silently (use it at login). **[O]**

## Other related events (dispatcher FUN_00513250)
- 0x1ac MsgFourInts (FUN_00511270): `i32 itemId?, i32 newContainer, i32 newSlot, i32`. Moves an item into a container slot and sets item type 0. **[O]** That the first field is the item key used by FUN_004fa970 is **[I]**.
- 0x1ad MsgFourInts (FUN_004f9760): moves an item to the combat inventory (type 7, container -1, slot = field2). **[O]**
- 0x1b4 MsgTwoInts (FUN_00500120): `(containerId, x)`. Refreshes the bag-item entry in InventoryList / InventoryCombatInvList whose provided-container (+0x650) matches. **[O]**
- 0xa5 is toolbelt flags and is unrelated.

## Minimal concrete example (Rusty Sword in bag slot 0)
1. Zone event 0x195, payload (16 bytes): `i32 50, i32 0, i32 0, i32 0`.
2. Zone event 0x197, payload with every field zero / empty wstr (just the UTF-16 NUL terminator `00 00`) except:
   - f0 = 0
   - f1 = 1002
   - f2 = "Rusty Sword"
   - f3 = "An old sword."
   - **f6 = 1**
   - **f7 = -1**
   - **f13 = 443**
   - f14 = 0
   - **f15 = -1**
   - **f16 = 0**
   - f17 = 0
   - f71 = 0
   - f81 = 1.0
   - **f92 = 0**
   - f99 = 1
   - f110 = 0
   - No trailing data.

The second item goes in f16 = 1, and so on up to 49. For a bag item, set f14 = slots and f71 = a unique ID N. The items inside it then use f15 = N and f16 = 0..slots-1.

## Equipping (verified live 2026-10-11)

- Wire field 71 (item `+0x650`) is the item's **handle**: the equip/move handlers look items up by it (`FUN_004fa970` / `FUN_004faa70`), and a bag's own slots are `InventoryContainerID_<handle>`. The server sets it to the item id.
- **0x1a7** (`FUN_0050feb0`): `i32 handle, u8 list (0 = main inventory list; 1 = the other list), u8 equip slot`. Moves the item out of its bag slot onto the paper doll and marks it equipped (`+0x570 = 1`, `+0x58 = slot`).
- Equipment slot ids come from the slot-tag table `FUN_0050cc10`, e.g. HEAD 0, NECK 3, CHEST 6, CLOAK 7, WAIST 21, FEET 26, PRIMARYHAND 28 (0x1c), SECONDARYHAND 29, LEGS 32, HANDS 33, WRISTS 34, SHOULDERS 35, TWOHANDS 36 (0x24), RANGED 42, AMMO 43. The full table is `vgmsg.EQUIP_SLOTS`.
- The equipped weapon is not yet drawn in the character's hand (that needs the pawn's attachment groups).

## Equipping (verified live 2026-10-12)

- **Equip:** right-clicking an item in a bag sends client event `0x8e` {i32 handle, u8} (`FUN_005042b0`), but only if the item allows it.
  - Field 8 (item `+0x5c`) must hold the item's default equip slot.
  - Fields 18–21 (`+0x78..+0x84`, a bit mask over slot numbers) must include that slot. Otherwise the client prints "Designer error: default equipslot for item is restricted for that item."
- **Server reply to an equip:** `0x1a7` {i32 handle, u8 0, u8 slot} moves the item onto the paper doll.
- **Unequip:** right-clicking an equipped item sends `0x98` {i32 handle, u8 0}. The server answers `0x1a9` {i32 handle, i32 bag slot, i32 container} (`FUN_00511100`), which puts it back into a bag slot. The same message returns a replaced piece to the bag when an item is swapped.
- **Model:** the pawn's `m_AttachmentGroups` is resent so everyone sees the new gear (see [GEAR.md](GEAR.md)).
- **Item templates** (equip slot, 3D model): `server/content/items.json`.
- The red icons and "Durability: 0%" are fixed: see [ITEM_FIELDS.md](ITEM_FIELDS.md), which also corrects fields 74 (item type), 76 (level), 77 (damage base), 82 (delay) and 100 (255 = a normal item) in the table above.

## Moving and destroying items (verified live 2026-10-13)

- **Move:** dragging an item to another bag slot sends client **0x92** `{i32 handle, i32 container (-1 = the main bags), i32 slot}`; the client waits for the server. The server answers **0x1ac** `{i32 handle, i32 container, i32 slot, i32 0}` and the icon moves (`zone.move_item`). Onto an occupied slot the two items swap (two 0x1ac); onto a stack of the same item it merges up to 99 (0x1ae new count, 0x1a5 removes the emptied item). Moves into bags inside the bags (container = a bag's handle) are refused for now.
- **Destroy:** dragging an item out of the window opens the client's "Delete: <item>" popup; Delete sends **0x89** `{i32 handle}`. The server removes it (0x1a5) and prints "You destroy Hunter's Shortsword.".
- **Split (verified live 2026-10-13):** Ctrl+click a stack opens the client's "Split" popup (VGUIInventoryPopups.xml; shift+click shows the item's info instead). OK (`inventory_unstack_ok`, FUN_0068e8e0 -> FUN_004fc8f0) sends **0x97** MsgTwoInts `{i32 handle, i32 count}`; the client itself refuses counts below 1. The server answers 0x1ae (the old stack's new count) and 0x197 (a new item with `count` in the first free slot) (`zone.split_stack`). Travel Rations x5, split 2 -> x3 and x2.
- The "combat inventory" (0x1ad, InventoryCombatInvList) is the crafting inventory used during Table Setup; see CRAFTING.md (0x1b0, 0x305).

## Bags (verified live 2026-10-13)

- A bag is an item whose items.json template has `"bag": <slots>`. The server sends it with **field 14 = capacity**; the client then makes the gamevar list `InventoryContainerID_<handle>` (field 71).
- Bags are **equipped into the main bar's three bag slots**, equip slots CONTAINER1-3 = 12, 27, 38 (VGUIMainBar.xml; the fourth slot there is MOUNTSADDLEBAGS). Right-clicking a bag in the inventory equips it into the first empty bag slot (0x8e -> 0x1a7). Clicking the bag on the bar opens its window (`_inventory_container_template`, titled with the item name); the bags button opens every equipped bag (FUN_00500750 checks equip slots 0x0c, 0x1b, 0x26 and 0x2e).
- Dragging an item into a bag window sends the usual **0x92** `{handle, container = the bag's handle, slot}`; the server answers 0x1ac with the same container and slot. Items inside a bag are sent with field 15 = the bag's handle and field 16 = the slot. The server stores that as one slot number, `vgmsg.bag_slot` (1000000 + handle*100 + slot).
- At login the main grid is sent first, then the equipment (bags included), then the items inside the bags, so each bag exists before its contents.
- A bag that holds items can't be unequipped, destroyed, sold, traded, mailed or banked ("You need to empty that bag first."), and bags can't go inside bags.
- Test: `!give Small Pouch` (8 slots). Verified: the pouch went onto the bar, its window opened, Copper Ore x2 moved into slot 0 and was still there after logging in again.

## Character service items (verified live 2026-10-13)

Right-clicking an item checks its **template id** (item field 1) in `FUN_00500030` before anything is sent. A few template ids open the client's own windows instead. items.json `"template_id"` gives an item one of these ids. The real item names, prices and sources are unknown, so the emulator's items have placeholder names and are `!give` only.

| Template id | Client window | Submit sends | Reply | Server status |
|---|---|---|---|---|
| 1454015 | "Race Change" (race dropdown, current race left out) | 0x5d7 `{i32 race, i32 item handle}` | 0x5d8 MsgPaidRaceChangeResult `{i32, i32 code, u8, u8 race}`: 0x11 done (strRaceSelf), 0x15 "You are not allowed to change your race.", else "Race change failed." | done: saves `race`, sends `m_iRaceId`, MsgScore and the race's attributes. Verified: the sheet reads "Thestran Ranger"; the body keeps the old appearance sliders |
| 1454016 | "Gender Change" ("Press submit to become female.") | 0x5d5 `{i32 new gender, i32 item handle}` | 0x5d6 MsgPaidGenderChangeResult `{i32, i32 code, u8, u8 gender}`: 0x0c done (the client switches gender itself), 0x10 not allowed | done: saves `gender`, sends `m_Gender`. Verified: the character turns female at once and stays female after a relog |
| 1454021 | none | 0x4fc (no payload) at once | ? | not handled |
| 1454022 | "Clear Experience Debt" | 0x5da `{i32 item handle}` | 0x5db `{i32 code}` (see DEATH.md) | done |
| 1463295 | "Character Rename" (first and last name boxes) | 0x5d3 (item handle and the two names; field order unverified) | 0x5d4 `{i32, i32 code, u8, wstr first, wstr last}`: 6 done (strNameSelf / strNameFullSelf), 7 "That first name is not available.", 0xb not allowed | not handled yet |
| 1464359 / 1464362 | none: they put the cursor into targeting mode 5 / 6 (item handle kept at +0x6cc / +0x6d0) | ? | ? | not handled |
| 1466724 | "_inventory_consume_kronos" (subscription time) | ? | ? | not handled (no use on a private server) |

All replies are zone events in the main dispatcher `FUN_00622350` (jump-table indices 14-17 for 0x5d4/0x5d6/0x5d8/0x5db).

**Player gender.** The create request (MsgClientCharacterCreate, schema `FUN_004896a0`) is: wstr first, last, world, a fourth wstr, i32, **u8 gender**, u8 race, u8 class, i32, i32, 64 slider bytes. In the bytes the server keeps after the names (`raw`), gender is +6 (0 male, 1 female). The server sends it as the player pawn's `m_Gender` and MsgScore field 6. Before this, every character was drawn male.
