# Bank

**Verified live (2026-10-12):** the banker Hollis Grent (`"banker": true` in mobs.json) offers "I need to do some banking". It opens the 40-slot Bank window with its coin bar.
- Depositing and withdrawing items and coins works through the dev commands `!bankput <bag slot>`, `!bankget <bank slot>` and `!bankput|!bankget coins <copper>`. They send the same requests as the client's `/bankadditem` path (`0x14d`/`0x14f`) and its coin drags (`0x93`/`0x94`).
- Items move between bag and bank (`0x1cf`/`0x1d0`), and the bank's coin total updates (`0x1ab`).
- After closing and reopening, the bank shows its saved contents (`0x48a`).
- Bank items and coins are saved per character (`bank`, `bank_coins`).
- The code is in `server/bank.py` and `login_stub.handle_bank_event`.

Not tested live:
- Dragging, which scripted input can't do. The drag messages `0x14e`/`0x150`/`0x14c` are implemented from the static analysis.
- Which of `0x93`/`0x94` is deposit. The emulator assumes `0x93` = deposit, `0x94` = withdraw.
- The typed `/bankadditem` command printed nothing.

The client's bank dispatcher is `FUN_0046e5f0`. All messages are zone events.

| Direction | Id | Payload | Meaning |
|---|---|---|---|
| S→C | `0x2b3` | none | adds the banking dialogue option (type 3) |
| C→S | `0x14a` | none | begin banking (`FUN_0046aa40`) |
| S→C | `0x487` | `wstr name, f32 capacity, i64 bank coins` | opens the Bank window (gamevar `Banking` = 1) |
| S→C | `0x48a` | item record (`0x197` layout) | one bank item; placed by field 16 (slot) |
| S→C | `0x489` | none | clears the bank list |
| C→S | `0x14e` | `i32 handle, i32 qty, i32 bank slot` | bag → bank (drag) |
| C→S | `0x14d` | `i32 handle, i32 qty` | bag → bank, any slot |
| S→C | `0x1cf` | `i32 handle, i32 container, i32 slot` | bag → bank done |
| C→S | `0x150` | `i32 handle, i32 qty, i32 container, i32 slot` | bank → bag (drag; container -1 = main bag) |
| C→S | `0x14f` | `i32 handle, i32 qty` | bank → bag, any slot |
| S→C | `0x1d0` | `i32 handle, i32 container, i32 slot` | bank → bag done |
| C→S | `0x14c` | `i32 handle, i32 qty, i32 bank slot` | move inside the bank. There is no reply message, so the server sends `0x489` and every `0x48a` again |
| C→S | `0x93` / `0x94` | `i64 copper` | coins to / from the bank (direction inferred) |
| S→C | `0x1ab` | `i64` | the bank's coin total (the purse uses `0x1aa`) |
| S→C | `0x486` | `u8` | error text: 0 not banking, 1 target a banker, 2 move closer, 3 bank full, 4 bags full, 5 not a banker, 6 transfer to the local bank first, 7 not while trading |
| C→S | `0x14b` | none | stop banking |
| S→C | `0x488` | none | "You stop banking." (closes the window) |

When part of a stack is deposited, the bag stack is reduced with `0x1ae`, and the deposited part becomes a new bank item (`0x48a`).
