"""Caravans: travel together while offline (docs/DUELS.md part B; client dispatcher FUN_00488ff0).

A caravan member who has been offline long enough can log in at the caravan (leader's)
location. All traffic is on the zone connection except the character-select choice.
Client -> server: 0x4ae {wstr name} invite, 0x4b0 {wstr inviter} accept, 0x4b4 {wstr inviter}
  decline, 0x4b5 leave, 0x4b6 {i32 member id} remove (leader).
Server -> client: 0x4ae {wstr inviter} invite popup; 0x4bc {i32} 0 none / 1 leader / 2 member;
  0x4ba {wstr name, i32 id, i32 class, f32 seconds left, i32 state} member row (state 1 Must
  Logout, 2 Traveling, 3 Can Login, 4 Leader); 0x4b7 {i32 id} remove row;
  0x4bb {i32 chunk x, y, z, f32 x, y, z, i32} caravan location ("Destination:");
  0x0e 0x62 joined, 0x63 left, 0x64 not in a caravan, 0x65 not with yourself, 0x66 not dead."""
import struct

INVITE, ACCEPT, DECLINE, LEAVE, REMOVE = 0x4AE, 0x4B0, 0x4B4, 0x4B5, 0x4B6
CLIENT_EVENTS = (INVITE, ACCEPT, DECLINE, LEAVE, REMOVE)
NONE, LEADER, MEMBER = 0, 1, 2
MUST_LOGOUT, TRAVELING, CAN_LOGIN, IS_LEADER = 1, 2, 3, 4
JOINED, LEFT, NOT_IN, SELF, DEAD = 0x62, 0x63, 0x64, 0x65, 0x66
TRAVEL_SECONDS = 3 * 3600


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def invite(inviter):
    return _event(0x4AE, _w(inviter))


def role(r):
    return _event(0x4BC, struct.pack("<i", r))


def member(name, mid, klass, seconds, state):
    return _event(0x4BA, _w(name) + struct.pack("<iifi", mid, klass, float(seconds), state))


def removed(mid):
    return _event(0x4B7, struct.pack("<i", mid))


def location(cx, cy, x, y, z):
    return _event(0x4BB, struct.pack("<iiifffi", cx, cy, 0, x, y, z, 0))


def read_name(data):
    return data.decode("utf-16-le", "replace").split("\0")[0].strip()
