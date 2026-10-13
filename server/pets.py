"""Pets (docs/PETS.md; client pet dispatcher FUN_0057ca30). The client runs no pet AI.

Server -> client (zone):
  0x419 MsgPetNew {eid64 pet, wstr name, u8 type, f32}: this NPC is your pet. type 8/0xb =
        controllable (health bar, dismiss X, Pet Commands and Pet Abilities bars); 6 = minion.
  0x41a (none) pet gone; 0x41b {u8} command reply (0 "Yes, Master.", 1 no pet, 2-4/7 can't,
        5 "returns to dust."); 0x41d {u8 0..255} pet health; 0x418 {wstr} renamed.
Client -> server (zone, no payload unless noted): /pet follow 0x76, stay 0x77, attack 0x79,
  backoff 0x7a, assistme 0x7b, assistmealways 0x7c, guard 0x7d, toggledefendself 0x7e,
  dismiss 0x7f; /petname 0x80 {wstr}."""
import struct

FOLLOW, STAY, ATTACK, BACKOFF, ASSIST, ASSIST_ALWAYS, GUARD, DEFEND, DISMISS, RENAME = (
    0x76, 0x77, 0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F, 0x80)
CLIENT_EVENTS = (FOLLOW, STAY, ATTACK, BACKOFF, ASSIST, ASSIST_ALWAYS, GUARD, DEFEND, DISMISS, RENAME)
CONTROLLABLE = 8
YES, NO_PET, CANT, DUST = 0, 1, 2, 5
FOLLOW_DISTANCE = 150.0
SPEED = 450.0
ATTACK_SECONDS = 2.5
EID_BASE = 0x3800000


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def new(pet_eid, name, kind=CONTROLLABLE):
    return _event(0x419, struct.pack("<Q", pet_eid) + _w(name) + struct.pack("<Bf", kind, 0.0))


def gone():
    return _event(0x41A)


def reply(code):
    return _event(0x41B, struct.pack("<B", code))


def health(npc):
    return _event(0x41D, struct.pack("<B", max(0, min(255, npc.health * 255 // max(1, npc.max_health)))))


def renamed(name):
    return _event(0x418, _w(name))
