"""Broker / market (docs/MARKET.md; client dispatcher FUN_005426e0, manager DAT_01463a2c).

A broker is an ordinary NPC whose dialogue gets option 0x2b7 (type 0xf, "I would like to
browse the local market." from the client).
Client -> server:
  0x52b (none)  open (option clicked; uses the target)        0x52c (none) close
  0x53a search {eid64, i32, wstr item name, wstr seller, i32, i32, i16 min level, i16 max level,
        i16, i16 class, i16 slot, i16 type, i16 rarity, bool8, i16 sphere}
  0x53b buy {eid64, i32 listing id, i32}                       0x53c cancel {eid64, i32 listing id, i32}
  0x53d place {i32 inventory handle, i64 price copper}        0x53f relist {i32 listing id, i64 price}
  0x53e examine {i32 listing id} -> 0x537 item record (field 71 = listing id)
Server -> client:
  0x52e MsgClientMarketInfo {i32, wstr market name, f32 commission %, f32 deposit %,
        f32 reduction %, i32 max listings per player, i32} opens the window; 0x52d closes it.
  0x52f clear my listings, 0x531 add (batch) + 0x530 redraw, 0x532 add one now, 0x533 replace one.
  0x534 clear results, 0x536 add a result (max 200), 0x535 redraw.
  0x538 {eid64, i32 listing id} remove a listing from both lists; 0x61d clear the price boxes.
  Results via 0x0e codes: 0x1bd purchase success, 0x1be can't find item, 0x1bf must enter a price,
  0x1c0-0x1c6 can't place (no trade, soulbound, account bound, must repair, can't sell, quest,
  only from main inventory), 0x51 can't trade while using the market.
The client adds the commission to the buyer's price and refuses ("You can't afford that.")
by itself; it shows the seller's deposit but the server charges both."""
import struct
import time

OPEN, CLOSE, SEARCH, BUY, CANCEL, PLACE, EXAMINE, RELIST = 0x52B, 0x52C, 0x53A, 0x53B, 0x53C, 0x53D, 0x53E, 0x53F
CLIENT_EVENTS = (OPEN, CLOSE, SEARCH, BUY, CANCEL, PLACE, EXAMINE, RELIST)
OPTION = 0x2B7
PURCHASE_SUCCESS, CANT_FIND, MUST_ENTER_PRICE, CANT_SELL = 0x1BD, 0x1BE, 0x1BF, 0x1C4
COMMISSION, DEPOSIT, REDUCTION = 5.0, 1.0, 0.0     # percent
MAX_LISTINGS = 20
MAX_RESULTS = 200
MAX_PRICE = 30_000_000
DURATION = 7 * 86400                # a listing lasts a week
FIRST_ID = 900000                    # listing ids double as item handles in the market lists


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def info(name):
    return _event(0x52E, struct.pack("<i", 0) + _w(name)
                  + struct.pack("<fffii", COMMISSION, DEPOSIT, REDUCTION, MAX_LISTINGS, 0))


def close():
    return _event(0x52D)


def record(listing):
    """MsgClientMarketItem (FUN_00536300) for a stored listing dict."""
    lid = listing["id"]
    return (struct.pack("<ii", lid, lid) + _w(listing["name"]) + _w(listing["seller"])
            + _w(listing.get("description", "")) + _w("")
            + struct.pack("<iiiqIBBi", -1, 0, listing.get("icon", 443), listing["price"], time_left(listing), 0, 1,
                          listing.get("qty", 1))
            + _w("") + struct.pack("<iBBiii", 0, 0, 1, 0, listing.get("level", 1), 0) + _w("") + _w(""))


def time_left(listing):
    """Field 10: the listing's expiry as a unix time. The Time column shows it minus the
    client's clock (around 0x67c14b); a past time shows "Expired"."""
    return int(listing.get("posted", 0) + DURATION)


def my_listings(listings):
    return [_event(0x52F)] + [_event(0x531, record(x)) for x in listings] + [_event(0x530)]


def listed(listing):
    return _event(0x532, record(listing))


def relisted(listing):
    return _event(0x533, record(listing))


def results(listings):
    return ([_event(0x534)] + [_event(0x536, record(x)) for x in listings[:MAX_RESULTS]]
            + [_event(0x535)])


def removed(lid):
    return _event(0x538, struct.pack("<qi", 0, lid))


def clear_price():
    return _event(0x61D)


def examined(item_record):
    return _event(0x537, item_record)


PERCENT = struct.unpack("<f", struct.pack("<f", 0.01))[0]   # the client's 0.01f: 40 x 5% shows as 1


def commission(price):
    """What the client adds to the buyer's price (FUN_00536af0), truncated like the client."""
    return int(price * max(0.0, COMMISSION - REDUCTION) * PERCENT)


def deposit(price):
    return max(1, int(price * max(0.0, DEPOSIT - REDUCTION) * PERCENT))


def parse_search(data):
    """-> (item name, seller name, min level, max level)."""
    pos = 12
    out = []
    for _ in range(2):
        end = pos
        while data[end:end + 2] != b"\0\0":
            end += 2
        out.append(data[pos:end].decode("utf-16-le", "replace"))
        pos = end + 2
    pos += 8
    lo, hi = struct.unpack_from("<hh", data, pos)
    return out[0].strip(), out[1].strip(), lo, hi
