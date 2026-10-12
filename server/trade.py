"""Player-to-player trade (client dispatcher FUN_005cdd90; docs/TRADE.md).

client -> zone: 0xc0 invite {wstr name}, 0xc1 cancel invite, 0xc2 decline,
  0xc3 accept invite, 0xc4 add item {i32 bag handle, i32 seq, i32 qty},
  0xc5 remove item {i32 handle, i32 seq}, 0xc6 coin {i64 copper, i32 seq},
  0xc7 accept {i32 seq}, 0xc8 cancel {i32 seq}, 0x206 busy (= decline)
server -> client: 0x208 {wstr inviter} to the invitee, 0x205 {wstr partner} opens
  the inviter's window (the invitee opens its own on 0xc3), 0x206 declined,
  0x207 invite cancelled, 0x1fc / 0x1fe / 0x20a / 0x202 my offer / accept,
  0x1fd / 0x1ff / 0x20b / 0x203 their offer / accept, 0x204 reset accepts,
  0x200 cancelled, 0x201 done, 0x209 {u8} item refused.
Every server message with a seq overwrites the client's; accepts with an old
seq are ignored. Items stay in the bags until the trade completes."""
import struct

INVITE, CANCEL_INVITE, DECLINE, ACCEPT_INVITE = 0xC0, 0xC1, 0xC2, 0xC3
ADD, REMOVE, COIN, ACCEPT, CANCEL, BUSY = 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0x206
CLIENT_EVENTS = (INVITE, CANCEL_INVITE, DECLINE, ACCEPT_INVITE, ADD, REMOVE, COIN, ACCEPT,
                 CANCEL, BUSY)
MAX_ITEMS = 8


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


class Trade:
    def __init__(self, a, b):
        self.pairs = [(a, Side()), (b, Side())]   # (zone connection state, Side)
        self.seq = 1

    def side(self, state):
        return next(side for s, side in self.pairs if s is state)

    def other(self, state):
        return next(s for s, _ in self.pairs if s is not state)


class Side:
    def __init__(self):
        self.items = []        # bag handles offered (in window order)
        self.coins = 0
        self.accepted = False


def invited(name):
    return _event(0x208, _w(name))


def open_window(partner_name):
    return _event(0x205, _w(partner_name))


def declined():
    return _event(0x206)


def invite_cancelled():
    return _event(0x207)


def my_item(seq, slot, handle):
    return _event(0x1FC, struct.pack("<iiiii", seq, slot, handle, handle, 0) + _w("")
                  + struct.pack("<qiBii", 0, 0, 0, 0, 0))


def their_item(item_record):
    return _event(0x1FD, item_record)


def my_item_removed(seq, handle):
    return _event(0x1FE, struct.pack("<ii", seq, handle))


def their_item_removed(seq, handle):
    return _event(0x1FF, struct.pack("<ii", seq, handle))


def my_coins(copper, seq):
    return _event(0x20A, struct.pack("<qi", copper, seq))


def their_coins(copper, seq):
    return _event(0x20B, struct.pack("<qi", copper, seq))


def i_accepted(seq):
    return _event(0x202, struct.pack("<i", seq))


def they_accepted(seq):
    return _event(0x203, struct.pack("<i", seq))


def reset_accepts(seq):
    return _event(0x204, struct.pack("<i", seq))


def cancelled():
    return _event(0x200)


def done():
    return _event(0x201)


def refused(reason):
    return _event(0x209, struct.pack("<B", reason))
