"""Vendors: NPC dialog, the merchant window, buying and selling.

Flow (docs/MERCHANTS.md; from the client's dispatchers FUN_004c9170 / FUN_00547220):
  player hails ("Hail, <name>" Say) or uses (U) a merchant NPC
    -> 0x2bb {u64 npc} opens the NPC dialog, 0x2b5 adds "Show me your wares."
  client 0xe5 (no payload; the merchant is the current target)
    -> 0x28b clear, 0x283 open window, 0x285 per item, 0x28c publish the list
  client 0xe7 {i32 handle, i32 qty} buy  -> 0x197 item into the bag, 0x1aa new coin total
  client 0xe8 {i32 handle, i32 qty} sell -> 0x1a5 {handle, 0} remove, 0x1aa coin total
  client 0xe6 / 0xf4 close               -> 0x284 {u8 3} (closes quietly)
Errors: 0x0e {i16 code}: 0xfb can't afford, 0x100 no inventory space, 0x103 can't sell that."""
import struct

DIALOG_OPEN, DIALOG_WARES = 0x2BB, 0x2B5
WINDOW_CLEAR, WINDOW_OPEN, WINDOW_ITEM, WINDOW_PUBLISH, WINDOW_CLOSE = 0x28B, 0x283, 0x285, 0x28C, 0x284
REQ_OPEN, REQ_BUY, REQ_SELL, REQ_CLOSE, REQ_CLOSE2 = 0xE5, 0xE7, 0xE8, 0xE6, 0xF4
COINS_CHANGED = 0x1AA          # i64 total copper, with a "You receive/lose" chat line
ITEM_REMOVED = 0x1A5           # {i32 handle, bool8}
MERCHANT_ERROR = 0x0E          # {i16 code}
ERR_CANT_AFFORD, ERR_NO_SPACE, ERR_CANT_SELL = 0xFB, 0x100, 0x103
SELL_FRACTION = 4              # merchants pay price / 4
HANDLE_BASE = 70000            # merchant list handles: HANDLE_BASE + index


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def dialog(npc):
    return [_event(DIALOG_OPEN, struct.pack("<Q", npc.entity_id)), _event(DIALOG_WARES)]


def merchant_item(item_id, handle, name, icon, price, slot=-1, description=""):
    """0x285 MsgClientMerchantItem (serializer FUN_00542950)."""
    return (struct.pack("<ii", item_id, handle) + _w(name) + _w(description) + _w("")
            + struct.pack("<iiif", slot, 0, icon, float(price))
            + struct.pack("<BBB", 0, 1, 0)
            + struct.pack("<iiiii", 1, 0, 0, 0, 100)
            + _w("") + _w("") + struct.pack("<8i", *[-1] * 8) + _w("")
            + struct.pack("<3i", -1, -1, -1) + _w("") + _w(""))


def stock(content, npc):
    """[(handle, item name, icon, price)] for a merchant NPC."""
    out = []
    for n, entry in enumerate(content.merchants.get(npc.merchant, [])):
        tpl = content.item(entry["item"])
        out.append((HANDLE_BASE + n, entry["item"], tpl.get("icon", 443), entry["price"]))
    return out


def open_window(content, npc):
    out = [_event(WINDOW_CLEAR), _event(WINDOW_OPEN)]
    for handle, name, icon, price in stock(content, npc):
        out.append(_event(WINDOW_ITEM, merchant_item(handle, handle, name, icon, price)))
    out.append(_event(WINDOW_PUBLISH))
    return out


def close_window(reason=3):
    return _event(WINDOW_CLOSE, struct.pack("<B", reason))


def error(code):
    return _event(MERCHANT_ERROR, struct.pack("<h", code))


def coins(total):
    return _event(COINS_CHANGED, struct.pack("<q", total))


def buy(content, npc, player, handle, qty, item_message):
    """item_message(item_id, name, icon, qty, slot) builds the 0x197 for the bag."""
    entry = next((s for s in stock(content, npc) if s[0] == handle), None)
    if entry is None:
        return []
    _, name, icon, price = entry
    qty = max(1, qty)
    if player.coins < price * qty:
        return [error(ERR_CANT_AFFORD)]
    if len(player.items) + len(player.equipment) >= 50:
        return [error(ERR_NO_SPACE)]
    player.coins -= price * qty
    new_id = max([i[0] for i in player.items] + [e[0] for e in player.equipment] + [10000]) + 1
    player.items.append((new_id, name, icon, qty))
    return [item_message(new_id, name, icon, qty, len(player.items) - 1), coins(player.coins)]


def sell(content, npc, player, handle):
    item = next((i for i in player.items if i[0] == handle), None)
    if item is None:
        return [error(ERR_CANT_SELL)]
    prices = {s[1]: s[3] for s in stock(content, npc)}
    value = max(1, prices.get(item[1], 20) // SELL_FRACTION) * item[3]
    player.items.remove(item)
    player.coins += value
    return [_event(ITEM_REMOVED, struct.pack("<iB", handle, 0)), coins(player.coins)]
