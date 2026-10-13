"""Titles and the game clock (docs/TITLES.md; client title dispatcher FUN_005c88e0).

Server -> client (zone):
  0x35f {i32 count, i32 active prefix id, i32 active suffix id, bool8 show mine,
         count x {wstr name, i32 id, bool8 suffix}}  the character's titles (appends; once per login)
  0x360 {wstr name, i32 id, bool8 suffix}  new title ("TitleNewTitle")
  0x361 {i32 id} title removed; 0x362 {bool8 suffix} clear the active slot; 0x363 {i32 id} select
Client -> server (zone):
  0x185 {i32 id} /titleset <title name>; 0x186 {bool8 suffix} remove the active prefix/suffix;
  0x187 (none) /togglemytitle
Over the head: pawn m_PlayerDisplayTitlePre / m_PlayerDisplayTitlePost (Pre + Name + Post).
Game clock: WORLD event 0x1d {i32 seconds of the day, i32 day number} (FUN_0062aaf0; day 0 =
01/01/1000, 30-day months, 360-day years). The client runs it at 20 game seconds per second."""
import struct
import time

SET, REMOVE, TOGGLE = 0x185, 0x186, 0x187
CLIENT_EVENTS = (SET, REMOVE, TOGGLE)
CLOCK_EVENT = 0x1D
GAME_SPEED = 20                          # game seconds per real second
EPOCH = 1791849600                       # 2026-10-13 00:00 UTC = day 0, 12:00


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def title_list(owned, prefix_id, suffix_id, show=True):
    """owned: [(id, name, suffix)]."""
    data = struct.pack("<iiiB", len(owned), prefix_id, suffix_id, int(show))
    for tid, name, suffix in owned:
        data += _w(name) + struct.pack("<iB", tid, int(suffix))
    return _event(0x35F, data)


def new_title(tid, name, suffix):
    return _event(0x360, _w(name) + struct.pack("<iB", tid, int(suffix)))


def game_clock(now=None):
    """WORLD 0x1d {seconds of day, day}: one game day every 72 real minutes."""
    game = int(((now or time.time()) - EPOCH) * GAME_SPEED) + 12 * 3600
    return _event(CLOCK_EVENT, struct.pack("<ii", game % 86400, game // 86400))
