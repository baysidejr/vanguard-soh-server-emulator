"""Guilds (docs/GUILDS.md; client dispatcher FUN_004f1610).

Zone events (client): 0x4d3 create {eid64, wstr name, ...}, 0x4d5 invite {wstr name},
  0x4d6 accept, 0x4d7 decline, 0x4dc quit, 0x4da delete, 0x4db kick {wstr},
  0x4d8 promote {wstr}, 0x4d9 demote {wstr}.
Server: 0x4e7 opens the guild-name dialog; 0x4dd {i32 guild id, i32 my rank} (0 = none);
  0x4ea MsgGuildInfo; 0x4eb clear members, 0x4ec member, 0x4ed end of list;
  0x4ee member update (rank 0 = removed; notify 1 joined, 2 removed, 3 quit);
  0x4e9 invite popup {eid64, wstr inviter, wstr guild, wstr rank, i32};
  0x40 {u64 0, i32 id, wstr name} guild name for overhead tags.
World social (type 5) from the client: 0x4e2 MOTD set {raw wstr}, 0x4e3 MOTD view,
  0x4d2 rename rank {i32 name bytes, i32 rank, wstr name}, 0x4df /guildstatus {wstr name}, 0x4ec member list.
Server: 0x4e1 MOTD {wstr motd, wstr by, i32 time}; 0x4de rank renamed {i32 rank, wstr name};
  0x4df status {wstr name, wstr guild, i32 rank} ("%s is a %s in %s."; the client takes the
  rank name from its own guild's table; rank 0 -> "That player is not in a Guild.").
Guild chat: world type 6 command "guildsay <text>" -> 0x0f {text, speaker, 0x0b}, echo 0x11.
Ranks 1..10 (10 = leader)."""
import struct

CREATE, INVITE, ACCEPT, DECLINE, DELETE, KICK, PROMOTE, DEMOTE, QUIT = (
    0x4D3, 0x4D5, 0x4D6, 0x4D7, 0x4DA, 0x4DB, 0x4D8, 0x4D9, 0x4DC)
CLIENT_EVENTS = (CREATE, INVITE, ACCEPT, DECLINE, DELETE, KICK, PROMOTE, DEMOTE, QUIT)
LEADER, OFFICER, MEMBER = 10, 9, 1
CHAT_GUILD = 0x0B
RANK_NAMES = ["Recruit", "Member", "Member", "Member", "Member", "Veteran", "Veteran",
              "Senior", "Officer", "Leader"]
JOINED, REMOVED, QUIT_NOTE = 1, 2, 3
RENAME_RANK, STATUS, MOTD_SET, MOTD_VIEW, MEMBER_LIST = 0x4D2, 0x4DF, 0x4E2, 0x4E3, 0x4EC
WORLD_EVENTS = (RENAME_RANK, STATUS, MOTD_SET, MOTD_VIEW, MEMBER_LIST)


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def name_dialog():
    return _event(0x4E7)


def membership(guild_id, rank):
    return _event(0x4DD, struct.pack("<ii", guild_id, rank))


def info(name, ranks=None):
    data = _w(name) + struct.pack("<iBB", 0, 0, 0) + _w("") + struct.pack("<ii", 0, 0)
    for n, rank in enumerate(ranks or RANK_NAMES, start=1):
        power = int(n >= OFFICER)
        data += _w(rank) + struct.pack("<BBB", power, power, power)
    return _event(0x4EA, data + bytes(20))


def member_record(m, notify=0):
    """m: dict with id, name, rank, chunk, klass, level, online."""
    cx, cy = m.get("chunk", (0, 0))
    return (struct.pack("<Q", m["id"]) + _w(m["name"])
            + struct.pack("<iiiiiBBI", m["rank"], cx, cy, m.get("klass", 0), m.get("level", 1),
                          int(m.get("online", False)), 0, 0)
            + _w("") + _w("") + struct.pack("<f", 0.0) + _w("") + struct.pack("<i", notify))


def member_list(members):
    return ([_event(0x4EB)] + [_event(0x4EC, member_record(m)) for m in members] + [_event(0x4ED)])


def member_update(m, notify=0):
    return _event(0x4EE, member_record(m, notify))


def invite(inviter_eid, inviter, guild_name, rank=MEMBER, ranks=None):
    return _event(0x4E9, struct.pack("<Q", inviter_eid) + _w(inviter) + _w(guild_name)
                  + _w((ranks or RANK_NAMES)[rank - 1]) + struct.pack("<i", rank))


def motd(text, by, when):
    return _event(0x4E1, _w(text) + _w(by) + struct.pack("<i", int(when)))


def rank_renamed(rank, name):
    return _event(0x4DE, struct.pack("<i", rank) + _w(name))


def status(name, guild_name, rank):
    return _event(0x4DF, _w(name) + _w(guild_name) + struct.pack("<i", rank))


def name_tag(guild_id, name):
    return _event(0x40, struct.pack("<Qi", 0, guild_id) + _w(name))


def read_create_name(data):
    """0x4d3: eid64 then the guild name."""
    return data[8:].decode("utf-16-le", "replace").split("\0")[0]


def read_name(data):
    return data.decode("utf-16-le", "replace").split("\0")[0]
