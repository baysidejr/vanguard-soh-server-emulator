"""Zone server: the Unreal Engine 2 channel (zone message type 1).

Handles the UE2 login handshake (HELLO/CHALLENGE, LOGIN/USES.../WELCOME, JOIN)
and spawns the player's pawn and PlayerController on actor channels. See
docs/PROTOCOL.md, ue2net.py, packagemap.py and netcache.py.
"""

import struct
import time

import rpc
import ue2net
from netcache import NetCache
from packagemap import PackageMap


def unreal_message(packet):
    # Zone message type 1 carries one UE2 packet: u16le 1, u32le length, bytes.
    return struct.pack("<HI", 1, len(packet)) + packet


def handle_unreal(send, state, payload, args):
    """Zone type 1: a UE2 UNetConnection packet (see ue2net.py)."""
    (length,) = struct.unpack_from("<I", payload, 2)
    packet = payload[6:6 + length]
    ue = state.setdefault("ue", ue2net.UnrealSession())
    player = state.get("player") or args.default_player()
    state["player"] = player
    try:
        packet_id, acks, bunches = ue.receive(packet)
    except ValueError as e:
        print(f"  >>> UNREAL undecodable packet ({e}): {packet.hex(' ')}")
        return
    replies = []
    for b in bunches:
        if b.channel == 0 and b.ch_type == ue2net.CHTYPE_CONTROL:
            for text in ue2net.read_fstrings(b.data):
                print(f"  >>> UNREAL control <- {text!r}")
                replies.extend(unreal_control_reply(text, args, player))
        elif b.channel == PC_CHANNEL and not b.open:
            log_client_rpc(state, b, args, player)
        else:
            print(f"  >>> UNREAL bunch {b!r} data={b.data[:32].hex(' ')}")
    out = []
    for t in replies:
        if t == "<SPAWN>":
            out.extend(spawn_bunches(ue, args, player))
            continue
        out.append(ue.control_bunch(t))
        print(f"  <- UNREAL control -> {t!r}")
    # One packet per bunch keeps every packet well under the 512-byte bunch limit.
    if not out:
        send(unreal_message(ue.build()))
    for b in out:
        send(unreal_message(ue.build([b])))
    if "<SPAWN>" in replies:
        motd = "Welcome to the Vanguard emulator."
        send(zone_event(0x70, (motd + "\0").encode("utf-16-le")))   # message of the day
        for event_id in args.zone_in_events:
            # Zone events after the spawn. 0x485 (no payload) sets the client's
            # "world loaded" flags (subsystem manager +0x2b1, +0xd8).
            send(zone_event(event_id))
            print(f"  <- ZONE event {event_id:#x} (no payload)")
        # Other pawns go out after the world-loaded event: the client only builds
        # a pawn's mesh (FUN_00bcb8e0) once that flag is set.
        if args.test_npc:
            pm = package_map(args, player.level)
            for n, (cls_path, name, race, off) in enumerate(TEST_NPCS):
                loc = tuple(a + b for a, b in zip(player.spawned_at, off))
                eid = getattr(args, "npc_entity_id", None) or (0x2000000 + n)
                b = npc_bunch(ue, pm, FIRST_NPC_CHANNEL + n, cls_path, name, race, loc, eid)
                print(f"  <- UNREAL actor open ch={FIRST_NPC_CHANNEL + n} {cls_path} {name!r} at {loc}")
                send(unreal_message(ue.build([b])))


def zone_event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def log_client_rpc(state, b, args, player):
    """Decode an RPC from the client's PlayerController and track its position."""
    pm = package_map(args, player.level)
    try:
        name, params = rpc.decode_rpc(pm.net_cache, args.spawn_class.split(".", 1)[1],
                                      b.data, b.nbits, pm.max_object_index)
    except ValueError as e:
        print(f"  >>> UNREAL RPC undecodable ({e}): {b.data.hex(' ')}")
        return
    loc = params.get("ClientLoc")
    if loc is not None:
        moved = state.get("position") != loc
        state["position"] = loc
        if moved:
            print(f"  >>> UNREAL {name}: position {loc}")
            save = player.save_position
            now = time.time()
            if save and now - state.get("position_saved", 0) > 2.0:
                save(loc)
                state["position_saved"] = now
        return
    print(f"  >>> UNREAL RPC {name} {params}")


def package_map(args, level):
    """PackageMap + NetCache for a level, built once (chunk files are large)."""
    if level not in args.package_maps:
        pm = PackageMap(args.client_dir, level)
        pm.net_cache = NetCache([(n, p) for n, p, _ in pm.packages])
        args.package_maps[level] = pm
    return args.package_maps[level]


class Player:
    """One character in the zone: who it is and where it should appear. Built by
    the world server on Play and claimed by the zone connection with the same
    session key (see login_stub.py)."""

    def __init__(self, name="", char_id=None, race=0x0E, level="", position=None,
                 save_position=None):
        self.name = name
        self.char_id = char_id
        self.race = race
        self.level = level
        self.position = position          # saved spawn point, or None
        self.save_position = save_position
        self.spawned_at = None


PC_CHANNEL = 1
PAWN_CHANNEL = 2
FIRST_NPC_CHANNEL = 3

# Test pawn for --test-npc: (class, name, race, offset from the player's spawn
# point). The client spawns it and applies the properties, but as of now a
# non-owned pawn (SGONPCPawn or SGOPCPawn) does not render - it likely needs
# appearance/model data we don't send yet.
TEST_NPCS = [
    ("SGOUnrealAbstractionLayer.SGOPCPawn", "Guide North", 0x0E, (150.0, 0.0, 0.0)),
    ("SGOUnrealAbstractionLayer.SGOPCPawn", "Guide South", 0x0E, (-150.0, 0.0, 0.0)),
    ("SGOUnrealAbstractionLayer.SGONPCPawn", "Guide East", 0x0E, (0.0, 150.0, 0.0)),
    ("SGOUnrealAbstractionLayer.SGONPCPawn", "Guide West", 0x0E, (0.0, -150.0, 0.0)),
]


def npc_bunch(ue, pm, channel, cls_path, name, race, location, entity_id):
    """Open an actor channel for a non-player pawn (same layout as the player's
    pawn, without bNetOwner)."""
    cls = cls_path.split(".", 1)[1]
    props = pm.net_cache.props(cls, {
        "bHidden": False,
        "m_iRaceId": race,
        "Health": 100,
        "m_iModelNum": -1,          # the race's default model (FUN_00bcb8e0)
        "m_PlayerDisplayName": name,
        "EntityIDLowInt": entity_id & 0xFFFFFFFF,
        "EntityIDHighInt": entity_id >> 32,
    })
    return ue.actor_open_bunch(channel, pm.object_index(cls_path), pm.max_object_index,
                               location=location, extra=(0xFF, -1, 0x3F800000), properties=props)


def spawn_location(args, pm, player):
    if args.spawn_location:
        return tuple(float(v) for v in args.spawn_location.split(","))
    if player.position:
        return tuple(float(v) for v in player.position)
    starts = [s for s in pm.packages[0][1].player_starts() if s]
    return starts[0] if starts else (0.0, 0.0, 0.0)


def spawn_bunches(ue, args, player):
    """Spawn the player's pawn and PlayerController on actor channels.

    Vanguard replicates Actor.bNetOwner; an owned PlayerController makes the
    client run UNetConnection::HandleClientPlayer and take it as the local
    player. Controller.Pawn points at the pawn's channel."""
    pm = package_map(args, player.level)
    nc = pm.net_cache
    location = spawn_location(args, pm, player)
    print(f"  spawn location {location}")
    rotation = (0, 0, 0) if args.spawn_rotation else None
    out = []

    pawn_cls = args.pawn_class.split(".", 1)[1] if args.pawn_class else None
    if pawn_cls:
        values = {
            "bNetOwner": True,
            "m_iRaceId": player.race,
            "Health": 100,
            "m_PlayerDisplayName": player.name,
        }
        cid = player.char_id
        if cid is not None:
            values["EntityIDLowInt"] = cid & 0xFFFFFFFF
            values["EntityIDHighInt"] = cid >> 32
        props = nc.props(pawn_cls, values)
        # Pawn subclasses carry three extra fields (FUN_00962350); these are the
        # client's own defaults (0xff, -1, 1.0f).
        b = ue.actor_open_bunch(PAWN_CHANNEL, pm.object_index(args.pawn_class), pm.max_object_index,
                                location=location, rotation=rotation,
                                extra=(0xFF, -1, 0x3F800000), properties=props)
        print(f"  <- UNREAL actor open ch={PAWN_CHANNEL} {args.pawn_class} {b.nbits} bits: {b.data.hex(' ')}")
        out.append(b)

    pc_cls = args.spawn_class.split(".", 1)[1]
    cache = nc.class_cache(pc_cls)
    props = nc.props(pc_cls, {"bNetOwner": True})
    if pawn_cls:
        def pawn_ref(w):
            w.bit(1)                                   # actor, by channel
            w.serialize_int(PAWN_CHANNEL, ue2net.MAX_CHANNELS)
        props.append((nc.field(pc_cls, "Pawn").index, cache["max"], pawn_ref))
    b = ue.actor_open_bunch(PC_CHANNEL, pm.object_index(args.spawn_class), pm.max_object_index,
                            location=location, rotation=rotation, properties=props)
    print(f"  <- UNREAL actor open ch={PC_CHANNEL} {args.spawn_class} {b.nbits} bits: {b.data.hex(' ')}")
    out.append(b)
    player.spawned_at = location
    if pawn_cls:
        # RPC PlayerController.ClientRestart() (no parameters in this build): the
        # client takes the pawn and enters its walking state.
        w = ue2net.BitWriter()
        w.serialize_int(nc.field(pc_cls, "ClientRestart").index, cache["max"])
        data, nbits = w.packed()
        out.append(ue.actor_bunch(PC_CHANNEL, data, nbits))
        print(f"  <- UNREAL RPC ClientRestart on ch={PC_CHANNEL}")
    return out


def unreal_control_reply(text, args, player):
    """Server side of the UE2 login handshake (UWorld::NotifyReceivedText):
    HELLO -> CHALLENGE, LOGIN -> WELCOME. The client then loads the level and
    sends JOIN."""
    word = text.split(" ", 1)[0]
    if word == "HELLO":
        return ["CHALLENGE VER=3186 CHALLENGE=12345 STATS=0"]
    if word == "LOGIN":
        # USES lines fill the client's package map before WELCOME (FUN_009677e0).
        level = player.level
        return package_map(args, level).uses_lines() + [f"WELCOME LEVEL={level} LONE=0"]
    if word == "JOIN" and args.spawn_class:
        return ["<SPAWN>"]
    return []
