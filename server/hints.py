"""Hints: the client's "Hints" popup (verified live 2026-10-14).

0x56f MsgTutorialDisplayEvent {i32 id, wstr title, wstr text, bool8} puts a red "!" button by the
player's portrait; clicking it opens the Hints window with the title and text and a "Do not show
me any more hints." box. Closing it sends 0x17e (no payload); the code (FUN_0068b0c0) sends 0x17f
instead when a check on the window passes, meant for the ticked box, but live (tools/winbreak.py)
the client sent 0x17e with the box ticked too, and later hints still showed. The server still
honours 0x17f. /hintsenable 0x180 and /craftinghintsenable 0x181 turn hints back on,
/hintsreset 0x182 shows the ones already seen again (all without payload).

Hints are content (server/content/hints.json, {key: {"title", "text"}}); the server shows each
once per character when its trigger happens: "welcome" (first time in the world), "death",
"level" (first level up), "kill" (first kill), "loot" (first corpse opened).
"""
import struct

SHOW = 0x56F
CLOSED, CLOSED_NO_MORE, ENABLE, ENABLE_CRAFTING, RESET = 0x17E, 0x17F, 0x180, 0x181, 0x182
CLIENT_EVENTS = (CLOSED_NO_MORE, ENABLE, ENABLE_CRAFTING, RESET)


def show(hint_id, title, text):
    data = (struct.pack("<i", hint_id) + (title + "\0").encode("utf-16-le")
            + (text + "\0").encode("utf-16-le") + struct.pack("<B", 1))
    return struct.pack("<HII", 2, SHOW, len(data)) + data


def pick(hints, key, seen, off):
    """(id, title, text) of the hint for key if it should show now, else None."""
    h = hints.get(key)
    if off or not h or key in seen:
        return None
    hint_id = sorted(hints).index(key) + 1
    return hint_id, h.get("title", ""), h.get("text", "")
