"""Fishing (docs/FISHING.md; client dispatcher FUN_004cf940, manager DAT_014639d8).

The client checks the gear (pole in the primary hand and bait in the secondary hand, both
item type 26 "Fishing"), throws the bobber and plays the animations; the server runs the bite
and the minigame.
Client -> server: 0x59d /fishing (cast request); 0x599 {f32 x, y, z} bobber in water (then
  every 2 s); 0x59b {i32 dir} minigame key (0 forward, 1 right, 2 back, 3 left);
  0x59a {i32 0} stop.
Server -> client: 0x59d cast; 0x59a {i32 state} (0 stop, 4 "Fish on!", 5 reel);
  0x59c {eid64, i32 event, i32 dir}: 9 the fish pulls (dir), 3 "Good", 4 "Oops",
  5 "Fish caught!", 6 "The fish got away!", 11 "You scared the fish!"."""
import random
import struct

CAST, BOBBER, KEY, STATE = 0x59D, 0x599, 0x59B, 0x59A
CLIENT_EVENTS = (CAST, BOBBER, KEY, STATE)
FISH_ON, STOP = 4, 0
PULL, GOOD, OOPS, CAUGHT, GOT_AWAY, SCARED = 9, 3, 4, 5, 6, 11
SKILL = 0x5B                       # Fishing skill stat id
NEEDED, MISSES = 4, 2              # good answers to land the fish, misses before it escapes
PULL_SECONDS = 2.5                 # time to answer each pull
LAND_TIMEOUT = 15.0                # the bobber must reach water within this


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def cast():
    return _event(CAST)


def state(s):
    return _event(STATE, struct.pack("<i", s))


def event(eid, ev, direction=0):
    return _event(0x59C, struct.pack("<Qii", eid, ev, direction))


def bite_delay(rng=random):
    return rng.uniform(4.0, 10.0)
