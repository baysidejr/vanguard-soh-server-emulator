"""Reactions: combat chains (opener -> steps -> finisher) and the reaction windows that make
the next ability usable for a few seconds (docs/ABILITIES.md "Reactions").

server -> client:
  0x268 define a chain: 14 x i32 {0, 0, 5 x (step ability id, step line id), finisher id,
        finisher line id}; step 0 is the opener, -1 = unused. 0x26a forgets all chains.
  0x391 open a reaction: {eid64 target, i32 reaction id, i32 ability id, f32 seconds,
        i32 type, bool8 0, i32 0, i32 0}; the client lights the ability (hotbar and the
        Reactions window), runs the countdown sweep and closes it when the time is up.
        type: 0 chain step, 8 finisher, 2 counter, 3 rescue (rescues never time out).
  0x392 {i32 reaction id} close one; 0x396 close all.
  0x39a {u8} activation result: 0 ok, 1 timed out, 4 invalid target, 5 target dead, 7 cost.
  0x242 {u8 0x2a} "That requires a chain." (a locked chain ability used directly).
client -> server: 0x145 {i32 reaction id} activate.

Ability records (0x215, vgmsg.ability_info): flags (wire #8) 0x03 = chain opener, 0x02 =
chain step / finisher (locked until a reaction opens it); line id (#18) = the ability id, so
every ability is its own line."""
import itertools
import struct

ACTIVATE = 0x145
CHAIN_STEP, COUNTER, RESCUE, FINISHER = 0, 2, 3, 8
OK, TIMED_OUT, INVALID_TARGET, TARGET_DEAD = 0, 1, 4, 5
REQUIRES_CHAIN = 0x2A
FLAG_OPENER, FLAG_STEP = 0x03, 0x02
DEFAULT_WINDOW = 6.0

_ids = itertools.count(1)


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def class_chains(chains, class_name, abilities):
    """The class's chains as [{"ids": [opener id, step ids..., finisher id], "window"}] for
    the abilities the player has (by display name; abilities = player.abilities tuples)."""
    by_name = {a[2]: a[1] for a in abilities}
    out = []
    for c in chains.get(class_name, []):
        names = [c["opener"]] + list(c.get("steps", [])) + [c["finisher"]]
        if all(n in by_name for n in names) and len(names) <= 6:
            out.append({"ids": [by_name[n] for n in names], "window": c.get("window", DEFAULT_WINDOW)})
    return out


def chain_names(chains, class_name):
    """Every ability name the class's chains use (they join the ability book)."""
    out = []
    for c in chains.get(class_name, []):
        out += [c["opener"]] + list(c.get("steps", [])) + [c["finisher"]]
    return out


def flags(chains, ability_id):
    """Ability record flags (wire #8) for an ability id."""
    for c in chains:
        if ability_id == c["ids"][0]:
            return FLAG_OPENER
        if ability_id in c["ids"][1:]:
            return FLAG_STEP
    return 0


def locked(chains, ability_id, counters=()):
    return flags(chains, ability_id) == FLAG_STEP or ability_id in counters


RESCUE_WINDOW = 6.0


def class_counters(counters, class_name, abilities):
    """Ability ids of the class's counter abilities the player has."""
    by_name = {a[2]: a[1] for a in abilities}
    return [by_name[n] for n in counters.get(class_name, []) if n in by_name]


def define(chain):
    """0x268 for one chain."""
    ids = chain["ids"]
    steps = ids[:-1] + [-1] * (5 - len(ids[:-1]))
    vals = [0, 0]
    for s in steps:
        vals += [s, s]
    vals += [ids[-1], ids[-1]]
    return _event(0x268, struct.pack("<14i", *vals))


def forget_all():
    return _event(0x26A)


def next_step(chains, ability_id):
    """(next ability id, reaction type, window) after ability_id went off, or None."""
    for c in chains:
        ids = c["ids"]
        if ability_id in ids[:-1]:
            nxt = ids[ids.index(ability_id) + 1]
            return nxt, FINISHER if nxt == ids[-1] else CHAIN_STEP, c["window"]
    return None


def open_reaction(target_eid, ability_id, seconds, kind=CHAIN_STEP):
    """(reaction id, 0x391 message)."""
    rid = next(_ids)
    return rid, _event(0x391, struct.pack("<QiifiBii", target_eid, rid, ability_id, seconds, kind, 0, 0, 0))


def close_reaction(rid):
    return _event(0x392, struct.pack("<i", rid))


def close_all():
    return _event(0x396)


def result(code):
    return _event(0x39A, struct.pack("<B", code))


# Enemy spell casts (docs/ABILITIES.md "Enemy casts and counters"): the client has no
# enemy cast bar; it prints "<name> begins to cast a spell." (0x248) and shows the spell as
# an in-flight ability icon by the target frame (0x3a5, one at a time).
CAST_SUCCESS, CAST_COUNTERED, CAST_INTERRUPTED = 0, 3, 13
ONLY_AS_REACTION = 0x01          # 0x242 code: the ability can only be used as a reaction
_flights = itertools.count(1)


def begins_to_cast(caster_eid):
    return _event(0x248, struct.pack("<Q", caster_eid))


def in_flight(name, icon, seconds):
    """(in-flight id, 0x3a5 {i32 id, i32 icon, wstr name, f32 seconds})."""
    fid = next(_flights)
    return fid, _event(0x3A5, struct.pack("<ii", fid, icon) + (name + "\0").encode("utf-16-le")
                       + struct.pack("<f", seconds))


def in_flight_result(fid, code, value=0):
    """0x3a7 {i32 id, i32 result, i32 value, i32 flag, bool8}: removes the icon."""
    return _event(0x3A7, struct.pack("<iiiiB", fid, code, value, 0, 0))


def clear_in_flight():
    return _event(0x3A8)


def incoming_result(code, value=0):
    """0x3b2 {i32, i32 result, i32 value, i32 flag, bool8}: result text in the incoming
    attacks queue (2 "Countered", 13 "Interrupt")."""
    return _event(0x3B2, struct.pack("<iiiiB", 0, code, value, 0, 0))
