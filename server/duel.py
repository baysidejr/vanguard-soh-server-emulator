"""Duels between players (docs/DUELS.md; zone connection only).

Client -> server:
  0x3fd (none)  /duel (challenges the defensive target) and /duelcancel (same bytes)
  0x3ff {i32}   /duelaccept (0) / /dueldecline (1)
  0x5c {u64}    defensive target (clicking a friendly player)
Server -> client:
  0x3fe {wstr name, i32 mode}  1 = "Duel challenge" popup on the challenged player,
                               0 = "You challenge %s to a duel." for the challenger
  0x400 {wstr opponent, i32 seconds}  countdown (also stores the name for the result text)
  0x401 {eid64 opponent}  the duel starts (the client makes it the offensive target)
  0x402 declined, 0x403 timed out, 0x404 already engaged / unable
  0x405 {u8} 1 "You have defeated %s", 0 "You have been defeated by %s"
  0x0e codes 0xb2-0xc2 (errors: need a defensive target, can't duel yourself, ...)."""
import struct

CHALLENGE, ANSWER, DEFENSIVE_TARGET = 0x3FD, 0x3FF, 0x5C
CLIENT_EVENTS = (CHALLENGE, ANSWER, DEFENSIVE_TARGET)
COUNTDOWN = 10
CHALLENGE_SECONDS = 30
RANGE = 3000.0


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def challenge(name, to_challenged):
    return _event(0x3FE, _w(name) + struct.pack("<i", 1 if to_challenged else 0))


def countdown(opponent, seconds=COUNTDOWN):
    return _event(0x400, _w(opponent) + struct.pack("<i", seconds))


def start(opponent_eid):
    return _event(0x401, struct.pack("<Q", opponent_eid))


def attackable(eids):
    """0x406 {i32 n, n x eid64}: the pets / charmed pawns this duelist may attack during the duel
    (FUN_004ca180; 0x407 {eid64} adds one). An empty list clears it."""
    return _event(0x406, struct.pack("<i", len(eids)) + b"".join(struct.pack("<Q", e) for e in eids))


def declined():
    return _event(0x402)


def timed_out():
    return _event(0x403)


def busy():
    return _event(0x404)


def result(won):
    return _event(0x405, struct.pack("<B", 1 if won else 0))


class Target:
    """Lets combat.targets() describe a player (entity_id + health byte)."""
    def __init__(self, player):
        self.entity_id = player.char_id
        self._p = player

    def health_byte(self):
        return max(0, min(255, self._p.health * 255 // max(1, self._p.stats["hit_points"])))
