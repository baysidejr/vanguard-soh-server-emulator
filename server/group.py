"""Groups (parties). Message layouts from the client's group dispatcher
FUN_004e2910 (docs/GROUPS.md):

client -> zone:  0xb0 invite {wstr name}, 0xb1 accept, 0xb2 decline, 0xae leave,
                 0xaf disband, 0xb3 boot {wstr name}, 0xb4 promote {wstr name}
client -> world: message type 6 "gsay <text>" (group chat)
server -> client:
  0x6b3 invite popup {eid64 inviter, wstr name, i32 0, i32 n, bool8 raid,
        24 x wstr names, 24 x i32 levels, 24 x i32 classes}
  0x6b5 {u8 error}: 1 not leader, 2 already grouped, 3 group full
  0x6b9 {wstr name, i32 0, i32 0} declined
  0x6b2 {eid64 group id} you formed a group (own row, leader)
  0x6bb member added (row; also joins the receiver if not grouped yet)
  0x6cb {eid64} leader icon, 0x6a4 you are leader
  0x695 {eid64, f32 x, y, z, i32 chunk x, y} member position
  0x68b / 0x68c / 0x68d {eid64, u8} member health / endurance / energy (0..255)
  0x6bc {eid64, i32} member left, 0x6a1 you left, 0x6be group disbanded
  0x0f channel 8 = group chat line"""
import itertools
import struct

INVITE, ACCEPT, DECLINE, LEAVE, DISBAND, BOOT, PROMOTE = 0xB0, 0xB1, 0xB2, 0xAE, 0xAF, 0xB3, 0xB4
CLIENT_EVENTS = (INVITE, ACCEPT, DECLINE, LEAVE, DISBAND, BOOT, PROMOTE)
MAX_MEMBERS = 6
CHAT_GROUP = 8

_group_ids = itertools.count(0x7000001)


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def _byte(cur, mx):
    return max(0, min(255, round(255 * cur / mx))) if mx else 0


class Group:
    def __init__(self, leader):
        self.id = next(_group_ids)
        self.leader = leader
        self.members = [leader]


def invite_popup(inviter, members):
    names = [m.name for m in members] + [""] * (24 - len(members))
    levels = [m.level_number for m in members] + [0] * (24 - len(members))
    classes = [m.klass for m in members] + [0] * (24 - len(members))
    data = (struct.pack("<Q", inviter.char_id) + _w(inviter.name)
            + struct.pack("<iiB", 0, len(members), 0)
            + b"".join(_w(n) for n in names[:24])
            + struct.pack("<24i", *levels[:24]) + struct.pack("<24i", *classes[:24]))
    return _event(0x6B3, data)


def error(code):
    return _event(0x6B5, struct.pack("<B", code))


def declined(name):
    return _event(0x6B9, _w(name) + struct.pack("<ii", 0, 0))


def formed(group):
    return _event(0x6B2, struct.pack("<Q", group.id))


def member_added(member):
    pos = member.live_position or member.spawned_at or (0.0, 0.0, 0.0)
    eid = member.char_id
    data = (_w(member.name) + struct.pack("<QQii", eid, eid, eid & 0x7FFFFFFF, 0)
            + struct.pack("<Bii", _byte(member.health, member.stats["hit_points"]), -1, member.klass)
            + struct.pack("<i", member.level_number)
            + struct.pack("<BBB", _byte(member.endurance, member.stats["endurance"]), 255, 255)
            + struct.pack("<fff", *pos) + struct.pack("<ii", 0, 0) + struct.pack("<BBB", 0, 0, 0))
    return _event(0x6BB, data)


def leader_is(member):
    return _event(0x6CB, struct.pack("<Q", member.char_id))


def you_are_leader():
    return _event(0x6A4)


def member_position(member):
    pos = member.live_position or member.spawned_at or (0.0, 0.0, 0.0)
    return _event(0x695, struct.pack("<Qfffii", member.char_id, *pos, 0, 0))


def member_vitals(member):
    return [_event(0x68B, struct.pack("<QB", member.char_id,
                                      _byte(member.health, member.stats["hit_points"]))),
            _event(0x68C, struct.pack("<QB", member.char_id,
                                      _byte(member.endurance, member.stats["endurance"])))]


def member_left(member):
    return _event(0x6BC, struct.pack("<Qi", member.char_id, 0))


def you_left():
    return _event(0x6A1)


def disbanded():
    return _event(0x6BE)
