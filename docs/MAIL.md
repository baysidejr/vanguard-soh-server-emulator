# Mail

> **Verified live (2026-10-13):** a Mailbox (race 527, EntityTypes 0x20000) stands at the camp. Targeting it and typing /mail (or clicking it) opens the Mail window. The inbox lists "Orin the Trader / A small gift / 29 days"; the Read Mail window shows the body, the attached coin and item; clicking them prints "You receive 50 copper." and "You receive Copper Ore.". After reading, the lifetime drops to the read-mail value (7 days). Compose to Justins with 5 copper shows the client's "Confirm Send Money" popup, then sends ("You lose 15 copper." before the postage fix). Delete removes the letter. Mail survives a server restart (`server/mail.json`).
>
> Also verified: dragging an item from the bags into the compose slot (the client fills the subject with the item name and shows shipping 24); a cash-on-delivery letter shows the client's "Confirm Shipping Fee" popup with the price, and accepting takes the item ("You receive 2 Copper Ore.", "You lose 12 copper.") and mails the payment to the sender; Return sends a letter back with its coin.

Server: `server/mail.py`, `login_stub.handle_mail_event`. Storage: `server/mail.json` (not committed). Dev command: `!mailme` (a letter from Orin with 50 copper and a Copper Ore).

## Server behaviour

- 0x520 needs a targeted mailbox within 800 units (otherwise 0x0e code 0xf8 PleaseTargetMailbox or 0xf9 MoveCloserToMailbox). The first open sends 0x51e; every open sends 0x518, the mails (0x515, plus 0x516 for an item) and 0x519.
- Sending checks the recipient (an existing character), self-mail, subject (49) and body (1000) lengths and the attached item. It charges postage and item shipping as the client shows them (20% off the 0x51e values: 8 and 24 copper), and the coin sent. An item leaves the bags at once. Online recipients get 0x513 and "You have new mail from X.".
- Cash on delivery: the copper amount is the price. Taking the item charges it and mails the payment to the sender ("Payment: ...").
- Return sends the mail (coin and item included) back to a player sender with "Returned:" in the subject. Returned and system mail can't be returned.
- At login, unread mail sends 0x513 (the client prints "You have unread mail messages.").
- Postage, shipping and lifetimes are constants in mail.py; mail doesn't expire yet.


Legend: [O] observed in disassembly/decompile, [I] inferred.
Wire encoding is the usual SGO field packing: i32/u32 = 4 bytes, i64 = 8, bool8 = 1, wstr = UTF-16LE + NUL terminator.
Events are framed as in server/bank.py `_event()`.
The mail manager singleton is `DAT_01463a28` (ECX in every handler). Its fields:
- `+0x00..+0x1c`: the 8 ints from 0x51e
- `+0x20` vector: VGMailMessageInfo* (begin +0x24)
- `+0x30` vector: attached item objects (begin +0x34)
- `+0x40` vector: coin pseudo-items (begin +0x44)
- `+0x50` u8: bHaveUnreadMail
- `+0x51` u8: session open

## 1. Opening a session

- **Client -> 0x520, no payload** [O]. Sent by `FUN_00525140`, which first clears the session flag (`mgr+0x51 = 0`) and then calls `FUN_004cfb50(0x520)`. `FUN_00525140` is called from:
  - **Mailbox click**: `0x417eee`. This is the entity-flag dispatch. `test eax,0x20000` leads to `call 0x525140`.
  - **`/mail`**: `0x5fbfc0`, which is just `mov ecx,[0x1463a28]; jmp 0x525140`.
  - **A CSR "Send Mail" UI path**: `0x64d13a`.
  - **Unread-mail notification**: 0x513 also re-sends 0x520 while a session is open.

  The client sends **no target or entity id**. The server must check the player's current target and range itself. Failures use the generic **0x0e i16 code** (`FUN_0061d530` table):
  - `0xf8` PleaseTargetMailbox
  - `0xf9` MoveCloserToMailbox
  - Related codes: `0x50` CantTradeMailing, `0x1b5` CantGiveMailItem, `0x1b6` CantGiveMailMoney [O]
- **The server reply that opens the window is 0x51e MsgServerMailInfoVars, not 0x51f** [O]. `FUN_00527b40` acts only if `mgr+0x51 == 0`. It then:
  - sets `+0x51 = 1`
  - stores the 8 ints
  - sets `MailPostage` and clears the other cost gamevars
  - shows the `_mail` window (`FUN_00c0be50("_mail")` -> `FUN_00c1f190(1)`)
- **0x51f (both directions, no payload) closes the session.**
  - Server -> client (`FUN_00528780`): `+0x51 = 0`, clears the send form (`FUN_00527f10`), hides `_mail`, and resets `mail_pagelist` to "Inbox" [O].
  - Client -> server: the `mail_cancel` UI command (0x3a -> `FUN_00528760`) sends 0x51f with no payload [O]. `mail_close` (0x3d) only closes the read-mail sub-window locally and sends nothing [O].

## 2. Server -> client (dispatcher FUN_0052bbd0)

### 0x513: new mail notification, no payload (`FUN_00524f90`) [O]
- Sets `mgr+0x50 = 1` and gamevar `bHaveUnreadMail = 1`.
- Plays `UISounds.Tell7` and shows the "UnreadMail" (0x45) system message.
- If a session is open (`+0x51`), sends 0x520 again to refresh. Because 0x51e is ignored while `+0x51 == 1`, the server should answer that refresh with the list only (0x518/0x515/0x516/0x519).
- Use it at login when unread mail exists, and when mail arrives.

### 0x514: raw i32 result code (`FUN_005291b0`) [O]
The text is written to `_mail_status` (`FUN_00527e40`). Code 1 also clears the send form (`FUN_00527f10`). Other codes are ignored.

| code | text |
|---|---|
| 0 | Mail database error. Please try again in a few minutes. |
| 1 | Mail sent. (clears the compose form) |
| 2 | Unable to find mail recipient. |
| 3 | Mail subject is too long. |
| 4 | Mail body is too long. |
| 5 | Invalid Mail Session. |
| 6 | This item can not be mailed. |
| 7 | Test characters cannot send an item or coin in the mail. |
| 8 | You can not send yourself mail messages. |
| 9 | You can not mail damaged items. |
| 10 | Your account does not qualify to send mail. |
| 11 | You are at the max sent mail limit. |

### 0x515: MsgMailMessageFull, one inbox entry (`FUN_0052b9d0`; registration `FUN_00524af0`) [O]
Copied into a new VGMailMessageInfo (0x90 bytes, ctor `FUN_0052ae00`) and appended to the `mgr+0x20` vector. The handler does **not** check for duplicates, so send 0x518 first.

| # | type | msg off | -> info | meaning |
|---|---|---|---|---|
| 1 | i64 | 0x18 | +0x68 | **attached coin (copper)**. If nonzero, the client creates a coin pseudo-item (`FUN_00516750`; handle +0x650 = mail id, +0x6ec = -1, icon via `FUN_004bdd00`) shown in `_mail_item_slot1` [O] |
| 2 | i64 | 0x20 | +0x70 | **CoD price (copper)**. Charged on take-item when field 16 is set [O] |
| 3 | i32 | 0x2c | (dropped) | client ignores it. Send 0 [O] |
| 4 | i32 | 0x30 | +0x04 | **mail id**, the key for every other message. Must be nonzero, because 0x519 skips id 0 [O] |
| 5 | wstr | 0x5c | +0x24 | **subject** (`_subject_entry_name`, `_mail_subject_text`) [O] |
| 6 | wstr | 0x78 | +0x40 | **body** (`_mail_body_text`) [O] |
| 7 | u32 | 0x94 | +0x5c | **sent time**, unix seconds (compared with `time(NULL)`, `FUN_00ac3c70`). Unread expiry text = `mgr[6] - now + sent` [O] |
| 8 | u32 | 0x98 | +0x60 | **read time**, unix seconds; **0 = unread**. Unread rows are drawn in a different colour. On read the client sets it to `time(NULL)` if it is 0. Read expiry text = `mgr[7] - now + read`. `FUN_00526940` uses it to clear bHaveUnreadMail [O] |
| 9 | i32 | 0x34 | (dropped) | ignored. Send 0 [O] |
| 10 | i64 | 0x38 | (dropped) | ignored. Send 0 [O] |
| 11 | wstr | 0x40 | +0x08 | **sender name** (`_sender_entry_name`, `_mail_from_text`) [O] |
| 12 | bool8 | 0x9c | +0x79 | **already returned / is a returned mail**. The Return button shows only when this is 0 and field 15 is 1 [O for logic, I for name] |
| 13 | i32 | 0xa0 | +0x7c | **location id where the mail/item sits**. Shown as "Location: %s" via `FUN_00d06e50`. If it is not -1 and not equal to `mgr[5]`, the shipping cost (field 14) is added on take-item [O for logic, I for "location"] |
| 14 | i32 | 0xa4 | +0x80 | **item forwarding shipping cost (copper)**. Shown as silver/copper in the read window when field 13 != `mgr[5]` [O] |
| 15 | bool8 | 0xa8 | +0x7a | **from a player (can reply/return)**. Reply button is hidden when 0. Use 0 for system mail [O for logic] |
| 16 | bool8 | 0x28 | +0x78 | **is CoD**. Take-item sends 0x524 instead of 0x525 [O] |

### 0x516: MsgSingleItemInfo, a mail's attached item (`FUN_0052b8d0`) [O]
- Same class and layout as the inventory item record (`vgmsg.item_info`, as used for 0x48a).
- **Item field 71 (wire 0x550, item+0x650) must equal the mail id.** The handler reads it to find the mail, and the slot0 lookup (`FUN_00526240`) and 0x51a removal match on it.
- The item goes into the `mgr+0x30` vector. The mail's info+0x64 is set to the item's icon (+0x70), which is the list-row icon (`_mail_entry_icon`).
- Send it **after** that mail's 0x515. One item per mail is supported (slot0).

### 0x517: raw i32 mail id, mail removed (`FUN_00528b90`) [O]
Removes the attached item, frees the info, and deletes the UI row. Ack for delete (0x522), return (0x523) and expiry.

### 0x518: no payload, clear the mailbox (`FUN_00528630`) [O]
Frees all infos and empties the item and coin vectors. The doc's "?" means the handler takes no payload.

### 0x519: no payload, rebuild the MailMessageList UI (`FUN_00525ff0`) [O]
Clears the list (`FUN_00524dd0`) and adds a row (`FUN_0067b7d0`, vtbl `0x10b9f1c`) for each info with id != 0. Send it after the 0x515/0x516 batch.

### 0x51a: MsgSingleInt {i32 mailId}, item taken (`FUN_00528e70`) [O]
- Removes the item (`FUN_00528440`) and refreshes the row.
- If `_read_mail_<id>` is open, clears `_mail_item_slot0`.
- If no item and no coin remain, enables `_delete_button` and disables `_return_button`.

### 0x51b: MsgSingleInt {i32 mailId}, coin taken (`FUN_00529010`) [O]
Sets info coin (+0x68) to 0, removes the coin pseudo-item (`FUN_005284d0`), and clears `_mail_item_slot1`. Button logic is the same as 0x51a.

### 0x51e: MsgServerMailInfoVars, 8 x i32 in order -> mgr[0..7] (registration `FUN_00524a70`; offsets msg+0x14..0x30) [O]

| idx | meaning |
|---|---|
| 0 | **postage** (copper) for sending a letter (`MailPostage`). The client shows it 20% off when `[DAT_01463a58+0x378]==2` (unknown account/player flag) [O] |
| 1 | item shipping base cost [O] |
| 2 | unused by the client (none found) [I; e.g. insurance] |
| 3 | item shipping cost x rarity factor. `FUN_00513a80` maps item+0x61c (rarity) as 0->6, 1->5, 2/4->3, 6->2, 7->1, 9->7, 10->4, else 0 [O] |
| 4 | item shipping cost x item field 75 (item+0x528). If that value is in 900..950: `(v/2-449)*mgr[4]*5` [O] |
| 5 | **current mailbox location id** (compared with mail field 13) [O for compare, I for name] |
| 6 | lifetime of **unread** mail, seconds (row timeout = `mgr[6] - now + sentTime`) [O] |
| 7 | lifetime of **read** mail, seconds (row timeout = `mgr[7] - now + readTime`) [O] |

The send-form item shipping estimate (`FUN_005293c0`, run when an item is dropped in the send slot) is `mgr[1] + mgr[4]*f75 + mgr[3]*rarityFactor`, with the same 20% discount rule [O].

## 3. Client -> server

Single-int events use MsgSingleInt (ctor `FUN_00422cd0`), i.e. a 4-byte i32 payload. UI command ids are from the table at `0x69ccb5..`, jump table `0x6aa19c`.

| event | payload | trigger | notes |
|---|---|---|---|
| 0x520 | none | mailbox click / `/mail` / unread-refresh | open session, request vars + list [O] |
| 0x51f | none | `mail_cancel` (0x3a) -> `FUN_00528760` | close session [O] |
| 0x521 | i32 mailId | `mail_read` (0x3c) -> `FUN_006875b0` -> `FUN_0052ae90` | mark read. The client fills the read window from its cache (`FUN_0052a320`); **no server reply is required** [O] |
| 0x522 | i32 mailId | `mail_delete` (0x3b) -> `FUN_0068da80` -> `FUN_00526140` | delete. Reply 0x517 [O for send, I for reply] |
| 0x523 | i32 mailId | `mail_return` (0x3f) -> `FUN_0068d8f0` -> `FUN_005261c0` | return to sender. Reply 0x517 [O / I] |
| 0x524 | i32 mailId | take item from slot0 when the mail is CoD | server charges CoD (field 2) plus shipping (field 14 if location != mgr[5]), gives the item, then sends 0x51a [O for send, I for reply] |
| 0x525 | i32 mailId | take item from slot0, not CoD | pay shipping if any, give the item, then 0x51a [O / I] |
| 0x526 | i32 mailId | take coin from slot1 (the coin pseudo-item has +0x6ec == -1, so `FUN_0068d7b0` passes flag=1) | credit coin, then 0x51b [O / I] |
| 0x527 | MsgMailSend (see below) | `mail_send` (0x39) -> `FUN_0052b030` (coin confirm popup) -> `FUN_00529890` | reply 0x514 code [O] |

### Take-item flow (`mail_take_item` 0x40 -> `FUN_0068d7b0` -> `FUN_00527220(mailId, isCoin)`) [O]
- If it is not coin and the cost (CoD if field16, plus field14 shipping when field13 is not -1 and not `mgr[5]`) is > 0, the client first shows `_shipping_fee_confirm`. `mail_shipping_cost_accept` (0x45) -> `FUN_00527600` then sends 0x524/0x525. Cancel (0x46) sends nothing.
- `FUN_00526380`, which sends 0x525 with value 1, has no callers (dead code).

### 0x527 send mail
Registration `FUN_00524bf0`, ctor `FUN_00526e30`, filled at `0x52a188..0x52a215` [O].

| # | type | msg off | value |
|---|---|---|---|
| 1 | eid64 | 0x18 | **not initialised by the client** (stack garbage). Ignore it |
| 2 | wstr | 0x20 | recipient name (client limit < 41 chars) |
| 3 | wstr | 0x3c | subject (client limit < 50 chars) |
| 4 | wstr | 0x58 | body (client limit <= 1000 chars) |
| 5 | bool8 | 0x74 | **CoD flag** (`_mail_send_cod` checkbox) |
| 6 | i64 | 0x78 | coin amount in copper = `plat*1e6 + gold*1e4 + silver*100 + copper`. If CoD=1 this is the **CoD price**; otherwise it is coin attached to the mail |
| 7 | i32 | 0x80 | attached item **handle** (item+0x650, i.e. inventory field 71 / the item id) taken from `_mail_send_item_slot` (`FUN_00687500`); **-1 = no item** |

Client-side checks before sending:
- With CoD off, the client checks coin against the purse (`*DAT_01463944`).
- CoD requires an item and a price > 0.
- The amount must be <= 30,000,000.

Postage and shipping are **not** in the packet. The server must compute them (mgr[0], and the item formula above) and deduct them.

UI commands that send nothing: reply 0x3e, drag-drop 0x41, clear slot 0x42, coin confirm accept/cancel 0x43/0x44, shipping cancel 0x46, close 0x3d.

## 4. Recommended server sequence

**Open (on 0x520, after the target/range check; else 0x0e 0xf8/0xf9):**
1. **0x51e** vars, e.g. postage 30, ship base 50, 0, rarity 10, f75 1, locationId X, unread 30d = 2592000, read 3d = 259200.
2. **0x518** clear.
3. For each mail: **0x515**, then **0x516** if it has an item (item field71 = mail id).
4. **0x519** to draw the list.

**Other replies:**
- **Read (0x521):** update the read time in the DB. Nothing needs to be sent.
- **Delete / return:** **0x517 mailId**. For return, create the mail for the sender with field12 = 1.
- **Take item:** charge the purse, add the item to inventory (normal inventory add message), then **0x51a mailId**.
- **Take coin:** purse update, then **0x51b mailId**.
- **Send (0x527):**
  - Validate, deduct postage + shipping (+ coin when not CoD), and remove the item from inventory.
  - Send **0x514 code 1**, or the error code.
  - Notify the recipient if online with **0x513**. If their session is open, they send 0x520 again, so answer with 0x518 / 0x515... / 0x519.
- **Close:** on client 0x51f, or when the player walks away, send **0x51f** to the client.
- **At login, with unread mail:** send 0x513 (lights the UnreadMail indicator).

Confidence:
- Layouts and ids: [O].
- Exact server responses to 0x522/0x523/0x524-0x526: [I], but each follows directly from which client handler cleans up which state.
- Unknown or unused: mgr[2], `DAT_01463a58+0x378`, MailMessageFull fields 3, 9, 10.
