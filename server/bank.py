"""Banking (docs/BANK.md; client dispatcher FUN_0046e5f0).

Dialogue option 0x2b3 (type 3) -> client 0x14a begin
  -> 0x487 {wstr name, f32 capacity (slots), i64 bank coins}, 0x48a item (0x197 layout,
     field 16 = bank slot) per bank item
client 0x14e {i32 handle, i32 qty, i32 bank slot}   bag -> bank (drag)   -> 0x1cf {handle, container, slot}
client 0x14d {i32 handle, i32 qty}                  bag -> bank (/bankadditem)
client 0x150 {i32 handle, i32 qty, i32 container, i32 slot}  bank -> bag -> 0x1d0 {handle, container, slot}
client 0x14f {i32 handle, i32 qty}                  bank -> bag (no slot)
client 0x14c {i32 handle, i32 qty, i32 bank slot}   move inside the bank -> 0x489 + all 0x48a again
client 0x93 / 0x94 {i64 copper}                     coins to / from the bank -> 0x1ab {i64 bank}, 0x1aa purse
client 0x14b end -> 0x488. Errors 0x486 {u8}: 3 no room in the bank, 4 no room in the bags, 5 not a banker."""
import struct

BEGIN, END, TO_BANK, TO_BANK_ANY, FROM_BANK, FROM_BANK_ANY, MOVE = 0x14A, 0x14B, 0x14E, 0x14D, 0x150, 0x14F, 0x14C
DEPOSIT_COIN, WITHDRAW_COIN = 0x93, 0x94          # direction inferred, not yet confirmed live
CLIENT_EVENTS = (BEGIN, END, TO_BANK, TO_BANK_ANY, FROM_BANK, FROM_BANK_ANY, MOVE, DEPOSIT_COIN, WITHDRAW_COIN)
OPTION = 0x2B3
CAPACITY = 40
ERR_NOT_BANKING, ERR_BANK_FULL, ERR_BAGS_FULL, ERR_NOT_BANKER = 0, 3, 4, 5


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def start(name, coins, capacity=CAPACITY):
    return _event(0x487, _w(name) + struct.pack("<fq", float(capacity), coins))


def item(record):
    """record: a vgmsg.inventory_item payload with slot = the bank slot."""
    return _event(0x48A, record)


def clear():
    return _event(0x489)


def stored(handle, slot):
    return _event(0x1CF, struct.pack("<iii", handle, -1, slot))


def retrieved(handle, container, slot):
    return _event(0x1D0, struct.pack("<iii", handle, container, slot))


def bank_coins(total):
    return _event(0x1AB, struct.pack("<q", total))


def error(code):
    return _event(0x486, struct.pack("<B", code))


def stop():
    return _event(0x488)


def free_slot(bank, capacity=CAPACITY):
    used = {i[4] for i in bank}
    return next((s for s in range(capacity) if s not in used), None)
