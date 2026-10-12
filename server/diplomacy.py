"""Diplomacy parleys (docs/DIPLOMACY.md; client handler FUN_00556560).

At parley start: 0x331 {i32 slots}, 0x21c, 0x21f {i32 n, n x card}, 0x237 {i32 card, i32 slot}.
NPC dialogue option type 10 -> client 0x125 {i32 id}
  -> 0x31d open {eid64 npc, u8 status (bar, 11 = middle), u8 dp, u8 opp dp,
     u8 x8 expression pools, u8 parley type, wstr}
client 0xd9 {i32 card} select -> 0x332 {i32 card}
client 0xda play -> 0x32c {u8 status, u8 x8}, 0x337 {i32 dp, i32 opp}, 0x333,
   0x218 NPC card, 0x325 {wstr NPC line}, 0x256 new round, 0x334 your turn
win 0x324, XP 0x3d5 kind 2, close 0x338; client 0x12a cancel, 0x12b close,
0x12c pass."""
import struct

START, SELECT, PLAY, PASS, CANCEL, CLOSE = 0x125, 0xD9, 0xDA, 0x12C, 0x12A, 0x12B
CLIENT_EVENTS = (START, SELECT, PLAY, PASS, CANCEL, CLOSE)
OPTION_TYPE = 10
PARLEY_OPTION_ID = 9001
MIDDLE, WIN_AT = 11, 17
REASON, DEMAND, INSPIRE, FLATTER = 0x12, 0x11, 0x13, 0x14

# (id, name, expression, bar push)
CARDS = [(40025, "Reasoned Argument", REASON, 3),
         (40026, "Inspiring Words", INSPIRE, 2),
         (40027, "Flattery", FLATTER, 2)]
NPC_LINES = ["Hmm, go on.", "I suppose that's fair.", "You drive a hard bargain!"]


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def card(cid, name, expression, push, icon=443):
    """MsgAbilityParlayCard."""
    return (struct.pack("<i", cid) + _w(name) + struct.pack("<iiii", 0, icon, push, push)
            + struct.pack("<BBBB", 0, 0, 0, 0) + struct.pack("<8i", *[0] * 8)
            + struct.pack("<BBB", 0, 0, 0) + _w("")
            + struct.pack("<iii", 0, expression, 0) + struct.pack("<B", 1)
            + struct.pack("<3i", -1, -1, -1))


def deck_messages(resend=False):
    """Deck and strategy slots, sent when a parley starts: a client UI rebuild
    after login empties the card lists, so cards sent at login don't show.
    On a later parley the old slot entries are removed first (0x239), or the
    same card in the same slot is ignored."""
    out = [_event(0x239, struct.pack("<iB", c[0], 1)) for c in CARDS] if resend else []
    out += [_event(0x331, struct.pack("<i", len(CARDS))), _event(0x21C),
            _event(0x21F, struct.pack("<i", len(CARDS)) + b"".join(card(*c) for c in CARDS))]
    out += [_event(0x237, struct.pack("<ii", c[0], n)) for n, c in enumerate(CARDS)]
    return out


def open_parley(npc_eid, status=MIDDLE):
    return _event(0x31D, struct.pack("<QBBB", npc_eid, status, 0, 0) + bytes([3] * 8)
                  + struct.pack("<B", 0) + _w(""))


def selected(cid):
    return _event(0x332, struct.pack("<i", cid))


def round_messages(status, dp, line, npc_card):
    st = bytes([status]) + bytes([3] * 8)
    return [_event(0x32C, st), _event(0x337, struct.pack("<ii", dp, 0)), _event(0x333),
            _event(0x218, card(*npc_card)), _event(0x325, _w(line)), _event(0x32C, st),
            _event(0x256), _event(0x334)]


def won():
    return _event(0x324)


def ended():
    return [_event(0x31E), _event(0x338)]


def close():
    return _event(0x338)
