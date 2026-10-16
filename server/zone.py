"""Zone server: the Unreal Engine 2 channel (zone message type 1).

Handles the UE2 login handshake (HELLO/CHALLENGE, LOGIN/USES.../WELCOME, JOIN)
and spawns the player's pawn and PlayerController on actor channels. See
docs/PROTOCOL.md, ue2net.py, packagemap.py and netcache.py.
"""

import re
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
import assembly
import zlib
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
    if state.get("player") is None:
        if not getattr(args, "anonymous_zone", False):
            return                      # not logged in to the zone (PacketLoginRequest) yet
        state["player"] = args.default_player()
    ue = state.setdefault("ue", ue2net.UnrealSession())
    player = state["player"]
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
                    for m in args.open_loot(state, npc):
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
        send(score_message(player))      # again: the Harvesting tab reads its skill (0xc4) with it
        import attributes
        send(attributes.set_pool(attributes.pool(player.level_number, getattr(player, "attr_alloc", {}))))
        send(attributes.set_pool(attributes.pool(sphere(player, CRAFTING)[0], getattr(player, "craft_alloc", {})),
                                 attributes.CRAFTING))
        print("  <- ZONE events 0x2d5/0x2d4 (stats)")
        for m in inventory_messages(player):
            send(m)
        print("  <- ZONE events 0x195/0x197/0x1bb (inventory)")
        # Item reuse timers still running from before a relog ({group: (until, seconds)});
        # sent after the items, which pick the timer up by their field 107.
        for group, (until, seconds) in getattr(player, "item_cooldowns", {}).items():
            if until > time.time():
                send(item_cooldown(group, until - time.time(), seconds))
        if getattr(player, "active_toolbelt", None):
            send(craft.active_toolbelt(player.active_toolbelt))   # saved choice (checkmark)
        for m in ability_messages(player):
            send(m)
        print("  <- ZONE events 0x21b/0x215/0x21d (abilities)")
        import aa
        for m in aa.list_messages(aa_abilities(player), getattr(player, "aa_ranks", {})):
            send(m)
        # Recipe book and crafting actions (silent adds).
        for r in book_recipes(args, player):
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
        world.grid_move(w, state, player.live_position or player.spawned_at)
        if getattr(player, "tombstone", None) and player.tombstone.get("level") == player.level:
            tombstone_spawn(w, args, player)
        for npc in w.npcs.values():
            send(open_npc(state, args, npc))
        for obj in args.placed_objects(player.level):
            send(open_placed_object(state, args, obj))
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


SPAWN_EID_BASE = 0x2000000


def npc_list(rows, verbose=True):
    """0x786 MsgListNPCResponse[] {i32 count, i32 verbose, count x {wstr name, wstr tag, i32 encounter id,
    i32 level, f32 x, y, z}}: the client prints "<name> (Lvl N) <tag> EncounterDBId: <id>
    Loc: x, y, z." per row (FUN_00621500). rows: [(name, tag, level, id, (x, y, z))]."""
    import struct
    data = struct.pack("<ii", len(rows), int(verbose))
    for name, tag, level, eid, loc in rows:
        data += ((name + "\0").encode("utf-16-le") + (tag + "\0").encode("utf-16-le")
                 + struct.pack("<iifff", int(eid), int(level), *(float(c) for c in loc)))
    return zone_event(0x786, data)


def populate_world(w, args):
    """Create the shared NPCs of a chunk from content/spawns/<chunk>.json."""
    import os
    path = os.path.join(args.content.directory, "spawns", w.level + ".json")
    world.SPAWN_STAMPS[w.level] = os.path.getmtime(path) if os.path.exists(path) else None
    files = [os.path.join(args.content.directory, f) for f in ("mobs.json", "quests.json", "dialogs.json", "loot.json")]
    world.SPAWN_STAMPS.setdefault("mobs.json", max((os.path.getmtime(f) for f in files if os.path.exists(f)), default=None))
    for n, (spawn, template) in enumerate(args.content.spawns(w.level, args.client_dir)):
        npc = npc_from_template(w, args, SPAWN_EID_BASE + n, spawn, template, n)
        w.npcs[npc.entity_id] = npc
        print(f"  world {w.level}: {template['name']!r} ({spawn['mob']}) at {npc.location}")
    w.populated = True


def npc_from_template(w, args, eid, spawn, template, n=0):
    """A world NPC from a spawn {mob, x, y, z, yaw, ...} and its mobs.json template."""
    loc = (float(spawn["x"]), float(spawn["y"]), float(spawn["z"]))
    npc = combat.Npc(eid, template["name"], None,
                     f"{content.PAWN_PACKAGE}.{template['pawn_class']}",
                     max_health=template["health"], location=loc)
    npc.race = template["race"]
    npc.gear = [tuple(g) for g in template.get("gear", [])]
    npc.yaw = int(spawn.get("yaw", 0))
    npc.merchant = template.get("merchant")
    npc.harvest = template.get("harvest")
    npc.station = template.get("station") or False   # true (refining) or "finishing"
    npc.coin = template.get("coin")
    npc.crit = template.get("crit")              # critical chance 0-1 (None: the formula)
    npc.flee_at = template.get("flee_at")        # runs for a moment below this health share
    npc.spells = template.get("spells", [])
    npc.prop = bool(template.get("prop"))
    npc.trainer = bool(template.get("trainer"))
    npc.difficulty = template.get("difficulty")    # /con: 0 slightly easier ... 5 extremely difficult
    npc.trainer_classes = template.get("trainer_classes") or []     # empty: trains every class
    npc.banker = bool(template.get("banker"))
    npc.corpse_summoner = bool(template.get("corpse_summoner"))   # dialog option: bring my tombstone
    npc.chatter = list(template.get("chatter", []))           # lines said now and then (login_stub.npc_chatter_tick)
    npc.chatter_every = float(template.get("chatter_every", 120))
    npc.aggro_say = template.get("aggro_say")                  # said on noticing a player; {player} = their name
    npc.task_master = bool(template.get("task_master"))
    npc.mailbox = bool(template.get("mailbox"))
    npc.recipe_trainer = list(template.get("recipe_trainer", []))
    npc.broker = template.get("broker")
    npc.altar = bool(template.get("altar"))
    npc.dialog = args.content.dialogs.get(spawn["mob"])
    npc.riftway = template.get("riftway")
    npc.assembly_trainer = list(template.get("assembly_trainer", []))
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
    npc.blocked = lambda x, y, z, lvl=w.level: npc_blocked(lvl, x, y, z)
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
    if template.get("assembly_station"):
        npc.props["EntityTypes"] = assembly.STATION | 0x10
    if npc.assembly_trainer:
        npc.props["EntityTypes"] = npc.props.get("EntityTypes", 0) | assembly.TRAINER
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
    return npc


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


PLACED_OBJECT_CLASS = "Engine.PlayerPlacedObject"
HOUSE_PLOT, HOUSE_BUILDING, HOUSE_FIXTURE, HOUSE_CHEST, HOUSE_SIGN = 1, 2, 3, 4, 7


def open_placed_object(state, args, obj):
    """Open an actor channel for a housing object (Engine.PlayerPlacedObject, docs/HOUSING.md):
    obj = {id, prefab, loc, type, building, parent, hover}. The client builds the prefab
    named by m_PrefabNameTag."""
    ue, player = state["ue"], state["player"]
    pm = package_map(args, player.level)
    channel = world.channel_for(state, obj["id"], allocate=True)
    cls = PLACED_OBJECT_CLASS.split(".", 1)[1]
    props = pm.net_cache.props(cls, {
        "m_PrefabNameTag": obj["prefab"],
        "m_ParentUniqueID": obj.get("parent", 0),
        "m_ObjectUniqueId": obj["id"] & 0x7FFFFFFF,
        "m_MouseOverDisplay": obj.get("hover", ""),
        "m_BuildingType": obj.get("type", HOUSE_BUILDING),
        "m_BuildingUniqueId": obj.get("building", obj["id"] & 0x7FFFFFFF),
    })
    b = ue.actor_open_bunch(channel, pm.object_index(PLACED_OBJECT_CLASS), pm.max_object_index,
                            location=tuple(obj["loc"]), rotation=tuple(obj.get("rot", (0, 0, 0))),
                            properties=props)
    print(f"  <- UNREAL actor open ch={channel} PlayerPlacedObject {obj['prefab']!r}")
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
    # Everyone in the chunk opens this pawn with the same payload: encode it once.
    key = (id(pm), "open", args.pawn_class, repr(loc), repr(values))
    payload = _PROPS_CACHE.get(key)
    if payload is None:
        tmp = ue2net.UnrealSession()
        b = tmp.actor_open_bunch(channel, pm.object_index(args.pawn_class), pm.max_object_index,
                                 location=loc, extra=(0xFF, -1, 0x3F800000),
                                 properties=pm.net_cache.props(cls, values))
        payload = (b.data, b.nbits)
        if len(_PROPS_CACHE) > 512:
            _PROPS_CACHE.clear()
        _PROPS_CACHE[key] = payload
    return unreal_message(ue.build([ue.actor_open_from(channel, *payload)]))


def close_actor(state, entity_id):
    """Close this connection's channel for a world actor (it left)."""
    channel = state.get("channels", {}).pop(entity_id, None)
    if channel is None:
        return None
    ue = state["ue"]
    return unreal_message(ue.build([ue.actor_close_bunch(channel)]))


XP_PER_LEVEL = 1000            # experience from level 1 to 2 (placeholder curve below)
LEVEL_CAP = 50


def xp_for_level(level):
    """Experience needed to go from level to level + 1: grows 12% a level (placeholder)."""
    return int(round(XP_PER_LEVEL * 1.12 ** (max(1, level) - 1) / 10)) * 10


CRAFTING, DIPLOMACY = 1, 2              # spheres (0 is adventuring), as in 0x3d5 kind and 0x713
SPHERE_XP_PER_LEVEL = 1000


def sphere(player, which):
    """[level, xp] of the crafting (1) or diplomacy (2) sphere."""
    sp = player.__dict__.setdefault("spheres", {})
    return sp.setdefault(str(which), [1, 0])


def gain_sphere_xp(player, which, amount):
    """Add crafting or diplomacy XP; returns the levels reached (0x713 each)."""
    lv = sphere(player, which)
    lv[1] += amount
    out = []
    while lv[1] >= SPHERE_XP_PER_LEVEL and lv[0] < 50:
        lv[1] -= SPHERE_XP_PER_LEVEL
        lv[0] += 1
        out.append(zone_event(0x713, struct.pack("<ii", lv[0], which)))   # "Your Crafting level is now 2."
    if out and which == CRAFTING:
        import attributes                # crafting attribute points come with crafting levels
        out.append(attributes.set_pool(attributes.pool(lv[0], getattr(player, "craft_alloc", {})),
                                       attributes.CRAFTING))
        out.append(attributes.gained(attributes.CRAFTING))
    return out


def score_message(player, probe=False):
    """MsgScore (0x3de): the character sheet, level and XP bar."""
    if hasattr(player, "equipment") and hasattr(player, "stats"):
        apply_gear_stats(player)                 # armor class and attack come from the gear
    loc = player.spawned_at or (0.0, 0.0, 0.0)
    bind = getattr(player, "bind", None)
    if bind:
        loc = bind["loc"]
    return zone_event(0x3DE, vgmsg.score(probe=probe,
        bind_x=loc[0], bind_y=loc[1], bind_z=loc[2], race=player.race, gender=getattr(player, "gender", 0),
        adv_class=player.klass, adv_level=getattr(player, "mentor_level", None) or player.level_number,
        adv_exp_amount=player.xp, adv_exp_amount_next=xp_for_level(player.level_number),
        adv_exp_frac=player.xp / xp_for_level(player.level_number),
        adv_exp_debt_frac=min(1.0, getattr(player, "xp_debt", 0) / xp_for_level(player.level_number)),
        armor_class=getattr(player, "armor_class", 0), craft_level=sphere(player, CRAFTING)[0], harvest_level=1,
        harvest_class=HARVESTER_CLASS,
        dip_level=sphere(player, DIPLOMACY)[0],
        craft_exp=sphere(player, CRAFTING)[1], craft_exp_frac=sphere(player, CRAFTING)[1] / SPHERE_XP_PER_LEVEL,
        dip_exp=sphere(player, DIPLOMACY)[1], dip_exp_frac=sphere(player, DIPLOMACY)[1] / SPHERE_XP_PER_LEVEL,
        movement_mode=getattr(player, "movement_mode", 2), move_speed=1.0, craft_trade=getattr(player, "craft_trade", 0xFF),
        aa_points=getattr(player, "aa_points", 0), aa_spent=getattr(player, "aa_spent", 0),
        aa_exp=getattr(player, "aa_xp", 0), aa_exp_frac=getattr(player, "aa_xp", 0) / 1000.0,
        attack=-float(combat.auto_attack_damage(player)[0]), attack_max=-float(combat.auto_attack_damage(player)[1]),
        ranged=-25.0, spell_attack=-10.0,
        defense_input=6.0, melee_mitigation=1.0 - combat.mitigate(1000, getattr(player, "armor_class", 0)) / 1000.0,
        spell_mitigation=0.02,
        melee_evasion=0.05, spell_evasion=0.02,
        block=100 * combat.BASE_BLOCK if any(ITEM_CONTENT.item(e[1]).get("type") == "shield" for e in getattr(player, "equipment", [])) else 0.0,
        melee_crit_chance=100 * combat.crit_chance(getattr(player, "stats", {}).get("dexterity", 30)),
        melee_crit_damage=100 * (combat.CRIT_MULT - 1),
        dodge=100 * (combat.BASE_DODGE + combat.DODGE_PER_DEX * max(0, getattr(player, "stats", {}).get("dexterity", 30) - 30)),
        parry=100 * combat.BASE_PARRY if any(e[3] in (28, 36) for e in getattr(player, "equipment", [])) else 0.0,
        hp_regen_s=combat.REGEN_PER_SECOND + getattr(player, "regen_bonus", 0) / 6.0,
        endurance_regen_s=5.0, energy_regen_s=3.0))


def endurance_update(player):
    return zone_event(0x2D4, vgmsg.stat_update(vgmsg.STAT_IDS["endurance"], player.endurance,
                                               maximum=player.stats["endurance"]))


def energy_update(player):
    return zone_event(0x2D4, vgmsg.stat_update(vgmsg.STAT_IDS["energy"], int(player.energy),
                                               maximum=player.stats["energy"]))


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


_PROPS_CACHE = {}


def pawn_props(pm, cls_path, values):
    """(data, nbits) of a property update. Broadcasts send the same values to every player in
    the chunk, so the encoding is remembered for the next recipients (only the channel and the
    packet around it differ)."""
    key = (id(pm), cls_path, repr(values))
    hit = _PROPS_CACHE.get(key)
    if hit is None:
        w = ue2net.BitWriter()
        for rep_index, max_index, write in pm.net_cache.props(cls_path.split(".", 1)[1], values):
            w.serialize_int(rep_index, max_index)
            write(w)
        hit = w.packed()
        if len(_PROPS_CACHE) > 512:
            _PROPS_CACHE.clear()
        _PROPS_CACHE[key] = hit
    return hit


def pawn_update(state, args, channel, cls_path, values):
    ue, player = state["ue"], state["player"]
    data, nbits = pawn_props(package_map(args, player.level), cls_path, values)
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
    if params.get("View") is not None:
        player.yaw = world.view_yaw(params["View"])      # facing (builder !spawn uses it)
    if params.get("TimeStamp") is not None:
        state["move_ts"] = params["TimeStamp"]
    if loc is not None:
        moved = state.get("position") != loc
        state["position"] = loc
        player.live_position = loc
        if getattr(args, "on_move", None):
            args.on_move(state, loc)                   # every report: landing = no change
        if moved:
            state.pop("fly_stopped", None)
            broadcast_movement(state, args, player, loc, params.get("View"))
        elif getattr(player, "flying", False) and not state.get("fly_stopped"):
            # A flier that stops: others simulate it without gravity and would keep drifting
            # along its last velocity, so tell them it is hovering.
            state["fly_stopped"] = True
            state["move_sent"] = 0
            state["move_prev"] = (loc, time.time())
            broadcast_movement(state, args, player, loc, params.get("View"))
        if moved and not getattr(args, "quiet_packets", False):
            extra = ""
            if getattr(player, "flying", False):
                view = params.get("View") or 0
                extra = f" view pitch {((view >> 15) & 0x7FFF) * 2} yaw {(view & 0x7FFF) * 2}"
            print(f"  >>> UNREAL {name}: position {loc}{extra}")
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
# (distance, every nth update): within 4000 units every update (10 a second), within 12000
# every 3rd, beyond that every 10th (once a second).
MOVE_RATE_TIERS = ((4000.0, 1), (12000.0, 3))
MOVE_RATE_FAR = 10
CROWD_FULL_RATE = 25            # up to this many players nearby, everyone gets every update


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
    # Encoded once; queued as unreliable bunches and sent with the other players' moves in as
    # few packets as possible (world.flush_bunches, end of every server loop pass).
    data, nbits = pawn_props(package_map(args, player.level), args.pawn_class, values)
    n = state["move_count"] = state.get("move_count", 0) + 1
    # In a dense crowd every viewer gets every kth update (k grows with the number of players
    # near this one, counted on the previous update): the cost of a crowd grows with its size
    # instead of its square. The client extrapolates along the velocity in between.
    crowd = max(1, -(-state.get("near_count", 0) // CROWD_FULL_RATE))
    near = 0
    world.grid_move(w, state, loc)
    viewers = list(w.members.values()) if n % MOVE_RATE_FAR == 0 else world.near_members(w, loc)
    for s in viewers:
        if s is state or "ue" not in s:
            continue
        channel = world.channel_for(s, player.char_id)
        if channel is None:
            continue
        # Interest by distance: players far away get this player's movement less often, so
        # crowds spread over a chunk cost much less than everyone at full rate.
        other = s.get("player")
        pos = (getattr(other, "live_position", None) or s.get("position")) if other else None
        if pos is not None and (pos[0] - loc[0]) ** 2 + (pos[1] - loc[1]) ** 2 <= MOVE_RATE_TIERS[0][0] ** 2:
            near += 1
        if move_rate_skip(n, pos, loc) or (crowd > 1 and (n + id(s)) % crowd):
            continue
        world.queue_bunch(s, s["ue"].unreliable_bunch(channel, data, nbits))
    state["near_count"] = near


def move_rate_skip(n, pos, loc):
    """True when the nth movement update of something at loc should not go to a viewer at pos
    (MOVE_RATE_TIERS: far viewers get every 3rd or 10th update)."""
    if pos is None:
        return False
    d2 = (pos[0] - loc[0]) ** 2 + (pos[1] - loc[1]) ** 2
    every = next((k for limit, k in MOVE_RATE_TIERS if d2 <= limit * limit), MOVE_RATE_FAR)
    return bool(n % every)


def queue_npc_move(w, args, npc, values):
    """An NPC's movement step for everyone in its world: encoded once, queued as unreliable
    bunches (world.flush_bunches). Distant viewers get moving steps less often; a stop (no
    velocity) always goes out, so nobody sees an NPC frozen mid-stride."""
    pm = package_map(args, w.level)
    data, nbits = pawn_props(pm, npc.cls_path, values)
    vel = values.get("Velocity")
    moving = vel is not None and any(vel)
    n = npc.__dict__["move_count"] = npc.__dict__.get("move_count", 0) + 1
    loc = npc.location
    viewers = list(w.members.values()) if (not moving or n % MOVE_RATE_FAR == 0) else world.near_members(w, loc)
    for s in viewers:
        if "ue" not in s:
            continue
        channel = world.channel_for(s, npc.entity_id)
        if channel is None:
            continue
        if moving:
            other = s.get("player")
            pos = (getattr(other, "live_position", None) or s.get("position")) if other else None
            if move_rate_skip(n, pos, loc):
                continue
        world.queue_bunch(s, s["ue"].unreliable_bunch(channel, data, nbits))


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


BREATH_MAX = 60               # seconds of breath under water
HP_BASE, CON_HP = 210, 5      # maximum health at 40 Constitution, and per point above
HP_PER_LEVEL = 12             # maximum health gained per adventuring level (placeholder)
POOL_BASE, POOL_PER_POINT = 100, 2   # endurance / energy at default attributes, per point above


# Class attribute leanings (placeholders): the first attribute grows by 1 a level, the second
# by 1 every 2 levels, on top of these starting bonuses (races_classes ids).
CLASS_ATTRIBUTES = {
    28: (("strength", 8), ("constitution", 8)),     # Warrior
    4: (("constitution", 6), ("strength", 5)),      # Paladin
    20: (("strength", 6), ("constitution", 6)),     # Dread Knight
    19: (("dexterity", 8), ("strength", 4)),        # Ranger
    21: (("dexterity", 10), ("strength", 3)),       # Rogue
    15: (("dexterity", 6), ("strength", 5)),        # Monk
    2: (("dexterity", 4), ("intelligence", 4)),     # Bard
    27: (("wisdom", 5), ("dexterity", 5)),          # Disciple
    5: (("wisdom", 8), ("constitution", 4)),        # Cleric
    22: (("wisdom", 8), ("strength", 3)),           # Shaman
    7: (("wisdom", 6), ("intelligence", 4)),        # Druid
    25: (("intelligence", 10), ("wisdom", 2)),      # Sorcerer
    45: (("intelligence", 8), ("wisdom", 2)),       # Necromancer
    14: (("intelligence", 8), ("wisdom", 3)),       # Psionicist
    44: (("intelligence", 6), ("wisdom", 4)),       # Blood Mage
}


# Race attribute bonuses (placeholders; races_classes.RACES ids).
RACE_ATTRIBUTES = {
    2: {"constitution": 5, "strength": 3},          # Dwarf
    3: {"intelligence": 4, "dexterity": 3},         # Dark Elf
    4: {"wisdom": 4, "intelligence": 3},            # High Elf
    5: {"dexterity": 5, "wisdom": 2},               # Wood Elf
    6: {"intelligence": 5, "dexterity": 2},         # Gnome
    7: {"dexterity": 4, "constitution": 3},         # Goblin
    8: {"dexterity": 2, "intelligence": 2, "wisdom": 2},   # Half Elf
    9: {"strength": 6, "constitution": 4},          # Lesser Giant
    10: {"dexterity": 6},                           # Halfling
    11: {"strength": 6, "constitution": 2},         # Orc
    12: {"strength": 2, "wisdom": 2, "dexterity": 2},      # Kojani
    13: {"intelligence": 2, "wisdom": 2, "dexterity": 2},  # Qaliathari
    14: {"strength": 2, "constitution": 2, "wisdom": 2},   # Thestran
    15: {"intelligence": 3, "constitution": 3},     # Mordebi
    17: {"dexterity": 5, "wisdom": 2},              # Raki
    18: {"strength": 4, "dexterity": 3},            # Vulmane
    20: {"constitution": 5, "strength": 2},         # Varanthari
    21: {"strength": 5, "constitution": 2},         # Varanjar
    22: {"strength": 4, "constitution": 4},         # Kurashasa
}


def aa_abilities(player):
    """The alternate advancement abilities this character can see (content/aa.json)."""
    import aa
    import races_classes
    return aa.abilities(ITEM_CONTENT.aa, races_classes.class_name(getattr(player, "klass", 0)))


def aa_bonus(player):
    """{attribute: bonus} from trained alternate advancement ranks."""
    import aa
    ranks = getattr(player, "aa_ranks", None)
    return aa.stat_bonus(aa_abilities(player), ranks) if ranks else {}


def innate_bonus(player):
    """{attribute: bonus} from the race, class and level (counted as the character's base)."""
    out = dict(RACE_ATTRIBUTES.get(getattr(player, "race", None), {}))
    level = getattr(player, "level_number", 1)
    for n, (stat, start) in enumerate(CLASS_ATTRIBUTES.get(getattr(player, "klass", None), ())):
        out[stat] = out.get(stat, 0) + start + (level - 1) // (1 + n)
    return out


def gear_bonus(player):
    """{attribute: total} from the items.json "stats" of everything equipped."""
    out = {}
    for e in player.equipment:
        for k, v in (ITEM_CONTENT.item(e[1]).get("stats") or {}).items():
            if k in vgmsg.STAT_IDS:
                out[k] = out.get(k, 0) + int(v)
    return out


def gear_mod_total(player, mod):
    return sum(int((ITEM_CONTENT.item(e[1]).get("mods") or {}).get(mod, 0)) for e in player.equipment)


def apply_gear_stats(player):
    """Move player.stats by the change in gear bonuses since the last call (idempotent);
    returns the attributes that changed. Also sets the gear's armor class (item armor +
    "Armor Class" mods) and health regeneration bonus used by combat."""
    player.armor_class = (sum(int(ITEM_CONTENT.item(e[1]).get("armor", 0)) for e in player.equipment)
                          + gear_mod_total(player, "Armor Class"))
    player.regen_bonus = gear_mod_total(player, "Health Regeneration")
    changed = []
    for attr, fn in (("innate_bonus", innate_bonus), ("gear_bonus", gear_bonus), ("aa_bonus", aa_bonus),
                     ("alloc_bonus", lambda p: dict(getattr(p, "attr_alloc", None) or {}))):
        new, old = fn(player), player.__dict__.get(attr, {})
        for k in set(new) | set(old):
            delta = new.get(k, 0) - old.get(k, 0)
            if delta:
                player.stats[k] = player.stats.get(k, 0) + delta
                if k not in changed:
                    changed.append(k)
        setattr(player, attr, new)
    # Constitution sets maximum health (placeholder: CON_HP per point above the default).
    # Pools from attributes (placeholders): endurance from Vitality, energy from Intelligence
    # and Wisdom, POOL_PER_POINT per point above the defaults.
    for pool, from_stats in (("endurance", ("vitality",)), ("energy", ("intelligence", "wisdom"))):
        if pool in player.stats:
            extra = sum(player.stats.get(k, DEFAULT_STATS[k]) - DEFAULT_STATS[k] for k in from_stats)
            player.stats[pool] = POOL_BASE + POOL_PER_POINT * extra
            cur = pool if pool == "energy" else "endurance"
            if hasattr(player, cur):
                setattr(player, cur, min(getattr(player, cur), player.stats[pool]))
    level = getattr(player, "mentor_level", None) or getattr(player, "level_number", 1)
    hp = (HP_BASE + (player.stats.get("constitution", 40) - DEFAULT_STATS["constitution"]) * CON_HP
          + (level - 1) * HP_PER_LEVEL)
    if "hit_points" in player.stats and hp != player.stats["hit_points"]:
        player.stats["hit_points"] = hp
        if hasattr(player, "health"):
            player.health = min(player.health, hp)
    return changed


def stat_base(player, name):
    """The stat without gear and buff bonuses (the character window shows the rest in green)."""
    buffs = sum(e.get("bonus", 0) for e in getattr(player, "effects", [])
                if e.get("kind") == "buff" and e.get("stat") == name)
    return player.stats.get(name, 0) - player.__dict__.get("gear_bonus", {}).get(name, 0) - buffs


def attribute_update(player, name):
    return zone_event(0x2D4, vgmsg.stat_update(vgmsg.STAT_IDS[name], player.stats[name],
                                               base=stat_base(player, name)))


def breath_update(breath):
    return zone_event(0x2D4, vgmsg.stat_update(vgmsg.STAT_IDS["breath"], breath, maximum=BREATH_MAX))


def stat_messages(player):
    """Zone events that fill the character window and HUD bars.

    Stats are created with MsgStatList (0x2d5) and then updated with
    MsgStatUpdate (0x2d4): the attribute UI vars (PCAdvStrength...) are only set
    on the update path (FUN_00576c90 -> FUN_00573070); HP/End/Energy are set on
    creation (FUN_005763b0)."""
    apply_gear_stats(player)
    if not getattr(player, "pools_filled", False):
        # Logging in starts with full pools; the maximums are only known now (attributes,
        # gear and level), after the Player was built with the defaults.
        player.pools_filled = True
        player.health = player.stats["hit_points"]
        player.endurance = player.stats["endurance"]
        player.energy = player.stats["energy"]
    recs = []
    for name, value in player.stats.items():
        kind = 1 if name in vgmsg.ATTRIBUTES else 0
        recs.append(vgmsg.stat_info(vgmsg.STAT_IDS[name], value, kind=kind, maximum=value))
    for sid, value, subtype in player.skills:
        recs.append(vgmsg.stat_info(sid, value, kind=2, subtype=subtype, maximum=SKILL_CAP))
    recs.append(vgmsg.stat_info(vgmsg.STAT_IDS["breath"], BREATH_MAX, kind=5, maximum=BREATH_MAX))
    import attributes
    craft_alloc = getattr(player, "craft_alloc", None) or {}
    recs += attributes.craft_records(craft_alloc)
    recs += attributes.craft_skill_records(sphere(player, CRAFTING)[0], getattr(player, "skill_dirs", None))
    recs += harvest_records(player)
    out = [zone_event(0x2D5, vgmsg.stat_list(recs))]
    for name in vgmsg.ATTRIBUTES:
        out.append(attribute_update(player, name))
    for name in attributes.CRAFT_STATS:
        out.append(attributes.craft_update(name, craft_alloc))
    out += harvest_updates(player)
    out.append(skill_pool_caps(player))
    return out


# The character window's Harvesting tab (verified live 2026-10-15) reads category-3 stat
# records only: the harvesting skills (Mining 0x0f, Quarrying 0x32, Lumberjacking 0x4b, Reaping
# 0x59, Skinning 0x76, Gathering 0x79) and overall Harvesting 0xc4. "Skill N" (and the bar) is
# 0xc4's base value, read when MsgScore arrives; the class name is MsgScore field 23 (8 =
# Harvester). The primary / secondary rows show the skills 0x2e0 {i32 primary, i32 secondary}
# names, filled by the following 0x2d4 updates (FUN_00573070).
HARVEST_CATEGORY, HARVESTING_STAT, HARVESTER_CLASS = 3, 0xC4, 8
HARVEST_INSTANCE = 0x1000          # category-3 copies need instance ids of their own
HARVEST_SKILL_IDS = (0x0F, 0x32, 0x4B, 0x59, 0x76, 0x79)
HARVEST_PRIMARY_SECONDARY = 0x2E0


def harvest_skills(player):
    """{stat id: value} of the harvesting skills the player has, plus overall Harvesting (the
    best of them)."""
    have = {sid: v for sid, v, _sub in getattr(player, "skills", []) if sid in HARVEST_SKILL_IDS}
    have[HARVESTING_STAT] = max(have.values(), default=0)
    return have


def harvest_records(player):
    return [vgmsg.stat_info(sid, v, category=HARVEST_CATEGORY, kind=2, maximum=SKILL_CAP,
                            raw={1: HARVEST_INSTANCE + sid})
            for sid, v in harvest_skills(player).items()]


def harvest_updates(player):
    """0x2e0 (best two skills as primary / secondary), then a 0x2d4 per harvesting stat."""
    have = harvest_skills(player)
    ranked = sorted((sid for sid in have if sid != HARVESTING_STAT), key=lambda s: -have[s])
    primary, secondary = (ranked + [0, 0])[:2]
    out = [zone_event(HARVEST_PRIMARY_SECONDARY, struct.pack("<ii", primary, secondary))]
    for sid, v in have.items():
        # field 0 finds the stat by instance id; field 12 is the stat id (stat +0x5c) it keeps
        out.append(zone_event(0x2D4, vgmsg.stat_update(HARVEST_INSTANCE + sid, v, category=HARVEST_CATEGORY,
                                                       maximum=SKILL_CAP, raw={12: sid})))
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
    (0x5b, 1, 0x15),    # Fishing
]
SKILL_CAP = 50

# Skills tab group headers (verified live 2026-10-15): each header shows its pool's maximum
# minus the skill points spent in the group (PCPoolAdv<Group> = max - spent, FUN_0056b8xx);
# without 0x2d6 the maximum is 0 and the headers read -85, -90, ... 0x2d6 MsgSkillPoolCaps
# {12 x i32} (FUN_0056e500): 0 weapon types, 1 spell schools, 2 combat, 3 perception, 4 general,
# 5 weapon specialization; for the chosen crafting trade 6 finishing, 7 specializations,
# 8 refining, 9 general refining; 10-11 harvesting (inferred). The maximum here is SKILL_CAP for
# every skill in the group (placeholder), so a header shows how much the group can still grow.
SKILL_POOL_CAPS = 0x2D6
POOL_OF_SUBTYPE = {0: 0, 9: 1, 4: 2, 7: 3, 0x1E: 4, 2: 5}
# crafting skill subtypes per trade: (general refining, refining, specialization, finishing)
TRADE_SUBTYPES = {0: (0x05, 0x0A, 0x06, 0x0B), 2: (0x18, 0x0E, 0x19, 0x0F), 4: (0x1C, 0x12, 0x1D, 0x13)}


def skill_pool_caps(player):
    caps = [0] * 12
    for _sid, _value, subtype in getattr(player, "skills", []):
        pool = POOL_OF_SUBTYPE.get(subtype)
        if pool is not None:
            caps[pool] += SKILL_CAP
    import attributes
    general, refining, special, finishing = TRADE_SUBTYPES.get(getattr(player, "craft_trade", 0xFF), (None,) * 4)
    for _sid, sub in attributes.CRAFT_SKILLS:
        for field, want in ((9, general), (8, refining), (7, special), (6, finishing)):
            if sub == want:
                caps[field] += SKILL_CAP
    return zone_event(SKILL_POOL_CAPS, struct.pack("<12i", *caps))

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


ITEM_TYPE_IDS = {"misc": 3, "shield": 0, "weapon": 1, "armor": 4, "ranged": 9, "jewelry": 13,   # 10 is diplomacy jewelry (FUN_00d01550 level type 2)
                 "container": 11, "ammo": 20, "component": 7, "resource": 22,   # "Crafting Component" / "Crafting Resource"
                 "harvest_tool": 16, "fishing": 26}


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


def template_id(name):
    """A stable per-item-name template id (item field 1); handles (field 71) stay unique.
    items.json "template_id" sets a real client template id (the client switches on some,
    e.g. 1454022 opens the clear-experience-debt dialog)."""
    fixed = ITEM_CONTENT.item(name).get("template_id")
    if fixed:
        return fixed
    return 0x2000000 + (zlib.crc32(name.encode()) & 0xFFFFF)


# Item flags (wire field 102, FUN_006ab640 prints them in the tooltip): items.json "flags".
ITEM_FLAGS = {"no_trade": 0x01, "unique": 0x02, "no_rent": 0x04, "soulbound": 0x08,
              "no_drop_on_equip": 0x10, "quest": 0x20, "no_sell": 0x40, "bind_on_equip": 0x80}


def item_flags(name, bound=False):
    bits = 0
    for f in ITEM_CONTENT.item(name).get("flags", ()):
        bits |= ITEM_FLAGS[f]
    return bits | (ITEM_FLAGS["soulbound"] if bound else 0)


def item_restriction(player, item, action):
    """Why an item can't be traded / mailed / sold / put on the market / banked
    (action), or None. Soulbound means bound to this character (player.bound)."""
    bits = item_flags(item[1], item[0] in getattr(player, "bound", ()))
    if action in ("trade", "mail", "market") and bits & (ITEM_FLAGS["no_trade"] | ITEM_FLAGS["soulbound"] | ITEM_FLAGS["quest"]):
        return f"{item[1]} can't be given to anyone else."
    if action == "sell" and bits & (ITEM_FLAGS["no_sell"] | ITEM_FLAGS["quest"]):
        return f"The merchant won't buy {item[1]}."
    if action == "bank" and bits & ITEM_FLAGS["quest"]:
        # Quest and work-order items stay in the bags (work-order supplies parked in the bank
        # could be handed out again after abandoning the order).
        return f"{item[1]} can't be stored in the bank."
    return None


ITEM_LINK = re.compile(r"<item=(-?\d+)[^>]*>(.*?)</link>", re.S)


def item_link_name(text):
    """The item an item link names (`<item=template:...>Name</link>`, written by the client,
    FUN_00cde960): by its name, else by the template id; None if neither is known."""
    m = ITEM_LINK.search(text)
    if not m:
        return None
    tid, name = int(m.group(1)), m.group(2)
    if ITEM_CONTENT.item(name) or template_id(name) == tid:
        return name
    return next((n for n in ITEM_CONTENT.items if template_id(n) == tid), None)


def item_equip_fields(name, durability=100, bound=False):
    """inventory_item keyword arguments from content/items.json: equip slots and
    the tooltip/usability fields (see docs/INVENTORY.md, item field table)."""
    tpl = ITEM_CONTENT.item(name)
    extra = {94: 1, 100: 255, 106: durability, 99: grouploot_rarity_wire(tpl.get("rarity")), 76: tpl.get("level", 1),
             1: template_id(name),           # field 1: the template id (assembly matches ingredients on it)
             102: item_flags(name, bound)}
    # Field 74 = item type; 0 would be "Shield", 3 is a plain item.
    extra[74] = ITEM_TYPE_IDS[tpl.get("type", "misc")]
    if tpl.get("type", "misc") in ("component", "resource"):
        extra[106] = -1          # no durability line ("Required Level: N Crafting" stays)
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
    if "use" in tpl:
        # Field 107 (+0x5e4): the item's reuse-timer group; 0x1e5 starts a timer on every item of
        # the group (FUN_0050f910).
        extra[107] = cooldown_group(name)
    out_mods = vgmsg.item_mods(tpl.get("stats"), tpl.get("mods"))
    if tpl.get("bag"):
        extra[14] = tpl["bag"]           # capacity: the client makes InventoryContainerID_<handle>
    out = {"raw": extra}
    if out_mods:
        out["mods"] = out_mods
    if tpl.get("bag"):
        return dict(out, default_slot=BAG_EQUIP_SLOTS[0], allowed_slots=BAG_EQUIP_SLOTS)
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
    import reactions
    chains = getattr(player, "chains", [])
    out = [zone_event(0x21B)]
    for handle, ability_id, name, icon, desc, refresh in player.abilities:
        general = bool((ITEM_CONTENT.abilities.get(name) or {}).get("general"))
        import forms as forms_mod
        raw = dict({33: 1} if general else {},
                   **forms_mod.form_fields(forms_mod.allowed_forms(getattr(player, "forms", []), name)))
        out.append(zone_event(0x215, vgmsg.ability_info(handle, ability_id, name, icon, desc,
                                                       refresh=refresh, raw=raw or None,
                                                       flags=reactions.flags(chains, ability_id),
                                                       counter=ability_id in getattr(player, "counters", ()),
                                                       rescue=ability_id in getattr(player, "rescues", ()))))
    import songs
    for handle, aid, name, spec in getattr(player, "song_parts", []):
        out.append(songs.part_info(handle, aid, name, spec))
    out.append(zone_event(0x21D))
    out.append(reactions.forget_all())
    out += [reactions.define(c) for c in chains]
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


def grouploot_rarity_wire(name):
    import grouploot
    return grouploot.rarity_wire(name)


_obstacles = {}


_LOADING = object()


def _load_obstacles(level):
    try:
        import obstacles
        _obstacles[level] = obstacles.obstacles(level)
    except Exception as e:                           # missing or unreadable files
        print(f"  obstacles for {level} unavailable: {e}")
        _obstacles[level] = None


def npc_blocked(level, x, y, z):
    """True when (x, y, z) is inside one of the chunk's obstacles (obstacles.py; no obstacles if
    the client files can't be read). The first call for a chunk starts building its obstacles on
    a background thread (a city map takes most of a second, which stalled every player when it
    ran in the server loop: a 2 s ping in a 50-bot run in Bordinar's Cleft); until it is done
    nothing counts as blocked."""
    obs = _obstacles.get(level)
    if obs is None and level not in _obstacles:
        import threading
        _obstacles[level] = _LOADING
        threading.Thread(target=_load_obstacles, args=(level,), daemon=True).start()
        return False
    return obs is not None and obs is not _LOADING and obstacles_blocked(obs, x, y, z)


def obstacles_blocked(obs, x, y, z):
    import obstacles
    return obstacles.blocked(obs, x, y, z)


# Moving items in the bags (docs/INVENTORY.md "Moving and destroying"): client 0x92
# {i32 handle, i32 container (-1 = the main bags), i32 slot} when an item is dragged to a
# slot; the server answers 0x1ac {i32 handle, i32 container, i32 slot, i32 0}, which moves
# it. 0x89 {i32 handle} destroys an item (after the client's "Delete: <item>" popup).
MOVE_ITEM, DESTROY_ITEM = 0x92, 0x89
# Unstack (the "inventory_unstack_ok" popup, FUN_0068e8e0 -> FUN_004fc8f0): 0x97 MsgTwoInts
# {i32 handle, i32 count}; the client checks count > 0 itself.
UNSTACK = 0x97
MAX_STACK = 99


def item_moved(handle, slot, container=-1):
    if container == -1:
        container, slot = vgmsg.split_slot(slot)
    return zone_event(0x1AC, struct.pack("<iiii", handle, container, slot, 0))


# Bags (docs/INVENTORY.md "Bags"): an item whose items.json template has "bag": N is sent with
# field 14 = N; the client then makes the gamevar list InventoryContainerID_<handle>. A bag is
# equipped into one of the main bar's three bag slots (CONTAINER1-3); clicking it there, or the
# bags button, opens its window (FUN_00500750 opens every equipped bag). Items inside use
# field 15 = the bag's handle and field 16 = the slot; the server keeps that as one slot number
# (vgmsg.bag_slot). Only equipped bags hold items.
BAG_EQUIP_SLOTS = [vgmsg.EQUIP_SLOTS[s] for s in ("CONTAINER1", "CONTAINER2", "CONTAINER3")]


def bag_capacity(name):
    return ITEM_CONTENT.item(name).get("bag", 0)


def bag_items(items, handle):
    return [i for i in items if vgmsg.split_slot(i[4])[0] == handle]


# Item operation results: 0x1e4 {i32 code} (FUN_004fa120) prints the client's own line:
# 0 "Failed to add item.  You already have one of that Unique item!", 1 "Only adding one item as
# that item is Unique!", 2 / 11 "There is not enough space in your inventory for that item.",
# 9 "Destination container must be equipped to hold items.", 12 "You already have an item in that
# slot.", 13-19 grafts, 23-27 vehicle names, 28 "You cannot equip that item.", 29 "You cannot wield
# that item in that location.", 30-32 stacking, 33 "You cannot put any more of those there.",
# 34 "You have already reached the stack limit for that stack.", 35 "There aren't that many
# stacked items there." Item functions return such a code (int) or a text line (str) on failure.
ITEM_RESULT = 0x1E4
NO_ROOM_FOR_ITEM, CANT_EQUIP = 2, 28


def item_error(result):
    """The message for an item function's failure: the client's line for a code, else text."""
    import login_stub
    if isinstance(result, int):
        return zone_event(ITEM_RESULT, struct.pack("<i", result))
    return login_stub.build_system_text(result, login_stub.SYSTEM_TEXT_ERROR)


def move_target(items, equipment, handle, container, slot):
    """Check a drag to (container, slot); returns the stored slot or an error string."""
    item = next((i for i in items if i[0] == handle), None)
    if item is None:
        return "That item is not in your inventory."
    if container == -1:
        return slot if 0 <= slot < BAG_SLOTS else "You can't put that there."
    bag = next((e for e in equipment if e[0] == container), None)
    if bag is None or not bag_capacity(bag[1]):
        return "You can't put that there."
    if not 0 <= slot < bag_capacity(bag[1]):
        return "You can't put that there."
    target = vgmsg.bag_slot(container, slot)
    other = next((i for i in items if i[4] == target and i[0] != handle), None)
    if bag_capacity(item[1]) or (other is not None and bag_capacity(other[1])
                                 and vgmsg.split_slot(item[4])[0] != -1):
        return "You can't put a bag inside a bag."
    return target


def move_item(items, handle, slot, max_stack=MAX_STACK):
    """Move a bag item to a slot: into an empty slot, swap with the item there, or merge
    into a stack of the same item. Updates items ([(id, name, icon, qty, slot)]) and returns
    the messages, or None if the item isn't there."""
    item = next((i for i in items if i[0] == handle), None)
    if item is None or item[4] == slot:
        return None
    other = next((i for i in items if i[4] == slot and i[0] != handle), None)
    out = []
    if other is not None and other[1] == item[1] and other[3] < max_stack:
        moved = min(item[3], max_stack - other[3])
        items[items.index(other)] = other[:3] + (other[3] + moved, other[4])
        out.append(zone_event(0x1AE, struct.pack("<ii", other[0], other[3] + moved)))
        if moved == item[3]:
            items.remove(item)
            out.append(zone_event(0x1A5, struct.pack("<iB", item[0], 0)))
        else:
            items[items.index(item)] = item[:3] + (item[3] - moved, item[4])
            out.append(zone_event(0x1AE, struct.pack("<ii", item[0], item[3] - moved)))
        return out
    if other is not None:
        items[items.index(other)] = other[:4] + (item[4],)
        out.append(item_moved(other[0], item[4]))
    items[items.index(item)] = item[:4] + (slot,)
    out.append(item_moved(handle, slot))
    return out


def book_recipes(args, player):
    """The recipes in the player's book: no work-order recipes except the active work
    order's, no trainer recipes the player hasn't bought."""
    wo = args.content.workorders.get(getattr(player, "work_order", None) or "", {})
    out = []
    for key, r in args.content.recipes.items():
        if r.get("work_order") and key != wo.get("recipe"):
            continue
        if "trainer_cost" in r and key not in getattr(player, "known_recipes", []):
            continue
        out.append(r)
    return out


def inventory_messages(player):
    """0x195 resets the inventory UI and creates the 50-slot main grid
    (FUN_00513170; field 0 = InventorySpaceAvailable), then one 0x197 per item,
    then 0x1bb sets the coin total without a chat message (0x1aa prints one)."""
    main = [i for i in player.items if vgmsg.split_slot(i[4])[0] == -1]
    out = [zone_event(0x195, struct.pack("<iiii", 50 - len(main), 0, 0, 0))]
    dur = getattr(player, "durability", {})
    bound = getattr(player, "bound", set())
    for item_id, name, icon, qty, slot in main:
        out.append(zone_event(0x197, vgmsg.inventory_item(item_id, name, slot, item_icon(name, icon), qty,
                                                          **item_equip_fields(name, dur.get(str(item_id), 100),
                                                                              item_id in bound))))
    # Equipped items: create in the bag, then 0x1a7 (FUN_0050feb0: i32 item id,
    # u8 lookup kind, u8 equip slot) moves them to the paper doll.
    for n, (item_id, name, icon, equip_slot) in enumerate(player.equipment):
        out.append(zone_event(0x197, vgmsg.inventory_item(item_id, name, 49 - n, item_icon(name, icon),
                                                          **item_equip_fields(name, dur.get(str(item_id), 100),
                                                                              item_id in bound))))
        out.append(zone_event(0x1A7, struct.pack("<iBB", item_id, 0, equip_slot)))
    # Items inside the equipped bags, now that their containers exist.
    for item_id, name, icon, qty, slot in [i for i in player.items if i not in main]:
        out.append(zone_event(0x197, vgmsg.inventory_item(item_id, name, slot, item_icon(name, icon), qty,
                                                          **item_equip_fields(name, dur.get(str(item_id), 100),
                                                                              item_id in bound))))
    out.append(zone_event(0x1BB, struct.pack("<q", player.coins)))
    return out


class Player:
    """One character in the zone: who it is and where it should appear. Built by
    the world server on Play and claimed by the zone connection with the same
    session key (see login_stub.py)."""

    @property
    def alive(self):
        return self.health > 0

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


MOUNT_PACKAGE, MOUNT_SLOT, BARDING_SLOT = 500, 39, 45
MOUNT_GROUND, MOUNT_FLYING = 1, 3         # m_MountType (0 none, 2 aquatic)


def item_cooldown(group, remaining, seconds):
    """0x1e5 {i64 seconds remaining, i32 group, i32 seconds}: the reuse timer of every item whose
    field 107 is group (FUN_0050f910)."""
    return zone_event(0x1E5, struct.pack("<qii", int(remaining), group, int(seconds)))


def cooldown_group(name):
    """Items share a reuse timer when they name the same "cooldown_group"; else one per template."""
    return ITEM_CONTENT.item(name).get("cooldown_group") or template_id(name)


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
        if getattr(player, "barding", None) is not None:
            # (500, barding index, slot 45 MOUNTBARDING): armor on a modular mount (FUN_00bc46a0).
            gear.append((MOUNT_PACKAGE, player.barding, BARDING_SLOT))
    return gear + [(-1, -1, -1)] * (min(slots, len(gear) + 8) - len(gear))


BAG_SLOTS = 50


def split_stack(player, handle, count):
    """Take count off a stack into a new item in the first free bag slot. Returns the
    messages, or an error string."""
    item = next((i for i in player.items if i[0] == handle), None)
    if item is None:
        return "That item is not in your inventory."
    if not 0 < count < item[3]:
        return f"You can only unstack between 1 and {item[3] - 1} of those."
    slot = free_bag_slot(player)
    if slot is None:
        return NO_ROOM_FOR_ITEM
    new_id = new_item_id(player)
    player.items[player.items.index(item)] = item[:3] + (item[3] - count, item[4])
    player.items.append((new_id, item[1], item[2], count, slot))
    return [zone_event(0x1AE, struct.pack("<ii", handle, item[3] - count)),
            zone_event(0x197, vgmsg.inventory_item(new_id, item[1], slot, item[2], count,
                                                   **item_equip_fields(item[1])))]


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
    if bag_items(player.items, handle):
        return "You need to empty that bag first."
    slot = free_bag_slot(player)
    if slot is None:
        return NO_ROOM_FOR_ITEM
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
    if "slot" not in tpl and not tpl.get("bag"):
        return CANT_EQUIP
    if tpl.get("bag"):
        # The first empty bag slot on the main bar (else swap the first bag).
        used = {e[3] for e in player.equipment}
        slot = next((s for s in BAG_EQUIP_SLOTS if s not in used), BAG_EQUIP_SLOTS[0])
        if vgmsg.split_slot(item[4])[0] != -1:
            return "You can't equip a bag that is inside a bag."
    else:
        slot = vgmsg.EQUIP_SLOTS[tpl["slot"]]
    hands = {vgmsg.EQUIP_SLOTS[s] for s in ("PRIMARYHAND", "SECONDARYHAND", "TWOHANDS")}
    blocked = {slot}
    if slot == vgmsg.EQUIP_SLOTS["TWOHANDS"]:
        blocked |= hands
    elif slot in hands:
        blocked.add(vgmsg.EQUIP_SLOTS["TWOHANDS"])
    msgs = []
    displaced = [e for e in player.equipment if e[3] in blocked]
    if any(bag_items(player.items, e[0]) for e in displaced):
        return "You need to empty that bag first."
    split = item[3] > 1
    # Equipping from a stack keeps the rest in the bag, so every displaced piece
    # needs a free slot; otherwise the first one takes the equipped item's slot.
    main = [i for i in player.items if vgmsg.split_slot(i[4])[0] == -1]
    if len(main) - (0 if split else 1) + len(displaced) > BAG_SLOTS:
        return NO_ROOM_FOR_ITEM
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
    if "bind_on_equip" in tpl.get("flags", ()) and item[0] not in getattr(player, "bound", set()):
        player.bound = set(getattr(player, "bound", set())) | {item[0]}
        player.bound_changed = True
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
        "m_Gender": getattr(player, "gender", 0),   # 0 male, 1 female (create request raw +6)
        # EntityTypes 0x20 = a player: the client only takes a pawn with 0x20 or 0x1000 as
        # a defensive target (FUN_004cfb90: /targetself, F1, clicking a groupmate).
        "EntityTypes": 0x20,
        "Health": 100,
        "m_PlayerDisplayName": player.name,
        # The level on the defensive target panel's shield and /con (mentoring lowers it).
        "m_GameplayLevel": getattr(player, "mentor_level", None) or getattr(player, "level_number", 1),
        **getattr(player, "title_values", {}),
        # Guild tag over the head (name from zone event 0x40). m_bIsAfk = 1 made the
        # pawn disappear on every client (live test), so AFK/LFG stay in /who only.
        "m_GuildId": getattr(player, "guild_id", 0),
        # /hidehood, /hidehelm, /hidecloak, /setwearpreference, /setwieldpreference (saved).
        **getattr(player, "pawn_prefs", {}),
    }
    if getattr(player, "movement_mode", 2) == 1:
        values["bIsWalking"] = True             # /walk
    if getattr(player, "flying", False):
        values["bSimulateGravity"] = False      # a flier, for players who arrive while it flies
        values["Physics"] = 4
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


def client_goto_state(state, args, new_state, label=None):
    """RPC PlayerController.ClientGotoState(name NewState, name NewLabel) on the PC channel."""
    ue, player = state["ue"], state["player"]
    pm = package_map(args, player.level)
    nc = pm.net_cache
    pc_cls = args.spawn_class.split(".", 1)[1]
    cache = nc.class_cache(pc_cls)
    w = ue2net.BitWriter()
    w.serialize_int(nc.field(pc_cls, "ClientGotoState").index, cache["max"])
    for name in (new_state, label):
        if name:
            w.bit(1)
            index, count = nc.name_index(name)
            w.serialize_int(index, count + 1)
        else:
            w.bit(0)
    data, nbits = w.packed()
    return unreal_message(ue.build([ue.actor_bunch(PC_CHANNEL, data, nbits)]))


def client_adjust_position(state, args, location, physics, new_state=None, velocity=(0.0, 0.0, 0.0)):
    """RPC PlayerController.ClientAdjustPosition(TimeStamp, NewState, newPhysics, NewLocX..Z,
    NewVelX..Z, NewBase): UE2's correction of the client's own movement, which also sets the
    pawn's physics (and controller state). TimeStamp = the newest ServerMove TimeStamp, since the
    client ignores corrections older than its last acknowledged move."""
    import struct as _s
    ue, player = state["ue"], state["player"]
    pm = package_map(args, player.level)
    nc = pm.net_cache
    pc_cls = args.spawn_class.split(".", 1)[1]
    cache = nc.class_cache(pc_cls)
    w = ue2net.BitWriter()
    w.serialize_int(nc.field(pc_cls, "ClientAdjustPosition").index, cache["max"])

    def flt(v):
        w.bit(1)
        w.bits(_s.unpack("<I", _s.pack("<f", float(v)))[0], 32)
    flt(state.get("move_ts", 0.0))
    if new_state:
        w.bit(1)
        index, count = nc.name_index(new_state)
        w.serialize_int(index, count + 1)
    else:
        w.bit(0)
    # newPhysics is an EPhysics byte: an enum byte goes in ceil(log2(count)) bits, not 8.
    import netcache as _nc
    extra = next(p[3] for p in nc.field(pc_cls, "ClientAdjustPosition").params if p[0] == "newPhysics")
    count = _nc.param_enum_size(nc, args.spawn_class.split(".", 1)[0], extra)
    w.bit(1)
    w.bits(physics, max(1, (count - 1).bit_length()) if count else 8)
    for v in tuple(location) + tuple(velocity):
        flt(v)
    w.bit(0)                                           # NewBase: none
    data, nbits = w.packed()
    return unreal_message(ue.build([ue.actor_bunch(PC_CHANNEL, data, nbits)]))


def pawn_controller_bunch(ue, args, player):
    """Pawn.Controller = the PlayerController (replicated to the owner in UE2); without it
    the client's own pawn has no controller and does not move."""
    pm = package_map(args, player.level)
    nc = pm.net_cache
    cls = args.pawn_class.split(".", 1)[1]
    cache = nc.class_cache(cls)
    w = ue2net.BitWriter()
    w.serialize_int(nc.field(cls, "Controller").index, cache["max"])
    w.bit(1)                                           # actor, by channel
    w.serialize_int(PC_CHANNEL, ue2net.MAX_CHANNELS)
    data, nbits = w.packed()
    return ue.actor_bunch(PAWN_CHANNEL, data, nbits)


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
        if getattr(args, "pawn_role", None):
            # The owner's pawn: ROLE_AutonomousProxy (3) on the client, Authority (4) remote.
            values["Role"], values["RemoteRole"] = args.pawn_role
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
    if pawn_cls and not getattr(args, "pawn_role", None):     # GivePawn sets Pawn itself
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
        if getattr(args, "pawn_role", None):
            # GivePawn(Pawn NewPawn): sets NewPawn.Controller = self and calls ClientRestart()
            # (Engine.u PlayerController); ClientRestart alone leaves Pawn.Controller empty.
            w.serialize_int(nc.field(pc_cls, "GivePawn").index, cache["max"])
            w.bit(1)                                   # parameter present
            w.bit(1)                                   # actor, by channel
            w.serialize_int(PAWN_CHANNEL, ue2net.MAX_CHANNELS)
        else:
            w.serialize_int(nc.field(pc_cls, "ClientRestart").index, cache["max"])
        data, nbits = w.packed()
        out.append(ue.actor_bunch(PC_CHANNEL, data, nbits))
        print(f"  <- UNREAL RPC {'GivePawn' if getattr(args, 'pawn_role', None) else 'ClientRestart'} on ch={PC_CHANNEL}")
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
