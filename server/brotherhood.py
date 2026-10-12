"""Brotherhoods: small permanent fellowships (docs/BROTHERHOODS.md; client
dispatcher FUN_00470a20).

Client: zone 0x4bd {wstr name} invite, 0x4be accept, 0x4bf decline, 0x4c0 leave (the
client asks "Leave the Brotherhood?" first).
Server: 0x4bd {wstr inviter} invite popup ("%s has invited you to join a brotherhood.");
  0x6ef {i32 status} 0 not active / 1 member / 2 leader (gamevars);
  0x6ed {wstr} name; 0x6ea MsgBrotherhoodMemberAdd {wstr name, 6 x i32, wstr};
  0x6e7 {i32 id, bool8 kicked} member left / kicked; 0x6e8 {i32 id} new leader;
  0x6eb {wstr, i32} MOTD.
Errors (zone 0x0e): 0x68 full, 0x69 not leader, 0x6e can't brotherhood with yourself."""
import struct

INVITE, ACCEPT, DECLINE = 0x4BD, 0x4BE, 0x4BF
ZONE_EVENTS = (INVITE, ACCEPT, DECLINE, 0x4C0)
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
    """m: dict with id, name, level, klass, online, leader."""
    return _event(0x6EA, _w(m["name"]) + struct.pack("<6i", m["id"], m.get("level", 1), m.get("klass", 0),
                                                   int(m.get("online", False)), int(m.get("leader", False)), 0)
                  + _w(""))


def member_left(member_id, kicked=False):
    return _event(0x6E7, struct.pack("<iB", member_id, int(kicked)))


def new_leader(member_id):
    return _event(0x6E8, struct.pack("<i", member_id))
