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
import content
import merchant
import harvest
import craft
import workorder
import mail
import trainer
import diplomacy
import quest
import world
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
                # "Use" (U key): a merchant opens its dialog; a dead target its loot.
                npc = player.npcs.get(player.target) if player.target else None
                if args.use_tombstone(state):
                    pass
                elif npc and npc.harvest:
                    args.harvest_begin(state)
                elif npc and npc.station:
                    args.craft_event(state, craft.USE_STATION, b"")
                elif npc and npc.alive and npc.talks():
                    for m in args.npc_dialog(state, npc):
                        send(m)
                elif npc and not npc.alive:
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
        # Recipe book and crafting actions (silent adds).
        wo = args.content.workorders.get(getattr(player, "work_order", None) or "", {})
        for key, r in args.content.recipes.items():
            if r.get("work_order") and key != wo.get("recipe"):
                continue
            if "trainer_cost" in r and key not in getattr(player, "known_recipes", []):
                continue
            send(craft.learn_recipe(r))
            for n in range(len(craft.all_steps(r))):
                send(craft.learn_action(r, n))
            for c in r.get("complications", []):
                send(craft.learn_counter(c))
        # Quest journal: active quests (0x2cb entries) so the tracker and log are filled.
        import quest
        have = lambda name: sum(i[3] for i in player.items if i[1] == name)
        for key, prog in player.quests.active.items():
            q = args.content.quests.get(key)
            if q:
                send(quest.page(q, 0, quest.READY if quest.ready(q, prog, have) else quest.IN_PROGRESS,
                                prog, journal=True, have=have))
        # "SGOUI toggle" flips the windows, so only on the first zone-in of a session
        # (a chunk handoff keeps the client's UI).
        if not player.hud_shown:
            player.hud_shown = True
            for m in hud_messages():
                send(m)
        print("  <- ZONE events 0x598 (show hotbar, compass, menu bar)")
        # Join the shared world for this chunk: NPCs from content/spawns/<chunk>.json
        # and the other players. Sent after the world-loaded event: the client only
        # builds a pawn's mesh (FUN_00bcb8e0) once that flag is set.
        w = world.world_for(player.level)
        if not w.populated:
            populate_world(w, args)
        state["world"] = w
        player.npcs = w.npcs
        w.members[player.char_id] = state
        if getattr(player, "tombstone", None) and player.tombstone.get("level") == player.level:
            tombstone_spawn(w, args, player)
        for npc in w.npcs.values():
            send(open_npc(state, args, npc))
        for other in w.others(state):
            send(open_remote_player(state, args, other["player"]))
            other["send"](open_remote_player(other, args, player))
            print(f"  <- {player.name} and {other['player'].name} now see each other")


ALTAR = 0x1000000 | 0x10      # altar (cursor, "AltarHover") + NPC name plate
TOMBSTONE_RACE = 587          # the "Tombstone" static mesh; always gets the loot cursor (0x4187bb)
TOMBSTONE_TYPES = 0x2 | 0x20  # corpse + player: the name reads "<name>'s corpse" when m_bIsDead


def tombstone_eid(player):
    return 0x3000000 + (player.char_id & 0xFFFFF)


def tombstone_spawn(w, args, player):
    """The player's tombstone (player.tombstone = {level, loc}) as a world actor; returns
    the new Npc, or None if it is already there."""
    eid = tombstone_eid(player)
    if eid in w.npcs:
        return None
    npc = combat.Npc(eid, player.name, None, f"{content.PAWN_PACKAGE}.SGONPCPawn",
                     location=tuple(player.tombstone["loc"]))
    npc.race = TOMBSTONE_RACE
    npc.prop = True
    npc.tombstone_of = player.name
    npc.template_id = "tombstone"
    npc.props = {"EntityTypes": TOMBSTONE_TYPES, "m_bIsDead": 1, "DrawScale": 0.35}
    w.npcs[eid] = npc
    return npc


def populate_world(w, args):
    """Create the shared NPCs of a chunk from content/spawns/<chunk>.json."""
    for n, (spawn, template) in enumerate(args.content.spawns(w.level, args.client_dir)):
        eid = 0x2000000 + n
        loc = (float(spawn["x"]), float(spawn["y"]), float(spawn["z"]))
        npc = combat.Npc(eid, template["name"], None,
                         f"{content.PAWN_PACKAGE}.{template['pawn_class']}",
                         max_health=template["health"], location=loc)
        npc.race = template["race"]
        npc.gear = [tuple(g) for g in template.get("gear", [])]
        npc.yaw = int(spawn.get("yaw", 0))
        npc.merchant = template.get("merchant")
        npc.harvest = template.get("harvest")
        npc.station = bool(template.get("station"))
        npc.prop = bool(template.get("prop"))
        npc.trainer = bool(template.get("trainer"))
        npc.banker = bool(template.get("banker"))
        npc.task_master = bool(template.get("task_master"))
        npc.mailbox = bool(template.get("mailbox"))
        npc.recipe_trainer = list(template.get("recipe_trainer", []))
        npc.broker = template.get("broker")
        npc.altar = bool(template.get("altar"))
        npc.dialog = args.content.dialogs.get(spawn["mob"])
        npc.repairs = bool(template.get("repair"))
        npc.parley = template.get("parley")        # diplomacy.json parley key
        npc.template_id = spawn["mob"]
        npc.quests = [k for k, q in args.content.quests.items()
                      if spawn["mob"] in (q.get("giver"), quest.turn_in(q))
                      or any(s.get("talk") == spawn["mob"] for s in quest.steps(q))]
        npc.wander = float(spawn.get("wander", 0))
        npc.path = [tuple(p[:2]) for p in spawn.get("path", [])]
        npc.path_pause = float(spawn.get("pause", 2.0))
        npc.ground_z = lambda x, y, lvl=w.level: args.content.ground_z(lvl, x, y, args.client_dir)
        npc.next_wander = time.time() + n
        npc.aggro_radius = float(template.get("aggro_radius", 0))
        npc.level = template.get("level", 1)
        # Creature races (64+) bite and claw; people swing weapons.
        npc.attack_visual = template.get("attack_visual", combat.CREATURE_AUTO_ATTACK
                                         if template["race"] >= 64 else combat.NPC_AUTO_ATTACK)
        npc.props = {"m_GameplayLevel": npc.level}
        if "scale" in template:
            npc.props["DrawScale"] = float(template["scale"])
        if npc.harvest:
            npc.props["EntityTypes"] = harvest.HARVESTABLE
        if npc.station:
            npc.props["EntityTypes"] = craft.STATION
        if npc.task_master:
            npc.props["EntityTypes"] = workorder.TASK_MASTER
        if npc.mailbox:
            npc.props["EntityTypes"] = mail.MAILBOX
        if npc.recipe_trainer:
            npc.props["EntityTypes"] = trainer.RECIPE_TRAINER
        if npc.altar:
            npc.props["EntityTypes"] = ALTAR
        if "model" in template:
            npc.props["m_iModelNum"] = template["model"]
        if "gender" in template:
            npc.props["m_Gender"] = template["gender"]
        if template.get("title"):
            npc.props["m_PlayerDisplayTitle"] = template["title"]
        npc.faction = template.get("faction")
        if npc.faction is not None and template["pawn_class"] == "SGONPCPawn":   # SGOPCPawn has no m_FactionId
            npc.props["m_FactionId"] = int(npc.faction)
        npc.damage = tuple(template.get("damage", combat.NPC_DAMAGE))
        npc.abilities = list(template.get("abilities", []))
        npc.respawn = spawn.get("respawn", content.DEFAULT_RESPAWN)
        npc.loot_table = template.get("loot")
        npc.roll_loot = args.content.roll_loot
        w.npcs[eid] = npc
        print(f"  world {w.level}: {template['name']!r} ({spawn['mob']}) at {loc}")
    w.populated = True


def open_npc(state, args, npc):
    """Open this connection's actor channel for a world NPC (current state)."""
    ue, player = state["ue"], state["player"]
    pm = package_map(args, player.level)
    channel = world.channel_for(state, npc.entity_id, allocate=True)
    b = npc_bunch(ue, pm, channel, npc.cls_path, npc.name, npc.race, npc.location,
                  npc.entity_id, gear=npc.gear, facing=(0, npc.yaw, 0),
                  dead=not npc.alive, extra_props=npc.props)
    print(f"  <- UNREAL actor open ch={channel} {npc.name!r} for {player.name}")
    return unreal_message(ue.build([b]))


def open_remote_player(state, args, other):
    """Open this connection's actor channel for another player's pawn: the same
    properties as the owner's pawn, without bNetOwner."""
    ue, player = state["ue"], state["player"]
    pm = package_map(args, player.level)
    channel = world.channel_for(state, other.char_id, allocate=True)
    cls = args.pawn_class.split(".", 1)[1]
    loc = other.live_position or other.spawned_at
    values = player_pawn_values(other, loc)
    values.pop("bNetOwner", None)
    b = ue.actor_open_bunch(channel, pm.object_index(args.pawn_class), pm.max_object_index,
                            location=loc, extra=(0xFF, -1, 0x3F800000),
                            properties=pm.net_cache.props(cls, values))
    return unreal_message(ue.build([b]))


def close_actor(state, entity_id):
    """Close this connection's channel for a world actor (it left)."""
    channel = state.get("channels", {}).pop(entity_id, None)
    if channel is None:
        return None
    ue = state["ue"]
    return unreal_message(ue.build([ue.actor_close_bunch(channel)]))


XP_PER_LEVEL = 1000


def score_message(player, probe=False):
    """MsgScore (0x3de): the character sheet, level and XP bar."""
    loc = player.spawned_at or (0.0, 0.0, 0.0)
    bind = getattr(player, "bind", None)
    if bind:
        loc = bind["loc"]
    return zone_event(0x3DE, vgmsg.score(probe=probe,
        bind_x=loc[0], bind_y=loc[1], bind_z=loc[2], race=player.race,
        adv_class=player.klass, adv_level=player.level_number,
        adv_exp_amount=player.xp, adv_exp_amount_next=XP_PER_LEVEL,
        adv_exp_frac=player.xp / XP_PER_LEVEL,
        adv_exp_debt_frac=min(1.0, getattr(player, "xp_debt", 0) / XP_PER_LEVEL),
        armor_class=25, craft_level=1, harvest_level=1, dip_level=1,
        movement_mode=2, move_speed=1.0, craft_trade=0xFF,
        attack=-40.0, attack_max=-40.0, ranged=-25.0, spell_attack=-10.0,
        defense_input=6.0, melee_mitigation=0.05, spell_mitigation=0.02,
        melee_evasion=0.05, spell_evasion=0.02, block=5.0, dodge=8.0, parry=6.0,
        hp_regen_s=2.0, endurance_regen_s=5.0, energy_regen_s=3.0))


def endurance_update(player):
    return zone_event(0x2D4, vgmsg.stat_update(vgmsg.STAT_IDS["endurance"], player.endurance,
                                               maximum=player.stats["endurance"]))


def health_update(player):
    """MsgStatUpdate (0x2d4) of the Health stat: current value and maximum."""
    return zone_event(0x2D4, vgmsg.stat_update(vgmsg.STAT_IDS["hit_points"], player.health,
                                               maximum=player.stats["hit_points"]))


def npc_update(state, args, npc, values):
    """A zone message updating replicated properties of an NPC's pawn on this
    connection (None if it has no channel for it)."""
    channel = world.channel_for(state, npc.entity_id)
    if channel is None:
        return None
    return pawn_update(state, args, channel, npc.cls_path, values)


def remote_player_update(state, args, other, values):
    channel = world.channel_for(state, other.char_id)
    if channel is None:
        return None
    return pawn_update(state, args, channel, args.pawn_class, values)


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
        player.live_position = loc
        if moved:
            broadcast_movement(state, args, player, loc, params.get("View"))
        if moved:
            print(f"  >>> UNREAL {name}: position {loc}")
            save = player.save_position
            now = time.time()
            # Ignore positions at the world origin: the client reports one when the
            # pawn's location was never set (e.g. wrong net role).
            # Also ignore positions outside this chunk (crossing into a neighbour is
            # not handled yet; see docs/PROTOCOL.md "Chunk travel").
            plausible = ((abs(loc[0]) > 2 or abs(loc[1]) > 2)
                         and abs(loc[0]) <= CHUNK_HALF and abs(loc[1]) <= CHUNK_HALF)
            if save and plausible and now - state.get("position_saved", 0) > 2.0:
                save(loc)
                state["position_saved"] = now
        return
    print(f"  >>> UNREAL RPC {name} {params}")
    if name == "ServerUse":
        state["use_requested"] = True


CHUNK_HALF = 102400.0          # chunks are 204800 units wide, centred on 0
MOVE_BROADCAST_SECONDS = 0.1
MAX_BROADCAST_SPEED = 1200.0    # units/s; running is ~440


def broadcast_movement(state, args, player, loc, view):
    """Show this player's movement to everyone else in the chunk (10 Hz)."""
    w = state.get("world")
    now = time.time()
    if w is None or now - state.get("move_sent", 0) < MOVE_BROADCAST_SECONDS:
        return
    prev, prev_t = state.get("move_prev", (loc, now))
    dt = max(now - prev_t, 0.05)
    vel = tuple((a - b) / dt for a, b in zip(loc, prev))
    if sum(v * v for v in vel) > MAX_BROADCAST_SPEED ** 2:
        # A teleport or a stall, not walking: the other clients would keep
        # extrapolating along a huge velocity, so send none.
        vel = (0.0, 0.0, 0.0)
    state["move_sent"], state["move_prev"] = now, (loc, now)
    yaw = world.view_yaw(view)
    values = {"Location": loc, "Rotation": (0, yaw, 0), "Velocity": vel,
              "PawnPosition": (loc, (0, yaw, 0), vel)}
    w.broadcast(lambda s: remote_player_update(s, args, player, values), exclude=state)


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
    (0x0f, 1, 0x15),    # Mining
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
    0x1C: [("Militia Longsword", 423, "PRIMARYHAND"),
           ("Round Shield", 512, "SECONDARYHAND")],                      # Warrior
    0x04: [("Crusader's Mace", 425, "PRIMARYHAND"),
           ("Round Shield", 512, "SECONDARYHAND")],                      # Paladin
    0x14: [("Blackened Blade", 422, "PRIMARYHAND")],                    # Dread Knight
    0x13: [("Hunter's Shortsword", 422, "PRIMARYHAND"),
           ("Yew Longbow", 427, "RANGED")],                              # Ranger
    0x15: [("Rusted Dagger", 429, "PRIMARYHAND")],                      # Rogue
    0x02: [("Minstrel's Scimitar", 479, "PRIMARYHAND")],                # Bard
    0x0F: [("Training Staff", 483, "PRIMARYHAND")],                     # Monk
    0x1B: [("Training Staff", 483, "PRIMARYHAND")],                     # Disciple
    0x05: [("Acolyte's Mace", 425, "PRIMARYHAND")],                     # Cleric
    0x16: [("Spirit Hammer", 468, "PRIMARYHAND")],                      # Shaman
    0x07: [("Oak Staff", 483, "PRIMARYHAND")],                          # Druid
    0x19: [("Apprentice Staff", 483, "PRIMARYHAND")],                   # Sorcerer
    0x2D: [("Bone Staff", 483, "PRIMARYHAND")],                         # Necromancer
    0x0E: [("Focus Staff", 483, "PRIMARYHAND")],                        # Psionicist
    0x2C: [("Ritual Dagger", 429, "PRIMARYHAND")],                      # Blood Mage
}


STARTER_OUTFIT = [("Traveler's Robe", 436, "CHEST"), ("Traveler's Leggings", 434, "LEGS"),
                  ("Traveler's Boots", 461, "FEET")]


def starter_equipment(klass):
    """(item id, name, icon, equip slot) for the class's starter weapons and outfit."""
    kit = CLASS_STARTER_WEAPONS.get(klass, CLASS_STARTER_WEAPONS[0x1C]) + STARTER_OUTFIT
    return [(2001 + n, name, icon, vgmsg.EQUIP_SLOTS[slot])
            for n, (name, icon, slot) in enumerate(kit)]


ITEM_CONTENT = content.Content()


ITEM_TYPE_IDS = {"misc": 3, "shield": 0, "weapon": 1, "armor": 4, "ranged": 9, "jewelry": 10,
                 "container": 11, "ammo": 20,
                 "harvest_tool": 16}


def damage_encoding(lo, hi):
    """(base, variance) for item fields 77/78. The client shows
    int(base - base*v/255) .. int(base + base*v/255); because the two ends are
    symmetric around an integer base, a range whose ends sum to an even number
    can't be hit with a safe margin, so prefer exact-with-margin, then closest."""
    best = None
    for base in range(max(lo, 1), hi + 2):
        for v in range(256):
            d = base * v / 255
            a, b = base - d, base + d
            err = abs(int(a) - lo) + abs(int(b) - hi)
            margin = min(a - int(a), b - int(b))
            if margin < 0.01:        # on an integer boundary: float32 may land below
                err += 1
            key = (err, -margin)
            if best is None or key < best[0]:
                best = (key, base, v)
    return best[1], best[2]


def item_icon(name, fallback):
    """The icon from content/items.json wins over one saved with the item."""
    return ITEM_CONTENT.item(name).get("icon", fallback)


def item_equip_fields(name, durability=100):
    """inventory_item keyword arguments from content/items.json: equip slots and
    the tooltip/usability fields (see docs/INVENTORY.md, item field table)."""
    tpl = ITEM_CONTENT.item(name)
    extra = {94: 1, 100: 255, 106: durability, 99: tpl.get("rarity", 1), 76: tpl.get("level", 1)}
    # Field 74 = item type; 0 would be "Shield", 3 is a plain item.
    extra[74] = ITEM_TYPE_IDS[tpl.get("type", "misc")]
    if tpl.get("type", "misc") == "misc":
        extra[106] = -1          # no durability line
        extra[76] = 0            # no "Required Level" line
    if "damage" in tpl:
        # Shown as base*(1 -/+ variance/255): pick base and variance for [min, max].
        base, var = damage_encoding(*tpl["damage"])
        extra.update({77: base, 78: var, 79: base, 82: float(tpl.get("delay", 2.0))})
    if "skill" in tpl:
        extra[84] = tpl["skill"]
    if "armor" in tpl:
        extra[85] = tpl["armor"]
    out = {"raw": extra}
    if "slot" in tpl:
        slot = vgmsg.EQUIP_SLOTS[tpl["slot"]]
        allowed = [slot]
        pair = {vgmsg.EQUIP_SLOTS["LEFTFINGER"], vgmsg.EQUIP_SLOTS["RIGHTFINGER"]}
        if slot in pair:
            allowed = sorted(pair)
        out.update(default_slot=slot, allowed_slots=allowed)
    return out


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
    out.append(hotbar_message(player))
    return out


def hotbar_message(player):
    """Main hotbar: the abilities in the first slots (0x54e replaces all bars).
    A saved layout (player.hotbar, from the client's 0x54b/0x54c) wins."""
    if player.hotbar is not None:
        keys = [bytes.fromhex(v) for v in player.hotbar.values()]
    else:
        keys = [vgmsg.hotkey(slot, ability_id)
                for slot, (_, ability_id, *_rest) in enumerate(player.abilities[:12])]
    return zone_event(0x54E, vgmsg.hotkey_list(keys))


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
    dur = getattr(player, "durability", {})
    for item_id, name, icon, qty, slot in player.items:
        out.append(zone_event(0x197, vgmsg.inventory_item(item_id, name, slot, item_icon(name, icon), qty,
                                                          **item_equip_fields(name, dur.get(str(item_id), 100)))))
    # Equipped items: create in the bag, then 0x1a7 (FUN_0050feb0: i32 item id,
    # u8 lookup kind, u8 equip slot) moves them to the paper doll.
    for n, (item_id, name, icon, equip_slot) in enumerate(player.equipment):
        out.append(zone_event(0x197, vgmsg.inventory_item(item_id, name, 49 - n, item_icon(name, icon),
                                                          **item_equip_fields(name, dur.get(str(item_id), 100)))))
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
        self.items = normalize_items(DEFAULT_ITEMS)
        self.equipment = starter_equipment(klass)
        self.abilities = list(DEFAULT_ABILITIES)
        self.coins = DEFAULT_COINS
        self.npcs = {}                    # entity id -> combat.Npc seen by this player
        self.target = None                # entity id from client event 0x5d
        self.live_position = None         # last ClientLoc from ServerMove
        self.health = self.stats["hit_points"]   # current HP; the stat holds the maximum
        self.endurance = self.stats["endurance"]
        self.last_combat = 0.0
        self.pending_displays = []        # 0x3d1 messages queued by combat
        self.pending_rewards = []         # experience from kills
        self.auto_attack = False
        self.chunk = None                 # (x, y) of the current chunk
        self.hud_shown = False            # HUD windows toggled on this session
        self.group = None                 # group.Group
        import quest
        self.quests = quest.QuestLog()
        self.pending_invite = None        # inviter's zone connection state
        self.hotbar = None                # {"bank:slot": hotkey record hex} once changed
        self.level_number = 10            # adventuring level (self.level is the map name)
        self.xp = 500                     # toward the next level (XP_PER_LEVEL)
        self.next_swing = 0.0


PC_CHANNEL = 1
PAWN_CHANNEL = 2

def npc_bunch(ue, pm, channel, cls_path, name, race, location, entity_id, gear=(),
              facing=(0, 0, 0), dead=False, extra_props=None):
    """Open an actor channel for a non-player pawn (same layout as the player's
    pawn, without bNetOwner)."""
    cls = cls_path.split(".", 1)[1]
    props = pm.net_cache.props(cls, {
        "bHidden": False,
        "DrawScale": 1.0,
        "bSimulateGravity": True,   # else TickSimulated forces PHYS_Flying (hover)
        "m_bGMHide": False,
        "m_iRaceId": race,
        "Health": 0 if dead else 100,
        "m_bIsDead": 1 if dead else 0,
        "m_iModelNum": -1,          # the race's default model (FUN_00bcb8e0)
        "m_Customization": [0x32] * 64,   # appearance sliders (pawn +0xaa8)
        "m_PlayerDisplayName": name,
        "Rotation": facing,
        "PawnPosition": (location, facing, (0.0, 0.0, 0.0)),
        "m_AttachmentGroups": [tuple(g) for g in gear],
        "EntityIDLowInt": entity_id & 0xFFFFFFFF,
        "EntityIDHighInt": entity_id >> 32,
        **(extra_props or {}),
    })
    return ue.actor_open_bunch(channel, pm.object_index(cls_path), pm.max_object_index,
                               location=location, extra=(0xFF, -1, 0x3F800000), properties=props)


SPAWN_Z_LIFT = 90.0   # observed: spawn z 4900 -> pawn at 4990 (= CollisionHeight)


# Gear on the character model: pawn m_AttachmentGroups[60] of (mesh type,
# mesh number, inventory slot), built from the equipped items' "mesh" in
# content/items.json. Mesh types (FUN_00bb0200): 9 CHEST, 12 FEET, 14 HAND,
# 15 HEAD, 16 LEG, 18 SHOULDER, 23 BOW, 26 DAGGER, 28 HAMMER, 29 MACE, 31 STAFF,
# 33 SWORD, 34 SHIELD. Slots are vgmsg.EQUIP_SLOTS (28 right hand, 29 left).


MOUNT_PACKAGE, MOUNT_SLOT = 500, 39
MOUNT_GROUND, MOUNT_FLYING = 1, 3         # m_MountType (0 none, 2 aquatic)


def gear_attachments(player, slots=60):
    """m_AttachmentGroups: one (mesh type, mesh number, slot) per equipped item
    with a model (content/items.json), padded with empty (-1, -1, -1) entries so
    removed pieces are cleared on the client."""
    gear = []
    for _id, name, _icon, slot in player.equipment:
        mesh = ITEM_CONTENT.item(name).get("mesh")
        if mesh:
            gear.append((mesh[0], mesh[1], slot))
    if getattr(player, "mount", None):
        # (package 500 MOUNT_ITEMS, mount id, slot 39 MOUNT): the client mounts the rider (FUN_00bc9a70).
        gear.append((MOUNT_PACKAGE, player.mount, MOUNT_SLOT))
    return gear + [(-1, -1, -1)] * (min(slots, len(gear) + 8) - len(gear))


BAG_SLOTS = 50


def free_bag_slot(player):
    """Lowest empty main-bag slot, or None. Bag items are (id, name, icon, qty, slot)."""
    used = {i[4] for i in player.items}
    return next((s for s in range(BAG_SLOTS) if s not in used), None)


def new_item_id(player):
    new = max([i[0] for i in player.items] + [e[0] for e in player.equipment]
              + [b[0] for b in getattr(player, "bank", [])] + [10000]) + 1
    getattr(player, "durability", {}).pop(str(new), None)     # ids are reused: no stale wear
    return new


def normalize_items(items):
    """Saved/legacy bag lists: give 4-element items their list index as slot."""
    return [tuple(i) if len(i) == 5 else tuple(i) + (n,) for n, i in enumerate(items)]


def unequip_message(handle, bag_slot, container=-1):
    """0x1a9 (FUN_00511100): i32 item handle, i32 bag slot, i32 container (-1 =
    main bag): the client takes the item off the paper doll into that slot."""
    return zone_event(0x1A9, struct.pack("<iii", handle, bag_slot, container))


def unequip_item(player, handle):
    """Paper doll -> first free bag slot (client event 0x98). Returns a chat
    error (str) or the zone messages."""
    item = next((e for e in player.equipment if e[0] == handle), None)
    if item is None:
        return "That item is not equipped."
    slot = free_bag_slot(player)
    if slot is None:
        return "Your bags are full."
    player.equipment.remove(item)
    player.items.append((item[0], item[1], item[2], 1, slot))
    return [unequip_message(item[0], slot)]


def equip_item(player, handle):
    """Move a bag item onto the paper doll (client event 0x8e). Whatever was in
    that slot (or blocks it, e.g. a two-hander) goes back to the bag. Returns a
    chat error (str) or the zone messages that update the client."""
    item = next((i for i in player.items if i[0] == handle), None)
    if item is None:
        return "That item is not in your bags."
    tpl = ITEM_CONTENT.item(item[1])
    if "slot" not in tpl:
        return "That item does not equip."
    slot = vgmsg.EQUIP_SLOTS[tpl["slot"]]
    hands = {vgmsg.EQUIP_SLOTS[s] for s in ("PRIMARYHAND", "SECONDARYHAND", "TWOHANDS")}
    blocked = {slot}
    if slot == vgmsg.EQUIP_SLOTS["TWOHANDS"]:
        blocked |= hands
    elif slot in hands:
        blocked.add(vgmsg.EQUIP_SLOTS["TWOHANDS"])
    msgs = []
    displaced = [e for e in player.equipment if e[3] in blocked]
    split = item[3] > 1
    # Equipping from a stack keeps the rest in the bag, so every displaced piece
    # needs a free slot; otherwise the first one takes the equipped item's slot.
    if len(player.items) - (0 if split else 1) + len(displaced) > BAG_SLOTS:
        return "Your bags are full."
    if split:
        # 0x1ae {handle, count} shrinks the stack; the equipped one is a new item.
        player.items[player.items.index(item)] = item[:3] + (item[3] - 1, item[4])
        msgs.append(zone_event(0x1AE, struct.pack("<ii", item[0], item[3] - 1)))
        item = (new_item_id(player), item[1], item[2], 1, None)
        msgs.append(zone_event(0x197, vgmsg.inventory_item(
            item[0], item[1], -1, item_icon(item[1], item[2]), 1, equip_slot=slot,
            **item_equip_fields(item[1]))))
    else:
        player.items.remove(item)
    bag_slot = item[4]
    for old in displaced:
        # The old piece takes the bag slot the new one leaves (then any free slot).
        player.equipment.remove(old)
        if bag_slot is None:
            bag_slot = free_bag_slot(player)
        player.items.append((old[0], old[1], old[2], 1, bag_slot))
        msgs.append(unequip_message(old[0], bag_slot))
        bag_slot = None
    player.equipment.append((item[0], item[1], item[2], slot))
    # 0x1a7 (FUN_0050feb0): i32 item handle, u8 0, u8 slot moves it to the paper doll.
    msgs.append(zone_event(0x1A7, struct.pack("<iBB", item[0], 0, slot)))
    return msgs


def spawn_location(args, pm, player):
    if args.spawn_location:
        return tuple(float(v) for v in args.spawn_location.split(","))
    if player.position:
        # The saved position is the client's ClientLoc (pawn centre). The client
        # places a spawned pawn SPAWN_Z_LIFT above the given location, so
        # without this the character would rise 90 units at every login.
        x, y, z = (float(v) for v in player.position)
        return (x, y, z - SPAWN_Z_LIFT)
    # No saved position: the chunks' PlayerStarts are not real spawn points (in
    # chunk_n19_12 one hangs over a canyon, the other over the sea), so stand on
    # flat land from the terrain heightmap.
    ground = default_ground_spawn(args, player.level)
    if ground:
        return ground
    starts = [s for s in pm.packages[0][1].player_starts() if s]
    return starts[0] if starts else (0.0, 0.0, 0.0)


def default_ground_spawn(args, level):
    import os
    import terrain
    path = os.path.join(args.client_dir, "Assets", "Maps", level + ".vgr")
    try:
        land = terrain.Terrain(path).flat_land(count=1)
    except (OSError, StopIteration, KeyError, ValueError):
        return None
    if not land:
        return None
    x, y, z = land[0]
    return (x, y, z + 100.0)


def player_pawn_values(player, location, yaw=0):
    """Replicated properties of a player's pawn (own or seen by others)."""
    values = {
        "bNetOwner": True,
        # The client runs this pawn as a SimulatedProxy; APawn::TickSimulated
        # (FUN_00a03070) then sets PHYS_Flying every tick unless
        # bSimulateGravity is set, which made the character hover.
        "bSimulateGravity": True,
        "m_iRaceId": player.race,
        "Health": 100,
        "m_PlayerDisplayName": player.name,
        # Guild tag over the head (name from zone event 0x40). m_bIsAfk = 1 made the
        # pawn disappear on every client (live test), so AFK/LFG stay in /who only.
        "m_GuildId": getattr(player, "guild_id", 0),
    }
    gear = gear_attachments(player)
    if gear:
        values["m_AttachmentGroups"] = gear
    if getattr(player, "appearance", None):
        # The 64 appearance sliders from character creation (pawn +0xaa8);
        # PostNetReceive applies them through FUN_00bcaab0.
        values["m_Customization"] = list(player.appearance)
    # PawnPosition seeds the client's ground-stick cache (LastValidServerPosition,
    # FUN_007f9680); without it the pawn re-sticks from a stale height and sinks.
    values["PawnPosition"] = (location, (0, yaw, 0), (0.0, 0.0, 0.0))
    cid = player.char_id
    if cid is not None:
        values["EntityIDLowInt"] = cid & 0xFFFFFFFF
        values["EntityIDHighInt"] = cid >> 32
    return values


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
        values = player_pawn_values(player, location)
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
