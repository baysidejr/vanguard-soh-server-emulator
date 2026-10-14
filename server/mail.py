"""In-game mail (docs/MAIL.md; client dispatcher FUN_0052bbd0, mail manager DAT_01463a28).

Client -> server:
  0x520 (none)       open a mail session: mailbox click (EntityTypes 0x20000) or /mail. No target id
                     is sent; the server checks the target (0x0e codes 0xf8 PleaseTargetMailbox,
                     0xf9 MoveCloserToMailbox).
  0x51f (none)       close (mail_cancel)
  0x521 {i32 id}     read (the client shows its cached copy; no reply)
  0x522 {i32 id}     delete -> 0x517
  0x523 {i32 id}     return to sender -> 0x517
  0x524 {i32 id}     take the item and pay the CoD -> 0x51a
  0x525 {i32 id}     take the item -> 0x51a
  0x526 {i32 id}     take the coin -> 0x51b
  0x527 send {eid64 (garbage), wstr to, wstr subject, wstr body, bool8 cod, i64 copper
              (CoD price when cod, else coin sent), i32 item handle or -1} -> 0x514 result
Server -> client:
  0x51e 8 x i32 {postage, item shipping, ?, shipping x rarity, shipping x item field 75,
        this mailbox's location id, unread lifetime s, read lifetime s}: opens the window
        (only while no session is open)
  0x518 clear the cached list; 0x515 one mail; 0x516 its item (item record, field 71 = mail id);
  0x519 redraw the list; 0x517 {i32 id} remove one; 0x51a {i32 id} item taken; 0x51b {i32 id}
  coin taken; 0x513 new mail (unread icon and sound); 0x51f close the window.
  0x514 {i32 code}: 0 database error, 1 "Mail sent.", 2 recipient not found, 3 subject too long,
        4 body too long, 5 invalid session, 6 item can't be mailed, 7 test characters,
        8 can't mail yourself, 9 damaged items, 10 account doesn't qualify, 11 sent mail limit."""
import struct
import time

OPEN, CLOSE, READ, DELETE, RETURN, TAKE_ITEM_COD, TAKE_ITEM, TAKE_COIN, SEND = (
    0x520, 0x51F, 0x521, 0x522, 0x523, 0x524, 0x525, 0x526, 0x527)
CLIENT_EVENTS = (OPEN, CLOSE, READ, DELETE, RETURN, TAKE_ITEM_COD, TAKE_ITEM, TAKE_COIN, SEND)
MAILBOX = 0x20000                    # EntityTypes bit
PLEASE_TARGET_MAILBOX, MOVE_CLOSER = 0xF8, 0xF9
DB_ERROR, SENT, NO_RECIPIENT, SUBJECT_LONG, BODY_LONG, BAD_SESSION, CANT_MAIL_ITEM = 0, 1, 2, 3, 4, 5, 6
SELF, DAMAGED = 8, 9
POSTAGE, SHIPPING = 10, 30           # copper per letter, per attached item
LOCATION = 1                         # every mailbox is the same post office (no extra shipping)
UNREAD_DAYS, READ_DAYS = 30, 7
MAX_SUBJECT, MAX_BODY = 49, 1000


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def info():
    return _event(0x51E, struct.pack("<8i", POSTAGE, SHIPPING, 0, 0, 0, LOCATION,
                                     UNREAD_DAYS * 86400, READ_DAYS * 86400))


def clear():
    return _event(0x518)


def redraw():
    return _event(0x519)


def close():
    return _event(0x51F)


def new_mail():
    return _event(0x513)


def message(m):
    """0x515 MsgMailMessageFull for a stored mail dict."""
    cod = m.get("cod", 0)
    return _event(0x515, struct.pack("<qqii", m.get("coin", 0), cod, 0, m["id"])
                  + _w(m.get("subject", "")) + _w(m.get("body", ""))
                  + struct.pack("<IIiq", int(m.get("sent", 0)), int(m.get("read", 0)), 0, 0)
                  + _w(m.get("from", "")) + struct.pack("<BiiBB", int(m.get("returned", False)), LOCATION, 0,
                                                       int(m.get("from_player", True)), int(cod > 0)))


def item(record):
    return _event(0x516, record)


def removed(mid):
    return _event(0x517, struct.pack("<i", mid))


def item_taken(mid):
    return _event(0x51A, struct.pack("<i", mid))


def coin_taken(mid):
    return _event(0x51B, struct.pack("<i", mid))


def result(code):
    return _event(0x514, struct.pack("<i", code))


def parse_send(data):
    """0x527 -> (to, subject, body, cod, copper, handle)."""
    pos = 8
    out = []
    for _ in range(3):
        end = pos
        while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
            end += 2
        out.append(data[pos:end].decode("utf-16-le", "replace"))
        pos = end + 2
    cod, copper, handle = struct.unpack_from("<Bqi", data, pos)
    return out[0].strip(), out[1], out[2], bool(cod), copper, handle


def new(mid, sender, subject, body, coin=0, cod=0, item_=None, from_player=True, returned=False):
    return {"id": mid, "from": sender, "subject": subject, "body": body, "coin": coin, "cod": cod,
            "item": item_, "sent": int(time.time()), "read": 0, "from_player": from_player,
            "returned": returned}
