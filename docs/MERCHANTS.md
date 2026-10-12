# VGClient merchant (vendor NPC) flow - static analysis

> **Verified live (2026-10-12):** U on a merchant → `0x2bb` + `0x2b5` opens the Dialogue window with "Show me your wares."; clicking it sends `0xe5` → `0x28b`, `0x283`, `0x285` × items, `0x28c` shows the Merchant window with prices; right-click buys (`0xe7` → `0x197` + `0x1aa` "You lose 25 copper.") and right-clicking a bag item sells (`0xe8` → `0x1a5` + `0x1aa` "You receive 6 copper."). Implemented in `server/merchant.py`; vendor stock in `server/content/merchants.json`.


Tags: [O] = observed in decompiled code/assets, [I] = inferred.
Framing: all events are zone events `u16 2, u32 id, u32 len, payload`, in both directions.
Client sends events through FUN_004cfb00(id, msg) (with payload) and FUN_004cfb50(id) (no payload). Both end in FUN_00409210. [O]
Client merchant state object: byte[1] = state (0 = none, 1 = request pending, 2 = transaction open). Vectors: +0x8 merchant items, +0x18 escrow buyback, +0x28 repair list. [O]

## 1. Opening a merchant

### 1a. How the player starts it (client -> server)
| Trigger | What the client does | Addr |
|---|---|---|
| Dialog option "Show me your wares." (option type 5) | sets state=1, sends **0xe5** (no payload) | FUN_004c4640 case 5 -> FUN_00546380 [O] |
| `/haggle` slash command | same: FUN_00546380 -> **0xe5** (if state != 0 it closes instead: 0xe6 + 0xf4) | cmd table 0x13ef2c8, stub 0x5fc240 -> 0x546380 [O] |
| Merchant tab buttons (`_merchant_tab_pagelist`) | FUN_00546380 | FUN_0068b4b0 / FUN_0068b510 [O] |
| Escrow option (type 0xe) | sends **0xed** | FUN_005462c0 [O] |
| Repair option (type 0x10) | sends **0xf1** | FUN_00546440 [O] |
| Hail (`Hail` key/cmd) | sends **0x74 Say** (MsgSendSingleSGOString, wstr) with the localized text "Hail" + target name. There is no dedicated hail event. | FUN_005ecb20 [O] |

0xe5 carries no NPC id. The server must use the player's current target. The failure reason 2 ("Please target the merchant...") confirms the server checks the target. [O msg / I logic]

Other slash commands (category 18 = "merchant", table at 0x13ee4a0, 0x18-byte entries) [O]:
`/haggle` (0xe5 or close), `/stopshopping` (FUN_005458f0(1): 0xe6 + 0xf4), `/merclist` (local print, FUN_00546160), `/buy [n] name` (0x606400 -> 0x546a60 -> 0xe7), `/sell [n] name` (0x606630 -> 0x546b60 -> 0xe8), `/price name` (0x606860 -> 0x546c60 -> 0xea).

### 1b. NPC dialog that offers "Show me your wares" (server -> client, dispatcher FUN_004c9170)
- **0x2bb (699)** MsgSingleEntityId `eid64 npc`. Sets the talking NPC (`TalkingNPCName`), sets the flag at +0x24 = 1, and calls FUN_004c1e70(1,0), which opens the dialog. FUN_004c51c0/FUN_004c4960 [O behaviour; I that this opens the window].
- **0x2b5** (no payload). Adds option "Show me your wares." with type 5. FUN_004c7a00 [O]. Siblings: 0x2b1 teach (type 0), 0x2b2 recipes (1), 0x2b3 banking (3), 0x2b4 work (4), 0x2b6 escrow (0xe), 0x2b7 market (0xf), 0x2b8 assembly (2), 0x2b9 corpse summon (0xb), 0x2ba "I need to repair my gear." (0x10). [O]
- Alternative: **0x2bf** MsgEntityIDAndInt `eid64, i32 count`, followed by `count` records of MsgStringAndTwoInts `wstr text, i32 id, i32 type`. Each record becomes an option (text, type = 2nd int, id = 1st int). FUN_004c8d60 [O]
- Optional: **0x581** MsgSingleInt `i32 4` plays the voice set's "MerchantGreet". FUN_004c64d0 [O]
- After building the dialog, the client sends **0x127** (no payload, an ack). [O] The server can ignore it.
- Clicking an option -> FUN_0068a680 -> FUN_004c4860 -> FUN_004c4640(option): type 5 -> 0xe5. [O]

### 1c. Server reply: open the window (dispatcher FUN_00547220)
1. **0x283** (no payload) -> FUN_00542ca0. Sets state=2, gamevar `MerchantState`=2 and `MerchantTranactionStarted`=1, and opens `_inventory`. [O] VGUIMerchant.xml: the window "Merchant" has `visibilityGameVar="MerchantTranactionStarted"`, so this shows the window. [O]
   - On receipt, the client sends **0xeb** (no payload) [O]. Its meaning is unclear (ack, or a request for the list) [I]. The server can ignore it and just send the list.
2. **0x285** MsgClientMerchantItem, **one per item for sale**. Ignored unless state==2, so send it after 0x283. FUN_00546ff0 builds the item through FUN_005157b0 and appends it to list +0x8. [O]
3. **0x28c** (no payload) -> FUN_00544480. Publishes list +0x8 into the `MerchantItemList` gamevar (the pagelist, 12 entries per page with prev/next). This is the "list done / refresh" step. Without it nothing is drawn. [O]
- **0x28b** (or 0x293) (no payload) clears the merchant and escrow lists (FUN_00545460). Use it before resending a list. [O]
- No item-count limit was seen. [O]

**Failure / close: 0x284** (also 0x290 and 0x29a) MsgSingleByte `u8 reason` -> FUN_00545920. Resets state to 0, clears all lists, and sets `MerchantTranactionStarted`, `EscrowMerchantTranactionStarted` and `RepairMerchantTranactionStarted` to 0 (closes the window). Reason 0 = "Your target is not interested in transacting with you.", 1 = "You are out of range for buying and selling.", 2 = "Please target the merchant you would like to interact with.", any other value (e.g. 3) = silent close. [O]

### MsgClientMerchantItem (0x285) wire layout
Serializer FUN_00542950 [O]. Copy into the client item: FUN_005157b0 [O]. Meaning column: [O] where noted, else from ITEM_FIELDS.md semantics of the same item offset.
| # | type | msg off | item off | meaning / value to send |
|---|---|---|---|---|
| 0 | i32 | 0x14 | +0x000 | server item id (template id) |
| 1 | i32 | 0x18 | +0x650 | **handle**. The client echoes it in buy (0xe7). Must be unique per merchant entry [O] |
| 2 | wstr | 0x1c | (name) | item name (shown in `_merchant_entry_name`) [I] |
| 3 | wstr | 0x38 | | description [I] |
| 4 | wstr | 0x54 | | unknown, send "" |
| 5 | i32 | 0x70 | +0x5c | default equip slot (same as 0x197 field 8) |
| 6 | i32 | 0x74 | +0x74 | container capacity (0) |
| 7 | i32 | 0x78 | +0x70 | icon id (e.g. 443) |
| 8 | **f32** | 0x7c | **+0x1c4** | **price in copper** (also written again by the 0x285 handler) [O] |
| 9 | u8 | 0x80 | +0x574 | 0 |
| 10 | u8 | 0x81 | +0x668 | usable flag. **1** (0 = red icon) |
| 11 | u8 | 0x82 | +0x714 | quality grade, 0 |
| 12 | i32 | 0x84 | +0x70c | stack quantity (constructor default 1) |
| 13 | i32 | 0x88 | +0x710 | charges, 0 |
| 14 | i32 | 0x8c | +0x528 | 0 |
| 15 | i32 | 0x90 | - | not copied, 0 |
| 16 | i32 | 0x94 | +0x664 | durability %, 100 (or -1 to hide) |
| 17-18 | wstr x2 | 0x98, 0xb4 | | "" |
| 19-26 | i32 x8 | 0xd0..0xec | +0x66c..+0x688 | constructor default -1. Send -1 |
| 27 | wstr | 0xf0 | | "" |
| 28-30 | i32 x3 | 0x10c..0x114 | - | constructor default -1. Send -1 |
| 31 | wstr | 0x118 | | "" |
| 32 | wstr | 0x134 | | "" |
The client forces item+0x58b = 0xFF (normal tooltip path). [O]

## 2. Buying
**Client -> server 0xe7** MsgTwoInts `i32 handle, i32 quantity` (FUN_00543c90) [O].
- handle = merchant item field 1 (+0x650).
- The UI (drag from `merchant_buy`, FUN_006963e0, or action 0xb2 FUN_006887b0) always sends quantity **1**. `/buy N name` sends N. [O]
- After sending, the client plays a UI sound (FUN_004c0b60). [O]

**Server replies** [I, assembled from existing handlers]:
- Success:
  1. **0x197** MsgSingleItemInfo with the new item in a free bag slot (fields 7=-1, 15=-1, 16=slot, 71=unique handle). Set field 111 (f32) = the sell value (see section 4).
  2. **0x1aa** MsgSingleLong `i64 new total copper`. The client prints "You lose %s." and plays CoinsOut from the delta (FUN_0050b6e0, INVENTORY.md). [O]
  - For a stack merge, use **0x1ae** MsgTwoInts `i32 handle, i32 newCount` instead of a new 0x197 (FUN_00510080) [O].
- Failure: **0x0e** MsgSingleShort `i16 code` (string table FUN_0061d530) [O]:
  - 0xfb CantAffordThat
  - 0x100 SpaceInInventory
  - 0xfa OneMerchantAtATime
  - 0xfe DoNotMeetRequirementsToBuy
  - (0xfc/0xfd faction/infamy, 0xff RepairAllCouldntAffordAll)
- The merchant list does not need resending for unlimited stock.

## 3. Selling, buyback, closing
**Client -> server 0xe8** MsgTwoInts `i32 handle, i32 quantity` (FUN_00543df0) [O].
- handle = the inventory item's +0x650 = 0x197 **field 71**.
- Drag-drop onto the merchant window (`merchant_dragdrop_sell`, FUN_00688830) sends quantity = the full stack (+0x70c). `/sell N name` sends N.
- The client pre-checks that the item exists and that quantity <= stack count. [O]

**Server replies** [I]:
- Remove the item: **0x1a5** MsgIntAndBool `i32 handle, bool8 0` (FUN_005062f0 removes it from the main inventory list and clears its bag slot) [O]. For a partial stack, use **0x1ae** `i32 handle, i32 remaining` [O].
- **0x1aa** `i64 new total copper` ("You receive %s.", CoinsIn) [O].
- Optional buyback entry: **0x197** with field 92 = **10**, which puts it in `MerchantBuybackList` (the Buyback tab, INVENTORY.md) [O]. Then **0x289** MsgIntAndFloat `i32 handle, f32 price` sets the item's +0x1c4 and refreshes `MerchantBuybackList` (FUN_00544180) [O].
- Errors via 0x0e:
  - 0x103 CantSellThat
  - 0x104 CantSellNoSellItems
  - 0x105 EmptyThatBeforeSelling
  - 0x101 MerchantCantAffordThat
  - 0x102 NotThatManyItemsStacked

**Buyback: client -> 0xe9** MsgSingleInt `i32 handle` (FUN_00543fa0, drag from `merchant_buyback`) [O]. Server reply: **0x1d9** MsgSingleInt `i32 handle` (remove from buyback, FUN_004ff490 [O]), then 0x197 into the bag and 0x1aa coins [I].

**Price query: client -> 0xea** MsgSingleInt `i32 inventory handle`.
- Sent by `/price name`, and automatically on every 0x1ae stack change while a merchant is open (FUN_00510080 -> FUN_00543f00) [O].
- Suggested reply: **0x289** `i32 handle, f32 sell price`. If the handle is in the main inventory, it only sets +0x1c4 [O handler, I pairing].

**Examine a merchant item: client -> 0xec** (or 0xf0 when the escrow list is non-empty) MsgSingleInt `i32 handle` (FUN_00544040 from FUN_0068f6c0) [O]. Possible reply: **0x28a** MsgSingleItemInfo (updates the existing item by field 71 and refreshes `inventory_examine`, FUN_00545170) [I].

**Closing**:
- Client -> server: `merchant_done` / close box / `/stopshopping` / a second /haggle -> FUN_005458f0(1) or FUN_00546380. The client clears its lists, sets state=0 and sends **0xe6** then **0xf4** (both no payload) [O]. Treat either as "end transaction". Answer with **0x284 u8 3** (silent) so the gamevars reset and the window can reopen [I].
- Server -> client: **0x284** `u8 reason` (0/1/2 print a message, >=3 silent) [O]. Use it when the player walks out of range (reason 1) or the target is not a merchant (0/2).

Escrow / repair (not needed for a basic vendor) [O]:
- Escrow start 0x28d, item 0x295, list publish 0x294, remove 0x296 {i32 handle}.
- Repair start 0x297, entry 0x29f {i32 handle, f32 cost} (state 2), publish 0x29e, remove 0x2a0 {i32 handle}.
- Client 0xef / 0xf2 {i32 handle} come from UI actions 0xb7 / 0xb8. 0xf3 (no payload) is action 0xb9 (repair-all?) [I].

## 4. Where the price lives
- Item offset **+0x1c4 (f32, copper)** is the price/value. FUN_004be860(value, item+0x620, item+0x630) splits it into coin denominations for display (`_merchant_entry_price`, `_money_clip`) [O split; I denominations 1/100/10000/1000000].
- Merchant item: 0x285 field 8 (f32 @0x7c) [O].
- Inventory item (sell value): **0x197 field 111** (f32, msg 0x5d0 -> +0x1c4) [O]. It can be updated later with 0x289 [O].
- Coins: 0x1bb (silent set) / 0x1aa (set + chat line), both i64 total copper [O].

## Minimal server recipe
1. Player targets the vendor and presses U / hails (Say 0x74 starting with "Hail"):
   - send 0x2bb {eid64 npc}
   - send 0x2b5 (optional 0x581 {i32 4})
2. Player clicks "Show me your wares." (or types /haggle) -> client 0xe5.
   - Validate target and range. On failure send 0x284 {u8 0|1|2}.
   - Otherwise send 0x283, then 0x285 per item (unique handle, f32 price, usable=1, qty=1, durability 100, -1 defaults), then 0x28c.
3. 0xe7 {handle, qty}: check coins and bag space.
   - On failure send 0x0e {i16 0xfb or 0x100}.
   - Otherwise send 0x197 new item (field 111 = sell value), then 0x1aa {i64 total}.
4. 0xe8 {invHandle, qty}: send 0x1a5 {handle, 0} (or 0x1ae {handle, left}), then 0x1aa {i64 total}. Optionally add the item to buyback (0x197 with f92=10, plus 0x289).
5. 0xe9 {handle}: send 0x1d9 {handle}, 0x197, 0x1aa.
6. 0xea {handle}: send 0x289 {handle, f32 sell value}.
7. 0xe6 / 0xf4: send 0x284 {u8 3}. Server-side close (out of range): send 0x284 {u8 1}.
