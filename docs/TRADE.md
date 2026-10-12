# Player-to-player trade (VGClient.exe, class VGClientTrade)

> **Verified live with two clients (2026-10-12):** `/trade Name` (0xc0) → Trade Request popup (0x208); Accept (0xc3) → Trading window on both sides (0x205 to the inviter); an offered item (0xc4) and coin (0xc6) show on both sides; both Accept (0xc7) → items and coins move, "Trade successful." (0x201). Implemented in `server/trade.py` and `login_stub.handle_trade_event`. Dragging items into the window could not be scripted in testing; `!tradeadd <bag slot>` and `!tradecoin <copper>` send the same requests.


This comes from static analysis only (Ghidra via REA). [O] means read directly in the decompiled code. [I] means inferred.
Wire format: zone event `u16 2, u32 id, u32 len, payload`. Payload fields are packed little-endian in registration order. wstr = UTF-16LE text plus a 00 00 terminator.

## Client trade state (trade object +0x54) [O]
FUN_005c8b70 sets the state and drives the UI vars TradeState, TradeTrading, TradeInvitePending and TradeAwaitingInviteResp.

| value | meaning |
|---|---|
| 0 | idle |
| 1 | I invited someone and am waiting for their answer (TradeAwaitingInviteResp) |
| 2 | someone invited me (TradeInvitePending) |
| 3 | trading; the window is open (TradeTrading) |

Other fields of the trade object:
- **+0x50 = trade sequence number ("seq")**. Every trade request the client sends carries the current seq. Every server trade message that has a seq field overwrites it [O]. The server should increase seq on every offer change and reject accepts that carry an old seq [I].
- +0x20/+0x24 = my offered coins (i64).
- +0x28/+0x2c = the partner's offered coins (i64).
- +0x30 = I accepted. +0x31 = the partner accepted.
- +0x34 = the partner's name (wstr object).
- +0x8/+0xc = my offer list. +0x14/+0x18 = the partner's offer list.
- The client allows at most 8 items in my offer (`count < 8` check in FUN_005ca600) [O].

## Client -> server (send via FUN_004cfb00 / FUN_004cfb50, no payload for the latter) [O]

| id | sender fn | class | payload | trigger |
|---|---|---|---|---|
| **0xc0** | FUN_005cb750 | MsgSendSingleSGOString | `wstr targetName` | `/trade [name]`, or right-click "Trade" (FUN_00698030 -> FUN_005cb750). With no name the client uses the current target's name (DAT_01463a58+0xcc). Only sent from state 0; the client then sets state 1. |
| **0xc1** | FUN_005c9560 | none | - | the inviter cancels its own invite (state 1 -> 0, "Invitation cancelled.") |
| **0xc2** | FUN_005c95e0 | none | - | the invitee declines (`/tradeno`; state 2 -> 0) |
| **0xc3** | FUN_005c95a0 | none | - | the invitee accepts (`/tradeyes`; the client sets **state 3 locally**) |
| **0xc4** | FUN_005ca600 | MsgClientTradeAddItem (FUN_005c8f20) | `i32 itemHandle, i32 seq, i32 quantity` | drag a bag item into the trade window. The handle is the bag item's +0x650 (0x197 field 71). The client checks that quantity is no more than the stack size and that fewer than 8 items are already offered. |
| **0xc5** | FUN_005c9620 | MsgClientTradeRemoveItem (FUN_005c91b0) | `i32 offerHandle, i32 seq` | remove one of my offered items. offerHandle is the +0x658 key that 0x1fc field 4 set [I: the argument is lost in the caller's decompile] |
| **0xc6** | FUN_005cc470 | MsgClientTradeSetCoin (FUN_005c9070) | `i64 copper, i32 seq` | the platinum/gold/silver/copper boxes (`_trade_offer_*`), as p*1000000 + g*10000 + s*100 + c. Sent only when the value changed and is no more than my total coins. |
| **0xc7** | FUN_005c96f0 | MsgClientTradeAcceptTransaction (FUN_005c92f0) | `i32 seq` | Accept button (trade_accept) |
| **0xc8** | FUN_005cdb10 | MsgClientTradeAcceptTransaction | `i32 seq` | Cancel (trade_cancel). The client resets locally first ("Trade cancelled.", state 0, offers cleared) and then sends. |
| **0xc9** | FUN_005c9790 | MsgSingleInt | `i32 offerHandle` | hover/inspect an item in `_trade_their_offers` (from FUN_006930d0). Sends the partner item's +0x658. Reply: 0x20c. |
| **0x206** | FUN_005ccc30 | none | - | sent automatically when a 0x208 invite arrives while the client is not idle (busy). Treat it like a decline [I]. |

The client has **no "un-accept" message**. Acceptance is reset only by the server sending 0x204 [O].

## Server -> client (dispatcher FUN_005cdd90) [O]

| id | handler | payload | effect |
|---|---|---|---|
| **0x208** | FUN_005ccc30 | `wstr inviterName` | **Invite received.** Needs state 0 (otherwise the client answers 0x206). Prints "<name> has invited you to a trade. Use /tradeyes ... /tradeno", sets state 2 and sets TradeOthersName. |
| **0x205** | FUN_005cce10 | `wstr partnerName` | **Trade window opens.** Needs **state 1** (the inviter). Resets coins and offers, prints "You begin a trade session.", sets state 3 and sets TradeOthersName. |
| 0x206 | FUN_005c98b0 | none | to the inviter (state 1): "Your trade invite was declined.", state 0 |
| 0x207 | FUN_005c9810 | none | to the invitee (state 2): "Your current trade invite was cancelled.", state 0 |
| **0x1fc** | FUN_005ccf50 | MsgTradeAddMyItem (FUN_005c8a60): `i32 seq, i32 slot, i32 bagHandle, i32 offerHandle, i32, wstr, i64, i32, u8, i32, i32` | **My offer: add.** Copies my own bag item found by bagHandle (FUN_004fa970). The copy's +0x1bc = slot, +0x650 = bagHandle, +0x658 = offerHandle (the list key). Prints "%d %s was added to your offer." using the bag stack count and adds it to TradeMyItemsList. **Fields 5 to 11 are not read** (send 0 / empty). |
| **0x1fd** | FUN_005cd0e0 | full MsgSingleItemInfo (the same record as 0x197) | **The partner's offer: add.** Parsed by FUN_005167c0. **Field 15 (container, +0x654) = seq** and **field 71 (handle, +0x650) = offerHandle**; the client then sets +0x658 = the handle and resets +0x650/+0x654 to -1. Prints "<name> has added [N ]<item> to their offer." using field 6 (quantity) and adds it to TradeOthersItemsList. |
| **0x1fe** | FUN_005cd2f0 | MsgTradeRemoveMyItem: `i32 seq, i32 offerHandle` | My offer: remove. Lookup by +0x658 (FUN_005ca850). Prints "... was removed from your offer." |
| **0x1ff** | FUN_005cd4d0 | `i32 seq, i32 offerHandle` | The partner's offer: remove (FUN_005ca8d0). Prints "<name> removed ... from their offer." |
| **0x20a** | FUN_005cd6d0 | MsgClientTradeSetCoin: `i64 copper, i32 seq` | My offered coins (TradeMyOfferedCoins, `_trade_offer_*` boxes) |
| **0x20b** | FUN_005cd7d0 | `i64 copper, i32 seq` | The partner's offered coins (FUN_005cb950 refreshes TradeOthersOfferedCoins) |
| **0x202** | FUN_005c99f0 | `i32 seq` | I accepted. Sets +0x30 = 1, prints "You accept the trade as it stands." and sets TradeMyAccepted. |
| **0x203** | FUN_005cbcb0 | `i32 seq` | The partner accepted. Sets +0x31 = 1, prints "<name> accepts the trade as it stands." and sets TradeOthersAccepted. |
| **0x204** | FUN_005c9af0 | `i32 seq` | **Acceptance reset.** Clears both flags and prints "The trade status has changed. Both parties must okay the new status..." |
| **0x200** | FUN_005cdbd0 | none | Cancelled. Accepted in state 3 or 1. Sets state 0, clears offers, prints "The trade has been cancelled." and closes the window. |
| **0x201** | FUN_005cdc10 | none | Completed. Needs state 3. Sets state 0, clears offers, prints "Trade successful." and refreshes the inventory containers (FUN_0050ef30). |
| 0x209 | FUN_005c98f0 | `u8 reason` | Add-item refused: 1 equipped, 2 container not empty, 3 not that many stacked, 4 No Drop, 5 Unique already owned by the partner, 6 Quest, 7 Soulbound, 8 Account Bound |
| 0x20c | FUN_005cbe20 | MsgSingleItemInfo + sub-records | reply to 0xc9: extra detail for the partner's item, keyed by field 71 = offerHandle. Optional. |
| 0x0e | FUN_0061d530 | `i16 code` | generic errors: 0x4f CantTradePending, 0x50 CantTradeMailing, 0x51 CantTradeMarket, 0x52 CantTradeNoTarget, 0x53 CantTradeRange, 0x54 CantTradeInvalid, 0x55 CantTradeMoveCloser, 0x56 CantTradeRightNow, 0x58 TradeNotEnoughSpace, 0x59 InventoryLockedForTrade |

Which message shows which side: **mine** is 0x1fc / 0x1fe / 0x20a / 0x202. **The partner's** is 0x1fd / 0x1ff / 0x20b / 0x203. 0x204, 0x200 and 0x201 go to both players.

## Minimal server recipe
Keep one trade object per pair: A (inviter), B (invitee), seq, offers[A/B] = {handle: qty}, coins[A/B], accepted[A/B].

1. **A sends 0xc0 {wstr name}.** Find player B by name. If B is busy or invalid, send A `0x0e {i16 0x4f/0x54}` and `0x206` so A's state goes back to 0.
   Otherwise send **B: 0x208 {wstr A.name}**.
2. **B sends 0xc3** (accept). seq = 1. Send **A: 0x205 {wstr B.name}**.
   Send B nothing. B's client already set state 3 when it sent 0xc3, and TradeOthersName came from the 0x208. A 0x205 to B would only print "Programmer error ... not awaiting acceptance", because the 0x205 handler needs state 1 [O].
   - If B sends 0xc2 (or 0x206), send A: 0x206. If A sends 0xc1, send B: 0x207.
3. **0xc4 {handle, seq, qty} from P** (partner Q). Check the item is tradeable; on failure send P `0x209 {u8 reason}`. Otherwise:
   - seq++; offers[P][handle] = qty;
   - P: **0x1fc** `{i32 seq, i32 slotIndex(0..7), i32 handle, i32 handle, i32 0, wstr "", i64 0, i32 0, u8 0, i32 0, i32 0}`. Use offerHandle = bagHandle so every later key is the plain item handle.
   - Q: **0x1fd** = `inventory_item(item_id=handle, name, slot=slotIndex, quantity=qty, container=seq, ...)` (field 71 = handle, field 15 = seq).
   - If anyone had accepted: clear both flags and send **0x204 {seq}** to both.
4. **0xc5 {handle, seq} from P**: seq++; delete it; P: **0x1fe {seq, handle}**; Q: **0x1ff {seq, handle}**; then reset acceptance (0x204 to both) as above.
5. **0xc6 {i64 copper, seq} from P**: clamp to P's coins; seq++; P: **0x20a {copper, seq}**; Q: **0x20b {copper, seq}**; reset acceptance as above.
6. **0xc7 {seq} from P**: ignore it if seq != current seq. accepted[P] = 1; P: **0x202 {seq}**; Q: **0x203 {seq}**.
   When both have accepted, complete the trade:
   - For each item P gives Q: P gets **0x1a5 {i32 handle, bool8 0}** (or 0x1ae {handle, remaining} for part of a stack). Q gets **0x197** for the item in a free bag slot (container -1, new unique handle in field 71, slot = free index). Do the same in the other direction.
   - Coins: compute the new totals and send each player **0x1aa {i64 newTotal}** ("You receive/lose X."). Use 0x1bb to set it silently.
   - Then send **0x201** to both (closes the window, "Trade successful.", refreshes the bags).
   - If a bag is full, send `0x0e {i16 0x58}` (TradeNotEnoughSpace) and reset acceptance with 0x204 instead [I].
7. **0xc8 {seq} from P**: P already closed its window. Send **Q: 0x200** and drop the trade object. Also cancel on disconnect, zoning or death: send 0x200 to the player who is still there.

Items stay in the owner's bag until completion. The client only shows copies in the trade window, so nothing has to be removed before step 6 [O: 0x1fc copies the item, it does not move it].

## Uncertain points
- 0x1fc field 2 (slot → copy+0x1bc) is probably the trade-window slot. The list UI (FUN_005c8d40) does not read it, so any value 0..7 works [I].
- 0x1fc fields 5–11 are not read by the client. Their meaning is unknown.
- That 0xc5's argument is the +0x658 key comes from the lookup code, because the caller's decompile drops the argument [I]. Setting offerHandle = bagHandle removes the ambiguity.
- 0x206 sent by the client (busy auto-reply) means "decline" [I].
