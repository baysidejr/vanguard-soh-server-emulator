"""Brotherhoods: small permanent fellowships (docs/BROTHERHOODS.md; client
dispatcher FUN_00470a20).

Client: zone 0x4bd {wstr name} invite, 0x4be accept, 0x4bf decline, 0x4c0 leave (the
client asks "Leave the Brotherhood?" first), 0x4c2 promote {i32 member id}, 0x4c1 remove
{i32 member id} (after "Remove from Brotherhood?"), 0x4c3 MOTD {wstr}, 0x4c4 my note {wstr},
0x4c5 rename {wstr}.
Server: 0x4bd {wstr inviter} invite popup ("%s has invited you to join a brotherhood.");
  0x6ef {i32 status} 0 not active / 1 member / 2 leader (gamevars);
  0x6ed {wstr} name; 0x6ea MsgBrotherhoodMemberAdd (upsert by id) {wstr name, i32 class,
  i32 level, i32 id, i32 ?, i32 exp contribution, i32 rank (-1 leaving, 0 member, 1 leader),
  wstr note} (FUN_00470420; gamevar VGUIGameVarDataBrotherhoodMember);
  0x6e7 {i32 id, bool8 kicked} member left / kicked; 0x6e8 {i32 id} new leader;
  0x6eb {wstr motd, i32 set-by id} MOTD; 0x6ec {wstr note, i32 id} member note;
  0x6e9 {i32 id, i32 level} member level.
Errors (zone 0x0e): 0x68 full, 0x69 not leader, 0x6e can't brotherhood with yourself."""
import struct

INVITE, ACCEPT, DECLINE = 0x4BD, 0x4BE, 0x4BF
REMOVE, PROMOTE, MOTD, NOTE, RENAME = 0x4C1, 0x4C2, 0x4C3, 0x4C4, 0x4C5
ZONE_EVENTS = (INVITE, ACCEPT, DECLINE, 0x4C0, REMOVE, PROMOTE, MOTD, NOTE, RENAME)
LEAVE = 0x4C0                      # zone (after the client's confirm popup)
NOT_ACTIVE, MEMBER, LEADER = 0, 1, 2
MAX_MEMBERS = 6
ERR_FULL, ERR_NOT_LEADER, ERR_SELF = 0x68, 0x69, 0x6E


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def invite(inviter):
    return _event(0x4BD, _w(inviter))


def status(value):
    return _event(0x6EF, struct.pack("<i", value))


def name(text):
    return _event(0x6ED, _w(text))


def member_add(m):
    """m: dict with id, name, level, klass, online, leader, note."""
    return _event(0x6EA, _w(m["name"]) + struct.pack("<6i", m.get("klass", 0), m.get("level", 1), m["id"],
                                                   int(m.get("online", False)), m.get("exp", 0),
                                                   int(m.get("leader", False)))
                  + _w(m.get("note", "")))


def motd(text, setter_id):
    return _event(0x6EB, _w(text) + struct.pack("<i", setter_id))


def note(text, member_id):
    return _event(0x6EC, _w(text) + struct.pack("<i", member_id))


def read_text(data):
    return data.decode("utf-16-le", "replace").split("\0")[0]


def member_left(member_id, kicked=False):
    return _event(0x6E7, struct.pack("<iB", member_id, int(kicked)))


def new_leader(member_id):
    return _event(0x6E8, struct.pack("<i", member_id))
