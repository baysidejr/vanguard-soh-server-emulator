"""Zone server: the Unreal Engine 2 channel (zone message type 1).

Handles the UE2 login handshake (HELLO/CHALLENGE, LOGIN/USES.../WELCOME, JOIN)
and spawns the player's pawn and PlayerController on actor channels. See
docs/PROTOCOL.md, ue2net.py, packagemap.py and netcache.py.
"""

import struct
import time

import rpc
import vgmsg
import combat
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
            if state.pop("use_requested", False):
                # "Use" (U key) on a dead target opens its loot window.
                npc = player.npcs.get(player.target) if player.target else None
                if npc and not npc.alive:
                    for m in combat.loot_messages(npc):
                        send(m)
                    print(f"  <- ZONE loot window for {npc.name}")
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
        state.setdefault("position", player.spawned_at)   # until the first ServerMove
        motd = "Welcome to the Vanguard emulator."
        send(zone_event(0x70, (motd + "\0").encode("utf-16-le")))   # message of the day
        for event_id in args.zone_in_events:
            # Zone events after the spawn. 0x485 (no payload) sets the client's
            # "world loaded" flags (subsystem manager +0x2b1, +0xd8).
            send(zone_event(event_id))
            print(f"  <- ZONE event {event_id:#x} (no payload)")
        # Character sheet (MsgScore). Field meanings are inferred; see vgmsg.py.
        send(score_message(player, probe=args.test_stats))
        print("  <- ZONE event 0x3de (MsgScore)")
        for m in stat_messages(player):
            send(m)
        print("  <- ZONE events 0x2d5/0x2d4 (stats)")
        for m in inventory_messages(player):
            send(m)
        print("  <- ZONE events 0x195/0x197/0x1bb (inventory)")
        for m in ability_messages(player):
            send(m)
        print("  <- ZONE events 0x21b/0x215/0x21d (abilities)")
        for m in hud_messages():
            send(m)
        print("  <- ZONE events 0x598 (show hotbar, compass, menu bar)")
        # Other pawns go out after the world-loaded event: the client only builds
        # a pawn's mesh (FUN_00bcb8e0) once that flag is set.
        if args.test_npc:
            pm = package_map(args, player.level)
            for n, (cls_path, name, race, off) in enumerate(TEST_NPCS):
                loc = tuple(a + b for a, b in zip(player.spawned_at, off))
                eid = getattr(args, "npc_entity_id", None) or (0x2000000 + n)
                b = npc_bunch(ue, pm, FIRST_NPC_CHANNEL + n, cls_path, name, race, loc, eid)
                player.npcs[eid] = combat.Npc(eid, name, FIRST_NPC_CHANNEL + n, cls_path,
                                             location=loc)
                print(f"  <- UNREAL actor open ch={FIRST_NPC_CHANNEL + n} {cls_path} {name!r} at {loc}")
                send(unreal_message(ue.build([b])))


XP_PER_LEVEL = 1000


def score_message(player, probe=False):
    """MsgScore (0x3de): the character sheet, level and XP bar."""
    loc = player.spawned_at or (0.0, 0.0, 0.0)
    return zone_event(0x3DE, vgmsg.score(probe=probe,
        bind_x=loc[0], bind_y=loc[1], bind_z=loc[2], race=player.race,
        adv_class=player.klass, adv_level=player.level_number,
        adv_exp_amount=player.xp, adv_exp_amount_next=XP_PER_LEVEL,
        adv_exp_frac=player.xp / XP_PER_LEVEL,
        armor_class=25, craft_level=1, harvest_level=1, dip_level=1,
        movement_mode=2, move_speed=1.0, craft_trade=0xFF,
        attack=-40.0, attack_max=-40.0, ranged=-25.0, spell_attack=-10.0,
        defense_input=6.0, melee_mitigation=0.05, spell_mitigation=0.02,
        melee_evasion=0.05, spell_evasion=0.02, block=5.0, dodge=8.0, parry=6.0,
        hp_regen_s=2.0, endurance_regen_s=5.0, energy_regen_s=3.0))


def health_update(player):
    """MsgStatUpdate (0x2d4) of the Health stat: current value and maximum."""
    return zone_event(0x2D4, vgmsg.stat_update(vgmsg.STAT_IDS["hit_points"], player.health,
                                               maximum=player.stats["hit_points"]))


def npc_update(state, args, npc, values):
    """A zone message updating replicated properties of an NPC's pawn."""
    return pawn_update(state, args, npc.channel, npc.cls_path, values)


def player_pawn_update(state, args, values):
    return pawn_update(state, args, PAWN_CHANNEL, args.pawn_class, values)


def player_teleport(location, rotation=(0, 0, 0), tag=0):
    """Zone event 0x3e5 MsgForceLocationSet (FUN_006203d0 -> FUN_00b721d0): f32 x,
    y, z, i32 pitch, yaw, roll, i32. The client FarMoveActor()s its own pawn and
    echoes 0x3e5 back. (Replicated Location and the ClientSetLocation RPC are
    ignored for the local pawn.)"""
    return zone_event(0x3E5, struct.pack("<fffiiii", *location, *rotation, tag))


def pawn_update(state, args, channel, cls_path, values):
    ue, player = state["ue"], state["player"]
    pm = package_map(args, player.level)
    cls = cls_path.split(".", 1)[1]
    w = ue2net.BitWriter()
    for rep_index, max_index, write in pm.net_cache.props(cls, values):
        w.serialize_int(rep_index, max_index)
        write(w)
    data, nbits = w.packed()
    return unreal_message(ue.build([ue.actor_bunch(channel, data, nbits)]))


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
            # Ignore positions at the world origin: the client reports one when the
            # pawn's location was never set (e.g. wrong net role).
            plausible = abs(loc[0]) > 2 or abs(loc[1]) > 2
            if save and plausible and now - state.get("position_saved", 0) > 2.0:
                save(loc)
                state["position_saved"] = now
        return
    print(f"  >>> UNREAL RPC {name} {params}")
    if name == "ServerUse":
        state["use_requested"] = True


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
# Starter weapons per adventuring class (races_classes.ADVENTURING_CLASSES):
# [(name, icon, slot tag)]. Icons are iconsTK.xml numbers.
CLASS_STARTER_WEAPONS = {
    0x1C: [("Militia Longsword", 423, "PRIMARYHAND")],                  # Warrior
    0x04: [("Crusader's Mace", 425, "PRIMARYHAND")],                    # Paladin
    0x14: [("Blackened Blade", 422, "PRIMARYHAND")],                    # Dread Knight
    0x13: [("Hunter's Shortsword", 422, "PRIMARYHAND"),
           ("Yew Longbow", 427, "RANGED")],                              # Ranger
    0x15: [("Rusted Dagger", 429, "PRIMARYHAND")],                      # Rogue
    0x02: [("Minstrel's Scimitar", 479, "PRIMARYHAND")],                # Bard
    0x0F: [("Training Staff", 469, "PRIMARYHAND")],                     # Monk
    0x1B: [("Training Staff", 469, "PRIMARYHAND")],                     # Disciple
    0x05: [("Acolyte's Mace", 425, "PRIMARYHAND")],                     # Cleric
    0x16: [("Spirit Hammer", 468, "PRIMARYHAND")],                      # Shaman
    0x07: [("Oak Staff", 469, "PRIMARYHAND")],                          # Druid
    0x19: [("Apprentice Staff", 469, "PRIMARYHAND")],                   # Sorcerer
    0x2D: [("Bone Staff", 469, "PRIMARYHAND")],                         # Necromancer
    0x0E: [("Focus Staff", 469, "PRIMARYHAND")],                        # Psionicist
    0x2C: [("Ritual Dagger", 429, "PRIMARYHAND")],                      # Blood Mage
}


def starter_equipment(klass):
    """(item id, name, icon, equip slot) for the class's starter weapons."""
    kit = CLASS_STARTER_WEAPONS.get(klass, CLASS_STARTER_WEAPONS[0x1C])
    return [(2001 + n, name, icon, vgmsg.EQUIP_SLOTS[slot])
            for n, (name, icon, slot) in enumerate(kit)]
# Abilities: (handle, ability id, name, icon, description, refresh seconds).
DEFAULT_ABILITIES = [
    (1, 1001, "Strike", 553, "A basic melee attack.", 0.0),
    (2, 1002, "Shield Bash", 692, "Bash the target with your shield.", 10.0),
    (3, 1003, "Rend", 607, "A vicious cut that leaves the target bleeding.", 15.0),
    (4, 1004, "Battle Cry", 560, "A shout that draws the attention of nearby foes.", 30.0),
]
DEFAULT_COINS = 12345   # copper: 1 gold 23 silver 45 copper


def ability_messages(player):
    """0x21b clears the ability book, one 0x215 per ability, 0x21d marks it loaded
    (FUN_0042bd80 / FUN_00432570). The client creates the book lists itself."""
    out = [zone_event(0x21B)]
    for handle, ability_id, name, icon, desc, refresh in player.abilities:
        out.append(zone_event(0x215, vgmsg.ability_info(handle, ability_id, name, icon, desc,
                                                       refresh=refresh)))
    out.append(zone_event(0x21D))
    # Main hotbar: the abilities in the first slots (0x54e replaces all bars).
    keys = [vgmsg.hotkey(slot, ability_id)
            for slot, (_, ability_id, *_rest) in enumerate(player.abilities[:12])]
    out.append(zone_event(0x54E, vgmsg.hotkey_list(keys)))
    return out


# In-game system windows the client leaves hidden after character select; they
# are shown with the client's own console command (zone event 0x598 = wstr command,
# run via FUN_00b75140). "toggle" flips visibility, so send once per session.
HUD_WINDOWS = ["Hotkeys", "Compass", "Window Controller", "Containers", "Lag Meter"]


def hud_messages():
    return [zone_event(0x598, (f'SGOUI toggle "{name}"' + chr(0)).encode("utf-16-le"))
            for name in HUD_WINDOWS]


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
        self.equipment = starter_equipment(klass)
        self.abilities = list(DEFAULT_ABILITIES)
        self.coins = DEFAULT_COINS
        self.npcs = {}                    # entity id -> combat.Npc seen by this player
        self.target = None                # entity id from client event 0x5d
        self.health = self.stats["hit_points"]   # current HP; the stat holds the maximum
        self.last_combat = 0.0
        self.pending_displays = []        # 0x3d1 messages queued by combat
        self.pending_rewards = []         # experience from kills
        self.auto_attack = False
        self.level_number = 10            # adventuring level (self.level is the map name)
        self.xp = 500                     # toward the next level (XP_PER_LEVEL)
        self.next_swing = 0.0


PC_CHANNEL = 1
PAWN_CHANNEL = 2
FIRST_NPC_CHANNEL = 3

# Test pawn for --test-npc: (class, name, race, offset from the player's spawn
# point).
TEST_NPCS = [
    ("SGOUnrealAbstractionLayer.SGOPCPawn", "Guide North", 0x04, (260.0, 160.0, 0.0)),
    ("SGOUnrealAbstractionLayer.SGOPCPawn", "Guide South", 0x02, (260.0, -160.0, 0.0)),
    ("SGOUnrealAbstractionLayer.SGONPCPawn", "Guide East", 0x0E, (320.0, 60.0, 0.0)),
    ("SGOUnrealAbstractionLayer.SGONPCPawn", "Guide West", 0x02, (120.0, -40.0, 0.0)),
]
NPC_FACING = (0, 32768, 0)   # Rotation (pitch, yaw, roll); yaw 32768 = half a turn


def npc_bunch(ue, pm, channel, cls_path, name, race, location, entity_id):
    """Open an actor channel for a non-player pawn (same layout as the player's
    pawn, without bNetOwner)."""
    cls = cls_path.split(".", 1)[1]
    props = pm.net_cache.props(cls, {
        "bHidden": False,
        "DrawScale": 1.0,
        "bSimulateGravity": True,   # else TickSimulated forces PHYS_Flying (hover)
        "m_bGMHide": False,
        "m_iRaceId": race,
        "Health": 100,
        "m_iModelNum": -1,          # the race's default model (FUN_00bcb8e0)
        "m_Customization": [0x32] * 64,   # appearance sliders (pawn +0xaa8)
        "m_PlayerDisplayName": name,
        "Rotation": NPC_FACING,
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
            # The client runs this pawn as a SimulatedProxy; APawn::TickSimulated
            # (FUN_00a03070) then sets PHYS_Flying every tick unless
            # bSimulateGravity is set, which made the character hover.
            "bSimulateGravity": True,
            "m_iRaceId": player.race,
            "Health": 100,
            "m_PlayerDisplayName": player.name,
        }
        if getattr(player, "appearance", None):
            # The 64 appearance sliders from character creation (pawn +0xaa8);
            # PostNetReceive applies them through FUN_00bcaab0.
            values["m_Customization"] = list(player.appearance)
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
