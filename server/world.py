"""Shared world state: one World per level (chunk) holds the NPCs and the
players in it, so everyone in the chunk sees the same mobs and each other.

UE2 actor channels are per connection, so every connection keeps its own
map from world actor (entity id) to channel number: state["channels"].
Messages are built per connection (each has its own UE2 sequence numbers) and
sent with state["send"]."""
import struct

FIRST_DYNAMIC_CHANNEL = 3      # 1 = own PlayerController, 2 = own pawn
_worlds = {}


def world_for(level):
    if level not in _worlds:
        _worlds[level] = World(level)
    return _worlds[level]


def all_worlds():
    return list(_worlds.values())


class World:
    def __init__(self, level):
        self.level = level
        self.npcs = {}           # entity id -> combat.Npc (shared by every player)
        self.populated = False   # content spawns created
        self.members = {}        # player entity id -> zone connection state

    def players(self):
        return [s["player"] for s in self.members.values()]

    def others(self, state):
        return [s for s in self.members.values() if s is not state]

    def broadcast(self, build, exclude=None):
        """Send build(state) to every member (build may return None or a list)."""
        for s in list(self.members.values()):
            if s is exclude:
                continue
            out = build(s)
            if out is None:
                continue
            for m in out if isinstance(out, list) else [out]:
                s["send"](m)


QUEUED = []                 # connection states with bunches waiting in state["bunches"]
PACKET_BITS = 400 * 8       # bunch bits per packet (the client's limit is 512 bytes)


def queue_bunch(state, bunch):
    """Send bunch with the next flush_bunches, packed together with other queued bunches."""
    q = state.get("bunches")
    if not q:
        state["bunches"] = q = []
        QUEUED.append(state)
    q.append(bunch)


def flush_bunches(unreal_message):
    """Send every queued bunch: per connection, as few UE packets as fit."""
    while QUEUED:
        state = QUEUED.pop()
        bunches, state["bunches"] = state.get("bunches") or [], []
        if state.get("closed") or "send" not in state or "ue" not in state:
            continue
        batch, bits = [], 0
        for b in bunches:
            size = b.nbits + 48           # header: flags, channel, type, bit count
            if batch and bits + size > PACKET_BITS:
                state["send"](unreal_message(state["ue"].build(batch)))
                batch, bits = [], 0
            batch.append(b)
            bits += size
        if batch:
            state["send"](unreal_message(state["ue"].build(batch)))


def channel_for(state, entity_id, allocate=False):
    """This connection's actor channel for a world actor."""
    channels = state.setdefault("channels", {})
    if entity_id not in channels and allocate:
        used = set(channels.values())
        ch = FIRST_DYNAMIC_CHANNEL
        while ch in used:
            ch += 1
        channels[entity_id] = ch
    return channels.get(entity_id)


def view_yaw(view):
    """ServerMove's View int packs (pitch/2) << 15 | (yaw/2)."""
    return ((view or 0) & 0x7FFF) * 2


def zone_event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data
