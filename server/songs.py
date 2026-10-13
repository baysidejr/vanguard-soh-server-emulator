"""Bard songs (docs/SONGS.md; client song dispatcher FUN_005c5310, Song window VGUISong.xml).

Song parts are abilities (0x215 MsgAbilityInfo) with wire #31 kind = 10 and #32 = part
(0 Melody, 1 Verse, 2 Embellishment, 3 Bridge, 4 Lyric, 5 Chorus, 6 Coda, 7 Rest) and #56 =
energy per second; the client sorts them into the Song*Lists. A song references parts by
ability id (-1 = empty slot). Every message lists a melody, then for i = 0..5 one id per
part in the order Verse, Embellishment, Bridge, Lyric, Chorus, Coda.

Server -> client:
  0x572 {6 x u8}: unlocked slots per part (Verse..Coda; the melody slot is always 1)
  0x573 MsgSongCompose {i32 song id, wstr name, wstr description, i32 melody, 6 x 6 x i32}:
        add or update a saved song (matched by name)
  0x574: delete every song      0x57b {wstr}: the song now playing ("" = none)
Client -> server:
  0x578 MsgSongCompose: save (the song id field is junk: key songs by name)
  0x577 MsgSongCompose: play the composition without saving it
  0x576 {i32 song id}: play a saved song (list, /playsong "name", a song on the hotbar)
  0x575: stop (/stopsong)       0x579 {i32 song id}: delete
  0x57a {i32 id a, i32 id b}: move up / down (swap two songs)"""
import struct

SAVE, PLAY_COMPOSED, PLAY, STOP, DELETE, SWAP = 0x578, 0x577, 0x576, 0x575, 0x579, 0x57A
CLIENT_EVENTS = (SAVE, PLAY_COMPOSED, PLAY, STOP, DELETE, SWAP)
SONG_KIND = 10
PARTS = ("melody", "verse", "embellishment", "bridge", "lyric", "chorus", "coda", "rest")
SLOT_PARTS = PARTS[1:7]                 # the six arrays, in wire order
ABILITY_ID_BASE = 980000
HANDLE_BASE = 900
MAX_SONGS = 20
MAX_NAME, MAX_DESC = 32, 128


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def part_abilities(parts):
    """[(handle, ability id, name, spec)] for a class's song parts (songs.json)."""
    return [(HANDLE_BASE + n, ABILITY_ID_BASE + n, name, spec) for n, (name, spec) in enumerate(parts.items())]


def part_info(handle, aid, name, spec):
    """0x215 for one song part."""
    import vgmsg
    raw = {30: SONG_KIND, 31: PARTS.index(spec["part"]), 55: int(spec.get("energy", 1))}
    return _event(0x215, vgmsg.ability_info(handle, aid, name, spec.get("icon", 560),
                                            spec.get("description", f"A {spec['part']} for your songs."),
                                            type_text="Song", refresh=0.0, raw=raw))


def slots(counts=(1, 1, 1, 1, 1, 1)):
    return _event(0x572, bytes(counts))


def _pack(song):
    out = struct.pack("<i", song.get("melody", -1))
    for i in range(6):
        out += struct.pack("<6i", *(song["parts"][p][i] if i < len(song["parts"][p]) else -1 for p in SLOT_PARTS))
    return out


def compose(song_id, song):
    return _event(0x573, struct.pack("<i", song_id) + _w(song["name"]) + _w(song.get("description", "")) + _pack(song))


def clear_all():
    return _event(0x574)


def now_playing(name=""):
    return _event(0x57B, _w(name))


def parse_compose(data):
    """0x577 / 0x578 -> song dict {name, description, melody, parts {part: [6 ids]}}."""
    pos = 4
    strings = []
    for _ in range(2):
        end = pos
        while data[end:end + 2] != b"\0\0":
            end += 2
        strings.append(data[pos:end].decode("utf-16-le", "replace"))
        pos = end + 2
    melody = struct.unpack_from("<i", data, pos)[0]
    pos += 4
    parts = {p: [] for p in SLOT_PARTS}
    for i in range(6):
        for p, v in zip(SLOT_PARTS, struct.unpack_from("<6i", data, pos + 24 * i)):
            parts[p].append(v)
    return {"name": strings[0].strip(), "description": strings[1].strip(), "melody": melody, "parts": parts}


def problem(song, known_ids, songs=()):
    """None if the song may be saved / played, else the reason."""
    if not song["name"]:
        return "Your song needs a name."
    if len(song["name"]) > MAX_NAME:
        return f"Song names can't exceed {MAX_NAME} characters."
    if len(song.get("description", "")) > MAX_DESC:
        return f"Song descriptions can't exceed {MAX_DESC} characters."
    if song["melody"] not in known_ids:
        return "Your song needs a melody."
    if any(v != -1 and v not in known_ids for ids in song["parts"].values() for v in ids):
        return "That is not a valid song."
    if song["name"].lower() not in [s["name"].lower() for s in songs] and len(songs) >= MAX_SONGS:
        return f"You can't have more than {MAX_SONGS} songs."
    return None


ENERGY_REGEN = 3                       # energy a second while not singing


def energy_step(energy, maximum, cost):
    """One second: (new energy, still singing). cost None = not singing (regenerate)."""
    if cost is None:
        return min(maximum, energy + ENERGY_REGEN), False
    if energy < cost:
        return energy, False
    return energy - cost, True


def effect(song, parts_by_id):
    """The buff a playing song gives: the melody's stat, raised by every part's bonus; and its
    energy cost per second (rests lower it)."""
    used = [parts_by_id[song["melody"]]] + [parts_by_id[v] for ids in song["parts"].values() for v in ids
                                            if v in parts_by_id]
    stat = used[0].get("stat", "strength")
    bonus = sum(p.get("bonus", 0) for p in used)
    cost = max(0, sum(p.get("energy", 1) for p in used if p["part"] != "rest")
               - sum(p.get("energy", 1) for p in used if p["part"] == "rest"))
    return {"kind": "buff", "stat": stat, "bonus": bonus, "icon": used[0].get("icon", 560), "energy": cost}
