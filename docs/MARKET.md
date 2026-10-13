# Broker (player market)

> **Verified live (2026-10-13):** Tamsin Vale (Broker, `"broker": "Sundering Wastes Market"` in mobs.json) shows the client's own option "I would like to browse the local market.". The market window opens with that name. Search lists Justins' Copper Ingot (level 1, 40 copper, "6d", seller Justins); selecting it shows Seller Price 40, Commission Fee 1, Total 41. Buy shows the client's "Market Buy Confirmation" ("The item will be sent to your mailbox."); accepting charges 41 copper and the ingot arrives by mail from "The Market", and the seller is mailed the 40 copper. On the Your Market Items tab, dragging an item into the sell slot and typing 75 copper shows the deposit (1 copper); "Market Sell Confirmation" then lists it ("7d Ranger", "listing 1 of a possible 20 items"). Cancel Item Sale shows "End Sale Confirm" and removes the listing.
>
> **Not tested live:** Relist (0x53f) and examine (0x53e).

Server: `server/market.py`, `login_stub.handle_market_event`. Storage: `server/market.json` (not committed).

## Server behaviour

- Fees: 5% commission (the buyer pays it on top of the price), 1% deposit (paid by the seller when listing, not refunded), no favor reduction. The client computes both in single-precision floats and truncates (40 x 5% shows as 1), so the server does the same (`market.PERCENT`).
- Bought and cancelled items, and sale proceeds, are delivered by mail (the client's confirmations say so).
- Listings last 7 days (field 10 = unix expiry time). Expiry is not enforced yet.
- Search filters by item name and seller name; level, class, slot, type, rarity and sphere are ignored.
- The "Favor %" line in the sell panel is the reduction field (field 4 of 0x52e).

## Corrections to the protocol notes below

- MsgClientMarketItem field 10 is the **expiry as a unix time**: the Time column subtracts the client's clock (code around `0x67c14b`), and 0 shows "0m" and "Expired" in the seller column.
- Notice 0x1bd MarketPurchaseSuccess has no text in this client ("Localize() failed ... Key = MarketPurchaseSuccess"); the server prints its own line instead.


Tags: [O] means read directly from decompiled code or disassembly. [I] means inferred.
All messages are zone events in both directions. Wire layouts are packed in field-registration order (see ZONE_MESSAGES.md).
Market manager object: `DAT_01463a2c`. Its fields:
- `+0x04..0x0c`: search-result vector.
- `+0x14..0x1c`: my-listings vector.
- `+0x70/74/78/7c/80`: selected search filters (sphere/type/slot/class/rarity).
- `+0x84..0xb8`: data from MarketInfo.
- `+0xbc`: id of the listing being relisted (-1 when none).

Each list entry is a `VGMarketItemInfo` (0x38 bytes, ctor FUN_0053f400):
- `+4` = listing id
- `+8` = client-local item handle (item+0x6ec)
- `+0xc` = seller wstr
- `+0x28` = i64 price
- `+0x30` = u32
- `+0x34` = i32

## 1. Opening a session
- **No broker EntityTypes bit.** There is no Broker or Market hover/cursor string. The `*Hover` list is Player, Merchant, Altar, AssemblyTrainer, CraftingStation, Resource, TaskMaster, Trainer, RecipeTrainer, Interactable, Corpse, Mailbox, Banker, NonPlayer. So a broker is an ordinary NPC (0x10, optionally 0x8 for the merchant cursor) that offers a dialogue option. [O]
- **Dialogue.** Send S->C `0x2bb` {eid64 npc}, which opens the dialogue window. Then send S->C **`0x2b7`** (no payload). FUN_004c7a00 adds the option **"I would like to browse the local market."** (0x107a680) with option type **0xf**. Alternatively, use 0x2bf records with type 0xf. [O, see MERCHANTS.md 1b]
- **Click.** FUN_004c4640 case 0xf calls FUN_00536740, which sends **C->S `0x52b`** (no payload). The NPC is not in the payload, so the server must use the player's current target. [O]
- **Server opens the window with S->C `0x52e` MsgClientMarketInfo** (handler FUN_00541ba0). It stores the fields, rebuilds the search dropdowns (FUN_00540770), and sets gamevar **`MarketWindow`=1**, which shows the window. [O]
- **Close from the client.** The `market_done` button (UI cmd 0x48) calls FUN_0053dbc0. It sends **C->S `0x52c`** (no payload), then sets MarketWindow=0 and clears both lists. [O]
- **Force close from the server.** S->C **`0x52d`** (no payload, FUN_0053e040) does the same thing locally and sends nothing back. [O]

## 2. Server -> client messages (dispatcher FUN_005426e0)

| id | payload | handler | effect |
|---|---|---|---|
| 0x52d | none | FUN_0053e040 | Close the window: MarketWindow=0, clear search and listings, clear selections [O] |
| 0x52e | MsgClientMarketInfo (below) | FUN_00541ba0 | Set the fee/market gamevars and **open** the window [O] |
| 0x52f | none | FUN_0053c980 | Clear the my-listings vector [O] |
| 0x530 | none | FUN_00539150 | Redraw `MarketListingItemList` (my listings) from the vector [O] |
| 0x531 | MsgClientMarketItem | FUN_00542020(flag 0) | Append to **my listings**, no redraw (batch, then send 0x530) [O] |
| 0x532 | MsgClientMarketItem | FUN_00542020(flag 1) | Append to my listings and add the UI row right away (single new listing) [O] |
| 0x533 | MsgClientMarketItem | FUN_005425c0 | Remove the my-listings UI row with this listing id, then re-add it (update/replace) [O] |
| 0x534 | none | FUN_0053d070 | Clear search results [O] |
| 0x535 | none | FUN_005392d0 | Redraw `MarketSearchItemList` from the vector. Sets `bMarketMaxResults` = (count > 199), so the server caps results at 200 [O] |
| 0x536 | MsgClientMarketItem | FUN_00542180 | Append to **search results** (no redraw; finish with 0x535) [O] |
| 0x537 | MsgSingleItemInfo (same 119-field record as the inventory item, 0x197) | FUN_0053c4b0 | Reply to the examine request 0x53e. Finds the market item whose handle = record field 71 (FUN_00539540), rebuilds the full item, and shows the `inventory_examine` tooltip [O] |
| 0x538 | MsgEntityIDAndInt {eid64 (unused), i32 listing id} | FUN_0053d160 | Remove that listing from both vectors and both UI lists, and clear the buy/offer selection. Use it when something is sold, bought, cancelled or expired [O] |
| 0x61d | none | FUN_00538fd0 | Clear the four price edit boxes `_market_price_platinum/gold/silver/copper` and the selection (send after a successful place) [O] |

### MsgClientMarketInfo (0x52e)

Registrar FUN_00536280. Wire layout: `i32, wstr, f32, f32, f32, i32, i32`. [O]

| # | type | stored at | gamevar / meaning |
|---|---|---|---|
| 0 | i32 | mgr+0x84 | unused by the UI (market id?) [I] |
| 1 | wstr | mgr+0x88 | `MarketName` [O] |
| 2 | f32 | mgr+0xa8 | `MarketCommissionPercBase` (percent, e.g. 5.0) [O] |
| 3 | f32 | mgr+0xa4 | `MarketDepositAmountPercBase` [O] |
| 4 | f32 | mgr+0xac **and** +0xb0 | `MarketDepositAmountPercReduction` and `MarketCommissionPercReduction` (one value used for both) [O] |
| 5 | i32 | mgr+0xb8 | `MarketMaxItemsPerPlayer` [O] |
| 6 | i32 | mgr+0xb4 | no UI use found [O-absence] |

The client also publishes `...PercTotal` = Base − Reduction. All values are formatted "%.3f". [O]

**Fees, as the client computes them:**
- Buyer pays `price + price*max(0,comm−red)*0.01` (FUN_00536af0, FUN_0053a6c0). [O]
- If player money `*DAT_01463944` (i64) is less than that, the client prints "You can't afford that." and sends nothing. [O]
- The seller's deposit shown is `max(1, price*max(0,dep−red)*0.01)` (FUN_0053f6c0). `MarketTotalCost*` = price + deposit. [O]
- The server must charge and refund these itself. [I]

### MsgClientMarketItem (0x531/0x532/0x533/0x536)

Registrar FUN_00536300. FUN_00515a10 maps the fields onto a client item object. Item offsets match docs/INVENTORY.md and ITEM_FIELDS.md. [O]

| # | type | msg off | item off / use | meaning |
|---|---|---|---|---|
| 0 | i32 | 0x14 | item+0x00 | server item id |
| 1 | i32 | 0x18 | item+0x650, info+4 | **listing id = item handle**. Used as the key by 0x538, buy, cancel, relist and examine |
| 2 | wstr | 0x38 | item+0x04 | **item name** (`_market_entry_name`) |
| 3 | wstr | 0x1c | item+0x3c, info+0xc | **seller name** (`_market_entry_seller_name`, reads item+0x40) |
| 4 | wstr | 0x54 | item+0x20 | description |
| 5 | wstr | 0x70 | item+0x600 | (inventory field 5 string) |
| 6 | i32 | 0x8c | item+0x5c | default equip slot |
| 7 | i32 | 0x90 | item+0x74 | container capacity (0) |
| 8 | i32 | 0x94 | item+0x70 | **icon** |
| 9 | i64 | 0xa8 | info+0x28 | **seller asking price, copper** (`MarketSellerPrice`; the list shows it with commission added) |
| 10 | u32 | 0xb0 | info+0x30 | not read by the UI; probably time left or expiry [I] |
| 11 | u8 | 0x98 | item+0x574 | (inventory field 93) |
| 12 | u8 | 0x99 | item+0x668 | usable (0 = red icon) → send 1 |
| 13 | i32 | 0xb4 | item+0x70c | stack quantity |
| 14 | wstr | 0xb8 | item+0x6f0 | (inventory field 4 string) |
| 15 | i32 | 0xd4 | item+0x710 | charges |
| 16 | u8 | 0xd8 | item+0x714 | crafted quality grade |
| 17 | u8 | 0xd9 | item+0x61c | rarity / name colour |
| 18 | i32 | 0x9c | item+0x528 | (inventory field 75) |
| 19 | i32 | 0xa0 | item+0x52c | **item level** (`_market_entry_item_level`) |
| 20 | i32 | 0x114 | item+0x644, info+0x34 | gold-membership flag (inventory field 118) |
| 21-22 | wstr ×2 | 0xdc, 0xf8 | copied to the item (2-string array) | |

The client forces item+0x58b=0xFF (not a graft) and +0x664=-1 (no durability line).

### Result codes

Send these through S->C `0xe` MsgSingleShort (FUN_0061d530). [O]

| code | string id | text |
|---|---|---|
| 0x1bd | MarketPurchaseSuccess | "You successfully purchased the market item." |
| 0x1be | CanNotFindItem | |
| 0x1bf | MustEnterPriceForItem | |
| 0x1c0 | MarketCannotPlaceNoTradeItems | |
| 0x1c1 | MarketCannotPlaceSoulboundItems | |
| 0x1c2 | MarketCannotPlaceAccountboundItems | |
| 0x1c3 | MarketMustRepairItem | |
| 0x1c4 | MarketYouCannotSellItems | |
| 0x1c5 | MarketCannotPlaceQuestItems | |
| 0x1c6 | MarketItemsOnlyFromMainInventory | |
| 0x51 | CantTradeMarket | "You may not trade and use the market at the same time." |

Client-side text (not codes): "You can't afford that.", "You cannot specify that much money." (price > 30,000,000 copper), and MustEnterPriceForItem when the price is 0. [O]

## 3. Client -> server events

UI commands 0x47–0x51 go through FUN_005424f0. [O]

| id | class / layout | sender | meaning |
|---|---|---|---|
| 0x52b | none | FUN_00536740 (dialogue option type 0xf) | open-market request (uses current target) |
| 0x52c | none | FUN_0053dbc0 (`market_done`) | close session |
| 0x53a | MsgMarketSearch (below) | FUN_0053d8c0 (`market_search`) | search |
| 0x53b | MsgEntityIDAndTwoInts {eid64 0, i32 **listing id**, i32 (not set; ignore)} | FUN_0053a6c0 (`market_buy_item`) | buy the selected search result. Listing id = item+0x650 of the item in `MarketSelectedBuyItemSlot` |
| 0x53c | MsgEntityIDAndTwoInts {eid64 0, i32 **listing id**, i32 0} | FUN_0053a830 (`market_cancel_item_sale`) | cancel my selected listing (`market_listing_pagelist` selection) |
| 0x53d | MsgMarketClientPlaceItem {i32 **inventory item handle (field 71)**, i64 **price copper**} | FUN_0053f480 (`market_place_item` when not relisting) | list an item. The item was dragged into `MarketMyOfferItemSlot` (cmd 0x50 → FUN_0053a8c0). Price = plat·1e6 + gold·1e4 + silver·100 + copper (FUN_0053e130); 0 < price ≤ 30,000,000 |
| 0x53e | MsgSingleInt {i32 listing id/handle} | FUN_00538f50 (from FUN_006930d0, hovering `_market_entry_item_slot` / `_market_selected_item_slot`) | examine request; the reply is 0x537 [O sender; I that the int is the handle] |
| 0x53f | MsgMarketClientReListItem {i32 **listing id**, i64 **new price**} | FUN_0053f5b0 (`market_place_item` while mgr+0xbc>0, after `market_relist_item` cmd 0x4b → FUN_00540050) | change the price of / relist my listing |

### MsgMarketSearch (0x53a)

Registrar FUN_005364e0. Wire layout: `eid64, i32, wstr, wstr, i32, i32, i16×7, bool8, i16`. [O]

| # | type | value |
|---|---|---|
| 0 | eid64 | 0 |
| 1 | i32 | 0 |
| 2 | wstr | item name text (`_market/item_name_text`) |
| 3 | wstr | seller name text (`seller_name_text`) |
| 4, 5 | i32 | 0, 0 (unused/paging?) |
| 6 | i16 | min level (`min_level_text`; 0 if blank) |
| 7 | i16 | max level |
| 8 | i16 | 0 |
| 9 | i16 | **class** (mgr+0x7c; default 1) |
| 10 | i16 | **equip slot** (mgr+0x78; any = -1 → 0xFFFF) |
| 11 | i16 | **item type** (mgr+0x74; any = 0xFF) |
| 12 | i16 | **rarity** (mgr+0x80; any = 0xFF; choices 8,7,6,4,2,10,1) |
| 13 | bool8 | 0 |
| 14 | i16 | **sphere** (mgr+0x70; any = -1; choices 0,1,3,… via FUN_00d02b10) |

The dropdown values come from FUN_005422e0 and FUN_00540770. Valid types are those where FUN_00d01550(type)==sphere; slots are 0..0x61 where FUN_00d014c0. The class table is 0x108a890..0x108a8d4 (skipping 0x2e and 10). [O]

**Collect proceeds.** There is no client event for collecting proceeds; none exists in the 0x52b–0x53f range or the market UI commands. [O-absence] The server must pay the seller directly or by mail when an item sells. [I]

## 4. Recommended sequences

- **Open:**
  1. S `0x2bb`{npc}
  2. S `0x2b7`
  3. C `0x52b`
  4. S `0x52e`{0, "Market Name", comm%, deposit%, reduction%, maxItems, 0}
  5. S `0x52f`, then `0x531`×N (the player's own listings), then `0x530`
- **Search:**
  1. C `0x53a`
  2. S `0x534`
  3. S `0x536`×N (≤200)
  4. S `0x535`
- **Buy:**
  1. C `0x53b`{0, listingId, x}
  2. Server checks funds and takes price+commission (send the coin update the way merchant.py does)
  3. Add the item to the buyer's inventory (`0x197` inventory_item)
  4. S `0x538`{0, listingId} to the buyer (and to the seller if online)
  5. S `0xe` code `0x1bd`
  6. Pay the seller price (minus nothing; the buyer paid the commission) by mail or directly. [I for 2/3/6]
- **Sell (place):**
  1. C `0x53d`{handle, price}
  2. Validate (error → `0xe` 0x1c0–0x1c6)
  3. Charge the deposit
  4. Remove the item from inventory (as merchant sell / bank deposit do)
  5. S `0x532`{record, field1 = new listing id}
  6. S `0x61d` to clear the price boxes
- **Relist:**
  1. C `0x53f`{id, price}
  2. S `0x533`{updated record}
- **Cancel:**
  1. C `0x53c`{0, id, 0}
  2. S `0x538`{0, id}
  3. Return the item to the inventory (`0x197`)
- **Examine:**
  1. C `0x53e`{id}
  2. S `0x537`{full inventory item record with field 71 = id}
- **Close:**
  - C `0x52c` (no reply needed), or S `0x52d` to force a close.
