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
# Raids (docs/GROUPS.md "Raids"): 0xac /raidcreate, 0xa7 /raidalert {wstr}, 0xa8 /readycheck {wstr},
# 0xa9 ready answer {i32 initiator row, i32 status}, 0xaa move {i32 row, i32 raid group 0..3},
# 0xab role {i32 row, i32 1 main assist / 2 assistant / 3 main tank}.
RAID_CREATE, RAID_ALERT, READY_CHECK, READY_ANSWER, RAID_MOVE, RAID_ROLE = 0xAC, 0xA7, 0xA8, 0xA9, 0xAA, 0xAB
CLIENT_EVENTS = (INVITE, ACCEPT, DECLINE, LEAVE, DISBAND, BOOT, PROMOTE,
                 RAID_CREATE, RAID_ALERT, READY_CHECK, READY_ANSWER, RAID_MOVE, RAID_ROLE)
MAX_MEMBERS = 6
MAX_RAID = 24
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
        self.raid = False
        self.sub = {}                 # char_id -> raid group 0..3
        self.roles = {}               # char_id -> set of role numbers

    def limit(self):
        return MAX_RAID if self.raid else MAX_MEMBERS

    def free_subgroup(self):
        for g in range(4):
            if sum(1 for m in self.members if self.sub.get(m.char_id, 0) == g) < MAX_MEMBERS:
                return g
        return 3


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


# Invite referral (verified live 2026-10-14): a member who is not the leader invites someone, and
# the leader gets 0x727 {eid64 member, eid64 invitee, wstr text, wstr invitee name}
# (FUN_005eb550): an "Invite Referral" popup showing the text (also echoed to chat). Accept runs
# /groupinvitereferralaccept, which the client turns into a normal invite (0xb0) of the stored
# name; Decline sends nothing.
REFERRAL = 0x727


def referral(member, invitee_id, invitee_name):
    text = f"{member.name} would like to invite {invitee_name} to the group."
    return _event(REFERRAL, struct.pack("<QQ", member.char_id, invitee_id) + _w(text) + _w(invitee_name))


# Request to join (docs/GROUPS.md): world type 5 0x58b {wstr leader} from the Find list;
# the leader gets zone 0x58b {wstr leader, wstr requester, i32 level, i32 class} (an
# Invite/Decline dialog; Invite sends a normal 0xb0). Decline: world 0x58c {wstr requester};
# the requester gets 0x58c {wstr leader} ("... declined your request").
REQUEST_JOIN, REQUEST_DECLINE = 0x58B, 0x58C


def join_request(leader_name, requester):
    return _event(REQUEST_JOIN, _w(leader_name) + _w(requester.name)
                  + struct.pack("<ii", requester.level_number, requester.klass))


def join_declined(leader_name):
    return _event(REQUEST_DECLINE, _w(leader_name))


def declined(name):
    return _event(0x6B9, _w(name) + struct.pack("<ii", 0, 0))


def formed(group):
    return _event(0x6B2, struct.pack("<Q", group.id))


def row_id(member):
    return member.char_id & 0x7FFFFFFF


def raid_formed():
    return _event(0x6C2)


def prejoin(group, sub):
    return _event(0x6D7, struct.pack("<QQiB", group.id, group.leader.char_id, sub, 1))


def raid_moved(member, sub):
    return _event(0x6C1, struct.pack("<iii", row_id(member), 0, sub))


def raid_role(member, role):
    return _event(0x6A6, struct.pack("<iii", 0, row_id(member), role))


def ready_requested():
    return _event(0x6C4)


def ready_popup(initiator):
    return _event(0x6C5, struct.pack("<i", row_id(initiator)))


def ready_status(member, status):
    return _event(0x6C6, struct.pack("<ii", row_id(member), status))


# Mentoring (zone): 0x5c8 {wstr target} request; 0x5ca {wstr requester} popup to the target;
# 0x5c9 {bool8} accept/decline; 0x5cb stop. The mentor's level goes down to the requester's.
MENTOR_REQUEST, MENTOR_ANSWER, MENTOR_STOP = 0x5C8, 0x5C9, 0x5CB
MENTOR_EVENTS = (MENTOR_REQUEST, MENTOR_ANSWER, MENTOR_STOP)


def mentor_popup(requester):
    return _event(0x5CA, _w(requester))


def member_level(member, level):
    return _event(0x68F, struct.pack("<Qi", member.char_id, level))


def alert(text, sound=7):
    return _event(0x551, _w(text) + struct.pack("<B", sound))


def member_added(member, sub=0):
    pos = member.live_position or member.spawned_at or (0.0, 0.0, 0.0)
    eid = member.char_id
    data = (_w(member.name) + struct.pack("<QQii", eid, eid, eid & 0x7FFFFFFF, sub)
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


# /groupboot <name> (0xb3) and /grouppromote <name> (0xb4), leader only. A non-leader gets 0x6a3
# {u8} "MustBeGroupLeader" (FUN_004d4b60; the byte is not read). The booted player gets 0x6a2
# "YouBootedFromGroup"; the others get 0x6bd {eid64, i32} "OtherBootedFromGroup", which also drops
# that row (FUN_004e0960).
def must_be_leader():
    return _event(0x6A3, struct.pack("<B", 1))


def you_booted():
    return _event(0x6A2)


def member_booted(member):
    return _event(0x6BD, struct.pack("<Qi", member.char_id, 0))


def disbanded():
    return _event(0x6BE)
