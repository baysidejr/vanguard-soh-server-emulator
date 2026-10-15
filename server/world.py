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


SPAWN_STAMPS = {}          # level -> mtime of the spawn file its NPCs were made from

def all_worlds():
    return list(_worlds.values())


class World:
    def __init__(self, level):
        self.level = level
        self.npcs = {}           # entity id -> combat.Npc (shared by every player)
        self.populated = False   # content spawns created
        self.members = {}        # player entity id -> zone connection state
        self.grid = {}           # (cell x, cell y) -> {id(state): state}, see grid_move

    def players(self):
        return [s["player"] for s in self.members.values() if s.get("player") is not None]

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


GRID_CELL = 12000.0         # the far movement tier starts here (zone.MOVE_RATE_TIERS)


def cell_of(pos):
    return int(pos[0] // GRID_CELL), int(pos[1] // GRID_CELL)


def grid_move(w, state, pos):
    """Keep a member's grid cell up to date (only movement looks at the grid)."""
    if pos is None:
        return
    c = cell_of(pos)
    old = state.get("grid_cell")
    if old == c and state.get("grid_world") is w:
        return
    grid_remove(state)
    w.grid.setdefault(c, {})[id(state)] = state
    state["grid_cell"], state["grid_world"] = c, w


def grid_remove(state):
    w, c = state.pop("grid_world", None), state.pop("grid_cell", None)
    if w is not None and c in w.grid:
        w.grid[c].pop(id(state), None)
        if not w.grid[c]:
            del w.grid[c]


def near_members(w, pos):
    """Members in the 3x3 grid cells around pos (everyone within GRID_CELL, and some more)."""
    cx, cy = cell_of(pos)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cell = w.grid.get((cx + dx, cy + dy))
            if cell:
                yield from list(cell.values())


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
