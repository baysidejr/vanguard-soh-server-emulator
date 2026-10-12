"""Zone server: the Unreal Engine 2 channel (zone message type 1).

Handles the UE2 login handshake (HELLO/CHALLENGE, LOGIN/USES.../WELCOME, JOIN)
and spawns the player's pawn and PlayerController on actor channels. See
docs/PROTOCOL.md, ue2net.py, packagemap.py and netcache.py.
"""

import struct
import time

import rpc
import vgmsg
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
        # Character sheet (MsgScore). Field meanings are inferred; see vgmsg.py.
        loc = player.spawned_at or (0.0, 0.0, 0.0)
        send(zone_event(0x3DE, vgmsg.score(probe=args.test_stats,
            bind_x=loc[0], bind_y=loc[1], bind_z=loc[2], race=player.race,
            adv_class=player.klass, adv_level=10,
            adv_exp_amount=500, adv_exp_amount_next=1000, adv_exp_frac=0.5,
            armor_class=25, craft_level=1, harvest_level=1, dip_level=1,
            movement_mode=2, move_speed=1.0, craft_trade=0xFF,
            attack=-40.0, attack_max=-40.0, ranged=-25.0, spell_attack=-10.0,
            defense_input=6.0, melee_mitigation=0.05, spell_mitigation=0.02,
            melee_evasion=0.05, spell_evasion=0.02, block=5.0, dodge=8.0, parry=6.0,
            hp_regen_s=2.0, endurance_regen_s=5.0, energy_regen_s=3.0)))
        print("  <- ZONE event 0x3de (MsgScore)")
        for m in stat_messages(player):
            send(m)
        print("  <- ZONE events 0x2d5/0x2d4 (stats)")
        for m in inventory_messages(player):
            send(m)
        print("  <- ZONE events 0x195/0x197/0x1bb (inventory)")
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


DEFAULT_STATS = {
    "strength": 40, "constitution": 40, "dexterity": 30, "vitality": 30,
    "intelligence": 20, "wisdom": 20,
    "hit_points": 210, "endurance": 100, "energy": 100,
}


def stat_messages(player):
    """Zone events that fill the character window and HUD bars.

    Stats are created with MsgStatList (0x2d5) and then updated with
    MsgStatUpdate (0x2d4): the attribute UI vars (PCAdvStrength...) are only set
    on the update path (FUN_00576c90 -> FUN_00573070); HP/End/Energy are set on
    creation (FUN_005763b0)."""
    recs = []
    for name, value in player.stats.items():
        kind = 1 if name in vgmsg.ATTRIBUTES else 0
        recs.append(vgmsg.stat_info(vgmsg.STAT_IDS[name], value, kind=kind, maximum=value))
    for sid, value, subtype in player.skills:
        recs.append(vgmsg.stat_info(sid, value, kind=2, subtype=subtype, maximum=SKILL_CAP))
    out = [zone_event(0x2D5, vgmsg.stat_list(recs))]
    for name in vgmsg.ATTRIBUTES:
        out.append(zone_event(0x2D4, vgmsg.stat_update(vgmsg.STAT_IDS[name], player.stats[name])))
    return out


# Skills: (stat id, value, list subtype). Subtypes pick the character window
# list (FUN_00556c50, kind 2): 0 weapon types, 2 wield types, 3 armor,
# 4 combat, 7 perception and concealment, 8 resistance, 9 spell schools,
# 0x15 harvesting, 0x1e general.
DEFAULT_SKILLS = [
    (0x16, 25, 0),      # Mace
    (0xe3, 30, 0),      # Longsword
    (0xc6, 30, 0),      # One-handed Slashing
    (0x45, 20, 2),      # One-handed Wielding
    (0x3c, 20, 2),      # Sword and Shield Wielding
    (0x34, 30, 3),      # Heavy Armor
    (0x9c, 25, 4),      # Block
    (0x58, 35, 4),      # Dodge
    (0x88, 30, 4),      # Parry
    (0x4c, 12, 7),      # Sneak
    (0xfd, 40, 0x1e),   # Swimming
]
SKILL_CAP = 50

# Starter inventory: (item id, name, icon, quantity). Icons are the numbered
# entries of VGUIAssets/Global/Icons/iconsTK.xml (400..99008); 443 is the
# client's "missing icon" fallback.
DEFAULT_ITEMS = [
    (1001, "Rusty Sword", 422, 1),
    (1002, "Travel Rations", 442, 5),
    (1003, "Waterskin", 472, 1),
]
# Equipped items: (item id, name, icon, equip slot from vgmsg.EQUIP_SLOTS).
DEFAULT_EQUIPMENT = [
    (2001, "Militia Longsword", 422, vgmsg.EQUIP_SLOTS["PRIMARYHAND"]),
]
DEFAULT_COINS = 12345   # copper: 1 gold 23 silver 45 copper


def inventory_messages(player):
    """0x195 resets the inventory UI and creates the 50-slot main grid
    (FUN_00513170; field 0 = InventorySpaceAvailable), then one 0x197 per item,
    then 0x1bb sets the coin total without a chat message (0x1aa prints one)."""
    out = [zone_event(0x195, struct.pack("<iiii", 50 - len(player.items), 0, 0, 0))]
    for slot, (item_id, name, icon, qty) in enumerate(player.items):
        out.append(zone_event(0x197, vgmsg.inventory_item(item_id, name, slot, icon, qty)))
    # Equipped items: create in the bag, then 0x1a7 (FUN_0050feb0: i32 item id,
    # u8 lookup kind, u8 equip slot) moves them to the paper doll.
    for n, (item_id, name, icon, equip_slot) in enumerate(player.equipment):
        out.append(zone_event(0x197, vgmsg.inventory_item(item_id, name, 49 - n, icon)))
        out.append(zone_event(0x1A7, struct.pack("<iBB", item_id, 0, equip_slot)))
    out.append(zone_event(0x1BB, struct.pack("<q", player.coins)))
    return out


class Player:
    """One character in the zone: who it is and where it should appear. Built by
    the world server on Play and claimed by the zone connection with the same
    session key (see login_stub.py)."""

    def __init__(self, name="", char_id=None, race=0x0E, klass=0x1C, level="", position=None,
                 save_position=None):
        self.name = name
        self.char_id = char_id
        self.race = race
        self.klass = klass
        self.level = level
        self.position = position          # saved spawn point, or None
        self.save_position = save_position
        self.spawned_at = None
        # Character sheet values (no real character progression yet).
        self.stats = dict(DEFAULT_STATS)
        self.skills = list(DEFAULT_SKILLS)
        self.items = list(DEFAULT_ITEMS)
        self.equipment = list(DEFAULT_EQUIPMENT)
        self.coins = DEFAULT_COINS


PC_CHANNEL = 1
PAWN_CHANNEL = 2
FIRST_NPC_CHANNEL = 3

# Test pawn for --test-npc: (class, name, race, offset from the player's spawn
# point). The client spawns it and applies the properties, but as of now a
# non-owned pawn (SGONPCPawn or SGOPCPawn) does not render - it likely needs
# appearance/model data we don't send yet.
TEST_NPCS = [
    ("SGOUnrealAbstractionLayer.SGOPCPawn", "Guide North", 0x04, (-60.0, 50.0, 0.0)),
    ("SGOUnrealAbstractionLayer.SGOPCPawn", "Guide South", 0x02, (-60.0, -50.0, 0.0)),
    ("SGOUnrealAbstractionLayer.SGONPCPawn", "Guide East", 0x0E, (-120.0, 0.0, 0.0)),
    ("SGOUnrealAbstractionLayer.SGONPCPawn", "Guide West", 0x02, (-180.0, 40.0, 0.0)),
]


def npc_bunch(ue, pm, channel, cls_path, name, race, location, entity_id):
    """Open an actor channel for a non-player pawn (same layout as the player's
    pawn, without bNetOwner)."""
    cls = cls_path.split(".", 1)[1]
    props = pm.net_cache.props(cls, {
        "bHidden": False,
        "DrawScale": 1.0,
        "Physics": 0,               # PHYS_None: stay where spawned
        "m_bGMHide": False,
        "m_iRaceId": race,
        "Health": 100,
        "m_iModelNum": -1,          # the race's default model (FUN_00bcb8e0)
        "m_Customization": [0x32] * 64,   # appearance sliders (pawn +0xaa8)
        "m_PlayerDisplayName": name,
        "EntityIDLowInt": entity_id & 0xFFFFFFFF,
        "EntityIDHighInt": entity_id >> 32,
    })
    return ue.actor_open_bunch(channel, pm.object_index(cls_path), pm.max_object_index,
                               location=location, extra=(0xFF, -1, 0x3F800000), properties=props)


SPAWN_Z_LIFT = 90.0   # observed: spawn z 4900 -> pawn at 4990 (= CollisionHeight)


def spawn_location(args, pm, player):
    if args.spawn_location:
        return tuple(float(v) for v in args.spawn_location.split(","))
    if player.position:
        # The saved position is the client's ClientLoc (pawn centre). The client
        # places a spawned pawn SPAWN_Z_LIFT above the given location, so
        # without this the character would rise 90 units at every login.
        x, y, z = (float(v) for v in player.position)
        return (x, y, z - SPAWN_Z_LIFT)
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
