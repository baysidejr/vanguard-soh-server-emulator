"""Minimal Vanguard login-server stub: logs every UDP packet and answers the
UdpLibrary connect handshake so the client sends its PacketLoginRequest.

Formats come from static analysis of bin/VGClient.exe (see function addresses
in comments). Run:  python login_stub.py [--port 10101]
"""
import argparse
import json
import math
import os
import random
import select
import socket
import struct
import time
import traceback
import zlib

import races_classes
import ue2net
import vgmsg
import class_abilities
import chat
import combat
import group
import trade
import quest
import harvest
import craft
import trainer
import faction
import workorder
import mail
import bank
import social
import effects
import guild
import brotherhood
import diplomacy
import content
import merchant
import world
import zone

# Connect request built in UdpConnection::GiveTime (FUN_00c02830):
#   00 01 | u32be protocol(3) | u32be connectCode | u32be maxRawPacketSize | cstring
# Connect confirm parsed in UdpConnection::ProcessCookedPacket case 2 (FUN_00c01e70):
#   00 02 | u32be connectCode | u32be encryptCode | u8 crcBytes |
#   u8 encryptMethod1 | u8 encryptMethod2 | u32be maxRawPacketSize | u32be protocol
PROTOCOL_VERSION = 3
WORLD_NAME = "Stub World"
MAX_RAW_PACKET = 1460

# Cooked packet types handled by FUN_00c01e70 (byte after the leading 00).
PACKET_NAMES = {
    0x01: "Connect", 0x02: "Confirm", 0x03: "Multi", 0x05: "Terminate", 0x06: "KeepAlive",
    0x07: "ClockSync", 0x08: "ClockReflect",
    0x09: "Reliable1", 0x0A: "Reliable2", 0x0B: "Reliable3", 0x0C: "Reliable4",
    0x0D: "Fragment1", 0x0E: "Fragment2", 0x0F: "Fragment3", 0x10: "Fragment4",
    0x11: "Ack1", 0x12: "Ack2", 0x13: "Ack3", 0x14: "Ack4",
    0x15: "AckAll1", 0x16: "AckAll2", 0x17: "AckAll3", 0x18: "AckAll4",
    0x19: "Group", 0x1A: "Ordered", 0x1B: "Ordered2", 0x1D: "KeepAlive",
}


# UdpLibrary disconnect reasons, in the order of the client's name table.
DISCONNECT_REASONS = {
    0: "None", 1: "IcmpError", 2: "Timeout", 3: "OtherSideTerminated",
    4: "ManagerDeleted", 5: "ConnectFail", 6: "Application",
    7: "UnreachableConnection", 8: "UnacknowledgedTimeout",
    9: "NewConnectionAttempt", 10: "ConnectionRefused", 11: "ConnectError",
    12: "ConnectingToSelf", 13: "ReliableOverflow", 14: "ApplicationReleased",
    15: "CorruptPacket", 16: "ProtocolMismatch",
}


def hexdump(data):
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"    {off:04x}  {hexpart:<47}  {text}")
    return "\n".join(lines)


def read_group_length(data, pos):
    # Group/varint length (FUN_00bf5e80); assumed SOE style: 1 byte, or 0xff + u16be.
    if data[pos] != 0xFF:
        return data[pos], pos + 1
    return struct.unpack_from(">H", data, pos + 1)[0], pos + 3


def try_parse_login_request(payload):
    # Client::PacketLoginRequest (FUN_00d9ad10): u16le type=3, then two
    # strings of u32le length + bytes (likely username, then password).
    if len(payload) < 10 or struct.unpack_from("<H", payload, 0)[0] != 3:
        return None
    pos = 2
    fields = []
    for _ in range(2):
        if pos + 4 > len(payload):
            return None
        (n,) = struct.unpack_from("<I", payload, pos)
        pos += 4
        if pos + n > len(payload):
            return None
        fields.append(payload[pos:pos + n].decode("latin-1"))
        pos += n
    return fields


def describe(data, indent="  "):
    if len(data) < 2 or data[0] != 0:
        print(f"{indent}app/raw data ({len(data)} bytes)")
        login = try_parse_login_request(data)
        if login:
            print(f"{indent}>>> PacketLoginRequest: field1={login[0]!r} field2={'*' * len(login[1])}")
        return
    kind = data[1]
    print(f"{indent}type 0x{kind:02x} {PACKET_NAMES.get(kind, '?')} ({len(data)} bytes)")
    if kind == 0x03:  # Multi: 1-byte length-prefixed sub-packets
        pos = 2
        while pos < len(data):
            n = data[pos]
            describe(data[pos + 1:pos + 1 + n], indent + "  ")
            pos += 1 + n
    elif kind == 0x19:  # Group
        pos = 2
        while pos < len(data):
            n, pos = read_group_length(data, pos)
            describe(data[pos:pos + n], indent + "  ")
            pos += n
    elif 0x09 <= kind <= 0x0C:  # Reliable: u16be sequence, then payload
        (seq,) = struct.unpack_from(">H", data, 2)
        print(f"{indent}  reliable seq={seq}")
        describe(data[4:], indent + "  ")


def build_confirm(connect_code, max_raw):
    return struct.pack(
        ">BBIIBBBII",
        0x00, 0x02,
        connect_code,
        0,  # encryptCode
        0,  # crcBytes: no CRC on later packets
        0,  # encryptMethod1: none
        0,  # encryptMethod2: none
        min(max_raw, MAX_RAW_PACKET),
        PROTOCOL_VERSION,
    )


def build_login_reply(success):
    # Client::PacketLoginReply (ctor FUN_00d9a0f0, reader FUN_00d9a840):
    # u16le type=4, u8 success. The client stores the byte as its logged-in flag.
    return struct.pack("<HB", 4, 1 if success else 0)


def build_reliable(seq, payload):
    # Reliable1: 00 09 | u16be sequence | payload
    return struct.pack(">BBH", 0x00, 0x09, seq) + payload


def build_world_server_event(account, session, world_name, address):
    # Login-connection type 2 = event envelope (parsed by FUN_006ebb60, dispatched
    # by FUN_00617b10): u16le 2 | u32le eventId | u32le length | bytes.
    # Event 0x27 (FUN_00617810) reads four fixed 128-byte char fields and calls
    # the world-server connect (FUN_006ed100) with address, +0x000, +0x080.
    # The meaning of +0x000/+0x080 is a guess (account / session key).
    # Fields are UTF-16LE (wchar_t[64]); FUN_007a6d50 converts wide -> narrow.
    # Sending 8-bit text made the client log the address as "㈱⸷⸰⸰1".
    def field(text):
        raw = text[:63].encode("utf-16-le")
        return raw + b"\0" * (128 - len(raw))
    data = field(account) + field(session) + field(world_name) + field(address)
    return struct.pack("<HII", 2, 0x27, len(data)) + data


def build_world_list_entry_event(world_name, status=4, population=0):
    # Login-connection event 0x25 (FUN_006179a0 → FUN_005f0cf0) adds/updates one
    # server-select list entry: u8 status (FUN_00cda3b0: 2 Loading, 3 Locked,
    # 4 Up, 5 Low, 6 Medium, 7 High, else Down), 3 pad bytes, i32 population
    # (-2 marks the world down; >0 is shown as "Pop: n"), then a NUL-terminated
    # UTF-16LE world name that must match the name sent in event 0x27.
    data = struct.pack("<B3xi", status, population) + (world_name + "\0").encode("utf-16-le")
    return struct.pack("<HII", 2, 0x25, len(data)) + data


def build_reliable_fragments(start_seq, payload, max_raw):
    # Fragment1: 00 0d | u16be seq | (first only) u32be total length | data
    # Reassembled by FUN_00c04480.
    packets = []
    seq = start_seq
    pos = 0
    first = True
    while pos < len(payload):
        header = struct.pack(">BBH", 0x00, 0x0D, seq)
        if first:
            header += struct.pack(">I", len(payload))
        room = max_raw - len(header)
        packets.append(header + payload[pos:pos + room])
        pos += room
        seq += 1
        first = False
    return packets, seq


def build_ack_all(channel_type, seq):
    # AckAll1..4 = 0x15..0x18: 00 15 | u16be seq, acknowledges everything up
    # to and including seq on that reliable channel (FUN_00c05730).
    return struct.pack(">BBH", 0x00, 0x15 + (channel_type - 0x09), seq)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10101, help="login server port")
    parser.add_argument("--world-port", type=int, default=10100, help="world server port (ClientWorldApi default 0x2774)")
    parser.add_argument("--world-address", default="127.0.0.1", help="world/zone address sent to the client")
    parser.add_argument("--zone-port", type=int, default=10102, help="zone server port (ClientZoneApi has no default)")
    parser.add_argument("--zone-level", default=None,
                        help="force the level sent in the UE2 WELCOME (default: the character's chunk)")
    parser.add_argument("--spawn-location", default=None,
                        help="x,y,z of the replicated PlayerController (default: the level's first PlayerStart)")
    parser.add_argument("--client-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),
                        help="client install folder (package GUIDs for the UE2 package map)")
    parser.add_argument("--spawn-class", default="Engine.PlayerController",
                        help="actor class opened on an actor channel after JOIN ('' = none)")
    parser.add_argument("--pawn-class", default="SGOUnrealAbstractionLayer.SGOPCPawn",
                        help="pawn class spawned for the player ('' = none)")
    parser.add_argument("--zone-in-events", default="0x485",
                        help="comma-separated payload-less zone events sent after the spawn")
    parser.add_argument("--npc-entity-id", type=lambda v: int(v, 0), default=None,
                        help="entity id for the --test-npc pawn (experiments)")
    parser.add_argument("--test-stats", action="store_true",
                        help="fill MsgScore fields 35+ with their own index (to map UI slots)")
    parser.add_argument("--dev-commands", action="store_true",
                        help="enable !stat / !event chat commands (see dev_command)")
    parser.add_argument("--test-npc", action="store_true",
                        help="no longer needed: NPCs always come from content/spawns/<chunk>.json")
    parser.add_argument("--spawn-rotation", action="store_true",
                        help="include an initial rotation in the actor open bunch")
    args = parser.parse_args()
    # Used when a zone connection arrives without going through Play first.
    args.default_player = lambda: zone.Player(name="Someone",
                                              level=args.zone_level or chunk_name(*DEFAULT_CHUNK))
    args.package_maps = {}
    args.content = content.Content()
    args.npc_dialog = npc_dialog
    args.harvest_begin = lambda state: handle_harvest_event(state, harvest.BEGIN)
    args.craft_event = lambda state, event, data: handle_craft_event(state, event, data)
    global ARGS
    ARGS = args
    args.zone_in_events = [int(v, 0) for v in args.zone_in_events.split(",") if v]

    login_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    login_sock.bind((args.host, args.port))
    world_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    world_sock.bind((args.host, args.world_port))
    zone_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    zone_sock.bind((args.host, args.zone_port))
    names = {login_sock: "LOGIN", world_sock: "WORLD", zone_sock: "ZONE"}
    print(f"Login stub listening on UDP {args.host}:{args.port}")
    print(f"World stub listening on UDP {args.host}:{args.world_port}")
    print(f"Zone stub listening on UDP {args.host}:{args.zone_port}")

    # Per-(server, client) state: next outgoing reliable seq, reliable seqs already handled.
    clients = {}

    next_tick = next_move = time.time() + 1
    while True:
        ready, _, _ = select.select([login_sock, world_sock, zone_sock], [], [],
                                    max(min(next_tick, next_move) - time.time(), 0))
        for sock in ready:
            try:
                data, addr = sock.recvfrom(65535)
            except ConnectionResetError:
                # Windows reports an ICMP "port unreachable" from a client that
                # went away as an error on the next recvfrom; just carry on.
                continue
            serve(sock, names[sock], data, addr, clients, args)
        if time.time() >= next_move:
            next_move = time.time() + MOVE_TICK
            movement_tick(zone_sock, clients, args)
        if time.time() >= next_tick:
            next_tick = time.time() + 1
            world_tick(zone_sock, clients, args)


MOVE_TICK = 0.25


def movement_tick(zone_sock, clients, args):
    """Four times a second: NPCs that chase and attack their target player."""
    now = time.time()
    for (server, addr), state in list(clients.items()):
        player = state.get("player")
        if server != "ZONE" or player is None or "ue" not in state or state.get("handoff"):
            continue
        for lines, npc in combat.npc_turns(player, now):
            # npc_turns only attacks living players, so they were alive before.
            for m in combat_results(state, args, player, lines, None, True, player.auto_attack):
                send_message(zone_sock, addr, state, m)
            if player.health > 0:
                npc_special(state, npc, now)
    for w in world.all_worlds():
        players = w.players()
        for npc in w.npcs.values():
            victim = combat.proximity_aggro(npc, players, lambda p, npc=npc: faction_kos(p, npc))
            if victim is not None:
                vs = w.members.get(victim.char_id)
                if vs is not None:
                    vs["send"](build_system_text(f"{npc.name} notices you!", SYSTEM_TEXT_ERROR))
        for npc in w.npcs.values():
            target = npc.aggro_on.live_position if npc.aggro_on else None
            values = combat.chase_step(npc, target, MOVE_TICK)
            if values:
                w.broadcast(lambda s, npc=npc, values=values: zone.npc_update(s, args, npc, values))


def use_ability(state, args, player, ability):
    """An ability from the hotbar: its effect kind (effects.classify) decides what
    it does; the refresh time starts the hotbar cooldown sweep."""
    send = state["send"]
    handle, _aid, name, icon, _desc, refresh = ability[:6]
    now = time.time()
    cooldowns = player.__dict__.setdefault("cooldowns", {})
    if now < cooldowns.get(handle, 0):
        send(zone.zone_event(0x242, struct.pack("<B", 7)))       # error sound
        send(build_system_text(f"{name} is not ready yet ({cooldowns[handle] - now:.0f}s).", SYSTEM_TEXT_ERROR))
        return
    spec = effects.classify(name, args.content.abilities)
    if state.get("casting"):
        send(zone.zone_event(0x242, struct.pack("<B", 7)))
        send(build_system_text("You are already casting.", SYSTEM_TEXT_ERROR))
        return
    if spec.get("cast", 0) > 0 and not state.pop("cast_done", False):
        # Cast time: the client draws the bar (0x25c) and finishes it by itself;
        # the server resolves the ability when the time is up (effects_tick).
        state["casting"] = {"ability": ability, "ends": now + spec["cast"], "pos": state.get("position")}
        send(effects.cast_bar(name, spec["cast"]))
        send(build_system_text(f"You begin to cast {name}.", SYSTEM_TEXT_COMBAT))
        return
    was_alive, attacking = player.health > 0, player.auto_attack
    if spec["kind"] in ("heal", "buff"):
        if player.health <= 0:
            send(build_system_text("You can't do that while dead.", SYSTEM_TEXT_ERROR))
            return
        cost = combat.ABILITY_COST if refresh > 0 else 0
        if player.endurance < cost:
            send(build_system_text("You do not have enough endurance.", SYSTEM_TEXT_ERROR))
            return
        player.endurance -= cost
        send(zone.endurance_update(player))
        visual = ability[1] if ability[1] >= 500000 else None
        if visual:
            send(combat.display_ability(player.char_id, player.char_id, visual))
        if spec["kind"] == "heal":
            amount = random.randint(*spec["amount"])
            player.health = min(player.health + amount, player.stats["hit_points"])
            send(effects.combat_text(player.char_id, player.char_id, name, amount, heal=True))
            send(zone.health_update(player))
        else:
            apply_buff(state, player, name, spec, now)
    else:
        lines, npc = combat.use_ability(player, ability)
        for m in combat_results(state, args, player, lines, npc, was_alive, attacking):
            send(m)
        if spec["kind"] == "dot" and npc is not None and npc.alive and player.last_combat >= now:
            apply_dot(state, player, npc, name, spec, now)
        elif npc is None or player.last_combat < now:
            return                       # the ability didn't go off: no cooldown
    if refresh > 0:
        cooldowns[handle] = now + refresh
        send(effects.cooldown(handle, refresh))


def npc_special(state, npc, now):
    """After a melee swing an NPC may use one of its special abilities on the
    player: a DoT/debuff ("Venom Bite") shown in the harmful effects window."""
    player, send = state["player"], state["send"]
    for a in npc.abilities:
        if random.random() >= a.get("chance", 0.2):
            continue
        name, eid = a["name"], effect_id(player, a["name"]) + 500
        if a.get("kind", "dot") == "dot":
            ticks, interval = a.get("ticks", 4), a.get("interval", 3.0)
            player.__dict__.setdefault("effects", [])
            old = next((e for e in player.effects if e["id"] == eid), None)
            if old is not None:
                old["ticks"] = ticks                 # reapplied: refresh, keep the tick rhythm
            else:
                player.effects.append({"kind": "incoming", "id": eid, "name": name, "npc": npc,
                                       "damage": a.get("damage", [2, 4]), "ticks": ticks,
                                       "interval": interval, "next": now + interval})
            desc = f"Deals damage every {interval:g} seconds."
            send(effects.effect_add(eid, name, desc, a.get("icon", 553), ticks * interval, ticks * interval,
                                    harmful=True))
            send(build_system_text(f"{npc.name} uses {name} on you!", SYSTEM_TEXT_ERROR))
        return


def effect_id(player, name):
    return 7000 + sum(name.encode("utf-8")) % 1000


def apply_buff(state, player, name, spec, now):
    send = state["send"]
    stat, bonus, duration = spec["stat"], spec["bonus"], spec["duration"]
    eid = effect_id(player, name)
    player.__dict__.setdefault("effects", [])
    old = next((e for e in player.effects if e["id"] == eid), None)
    if old is not None:
        player.effects.remove(old)               # recast: refresh the timer, keep one bonus
    else:
        player.stats[stat] = player.stats.get(stat, 0) + bonus
    desc = f"Increases {stat.capitalize()} by {bonus}."
    player.effects.append({"kind": "buff", "id": eid, "name": name, "desc": desc, "icon": spec["icon"],
                           "stat": stat, "bonus": bonus, "ends": now + duration, "duration": duration,
                           "next_note": now + 5})
    send(effects.effect_add(eid, name, desc, spec["icon"], duration, duration))
    base = player.stats[stat] - bonus
    send(zone.zone_event(0x2D4, vgmsg.stat_update(vgmsg.STAT_IDS[stat], player.stats[stat], base=base)))


def apply_dot(state, player, npc, name, spec, now):
    eid = effect_id(player, name)
    player.__dict__.setdefault("effects", [])
    player.effects[:] = [e for e in player.effects if not (e["id"] == eid and e.get("npc") is npc)]
    desc = f"Deals damage every {spec['interval']:g} seconds."
    player.effects.append({"kind": "dot", "id": eid, "name": name, "desc": desc, "icon": spec["icon"],
                           "npc": npc, "damage": spec["damage"], "ticks": spec["ticks"],
                           "interval": spec["interval"], "next": now + spec["interval"]})
    if player.target == npc.entity_id:
        state["send"](effects.target_effect_add(eid, name, desc, spec["icon"], player.char_id))


def effects_tick(state, args, now):
    """Casts, buff timers and expiry, damage-over-time ticks."""
    player, send = state["player"], state["send"]
    cast = state.get("casting")
    if cast:
        if state.get("position") != cast["pos"]:
            state.pop("casting")
            send(effects.interrupted())
            send(build_system_text(f"Your {cast['ability'][2]} is interrupted.", SYSTEM_TEXT_ERROR))
        elif now >= cast["ends"]:
            state.pop("casting")
            state["cast_done"] = True
            use_ability(state, args, player, cast["ability"])
            state.pop("cast_done", None)
    for e in list(getattr(player, "effects", [])):
        if e["kind"] == "buff":
            if now >= e["ends"]:
                player.effects.remove(e)
                player.stats[e["stat"]] -= e["bonus"]
                send(effects.effect_remove(e["id"]))
                sid = vgmsg.STAT_IDS[e["stat"]]
                send(zone.zone_event(0x2D4, vgmsg.stat_update(sid, player.stats[e["stat"]])))
                send(build_system_text(f"{e['name']} wears off.", SYSTEM_TEXT_WHITE))
            elif now >= e["next_note"]:
                e["next_note"] = now + 5
                send(effects.effect_timer(e["id"], e["ends"] - now, e["duration"]))
        elif e["kind"] == "incoming" and now >= e["next"]:
            e["ticks"] -= 1
            e["next"] = now + e["interval"]
            if player.health > 0:
                dmg = random.randint(*e["damage"])
                was_alive = player.health > 0
                player.health = max(player.health - dmg, 0)
                player.last_combat = now
                send(effects.combat_text(e["npc"].entity_id, player.char_id, e["name"], dmg))
                lines = []
                if player.health == 0:
                    lines.append(("You have been slain!", "error"))
                for m in combat_results(state, args, player, lines, None, was_alive, player.auto_attack):
                    send(m)
            if e["ticks"] <= 0 or player.health <= 0:
                player.effects.remove(e)
                send(effects.effect_remove(e["id"]))
        elif e["kind"] == "dot" and now >= e["next"]:
            npc = e["npc"]
            e["ticks"] -= 1
            e["next"] = now + e["interval"]
            if not npc.alive or e["ticks"] < 0:
                player.effects.remove(e)
                if player.target == npc.entity_id:
                    send(effects.target_effect_remove(npc.entity_id, e["id"]))
                continue
            dmg = random.randint(*e["damage"])
            npc.health = max(npc.health - dmg, 0)
            send(effects.combat_text(player.char_id, npc.entity_id, e["name"], dmg))
            lines = []
            if not npc.alive:
                npc.died_at = now
                lines.append((f"You have slain {npc.name}!", "white"))
                player.pending_rewards.append(combat.KILL_XP)
            else:
                npc.aggro, npc.aggro_on = True, player
            for m in combat_results(state, args, player, lines, npc, player.health > 0, player.auto_attack):
                send(m)
            if e["ticks"] == 0 or not npc.alive:
                player.effects.remove(e)
                if player.target == npc.entity_id:
                    send(effects.target_effect_remove(npc.entity_id, e["id"]))


def combat_results(state, args, player, lines, npc, was_alive, was_attacking):
    """Zone messages after a combat step: ability visuals, chat lines, health
    bars, deaths and the auto-attack state."""
    out = list(player.pending_displays)
    player.pending_displays.clear()
    colours = {"combat": SYSTEM_TEXT_COMBAT, "error": SYSTEM_TEXT_ERROR, "white": SYSTEM_TEXT_WHITE}
    out += [build_system_text(text, colours[kind]) for text, kind in lines]
    out.append(zone.health_update(player))
    if getattr(player, "endurance_changed", False):
        player.endurance_changed = False
        out.append(zone.endurance_update(player))
    if was_alive and player.health == 0:
        player.auto_attack = False
        out += player_death(state, args, player)
    if npc:
        out.append(combat.target_health(npc))
        if not npc.alive and not npc.death_shown:
            for m_state in (group_states(player) or [state]):
                if m_state.get("world") is state.get("world"):
                    quest_kill(m_state, npc)
                    faction_kill(m_state, npc)
            # Everyone in the chunk sees it fall.
            print(f"  <- {npc.name} died")
            npc.death_shown = True
            npc.stance = False
            w = state.get("world")
            if w is not None:
                w.broadcast(lambda s: [m for m in (
                    zone.npc_update(s, args, npc, {"Health": 0, "m_bIsDead": 1}),
                    combat.play_animation(npc, combat.ANIM_DEATH)) if m is not None])
    for amount in player.pending_rewards:
        members = [s for s in group_states(player) if s.get("world") is state.get("world")]             or [state]
        share = max(1, amount * (100 + 10 * (len(members) - 1)) // 100 // len(members))
        source = npc.entity_id if npc else player.char_id
        for m_state in members:
            msgs = award_xp(m_state["player"], share, source, grouped=len(members) > 1)
            if m_state is state:
                out += msgs
            else:
                for m in msgs:
                    m_state["send"](m)
    player.pending_rewards.clear()
    if player.auto_attack != was_attacking:
        out += combat.auto_attack_state(player.auto_attack)
    set_combat_stance(state, args, player, player.auto_attack, out)
    if npc and npc.alive and npc.aggro and not npc.stance:
        npc.stance = True
        broadcast_npc(state, args, npc, {"m_CombatState": 1})
    return out


EQUIP_EVENT = 0x8E
UNEQUIP_EVENT = 0x98


def pawn_props_changed(state, values):
    """Replicated pawn properties of this player changed: own client and everyone in the chunk."""
    player = state["player"]
    if "ue" not in state:
        return
    state["send"](zone.player_pawn_update(state, ARGS, values))
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.remote_player_update(s, ARGS, player, values), exclude=state)


def gear_changed(state, args, player):
    """After equipment changed: the model for everyone in the chunk, and save."""
    values = {"m_AttachmentGroups": zone.gear_attachments(player)}
    state["send"](zone.player_pawn_update(state, args, values))
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.remote_player_update(s, args, player, values), exclude=state)
    save_character_field(player.name, "items", [list(i) for i in player.items])
    save_character_field(player.name, "equipment", [list(e) for e in player.equipment])


def award_xp(player, amount, source, grouped=False):
    """Experience for one player (0x3d5, level ups, XP bar via MsgScore); saved."""
    out = [combat.experience_reward(amount, source, group=1 if grouped else 0)]
    player.xp += amount
    while player.xp >= zone.XP_PER_LEVEL:
        player.xp -= zone.XP_PER_LEVEL
        player.level_number += 1
        out.append(build_system_text(f"You have reached level {player.level_number}!",
                                     SYSTEM_TEXT_WHITE))
    out.append(zone.score_message(player))
    save_character_progress(player.name, player.level_number, player.xp)
    return out


def set_combat_stance(state, args, player, on, out):
    """m_CombatState = 1 draws weapons (verified live); everyone in the chunk sees it."""
    if getattr(player, "stance", False) == on:
        return
    player.stance = on
    values = {"m_CombatState": int(on)}
    out.append(zone.player_pawn_update(state, args, values))
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.remote_player_update(s, args, player, values), exclude=state)


def broadcast_npc(state, args, npc, values):
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.npc_update(s, args, npc, values))


def player_death(state, args, player):
    """The player's pawn falls (m_bIsDead + death animation) and the release
    popup opens."""
    print(f"  <- {player.name} died")
    out = [zone.player_pawn_update(state, args, {"Health": 0, "m_bIsDead": 1}),
           combat.play_animation(player.char_id, combat.ANIM_DEATH),
           combat.death_popup(300)]
    # Death wears equipped gear (shown on the next login or after a repair).
    dur = getattr(player, "durability", None)
    if dur is not None and player.equipment:
        for item_id, name, _icon, _slot in player.equipment:
            if args.content.item(name).get("type", "misc") != "misc":
                dur[str(item_id)] = max(0, dur.get(str(item_id), 100) - DEATH_WEAR)
        save_character_field(player.name, "durability", dur)
        out.append(build_system_text("Your equipment has been damaged.", SYSTEM_TEXT_ERROR))
    return out


DEATH_WEAR = 10


CAMP_SECONDS = 20


def camp_tick(state, now):
    camp = state.get("camp")
    if not camp:
        return
    if state.get("position") != camp["pos"]:
        state.pop("camp")
        state["send"](zone.zone_event(0x40D))
    elif camp.get("closing"):
        if now >= camp["closing"]:
            # Closing the zone connection is what returns the client to character
            # select: its connection-closed handler (FUN_00bf4850) runs /camp, which
            # finds no zone connection and goes back (FUN_0061fe50), then asks the
            # world server for the character list again (world 0x19).
            state.pop("camp")
            if state.get("terminate"):
                state["terminate"]()
            state["closed"] = True
            print(f"  {state['player'].name} camped: zone connection closed")
    elif now >= camp["until"]:
        camp["closing"] = now + 1.0
        state["send"](zone.zone_event(0x40C))
        print(f"  {state['player'].name} finished camping")
    elif now >= camp["next_note"]:
        camp["next_note"] = now + 5
        state["send"](zone.zone_event(0x40E, struct.pack("<i", round(camp["until"] - now))))


def world_tick(zone_sock, clients, args):
    """Once a second: per player auto-attack swings and regeneration; per world
    NPC respawns (shown to everyone in the chunk)."""
    now = time.time()
    for (server, addr), state in list(clients.items()):
        player = state.get("player")
        if server != "ZONE" or player is None or "ue" not in state or state.get("handoff"):
            continue
        if "send" in state:
            camp_tick(state, now)
            if state.get("closed"):
                clients.pop((server, addr), None)
                leave_world(state, args)
                continue
            harvest_tick(state, now)
            effects_tick(state, args, now)
        for action in combat.tick(player, now):
            if action[0] == "swing":
                _, lines, npc = action
                for m in combat_results(state, args, player, lines, npc, True, True):
                    send_message(zone_sock, addr, state, m)
            elif action[0] == "health":
                send_message(zone_sock, addr, state, zone.health_update(player))
            elif action[0] == "endurance":
                send_message(zone_sock, addr, state, zone.endurance_update(player))
    group_tick()
    for s in list(ONLINE.values()):
        if s.get("handoff") and now - s.get("last_seen", now) > 60:
            # Handed off to another chunk but the new zone login never came: log out.
            s.pop("handoff")
            if PENDING_PLAYERS.get(s.get("session", "")) is s.get("player"):
                PENDING_PLAYERS.pop(s.get("session", ""))
            leave_world(s, args)
    for w in world.all_worlds():
        for s in list(w.members.values()):
            if now - s.get("last_seen", now) > 30:      # client gone without a disconnect
                leave_world(s, args)
        for npc in combat.respawns(w.npcs, now):
            print(f"  <- respawn {npc.name}")
            npc.death_shown = False
            values = {"Health": npc.max_health, "m_bIsDead": 0, "Location": npc.home, "m_CombatState": 0,
                      "Velocity": (0.0, 0.0, 0.0),
                      "PawnPosition": (npc.home, (0, npc.yaw, 0), (0.0, 0.0, 0.0))}

            def build(s, npc=npc, values=values):
                out = [zone.npc_update(s, args, npc, values)]
                if s["player"].target == npc.entity_id:
                    out.append(combat.target_health(npc))
                return [m for m in out if m is not None]
            w.broadcast(build)


ARGS = None           # parsed command line (set in main)

# Online zone connections, for groups and chat across connections.
ONLINE = {}            # lower-case character name -> zone connection state
ZONE_BY_SESSION = {}   # session key -> zone connection state (world chat -> player)


WORLD_BY_SESSION = {}  # session key -> (sock, addr, state) of the world connection


def world_send(zone_state, message):
    """Send a world-server message (chat) to the player of a zone connection."""
    conn = WORLD_BY_SESSION.get(zone_state.get("session"))
    if conn:
        send_message(conn[0], conn[1], conn[2], message)


def ignores(listener, speaker_name):
    return listener is not None and speaker_name.lower() in [n.lower() for n in getattr(listener, "ignores", [])]


def world_chat(zone_state, command, reply):
    """Chat commands from the world connection (see chat.py)."""
    player = zone_state["player"]
    verb, name, text = chat.parse(command)
    if verb == "shout":
        for s in ONLINE.values():
            if s is not zone_state and not ignores(s.get("player"), player.name):
                world_send(s, chat.line(text, player.name, chat.SHOUT))
        reply(chat.echo(text, chat.SHOUT))
    elif verb == "tell":
        target = ONLINE.get((name or "").lower())
        if target is zone_state:
            reply(chat.error(chat.ERR_TELL_SELF))
        elif target is None:
            reply(chat.error(chat.ERR_NOT_ONLINE))
        else:
            if not ignores(target["player"], player.name):
                world_send(target, chat.line(text, player.name, chat.TELL))
            reply(chat.echo_to(text, target["player"].name, chat.TELL))
    elif verb == "gsay":
        members = group_states(player)
        if not members:
            reply(chat.error(chat.ERR_NO_GROUP))
            return
        for m_state in members:
            if m_state is not zone_state:
                world_send(m_state, chat.line(text, player.name, chat.GROUP))
        reply(chat.echo(text, chat.GROUP))
    elif verb == "guildsay":
        g = guild_of(player.name)
        if g is None:
            reply(chat.error(0x1A))                      # "You are not in a guild."
            return
        for m in g["members"]:
            s = ONLINE.get(m.lower())
            if s is not None and s is not zone_state and not ignores(s.get("player"), player.name):
                world_send(s, chat.line(text, player.name, guild.CHAT_GUILD))
        reply(chat.echo(text, guild.CHAT_GUILD))
    elif verb == "regionsay":
        for s in ONLINE.values():
            if s is not zone_state:
                world_send(s, chat.channel_line(text, player.name, "OOC"))
        reply(chat.echo_to(text, "OOC", chat.CHANNEL))


def social_entry(name):
    """The who/friend record of a character by name (online or not)."""
    s = ONLINE.get(name.lower())
    if s and s.get("player"):
        p = s["player"]
        return {"name": p.name, "level": p.level_number, "klass": p.klass, "chunk": tuple(p.chunk),
                "online": True, "afk": getattr(p, "afk", False), "anon": getattr(p, "anon", False),
                "lfg": getattr(p, "lfg", False), "diplomacy_level": 1, "uid": social_uid(p.name),
                "guild": (guild_of(p.name) or {}).get("name", "")}
    return {"name": name, "online": False, "uid": social_uid(name)}


def social_uid(name):
    """A stable id per character name for friend/ignore entries."""
    return zlib.crc32(name.lower().encode("utf-8")) & 0x7FFFFFFF


def social_login(state):
    """Friend and ignore lists for the player; tell friends who list them."""
    player = state["player"]
    world_send(state, social.friend_list([social_entry(n) for n in getattr(player, "friends", [])]))
    world_send(state, social.ignore_list([social_entry(n) for n in getattr(player, "ignores", [])]))
    # Once per login, not on every chunk handoff.
    if player.name.lower() not in ANNOUNCED:
        ANNOUNCED.add(player.name.lower())
        notify_friends(state, online=True)


ANNOUNCED = set()


def notify_friends(state, online):
    """0x4f6 "X is now online." / "X has gone offline." to everyone who lists X."""
    player = state["player"]
    entry = social_entry(player.name) if online else {"name": player.name, "online": False}
    for s in list(ONLINE.values()):
        other = s.get("player")
        if s is state or other is None:
            continue
        friends = [n.lower() for n in getattr(other, "friends", [])]
        if player.name.lower() in friends:
            world_send(s, social.friend_status(entry, entry["uid"]))


GUILDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guilds.json")


def load_guilds():
    try:
        with open(GUILDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_guilds(guilds):
    with open(GUILDS_FILE, "w", encoding="utf-8") as f:
        json.dump(guilds, f, indent=2)


def guild_of(name, guilds=None):
    """The guild record {id, name, members: {name: rank}} a character is in, or None."""
    for g in (guilds if guilds is not None else load_guilds()).values():
        if name.lower() in [m.lower() for m in g["members"]]:
            return g
    return None


def guild_member(g, name, online=None):
    rank = next(r for m, r in g["members"].items() if m.lower() == name.lower())
    s = ONLINE.get(name.lower())
    p = s["player"] if s and s.get("player") else None
    char = next((c for c in load_characters() if c["first"].lower() == name.lower()), {})
    return {"id": character_id(char) if char else social_uid(name), "name": char.get("first", name),
            "rank": rank, "online": p is not None if online is None else online,
            "klass": p.klass if p else 0, "level": p.level_number if p else 1,
            "chunk": tuple(p.chunk) if p else (0, 0)}


def guild_broadcast(name, make, exclude=None):
    """Send make(guild) to every online member of name's guild."""
    g = guild_of(name)
    if g is None:
        return
    for m in g["members"]:
        s = ONLINE.get(m.lower())
        if s is not None and s is not exclude and s.get("send"):
            s["send"](make(g))


def set_guild(state, gid):
    """The player's guild id (overhead tag) changed."""
    state["player"].guild_id = gid
    pawn_props_changed(state, {"m_GuildId": gid})


def guild_login(state):
    """Guild membership, window info and member list at zone login."""
    player, send = state["player"], state["send"]
    for g in load_guilds().values():               # names for the overhead tags
        send(guild.name_tag(g["id"], g["name"]))
    g = guild_of(player.name)
    player.guild_id = g["id"] if g else 0
    if g is None:
        send(guild.membership(0, 0))
        return
    send_guild_window(state, g)
    if g.get("motd"):
        send(guild.motd(g["motd"], g.get("motd_by", ""), g.get("motd_time", 0)))
    if not state.get("guild_announced"):
        state["guild_announced"] = True
        guild_broadcast(player.name, lambda g: guild.member_update(guild_member(g, player.name)), exclude=state)


def send_guild_window(state, g):
    player, send = state["player"], state["send"]
    send(guild.membership(g["id"], guild_member(g, player.name)["rank"]))
    send(guild.info(g["name"], g.get("ranks")))
    send(guild.name_tag(g["id"], g["name"]))
    for m in guild.member_list([guild_member(g, n) for n in g["members"]]):
        send(m)


def handle_guild_event(state, event, data):
    """Guild create / invite / accept / quit / kick / promote / demote / delete."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE guild {event:#x}: {data[:48].hex(' ')}")
    guilds = load_guilds()
    mine = guild_of(player.name, guilds)
    rank = mine["members"][next(m for m in mine["members"] if m.lower() == player.name.lower())] if mine else 0

    def say(text, error=False):
        send(build_system_text(text, SYSTEM_TEXT_ERROR if error else SYSTEM_TEXT_WHITE))
    if event == guild.CREATE:
        name = guild.read_create_name(data).strip()
        if mine:
            send(zone.zone_event(0x0E, struct.pack("<h", 0xDC)))        # AlreadyInGuild
        elif not 3 <= len(name) <= 32:
            send(zone.zone_event(0x0E, struct.pack("<h", 0xDE)))
        elif any(g["name"].lower() == name.lower() for g in guilds.values()):
            say(f"A guild named {name} already exists.", True)
        else:
            gid = max([g["id"] for g in guilds.values()] + [0]) + 1
            guilds[str(gid)] = {"id": gid, "name": name, "members": {player.name: guild.LEADER}}
            save_guilds(guilds)
            say(f"You have founded the guild {name}.")
            for s in ONLINE.values():
                if s.get("send"):
                    s["send"](guild.name_tag(gid, name))
            send_guild_window(state, guilds[str(gid)])
            set_guild(state, gid)
    elif mine is None:
        if event == guild.ACCEPT and state.get("guild_invite"):
            gid = state.pop("guild_invite")
            g = guilds.get(str(gid))
            if g is None:
                return
            g["members"][player.name] = guild.MEMBER
            save_guilds(guilds)
            send(zone.zone_event(0x0E, struct.pack("<h", 0xD8)))        # JoinedGuild
            send_guild_window(state, g)
            set_guild(state, g["id"])
            guild_broadcast(player.name, lambda g: guild.member_update(guild_member(g, player.name),
                                                                       guild.JOINED), exclude=state)
        elif event == guild.DECLINE:
            state.pop("guild_invite", None)
        else:
            send(zone.zone_event(0x0E, struct.pack("<h", 0x1A)))        # NoGuild
    elif event == guild.INVITE:
        name = guild.read_name(data).strip()
        target = ONLINE.get(name.lower())
        if rank < guild.OFFICER:
            say("You don't have permission to invite.", True)
        elif target is None or not target.get("player"):
            say(f"{name} is not online.", True)
        elif guild_of(target["player"].name, guilds):
            say(f"{target['player'].name} is already in a guild.", True)
        else:
            target["guild_invite"] = mine["id"]
            target["send"](guild.invite(player.char_id, player.name, mine["name"], ranks=mine.get("ranks")))
            say(f"You invite {target['player'].name} to join {mine['name']}.")
    elif event in (guild.QUIT, guild.KICK, guild.DELETE):
        if event == guild.DELETE:
            if rank != guild.LEADER:
                send(zone.zone_event(0x0E, struct.pack("<h", 0xE6)))
                return
            leaving = list(mine["members"])
        elif event == guild.QUIT:
            leaving = [player.name]
        else:
            name = guild.read_name(data).strip()
            leaving = [m for m in mine["members"] if m.lower() == name.lower()]
            if not leaving or rank < guild.OFFICER or mine["members"][leaving[0]] >= rank:
                say("You can't remove that member.", True)
                return
        notify = guild.QUIT_NOTE if event == guild.QUIT else guild.REMOVED
        for name in leaving:
            m = guild_member(mine, name)
            m["rank"] = 0
            guild_broadcast(name, lambda g, m=m: guild.member_update(m, notify))
            s = ONLINE.get(name.lower())
            del mine["members"][name]
            if s is not None and s.get("send"):
                s["send"](guild.membership(0, 0))
                s["send"](zone.zone_event(0x0E, struct.pack("<h", 0xD9)))   # RemovedFromGuild
                if s.get("player"):
                    set_guild(s, 0)
        if not mine["members"] or event == guild.DELETE:
            guilds.pop(str(mine["id"]), None)
        elif event == guild.QUIT and rank == guild.LEADER:
            heir = max(mine["members"], key=lambda n: mine["members"][n])
            mine["members"][heir] = guild.LEADER
        save_guilds(guilds)
    elif event in (guild.PROMOTE, guild.DEMOTE):
        name = guild.read_name(data).strip()
        who = next((m for m in mine["members"] if m.lower() == name.lower()), None)
        if who is None or rank < guild.OFFICER or (mine["members"][who] >= rank and who != player.name):
            say("You can't change that member's rank.", True)
            return
        new = mine["members"][who] + (1 if event == guild.PROMOTE else -1)
        mine["members"][who] = max(1, min(rank - 1 if who != player.name else rank, new))
        save_guilds(guilds)
        guild_broadcast(who, lambda g: guild.member_update(guild_member(g, who)))
        s = ONLINE.get(who.lower())
        if s is not None and s.get("send"):
            s["send"](guild.membership(mine["id"], mine["members"][who]))
        say(f"{who} is now a {(mine.get('ranks') or guild.RANK_NAMES)[mine['members'][who] - 1]}.")


def handle_guild_world(state, event, data, reply):
    """World social guild events: MOTD set/view, rank rename, /guildstatus, member list."""
    player = state["player"]
    guilds = load_guilds()
    mine = guild_of(player.name, guilds)
    if event == guild.STATUS:
        name = guild.read_name(data).strip()
        g = guild_of(name, guilds) if name else None
        if g is None:
            state["send"](guild.status(name, "", 0))          # "That player is not in a Guild."
            return
        who = next(m for m in g["members"] if m.lower() == name.lower())
        state["send"](guild.status(who, g["name"], g["members"][who]))
        return
    if mine is None:
        reply(zone.zone_event(0x0E, struct.pack("<h", 0x1A)))          # NoGuild
        return
    rank = mine["members"][next(m for m in mine["members"] if m.lower() == player.name.lower())]
    if event == guild.MEMBER_LIST:
        for m in guild.member_list([guild_member(mine, n) for n in mine["members"]]):
            reply(m)
    elif event == guild.MOTD_VIEW:
        if mine.get("motd"):
            reply(guild.motd(mine["motd"], mine.get("motd_by", ""), mine.get("motd_time", 0)))
        else:
            reply(build_system_text("Your guild has no message of the day.", SYSTEM_TEXT_WHITE))
    elif event == guild.MOTD_SET:
        if rank < guild.OFFICER:
            reply(build_system_text("You don't have permission to set the guild MOTD.", SYSTEM_TEXT_ERROR))
            return
        mine["motd"] = guild.read_name(data).strip()
        mine["motd_by"], mine["motd_time"] = player.name, int(time.time())
        save_guilds(guilds)
        guild_broadcast(player.name, lambda g: guild.motd(g["motd"], g["motd_by"], g["motd_time"]))
    elif event == guild.RENAME_RANK and len(data) >= 8:
        # i32 name byte length, i32 rank, wstr name (seen live: 06 00 00 00 01 00 00 00 "Pup").
        number = struct.unpack_from("<i", data, 4)[0]
        new = guild.read_name(data[8:]).strip()
        if rank != guild.LEADER or not 1 <= number <= 10 or not new:
            reply(build_system_text("You can't rename that rank.", SYSTEM_TEXT_ERROR))
            return
        ranks = list(mine.get("ranks") or guild.RANK_NAMES)
        ranks[number - 1] = new[:32]
        # 0x4de prints "Guild rank %s has been renamed to %s." with the new name twice
        # (the client renames before formatting), so say it ourselves.
        old = (mine.get("ranks") or guild.RANK_NAMES)[number - 1]
        guild_broadcast(player.name, lambda g: build_system_text(
            f"Guild rank {old} has been renamed to {new[:32]}.", SYSTEM_TEXT_WHITE))
        mine["ranks"] = ranks
        save_guilds(guilds)
        guild_broadcast(player.name, lambda g: guild.info(g["name"], ranks))


BROTHERHOODS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brotherhoods.json")


def load_brotherhoods():
    try:
        with open(BROTHERHOODS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_brotherhoods(bhs):
    with open(BROTHERHOODS_FILE, "w", encoding="utf-8") as f:
        json.dump([b for b in bhs if len(b["members"]) > 1], f, indent=2)


def brotherhood_of(name, bhs=None):
    """The brotherhood {leader, members: [names]} name belongs to, or None."""
    return next((b for b in (bhs if bhs is not None else load_brotherhoods())
                 if name.lower() in [m.lower() for m in b["members"]]), None)


def bh_member(b, name):
    s = ONLINE.get(name.lower())
    p = s["player"] if s and s.get("player") else None
    return {"id": social_uid(name), "name": name, "level": p.level_number if p else 1,
            "klass": p.klass if p else 0, "online": p is not None,
            "leader": name.lower() == b["leader"].lower(), "note": b.get("notes", {}).get(name, "")}


def bh_send_all(b, make, exclude=None):
    for m in b["members"]:
        s = ONLINE.get(m.lower())
        if s is not None and s is not exclude and s.get("send"):
            s["send"](make(m))


def brotherhood_window(state, b):
    """Status, name and the full member list for one player."""
    player, send = state["player"], state["send"]
    leader = b["leader"].lower() == player.name.lower()
    send(brotherhood.status(brotherhood.LEADER if leader else brotherhood.MEMBER))
    send(brotherhood.name(b.get("name", f"{b['leader']}'s Brotherhood")))
    for m in b["members"]:
        send(brotherhood.member_add(bh_member(b, m)))
    if b.get("motd"):
        send(brotherhood.motd(b["motd"], social_uid(b.get("motd_by", b["leader"]))))
        send(build_system_text(f"Brotherhood MOTD: {b['motd']}", SYSTEM_TEXT_WHITE))


def brotherhood_login(state):
    b = brotherhood_of(state["player"].name)
    if b is None:
        state["send"](brotherhood.status(brotherhood.NOT_ACTIVE))
    else:
        brotherhood_window(state, b)


def handle_brotherhood(state, event, data):
    """Invite / accept / decline (zone) and leave (world social 0x4c0)."""
    player, send = state["player"], state["send"]
    print(f"  >>> brotherhood {event:#x}: {data[:40].hex(' ')}")
    bhs = load_brotherhoods()
    mine = brotherhood_of(player.name, bhs)
    if event == brotherhood.INVITE:
        name = social.read_name(data).strip()
        target = ONLINE.get(name.lower())
        if not name:
            return
        if target is state:
            send(zone.zone_event(0x0E, struct.pack("<h", brotherhood.ERR_SELF)))
        elif mine and mine["leader"].lower() != player.name.lower():
            send(zone.zone_event(0x0E, struct.pack("<h", brotherhood.ERR_NOT_LEADER)))
        elif mine and len(mine["members"]) >= brotherhood.MAX_MEMBERS:
            send(zone.zone_event(0x0E, struct.pack("<h", brotherhood.ERR_FULL)))
        elif target is None or not target.get("player"):
            send(build_system_text(f"{name} is not online.", SYSTEM_TEXT_ERROR))
        elif brotherhood_of(target["player"].name, bhs):
            send(build_system_text(f"{target['player'].name} is already in a brotherhood.", SYSTEM_TEXT_ERROR))
        else:
            target["bh_invite"] = player.name
            target["send"](brotherhood.invite(player.name))
            send(build_system_text(f"You invite {target['player'].name} to join your brotherhood.",
                                   SYSTEM_TEXT_WHITE))
    elif event == brotherhood.ACCEPT and state.get("bh_invite") and mine is None:
        inviter = state.pop("bh_invite")
        b = brotherhood_of(inviter, bhs)
        if b is None:
            b = {"leader": inviter, "members": [inviter], "name": f"{inviter}'s Brotherhood"}
            bhs.append(b)
            s = ONLINE.get(inviter.lower())
            if s is not None and s.get("send"):
                brotherhood_window(s, b)
        if len(b["members"]) >= brotherhood.MAX_MEMBERS:
            send(zone.zone_event(0x0E, struct.pack("<h", brotherhood.ERR_FULL)))
            return
        b["members"].append(player.name)
        save_brotherhoods(bhs)
        brotherhood_window(state, b)
        bh_send_all(b, lambda m: brotherhood.member_add(bh_member(b, player.name)), exclude=state)
        bh_send_all(b, lambda m: build_system_text(f"{player.name} has joined the brotherhood.",
                                                   SYSTEM_TEXT_WHITE))
    elif event == brotherhood.DECLINE:
        inviter = state.pop("bh_invite", None)
        s = ONLINE.get((inviter or "").lower())
        if s is not None and s.get("send"):
            s["send"](build_system_text(f"{player.name} declined your brotherhood invitation.", SYSTEM_TEXT_WHITE))
    elif event == brotherhood.LEAVE and mine:
        bh_remove(bhs, mine, player.name, kicked=False)
    elif event in (brotherhood.REMOVE, brotherhood.PROMOTE) and mine and len(data) >= 4:
        uid = struct.unpack_from("<i", data)[0]
        who = next((m for m in mine["members"] if social_uid(m) == uid), None)
        if mine["leader"].lower() != player.name.lower():
            send(build_system_text("Only the brotherhood leader can do that.", SYSTEM_TEXT_ERROR))
        elif who is None or who.lower() == player.name.lower():
            pass
        elif event == brotherhood.REMOVE:
            bh_remove(bhs, mine, who, kicked=True)
        else:
            mine["leader"] = who
            save_brotherhoods(bhs)
            bh_send_all(mine, lambda m: brotherhood.new_leader(uid))
            for n in (who, player.name):
                bh_send_all(mine, lambda m, n=n: brotherhood.member_add(bh_member(mine, n)))
            bh_send_all(mine, lambda m: brotherhood.status(
                brotherhood.LEADER if m.lower() == who.lower() else brotherhood.MEMBER))
    elif event in (brotherhood.MOTD, brotherhood.RENAME) and mine:
        text = brotherhood.read_text(data).strip()[:64]
        if mine["leader"].lower() != player.name.lower():
            send(build_system_text("Only the brotherhood leader can do that.", SYSTEM_TEXT_ERROR))
        elif event == brotherhood.MOTD:
            mine["motd"], mine["motd_by"] = text, player.name
            save_brotherhoods(bhs)
            bh_send_all(mine, lambda m: brotherhood.motd(text, social_uid(player.name)))
            bh_send_all(mine, lambda m: build_system_text(f"Brotherhood MOTD: {text}", SYSTEM_TEXT_WHITE))
        elif text:
            mine["name"] = text
            save_brotherhoods(bhs)
            bh_send_all(mine, lambda m: brotherhood.name(text))
            bh_send_all(mine, lambda m: build_system_text(f"Your brotherhood is now called {text}.",
                                                          SYSTEM_TEXT_WHITE))
    elif event == brotherhood.NOTE and mine:
        text = brotherhood.read_text(data).strip()[:64]
        mine.setdefault("notes", {})[player.name] = text
        save_brotherhoods(bhs)
        bh_send_all(mine, lambda m: brotherhood.note(text, social_uid(player.name)))


def bh_remove(bhs, mine, name, kicked):
    """name leaves (or is kicked from) mine. The client prints "%s has left the
    brotherhood." / "%s has been kicked from the brotherhood." from 0x6e7."""
    uid = social_uid(name)
    bh_send_all(mine, lambda m: brotherhood.member_left(uid, kicked))
    mine["members"] = [m for m in mine["members"] if m.lower() != name.lower()]
    mine.get("notes", {}).pop(name, None)
    s = ONLINE.get(name.lower())
    if s is not None and s.get("send"):
        s["send"](brotherhood.status(brotherhood.NOT_ACTIVE))
    if mine["leader"].lower() == name.lower() and mine["members"]:
        mine["leader"] = mine["members"][0]
        bh_send_all(mine, lambda m: brotherhood.new_leader(social_uid(mine["leader"])))
    if len(mine["members"]) < 2:
        for m in mine["members"]:
            s = ONLINE.get(m.lower())
            if s is not None and s.get("send"):
                s["send"](brotherhood.status(brotherhood.NOT_ACTIVE))
        bhs.remove(mine)
    save_brotherhoods(bhs)


def handle_social_world(zone_state, event, data, reply):
    """World type 5: /who, /friend, /ignore."""
    player = zone_state["player"]
    if event == brotherhood.LEAVE:
        handle_brotherhood(zone_state, event, data)
        return
    if event in guild.WORLD_EVENTS:
        handle_guild_world(zone_state, event, data, reply)
        return
    if event == social.WHO:
        f = social.parse_who(data)
        found = [e for e in (social_entry(s["player"].name) for s in ONLINE.values() if s.get("player"))
                 if social.who_matches(f, e)]
        for m in social.who_messages(found):
            reply(m)
    elif event in (social.FRIEND, social.IGNORE) and data:
        name = social.read_name(data).strip()
        if not name:
            return
        known = {c["first"].lower(): c["first"] for c in load_characters()}
        if name.lower() not in known:
            reply(build_system_text(f"There is no character named {name}.", SYSTEM_TEXT_ERROR))
            return
        name = known[name.lower()]
        field = "friends" if event == social.FRIEND else "ignores"
        names = getattr(player, field, None)
        if names is None:
            names = []
            setattr(player, field, names)
        entry = social_entry(name)
        uid = entry["uid"]
        if name.lower() in [n.lower() for n in names]:
            names[:] = [n for n in names if n.lower() != name.lower()]
            reply(social.friend_removed(entry, uid) if event == social.FRIEND else social.ignore_removed(entry, uid))
        else:
            names.append(name)
            reply(social.friend_added(entry, uid) if event == social.FRIEND else social.ignore_added(entry, uid))
        save_character_field(player.name, field, names)


def handle_social_zone(state, event, data):
    """Zone events: /afk, /anon, /lfg flags, /random, /inspect."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE social {event:#x}: {data.hex(' ')}")
    if event == social.AFK and data:
        player.afk = bool(data[0])
        send(build_system_text("You are now AFK." if player.afk else "You are no longer AFK.",
                               SYSTEM_TEXT_WHITE))
    elif event == social.ANON:
        player.anon = not getattr(player, "anon", False)
        send(build_system_text("You are now anonymous." if player.anon else "You are no longer anonymous.",
                               SYSTEM_TEXT_WHITE))
    elif event == social.LFG and data:
        player.lfg = bool(data[0])
        send(build_system_text("You are now looking for a group." if player.lfg
                               else "You are no longer looking for a group.", SYSTEM_TEXT_WHITE))
    elif event == social.RANDOM and len(data) >= 8:
        lo, hi = struct.unpack_from("<ii", data, 0)
        lo, hi = (lo, hi) if lo <= hi else (hi, lo)
        text = f"**A Magic Die is rolled by {player.name}. It could have been any number from {lo} to {hi}, " \
               f"but this time it turned up a {random.randint(lo, hi)}."
        w = state.get("world")
        if w is not None:
            w.broadcast(lambda s: build_system_text(text, SYSTEM_TEXT_WHITE))
        else:
            send(build_system_text(text, SYSTEM_TEXT_WHITE))
    elif event == social.INSPECT:
        name = social.read_name(data).strip()
        target = ONLINE.get(name.lower()) if name else None
        if target is None and player.target is not None:
            target = next((s for s in ONLINE.values() if s.get("player") and s["player"].char_id == player.target),
                          None)
        if target is None or target.get("world") is not state.get("world"):
            send(build_system_text("You must target a player to inspect.", SYSTEM_TEXT_ERROR))
            return
        t = target["player"]
        dur = getattr(t, "durability", {})
        records = [vgmsg.inventory_item(item_id, n, slot, zone.item_icon(n, icon), equip_slot=slot,
                                        **zone.item_equip_fields(n, dur.get(str(item_id), 100)))
                   for item_id, n, icon, slot in t.equipment]
        for m in social.inspect_messages(t.name, races_classes.class_name(t.klass), t.level_number, records):
            send(m)


def group_states(player):
    g = getattr(player, "group", None)
    return [ONLINE[m.name.lower()] for m in g.members if m.name.lower() in ONLINE] if g else []


def handle_group_event(state, event, payload):
    """Client group commands (group.CLIENT_EVENTS); see group.py."""
    player = state["player"]
    send = state["send"]
    text = payload[10:].decode("utf-16-le", "replace").split(chr(0))[0] if len(payload) > 10 else ""
    if event == group.INVITE:
        name = text
        if not name and player.target:
            other = next((s for s in ONLINE.values() if s["player"].char_id == player.target), None)
            name = other["player"].name if other else ""
        target = ONLINE.get(name.lower())
        g = getattr(player, "group", None)
        if target is None or target is state:
            send(build_system_text(f"{name or 'That player'} is not online.", SYSTEM_TEXT_ERROR))
        elif g and g.leader is not player:
            send(group.error(1))
        elif getattr(target["player"], "group", None):
            send(group.error(2))
        elif g and len(g.members) >= group.MAX_MEMBERS:
            send(group.error(3))
        else:
            target["player"].pending_invite = state
            target["send"](group.invite_popup(player, g.members if g else [player]))
        print(f"  >>> ZONE group invite {name!r} from {player.name}")
    elif event in (group.ACCEPT, group.DECLINE):
        inviter = getattr(player, "pending_invite", None)
        player.pending_invite = None
        print(f"  >>> ZONE group {'accept' if event == group.ACCEPT else 'decline'} by {player.name}")
        if inviter is None or inviter.get("player") is None:
            return
        if ONLINE.get(inviter["player"].name.lower()) is not inviter:
            return      # the inviter logged out meanwhile
        if event == group.DECLINE:
            inviter["send"](group.declined(player.name))
            return
        leader = inviter["player"]
        g = getattr(leader, "group", None)
        if getattr(player, "group", None):
            send(group.error(2))
            return
        if g and len(g.members) >= group.MAX_MEMBERS:
            send(group.error(3))
            return
        if g is None:
            g = leader.group = group.Group(leader)
            inviter["send"](group.formed(g))
        for m_state in group_states(leader):
            m_state["send"](group.member_added(player))
            send(group.member_added(m_state["player"]))
        g.members.append(player)
        player.group = g
        send(group.leader_is(g.leader))
    elif event == group.LEAVE:
        leave_group(state)
    elif event == group.DISBAND:
        g = getattr(player, "group", None)
        if g and g.leader is player:
            for m_state in group_states(player):
                m_state["send"](group.disbanded())
                m_state["player"].group = None


def leave_group(state):
    player = state["player"]
    g = getattr(player, "group", None)
    if g is None:
        return
    player.group = None
    g.members.remove(player)
    if "send" in state:
        state["send"](group.you_left())
    if len(g.members) <= 1:
        for m_state in [ONLINE[m.name.lower()] for m in g.members if m.name.lower() in ONLINE]:
            m_state["send"](group.disbanded())
            m_state["player"].group = None
        return
    if g.leader is player:
        g.leader = g.members[0]
    for m_state in [ONLINE[m.name.lower()] for m in g.members if m.name.lower() in ONLINE]:
        m_state["send"](group.member_left(player))
        m_state["send"](group.leader_is(g.leader))


def group_tick():
    """Once a second: members' positions and vitals to the rest of the group."""
    for state in list(ONLINE.values()):
        player = state.get("player")
        if not getattr(player, "group", None) or "send" not in state:
            continue
        for m_state in group_states(player):
            if m_state is not state:
                state["send"](group.member_position(m_state["player"]))
                for m in group.member_vitals(m_state["player"]):
                    state["send"](m)


CHUNK_CHANGE_EVENT = 0x9
CHUNK_SIZE = 204800.0


def chunk_handoff(state, payload, args):
    """Client zone event 0x9 {i32 chunk x, i32 chunk y, u8 cmd, ...} after the
    player crossed a chunk edge (sender FUN_00b71570). The client expects a full
    zone re-connect to the new chunk (world event 8 -> HELLO..WELCOME
    LEVEL=<new chunk>); its ChangeChunkMap keeps the streamed level and puts the
    new pawn at the travel location. Coordinates are per chunk: x grows with
    chunk x, y shrinks with chunk y (docs/PROTOCOL.md, Chunk travel)."""
    player = state.get("player")
    cx, cy = struct.unpack_from("<ii", payload, 10)
    if player is None:
        return
    old = getattr(player, "chunk", None) or DEFAULT_CHUNK
    loc = state.get("position") or player.spawned_at
    if loc is None or (cx, cy) == tuple(old):
        return
    dx, dy = cx - old[0], cy - old[1]
    # The last ClientLoc is usually still on the old side of the edge, so keep the
    # new position just inside the new chunk (the client logs its own TRAVLoc).
    edge = CHUNK_SIZE / 2 - 1000    # the heightmap ends one cell (400) before the edge
    x = max(-edge, min(edge, loc[0] - dx * CHUNK_SIZE))
    y = max(-edge, min(edge, loc[1] + dy * CHUNK_SIZE))
    level = chunk_name(cx, cy)
    z = args.content.ground_z(level, x, y, args.client_dir)
    print(f"  >>> ZONE chunk change {tuple(old)} -> ({cx}, {cy}): {level} at ({x:.0f}, {y:.0f}, {z:.0f})")
    player.chunk, player.level = (cx, cy), level
    player.position = (x, y, z + zone.SPAWN_Z_LIFT)
    player.spawned_at, player.live_position = None, None
    save_character_field(player.name, "chunk", [cx, cy])
    save_character_field(player.name, "position", list(player.position))
    save_character_field(player.name, "position_chunk", [cx, cy])
    # The coming zone disconnect is a handoff, not a logout: keep the group and
    # let the new zone login claim the same Player.
    state["handoff"] = True
    leave_world(state, args)
    PENDING_PLAYERS[state.get("session", "")] = player
    world_send(state, build_zone_connect_event(args.world_address, args.zone_port, level))


def handle_trade_event(state, event, payload, args):
    """Player trade (trade.py)."""
    player, send = state["player"], state["send"]
    t = state.get("trade")
    if event == trade.INVITE:
        name = payload[10:].decode("utf-16-le", "replace").split(chr(0))[0] if len(payload) > 10 else ""
        if not name and player.target:
            other = next((s for s in ONLINE.values() if s["player"].char_id == player.target), None)
            name = other["player"].name if other else ""
        target = ONLINE.get(name.lower())
        print(f"  >>> ZONE trade invite {name!r} from {player.name}")
        if (target is None or target is state or target.get("trade") or target.get("trade_invite")
                or t is not None or state.get("trade_invite_to")):
            send(build_system_text(f"You can't trade with {name or 'that'} right now.", SYSTEM_TEXT_ERROR))
            return
        target["trade_invite"] = state
        state["trade_invite_to"] = target
        target["send"](trade.invited(player.name))
    elif event in (trade.ACCEPT_INVITE, trade.DECLINE, trade.BUSY):
        inviter = state.pop("trade_invite", None)
        if inviter is None:
            return
        inviter.pop("trade_invite_to", None)
        if event != trade.ACCEPT_INVITE:
            inviter["send"](trade.declined())
            return
        if t is not None or inviter.get("trade"):
            send(trade.cancelled())     # closes the window the client opened on 0xc3
            inviter["send"](trade.declined())
            return
        t = trade.Trade(inviter, state)
        inviter["trade"] = state["trade"] = t
        inviter["send"](trade.open_window(player.name))
        print(f"  trade opened: {inviter['player'].name} <-> {player.name}")
    elif event == trade.CANCEL_INVITE:
        target = state.pop("trade_invite_to", None)
        if target is not None:
            target.pop("trade_invite", None)
            target["send"](trade.invite_cancelled())
    elif t is None:
        return
    elif event == trade.CANCEL:
        end_trade(t, trade.cancelled())
    elif event in (trade.ADD, trade.REMOVE, trade.COIN):
        side, other = t.side(state), t.other(state)
        changed = False
        if event == trade.ADD:
            handle, _seq, qty = struct.unpack_from("<iii", payload, 10)
            item = next((i for i in player.items if i[0] == handle), None)
            if item and handle not in side.items and len(side.items) < trade.MAX_ITEMS:
                side.items.append(handle)
                t.seq += 1
                send(trade.my_item(t.seq, len(side.items) - 1, handle))
                other["send"](trade.their_item(t_item_record(item, t.seq)))
                changed = True
            elif item is None:
                send(trade.refused(1))
        elif event == trade.REMOVE:
            handle = struct.unpack_from("<i", payload, 10)[0]
            if handle in side.items:
                side.items.remove(handle)
                t.seq += 1
                send(trade.my_item_removed(t.seq, handle))
                other["send"](trade.their_item_removed(t.seq, handle))
                changed = True
        else:
            copper = struct.unpack_from("<q", payload, 10)[0]
            side.coins = max(0, min(copper, player.coins))
            t.seq += 1
            send(trade.my_coins(side.coins, t.seq))
            other["send"](trade.their_coins(side.coins, t.seq))
            changed = True
        if changed and any(sd.accepted for _, sd in t.pairs):
            for s_state, s_side in t.pairs:
                s_side.accepted = False
                s_state["send"](trade.reset_accepts(t.seq))
    elif event == trade.ACCEPT:
        seq = struct.unpack_from("<i", payload, 10)[0]
        if seq != t.seq:
            return
        t.side(state).accepted = True
        send(trade.i_accepted(t.seq))
        t.other(state)["send"](trade.they_accepted(t.seq))
        if all(sd.accepted for _, sd in t.pairs):
            complete_trade(t, args)


def t_item_record(item, seq):
    item_id, name, icon, qty, _slot = item
    return vgmsg.inventory_item(item_id, name, 0, icon, qty, container=seq,
                                **zone.item_equip_fields(name))


def end_trade(t, message):
    for s_state, _ in t.pairs:
        s_state.pop("trade", None)
        s_state["send"](message)


def complete_trade(t, args):
    """Both accepted: move the offered items and coins, then 0x201."""
    (a, sa), (b, sb) = t.pairs
    moves = []
    for giver, side, taker in ((a, sa, b), (b, sb, a)):
        for handle in side.items:
            item = next((i for i in giver["player"].items if i[0] == handle), None)
            if item:
                moves.append((giver, item, taker))
    # Check both bags first so a full bag cancels the whole trade, not half of it.
    for s_state in (a, b):
        p = s_state["player"]
        incoming = sum(1 for _, _, tk in moves if tk is s_state)
        outgoing = sum(1 for gv, _, _ in moves if gv is s_state)
        if len(p.items) - outgoing + incoming > zone.BAG_SLOTS:
            s_state["send"](build_system_text("Your bags are full.", SYSTEM_TEXT_ERROR))
            end_trade(t, trade.cancelled())
            return
    for giver, item, taker in moves:
        giver["player"].items.remove(item)
        giver["send"](zone.zone_event(0x1A5, struct.pack("<iB", item[0], 0)))
    for giver, item, taker in moves:
        tp = taker["player"]
        slot = zone.free_bag_slot(tp)
        new_id = zone.new_item_id(tp)
        tp.items.append((new_id, item[1], item[2], item[3], slot))
        wear = getattr(giver["player"], "durability", {}).pop(str(item[0]), None)
        if wear is not None and hasattr(tp, "durability"):
            tp.durability[str(new_id)] = wear
        taker["send"](zone.zone_event(0x197, vgmsg.inventory_item(
            new_id, item[1], slot, item[2], item[3], **zone.item_equip_fields(item[1]))))
    for giver, side, taker in ((a, sa, b), (b, sb, a)):
        amount = min(side.coins, giver["player"].coins)
        giver["player"].coins -= amount
        taker["player"].coins += amount
    for s_state in (a, b):
        p = s_state["player"]
        s_state["send"](merchant.coins(p.coins))
        save_character_field(p.name, "items", [list(i) for i in p.items])
        save_character_field(p.name, "coins", p.coins)
        quest_items_changed(s_state)
    end_trade(t, trade.done())
    print("  trade completed")


def npc_dialog(state, npc):
    """Dialogue window for a talking NPC: greeting, quest options, merchant option."""
    player, content_ = state["player"], ARGS.content
    log = player.quests
    out, opts, greeting = [], [], None
    tpl = npc.template_id
    greeting = quest_talk(state, npc)
    have = have_items(player)
    for key, q in content_.quests.items():
        if key in log.done:
            continue
        if key in log.active:
            prog = log.active[key]
            if quest.ready(q, prog, have) and quest.turn_in(q) == tpl:
                opts.append((f"{q['name']} (complete)", q["id"], quest.OPTION_TYPE))
            elif q.get("giver") == tpl:
                opts.append((f"{q['name']} (in progress)", q["id"], quest.OPTION_TYPE))
        elif q.get("giver") == tpl and all(r in log.done for r in q.get("requires", [])):
            opts.append((q["name"], q["id"], quest.OPTION_TYPE))
            greeting = greeting or q.get("greeting")
    # Start clean: 0x55f closes an open Dialogue window and frees all its options
    # (0x2bf only replaces quest options), and an empty 0x3ea clears the text
    # (0x3ea appends). Not during a parley: 0x55f would ask to leave it.
    if not state.get("parley"):
        out.append(zone.zone_event(quest.END_CONVERSATION))
    out.append(quest.npc_text(npc.entity_id, ""))
    out.append(quest.npc_text(npc.entity_id, greeting or f"Greetings, {player.name}."))
    if npc.parley:
        opts.append(("Let's talk business. (Parley)", diplomacy.PARLEY_OPTION_ID,
                     diplomacy.OPTION_TYPE))
    if task_master_option(npc):
        opts.append(task_master_option(npc))
    if opts:
        out.append(quest.options(npc.entity_id, opts))
    if npc.merchant:
        out.append(zone.zone_event(merchant.DIALOG_WARES))
    if npc.repairs:
        out.append(zone.zone_event(merchant.DIALOG_REPAIR))
    if npc.trainer:
        out.append(zone.zone_event(trainer.OPTION))
    if npc.recipe_trainer:
        out.append(zone.zone_event(trainer.RECIPE_OPTION))
    if npc.banker:
        out.append(zone.zone_event(bank.OPTION))
    return out


def task_master_option(npc):
    return ("I'm looking for work. (Work orders)", workorder.OPTION_ID, workorder.OPTION_TYPE) \
        if getattr(npc, "task_master", False) else None


def quest_by_id(qid):
    return next(((k, q) for k, q in ARGS.content.quests.items() if q["id"] == qid), (None, None))


def have_items(player):
    """have(name) -> how many of that item are in the player's bags."""
    return lambda name: sum(i[3] for i in player.items if i[1] == name)


def handle_quest_event(state, event, payload):
    player, send = state["player"], state["send"]
    log = player.quests
    qid = struct.unpack_from("<i", payload, 10)[0] if len(payload) >= 14 else -1
    key, q = quest_by_id(qid)
    print(f"  >>> ZONE quest event {event:#x} quest {qid} ({key})")
    if q is None:
        return
    npc = player.npcs.get(player.target) if player.target else None
    npc_eid = npc.entity_id if npc else 0
    tpl = npc.template_id if npc else None
    have = have_items(player)
    if event == quest.CLICK_OPTION:
        if key in log.active:
            prog = log.active[key]
            if quest.ready(q, prog, have) and tpl == quest.turn_in(q):
                finish_quest(state, key, q)
            else:
                send(quest.page(q, npc_eid, quest.IN_PROGRESS, prog, have=have))
        elif key not in log.done and tpl == q.get("giver"):
            send(quest.page(q, npc_eid, quest.OFFER))
    elif event == quest.ACCEPT and key not in log.active and key not in log.done:
        # Only from the giver, and only once the quests it requires are done.
        if tpl != q.get("giver") or not all(r in log.done for r in q.get("requires", [])):
            return
        log.active[key] = quest.new_progress()
        send(quest.accepted(q))
        send(quest.page(q, npc_eid, quest.IN_PROGRESS, log.active[key], journal=True, have=have))
        save_character_field(player.name, "quests", log.to_json())
        quest_advance(state, key, q, npc_eid, quiet=True)
    elif event == quest.REQUEST_INFO and key in log.active:
        send(quest.page(q, npc_eid, quest.IN_PROGRESS, log.active[key], journal=True, have=have))
    elif event in (quest.CONTINUE, quest.COMPLETE) and key in log.active:
        if quest.ready(q, log.active[key], have) and tpl == quest.turn_in(q):
            finish_quest(state, key, q)


def quest_advance(state, key, q, source_eid, quiet=False):
    """Move past finished steps and update the tracker. quiet: only send an
    update if the step changed (e.g. right after accepting)."""
    player = state["player"]
    prog = player.quests.active[key]
    st, have = quest.steps(q), have_items(player)
    before = dict(prog)
    while prog["step"] < len(st) - 1 and quest.step_done(st[prog["step"]], prog, have):
        prog["step"] += 1
        prog["count"] = 0
    if quiet and prog == before:
        return
    state["send"](quest.progress_update(q, source_eid, prog, quest.ready(q, prog, have), have))
    save_character_field(player.name, "quests", player.quests.to_json())


def finish_quest(state, key, q):
    player, send = state["player"], state["send"]
    # Items gathered for "collect" steps are handed over.
    have = have_items(player)
    for step in quest.steps(q):
        for name, n in step.get("collect", {}).items():
            if have(name) < n:
                send(build_system_text(f"You need {n} {name}.", SYSTEM_TEXT_ERROR))
                return
    reward_items = q.get("reward", {}).get("items", [])
    if zone.BAG_SLOTS - len(player.items) < len(reward_items):
        send(build_system_text("You need more room in your bags for the reward.", SYSTEM_TEXT_ERROR))
        return
    for step in quest.steps(q):
        for name, n in step.get("collect", {}).items():
            take_items(state, name, n)
    del player.quests.active[key]
    player.quests.done.add(key)
    send(quest.finished(q))
    reward = q.get("reward", {})
    if reward.get("coin"):
        player.coins += reward["coin"]
        send(merchant.coins(player.coins))
        save_character_field(player.name, "coins", player.coins)
    for name in reward.get("items", []):
        give_item(state, name)
    if reward.get("xp"):
        for m in award_xp(player, reward["xp"], player.char_id):
            send(m)
    faction_reward(state, reward)
    save_character_field(player.name, "quests", player.quests.to_json())
    print(f"  {player.name} completed quest {q['name']}")


def quest_kill(state, npc):
    """Count a kill toward the current kill step of the player's active quests."""
    player = state["player"]
    for key, prog in list(player.quests.active.items()):
        q = ARGS.content.quests.get(key)
        st = quest.steps(q) if q else []
        if prog["step"] >= len(st):
            continue
        step = st[prog["step"]]
        if npc.template_id not in step.get("kill", {}) or prog["count"] >= quest.step_need(step):
            continue
        prog["count"] += 1
        quest_advance(state, key, q, npc.entity_id)


def quest_talk(state, npc):
    """Talking to an NPC finishes a current "talk" step for it. Returns that
    step's "say" text (the NPC's line) or None."""
    player = state["player"]
    line = None
    for key, prog in list(player.quests.active.items()):
        q = ARGS.content.quests.get(key)
        st = quest.steps(q) if q else []
        if prog["step"] < len(st) and st[prog["step"]].get("talk") == npc.template_id \
                and prog["count"] == 0:
            prog["count"] = 1
            line = line or st[prog["step"]].get("say")
            quest_advance(state, key, q, npc.entity_id)
    return line


def quest_items_changed(state):
    """Bags changed: update quests whose current step collects items."""
    player = state.get("player")
    if player is None or not hasattr(player, "quests"):
        return
    for key, prog in list(player.quests.active.items()):
        q = ARGS.content.quests.get(key)
        st = quest.steps(q) if q else []
        if prog["step"] < len(st) and "collect" in st[prog["step"]]:
            quest_advance(state, key, q, player.char_id)


def give_item(state, name, qty=1, quiet=False):
    """Put a new item in the player's bags; False if they are full."""
    player, send = state["player"], state["send"]
    slot = zone.free_bag_slot(player)
    if slot is None:
        send(build_system_text("Your bags are full.", SYSTEM_TEXT_ERROR))
        return False
    item_id, icon = zone.new_item_id(player), zone.item_icon(name, 443)
    player.items.append((item_id, name, icon, qty, slot))
    send(zone.zone_event(0x197, vgmsg.inventory_item(item_id, name, slot, icon, qty,
                                                     **zone.item_equip_fields(name))))
    if not quiet:
        send(build_system_text(f"You receive {name}." if qty == 1 else f"You receive {qty} {name}.",
                               SYSTEM_TEXT_WHITE))
    save_character_field(player.name, "items", [list(i) for i in player.items])
    return True


def take_items(state, name, need):
    """Remove `need` of an item from the bags (whole stacks first come first)."""
    player, send = state["player"], state["send"]
    for item in [i for i in player.items if i[1] == name]:
        if need <= 0:
            break
        take = min(need, item[3])
        need -= take
        if take == item[3]:
            player.items.remove(item)
            send(zone.zone_event(0x1A5, struct.pack("<iB", item[0], 0)))
        else:
            player.items[player.items.index(item)] = item[:3] + (item[3] - take, item[4])
            send(zone.zone_event(0x1AE, struct.pack("<ii", item[0], item[3] - take)))
    save_character_field(player.name, "items", [list(i) for i in player.items])


def handle_harvest_event(state, event):
    """0x109 begin harvesting the target node, 0x10a stop (harvest.py)."""
    player, send = state["player"], state["send"]
    if event == harvest.STOP:
        if state.pop("harvest", None):
            send(harvest.ended())
        return
    npc = player.npcs.get(player.target) if player.target else None
    print(f"  >>> ZONE harvest {npc.name if npc else None}")
    if npc is None or not npc.harvest:
        send(harvest.error(0x7C))
    elif state.get("harvest"):
        send(harvest.error(harvest.ERR_ALREADY))
    elif time.time() < npc.depleted_until:
        send(harvest.error(harvest.ERR_HARVESTED))
    elif not harvest_tool(player, npc.harvest["kind"]):
        send(harvest.tool_failed(npc.harvest.get("tool", "Mining")))
    elif player_skill(player, harvest.SKILLS[npc.harvest["kind"]]) < npc.harvest.get("skill", 1):
        send(harvest.error(harvest.ERR_NEED_SKILL))
    else:
        state["harvest"] = {"npc": npc, "step": 0, "next": time.time() + harvest.STRIKE_SECONDS}
        send(harvest.open_window(npc, npc.harvest["kind"]))
        send(harvest.begun())


def harvest_tool(player, kind):
    """The equipped harvesting tool (slot 0x35) if it works on this resource kind."""
    for _id, name, _icon, slot in player.equipment:
        tpl = ARGS.content.item(name)
        if slot == vgmsg.EQUIP_SLOTS["HARVESTTOOL"] and tpl.get("harvest") == kind:
            return name
    return None


def player_skill(player, stat_id):
    return next((v for sid, v, _ in player.skills if sid == stat_id), 0)


def skill_up(state, stat_id, name, ceiling):
    """Raise a skill by 1 (up to `ceiling` and the skill cap): stat update 0x2d4
    and a chat line. Saved with the character."""
    player, send = state["player"], state["send"]
    value = player_skill(player, stat_id)
    if value >= min(ceiling, zone.SKILL_CAP):
        return
    player.skills = [(sid, v + 1 if sid == stat_id else v, sub) for sid, v, sub in player.skills]
    send(zone.zone_event(0x2D4, vgmsg.stat_update(stat_id, value + 1, maximum=zone.SKILL_CAP)))
    send(build_system_text(f"Your {name} skill has increased to {value + 1}.", SYSTEM_TEXT_WHITE))
    save_character_field(player.name, "skills", {str(sid): v for sid, v, _ in player.skills})


def harvest_tick(state, now):
    h = state.get("harvest")
    if not h or now < h["next"]:
        return
    player, send, npc = state["player"], state["send"], h["npc"]
    kind = npc.harvest["kind"]
    h["step"] += 1
    h["next"] = now + harvest.STRIKE_SECONDS
    strike = combat.display_ability(player.char_id, npc.entity_id, harvest.STRIKE_VISUALS.get(kind, 20084))
    send(strike)
    if state.get("world"):
        state["world"].broadcast(lambda s: strike, exclude=state)
    remaining = 18.0 * (1 - h["step"] / harvest.STRIKES)
    send(harvest.progress(1.0, max(remaining, 0.0)))
    if h["step"] < harvest.STRIKES:
        return
    state.pop("harvest")
    lo, hi = npc.harvest.get("quantity", [1, 1])
    qty = random.randint(lo, hi)
    name = npc.harvest["item"]
    icon = zone.item_icon(name, 443)
    slot = zone.free_bag_slot(player)
    if slot is not None:
        item_id = zone.new_item_id(player)
        record = vgmsg.inventory_item(item_id, name, slot, icon, qty, **zone.item_equip_fields(name))
        for m in harvest.rewards(item_id, qty, record):
            send(m)
        player.items.append((item_id, name, icon, qty, slot))
        send(zone.zone_event(0x197, record))
        send(build_system_text(f"You harvest {qty} {name}.", SYSTEM_TEXT_WHITE))
        save_character_field(player.name, "items", [list(i) for i in player.items])
        quest_items_changed(state)
        # Skill-ups: likely while the node is still a challenge, rare once trivial.
        skill = player_skill(player, harvest.SKILLS[kind])
        ceiling = npc.harvest.get("difficulty", 10) + 20
        if random.random() < (0.75 if skill < npc.harvest.get("difficulty", 10) + 5 else 0.25):
            skill_up(state, harvest.SKILLS[kind], kind.capitalize(), ceiling)
    else:
        send(build_system_text("Your bags are full.", SYSTEM_TEXT_ERROR))
    send(harvest.ended())
    npc.depleted_until = now + npc.respawn
    depleted = combat.display_ability(npc.entity_id, combat.NO_ENTITY, harvest.NODE_DEPLETED_VISUAL)
    send(depleted)


def faction_value(player, fid):
    f = ARGS.content.factions.get(str(fid), {})
    return getattr(player, "factions", {}).get(str(fid), f.get("start", 0))


def faction_login(state):
    """Fill the Factions window: every faction the character has met or that has a
    standing other than neutral."""
    player = state["player"]
    for fid, f in sorted(ARGS.content.factions.items(), key=lambda kv: kv[1]["name"]):
        state["send"](faction.info(int(fid), f["name"], faction_value(player, fid)))


def adjust_faction(state, fid, delta, quiet=False):
    player = state["player"]
    f = ARGS.content.factions.get(str(fid))
    if f is None or not delta:
        return
    old = faction_value(player, fid)
    new = faction.clamp(old + delta)
    if new == old:
        return
    player.factions = dict(getattr(player, "factions", {}), **{str(fid): new})
    save_character_field(player.name, "factions", player.factions)
    state["send"](faction.change(int(fid), new))
    if not quiet:
        word = "improved" if new > old else "worsened"
        state["send"](build_system_text(f"Your standing with {f['name']} has {word}.", SYSTEM_TEXT_WHITE))
    if faction.tier(new) != faction.tier(old):
        state["send"](build_system_text(f"{f['name']} now regards you as {faction.tier(new)}.",
                                        SYSTEM_TEXT_WHITE))


def faction_kos(player, npc):
    """True when npc's faction holds the player Kill on Sight (it attacks on sight)."""
    fid = getattr(npc, "faction", None)
    if fid is None or npc.service():
        return False
    return faction_value(player, fid) < faction.TIERS[0][0]


def faction_consider(player, npc):
    fid = getattr(npc, "faction", None)
    f = ARGS.content.factions.get(str(fid)) if fid is not None else None
    if f is None or npc.harvest:
        return None
    return build_system_text(f"{npc.name} ({f['name']}) regards you as {faction.tier(faction_value(player, fid))}.",
                             SYSTEM_TEXT_WHITE)


def faction_reward(state, reward):
    for fid, amount in (reward or {}).get("faction", {}).items():
        adjust_faction(state, fid, amount)


def faction_kill(state, npc):
    """Killing a faction member: that faction (and its allies) think less of you,
    its enemies more."""
    fid = getattr(npc, "faction", None)
    f = ARGS.content.factions.get(str(fid)) if fid is not None else None
    if f is None:
        return
    hit = f.get("kill", -50)
    adjust_faction(state, fid, hit)
    for other in f.get("allies", []):
        adjust_faction(state, other, hit)
    for other in f.get("enemies", []):
        adjust_faction(state, other, -hit // 2)


def handle_faction_event(state, event, data):
    """/showfactions [page], /showfactionbyname <name>: list standings in the chat window."""
    player = state["player"]
    say = lambda t: state["send"](build_system_text(t, SYSTEM_TEXT_WHITE))
    rows = sorted(ARGS.content.factions.items(), key=lambda kv: kv[1]["name"])
    if event == faction.SHOW_BY_NAME:
        name = faction.read_name(data).strip().lower()
        rows = [r for r in rows if name in r[1]["name"].lower()]
        if not rows:
            say("No faction by that name.")
            return
    say("Your faction standings:")
    for fid, f in rows:
        v = faction_value(player, fid)
        say(f"  {f['name']}: {faction.tier(v)} ({v})")


MAIL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mail.json")
MAILBOX_RANGE = 800


def load_mail():
    """{"next_id": n, "boxes": {lower-case name: [mail dicts]}}"""
    try:
        with open(MAIL_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"next_id": 1, "boxes": {}}


def save_mail(db):
    with open(MAIL_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)


def deliver_mail(db, to, m):
    """Put mail m in to's box and tell them if they are online."""
    m["id"] = db["next_id"]
    db["next_id"] += 1
    db["boxes"].setdefault(to.lower(), []).append(m)
    s = ONLINE.get(to.lower())
    if s is not None and s.get("send"):
        s["send"](mail.new_mail())
        s["send"](build_system_text(f"You have new mail from {m['from']}.", SYSTEM_TEXT_WHITE))


def mail_login(state):
    box = load_mail()["boxes"].get(state["player"].name.lower(), [])
    unread = sum(1 for m in box if not m.get("read"))
    if unread:
        state["send"](mail.new_mail())            # "You have unread mail messages."


def mail_list(state, box):
    send = state["send"]
    send(mail.clear())
    for m in box:
        send(mail.message(m))
        it = m.get("item")
        if it:
            send(mail.item(vgmsg.inventory_item(m["id"], it["name"], 0, it.get("icon", 443), it.get("qty", 1),
                                                **zone.item_equip_fields(it["name"]))))
    send(mail.redraw())


def handle_mail_event(state, event, data):
    """Mailboxes (mail.py): inbox, read, send with coin / an item / cash on delivery."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE mail event {event:#x}: {data[:16].hex(' ')}")
    db = load_mail()
    box = db["boxes"].setdefault(player.name.lower(), [])
    if event == mail.OPEN:
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not getattr(npc, "mailbox", False):
            send(zone.zone_event(0x0E, struct.pack("<h", mail.PLEASE_TARGET_MAILBOX)))
            return
        if player_distance(player, npc) > MAILBOX_RANGE:
            send(zone.zone_event(0x0E, struct.pack("<h", mail.MOVE_CLOSER)))
            return
        if not state.get("mail_session"):
            send(mail.info())
        state["mail_session"] = True
        mail_list(state, box)
        return
    if event == mail.CLOSE:
        state.pop("mail_session", None)
        return
    if not state.get("mail_session"):
        if event == mail.SEND:
            send(mail.result(mail.BAD_SESSION))
        return
    if event == mail.SEND:
        try:
            to, subject, body, cod, copper, handle = mail.parse_send(data)
        except (struct.error, IndexError):
            send(mail.result(mail.DB_ERROR))
            return
        chars = load_characters()
        target = next((c["first"] for c in chars if c["first"].lower() == to.lower()), None)
        if target is None:
            send(mail.result(mail.NO_RECIPIENT))
            return
        if target.lower() == player.name.lower():
            send(mail.result(mail.SELF))
            return
        if len(subject) > mail.MAX_SUBJECT:
            send(mail.result(mail.SUBJECT_LONG))
            return
        if len(body) > mail.MAX_BODY:
            send(mail.result(mail.BODY_LONG))
            return
        it = next((i for i in player.items if i[0] == handle), None) if handle != -1 else None
        if handle != -1 and it is None:
            send(mail.result(mail.CANT_MAIL_ITEM))
            return
        if cod and it is None:
            send(build_system_text("Cash on delivery needs an attached item.", SYSTEM_TEXT_ERROR))
            send(mail.result(mail.DB_ERROR))
            return
        cost = mail.POSTAGE * 4 // 5 + (mail.SHIPPING * 4 // 5 if it else 0) + (0 if cod else max(0, copper))
        if player.coins < cost:
            send(build_system_text("You can't afford the postage for that.", SYSTEM_TEXT_ERROR))
            send(mail.result(mail.DB_ERROR))
            return
        player.coins -= cost
        send(merchant.coins(player.coins))
        save_character_field(player.name, "coins", player.coins)
        attached = None
        if it is not None:
            attached = {"name": it[1], "icon": it[2], "qty": it[3]}
            player.items.remove(it)
            send(zone.zone_event(0x1A5, struct.pack("<iB", it[0], 0)))
            save_character_field(player.name, "items", [list(i) for i in player.items])
        deliver_mail(db, target, mail.new(0, player.name, subject, body, coin=0 if cod else max(0, copper),
                                          cod=max(0, copper) if cod else 0, item_=attached))
        save_mail(db)
        send(mail.result(mail.SENT))
        print(f"  {player.name} mailed {target}: {subject!r}")
        return
    mid = struct.unpack_from("<i", data)[0] if len(data) >= 4 else 0
    m = next((x for x in box if x["id"] == mid), None)
    if m is None:
        return
    if event == mail.READ:
        if not m.get("read"):
            m["read"] = int(time.time())
            save_mail(db)
    elif event in (mail.DELETE, mail.RETURN):
        box.remove(m)
        if event == mail.RETURN and m.get("from_player", True) and not m.get("returned"):
            back = mail.new(0, player.name, f"Returned: {m.get('subject', '')}"[:mail.MAX_SUBJECT], m.get("body", ""),
                            coin=m.get("coin", 0), item_=m.get("item"), returned=True)
            deliver_mail(db, m["from"], back)
        save_mail(db)
        send(mail.removed(mid))
    elif event in (mail.TAKE_ITEM, mail.TAKE_ITEM_COD) and m.get("item"):
        cod = m.get("cod", 0)
        if cod and player.coins < cod:
            send(build_system_text("You can't afford the cash on delivery price.", SYSTEM_TEXT_ERROR))
            return
        it = m["item"]
        if not give_item(state, it["name"], it.get("qty", 1)):
            return
        if cod:
            player.coins -= cod
            send(merchant.coins(player.coins))
            save_character_field(player.name, "coins", player.coins)
            deliver_mail(db, m["from"], mail.new(0, player.name, f"Payment: {m.get('subject', '')}"[:mail.MAX_SUBJECT],
                                                 f"{player.name} paid for {it['name']}.", coin=cod,
                                                 from_player=False))
            m["cod"] = 0
        m["item"] = None
        save_mail(db)
        send(mail.item_taken(mid))
    elif event == mail.TAKE_COIN and m.get("coin"):
        player.coins += m["coin"]
        send(merchant.coins(player.coins))
        save_character_field(player.name, "coins", player.coins)
        m["coin"] = 0
        save_mail(db)
        send(mail.coin_taken(mid))


def wo_by_id(wid):
    return next(((k, w) for k, w in ARGS.content.workorders.items() if w["id"] == wid), (None, None))


def wo_record(player, w):
    tm = ARGS.content.mobs.get(w["task_master"], {})
    return workorder.record(w, tm.get("name", ""), workorder.con(player_skill(player, w.get("skill", 40)),
                                                                 w.get("difficulty", 1)))


def wo_available(player, npc):
    return [wo_record(player, w) for k, w in ARGS.content.workorders.items()
            if w["task_master"] == npc.template_id and k != getattr(player, "work_order", None)]


def workorder_login(state):
    player = state["player"]
    w = ARGS.content.workorders.get(getattr(player, "work_order", None) or "")
    if w:
        state["send"](workorder.active(wo_record(player, w)))
        state["send"](workorder.needed(w))      # 0x4a7 drops the needed-items text


def set_work_order(state, key):
    player = state["player"]
    player.work_order = key
    save_character_field(player.name, "work_order", key)


def handle_workorder_event(state, event, data):
    """Task master work orders (workorder.py, content/workorders.json)."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE work order event {event:#x}: {data.hex(' ')}")
    npc = player.npcs.get(player.target) if player.target else None
    wid = struct.unpack_from("<i", data)[0] if len(data) >= 4 else -1
    key, w = wo_by_id(wid)
    mine = getattr(player, "work_order", None)
    if event == workorder.REQUEST:
        if npc is None:
            send(workorder.ended(4))
        elif not getattr(npc, "task_master", False):
            send(workorder.ended(workorder.NOT_TASK_MASTER))
        elif player_distance(player, npc) > 1500:
            send(workorder.ended(workorder.TOO_FAR))
        else:
            state["requisition"] = npc.template_id
            offers = wo_available(player, npc)
            send(workorder.open_window())
            send(workorder.available(offers))
            if not offers:
                send(workorder.ended(workorder.NO_WORK))
    elif event == workorder.END:
        state.pop("requisition", None)
        send(workorder.ended(workorder.ENDED))
    elif event == workorder.SELECT:
        if not state.get("requisition"):
            send(workorder.select_result(wid, workorder.NOT_REQUISITIONING))
        elif w is None or w["task_master"] != state["requisition"]:
            send(workorder.select_result(wid, workorder.NOT_AVAILABLE))
        elif mine:
            send(workorder.select_result(wid, workorder.ALREADY_WORKING))
        elif zone.BAG_SLOTS - len(player.items) < len(w.get("supplies", {})):
            send(build_system_text("You need more room in your bags for the work order supplies.",
                                   SYSTEM_TEXT_ERROR))
            send(workorder.select_result(wid, workorder.FAILED))
        else:
            set_work_order(state, key)
            send(workorder.select_result(wid, workorder.OK))
            send(workorder.active(wo_record(player, w)))
            send(workorder.needed(w))
            r = ARGS.content.recipes[w["recipe"]]
            send(craft.learn_recipe(r))
            for n in range(len(craft.all_steps(r))):
                send(craft.learn_action(r, n))
            for c in r.get("complications", []):
                send(craft.learn_counter(c))
            for name, n in w.get("supplies", {}).items():
                give_item(state, name, n)
            send(workorder.available(wo_available(player, npc) if npc else []))
            send(build_system_text(f"You take the work order: {w['name']}. Bring back {workorder.needed_text(w)}.",
                                   SYSTEM_TEXT_WHITE))
    elif event == workorder.COMPLETE:
        if w is None or key != mine:
            send(workorder.complete_result(wid, workorder.NOT_WORKING))
        elif npc is None or npc.template_id != w["task_master"]:
            send(workorder.complete_result(wid, workorder.WRONG_TASK_MASTER))
        elif any(have_items(player)(name) < n for name, n in w["deliver"].items()):
            send(workorder.complete_result(wid, workorder.NEED_ITEMS))
        else:
            for name, n in w["deliver"].items():
                take_items(state, name, n)
            wo_cleanup(state, w)
            send(workorder.complete_result(wid, workorder.OK))
            reward = w.get("reward", {})
            if reward.get("coin"):
                player.coins += reward["coin"]
                send(merchant.coins(player.coins))
                save_character_field(player.name, "coins", player.coins)
            if reward.get("xp"):
                send(combat.experience_reward(reward["xp"], player.char_id, kind=1))
            faction_reward(state, reward)
            send(build_system_text(f"Work order complete: {w['name']}.", SYSTEM_TEXT_WHITE))
            if state.get("requisition") and npc is not None:
                send(workorder.available(wo_available(player, npc)))
    elif event == workorder.ABANDON:
        if w is None or key != mine:
            send(workorder.abandon_result(wid, workorder.NOT_WORKING))
        else:
            for name, n in w.get("supplies", {}).items():
                take_items(state, name, min(n, have_items(player)(name)))
            wo_cleanup(state, w)
            send(workorder.abandon_result(wid, workorder.OK))
    elif event == workorder.NEEDED and w is not None:
        send(workorder.needed(w))


def wo_cleanup(state, w):
    """The order is over: forget its recipe and clear it from the character."""
    set_work_order(state, None)
    state["send"](craft.forget_recipe(ARGS.content.recipes[w["recipe"]]))


def player_distance(player, npc):
    pos = player.live_position or player.spawned_at
    if pos is None:
        return 0
    return math.hypot(pos[0] - npc.location[0], pos[1] - npc.location[1])


def diplomacy_deck(player):
    """The character's cards and strategy slots (content defaults until changed)."""
    dip = ARGS.content.diplomacy
    deck = getattr(player, "diplomacy_deck", None) or list(dip["deck"])
    count = dip.get("slots", 4)
    slots = getattr(player, "diplomacy_slots", None) or diplomacy.default_slots(deck, count)
    slots = (list(slots) + [None] * count)[:count]
    player.diplomacy_deck, player.diplomacy_slots = deck, slots
    return deck, slots


def handle_parley_event(state, event, data):
    """A parley (diplomacy.py, content/diplomacy.json): the player plays a card,
    the NPC answers with one of its own; the bar decides the winner."""
    player, send = state["player"], state["send"]
    p = state.get("parley")
    dip = ARGS.content.diplomacy
    print(f"  >>> ZONE parley event {event:#x}: {data.hex(' ')}")
    if event == diplomacy.START:
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not npc.parley:
            return
        parleys = dip["parleys"]
        config = parleys.get(npc.parley) if isinstance(npc.parley, str) else next(iter(parleys.values()))
        deck, slots = diplomacy_deck(player)
        p = diplomacy.Parley(config, dip["cards"], [c for c in slots if c is not None])
        p.npc = npc
        state["parley"] = p
        for m in diplomacy.deck_messages(dip["cards"], deck, slots, resend=state.get("deck_sent", False)):
            send(m)
        state["deck_sent"] = True
        send(diplomacy.open_parley(npc.entity_id, p))
    elif event in (diplomacy.SLOT, diplomacy.UNSLOT) and len(data) >= 4:
        # Dragging a card to / off the strategy bar (saved per character).
        deck, slots = diplomacy_deck(player)
        cid = struct.unpack_from("<i", data)[0]
        if cid not in deck:
            return
        was_slotted = cid in slots
        for n, c in enumerate(slots):
            if c == cid:
                slots[n] = None
        if event == diplomacy.SLOT and len(data) >= 8:
            if was_slotted:
                send(diplomacy.unslotted(cid))   # a card already in a slot ignores 0x237
            slot = struct.unpack_from("<i", data, 4)[0]
            if 0 <= slot < len(slots):
                if slots[slot] is not None:
                    send(diplomacy.unslotted(slots[slot]))
                slots[slot] = cid
                send(diplomacy.slotted(cid, slot))
        else:
            send(diplomacy.unslotted(cid))
        player.diplomacy_slots = slots
        save_character_field(player.name, "diplomacy_slots", slots)
        if p is not None:
            p.deck = [c for c in slots if c is not None]
    elif p is None:
        if event in (diplomacy.SELECT, diplomacy.PLAY, diplomacy.PASS):
            send(diplomacy.error(diplomacy.ERR_OVER))
        elif event == diplomacy.CANCEL:
            for m in diplomacy.ended():
                send(m)
        elif event == diplomacy.CLOSE:
            send(diplomacy.close())
    elif event == diplomacy.SELECT:
        cid = struct.unpack_from("<i", data, 0)[0]
        code = p.check(cid)
        if code:
            send(diplomacy.error(code))
            return
        p.card = cid
        send(diplomacy.selected(cid))
    elif event in (diplomacy.PLAY, diplomacy.PASS):
        if event == diplomacy.PLAY:
            if p.card is None:
                send(diplomacy.error(diplomacy.ERR_NO_CARD))
                return
            code = p.check(p.card)
            if code:
                send(diplomacy.error(code))
                return
            p.play(p.card)
            p.card = None
            send(diplomacy.update(p))
            send(diplomacy.points(p))
        if p.outcome() is None:
            for m in diplomacy.round_messages(p, p.npc_turn()):
                send(m)
        result = p.outcome()
        if result:
            finish_parley(state, p, result)
    elif event in (diplomacy.CANCEL, diplomacy.CLOSE):
        state.pop("parley", None)
        for m in diplomacy.ended() if event == diplomacy.CANCEL else [diplomacy.close()]:
            send(m)


def damaged_items(player):
    """[(handle, name, durability, equipped?)] for items below 100%."""
    dur = getattr(player, "durability", {})
    out = [(i[0], i[1], dur[str(i[0])], False) for i in player.items if dur.get(str(i[0]), 100) < 100]
    out += [(e[0], e[1], dur[str(e[0])], True) for e in player.equipment if dur.get(str(e[0]), 100) < 100]
    return out


def handle_repair_event(state, event, data):
    """Repair at a merchant with "repair": true: list damaged items, fix them for coin."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE repair event {event:#x}: {data.hex(' ')}")
    npc = player.npcs.get(player.target) if player.target else None
    if npc is None or not npc.repairs:
        send(zone.zone_event(merchant.WINDOW_CLOSE, struct.pack("<B", 2)))
        return
    damaged = damaged_items(player)

    def cost(name, d):
        return merchant.repair_cost(ARGS.content.item(name).get("level", 1), d)
    if event == merchant.REQ_REPAIR_OPEN:
        send(zone.zone_event(0x55F))          # the repair window replaces the dialogue
        for m in merchant.repair_window([(h, cost(n, d)) for h, n, d, _ in damaged]):
            send(m)
        return
    if event == merchant.REQ_REPAIR:
        handle = struct.unpack_from("<i", data, 0)[0]
        todo = [x for x in damaged if x[0] == handle]
    else:
        todo = damaged
    for handle, name, d, equipped in todo:
        price = cost(name, d)
        if player.coins < price:
            send(merchant.error(merchant.ERR_REPAIR_ALL if event == merchant.REQ_REPAIR_ALL
                                else merchant.ERR_CANT_AFFORD))
            break
        player.coins -= price
        player.durability = getattr(player, "durability", {})
        player.durability[str(handle)] = 100
        # Resend the item with full durability (bag items in place; equipped items
        # are recreated and put back on the paper doll).
        if equipped:
            n = next(k for k, e in enumerate(player.equipment) if e[0] == handle)
            item_id, name, icon, slot = player.equipment[n]
            send(zone.zone_event(0x197, vgmsg.inventory_item(item_id, name, 49 - n, zone.item_icon(name, icon),
                                                             **zone.item_equip_fields(name))))
            send(zone.zone_event(0x1A7, struct.pack("<iBB", item_id, 0, slot)))
        else:
            it = next(i for i in player.items if i[0] == handle)
            send(zone.zone_event(0x197, vgmsg.inventory_item(it[0], it[1], it[4], zone.item_icon(it[1], it[2]),
                                                             it[3], **zone.item_equip_fields(it[1]))))
        send(merchant.repaired(handle))
        send(build_system_text(f"{name} has been repaired.", SYSTEM_TEXT_WHITE))
    send(merchant.coins(player.coins))
    save_character_field(player.name, "coins", player.coins)
    save_character_field(player.name, "durability", getattr(player, "durability", {}))


def bank_record(item_id, name, icon, qty, slot, durability=100):
    return vgmsg.inventory_item(item_id, name, slot, icon, qty, **zone.item_equip_fields(name, durability))


def save_bank(player):
    save_character_field(player.name, "bank", [list(i) for i in player.bank])
    save_character_field(player.name, "bank_coins", player.bank_coins)
    save_character_field(player.name, "items", [list(i) for i in player.items])
    save_character_field(player.name, "coins", player.coins)


def handle_bank_event(state, event, data):
    """Banking (bank.py): items and coins between the bags and the bank."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE bank event {event:#x}: {data.hex(' ')}")
    if event == bank.BEGIN:
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not npc.banker:
            send(bank.error(bank.ERR_NOT_BANKER))
            return
        state["banking"] = True
        send(bank.start("Bank", player.bank_coins))
        for i in player.bank:
            send(bank.item(bank_record(*i, getattr(player, "durability", {}).get(str(i[0]), 100))))
        return
    if not state.get("banking"):
        send(bank.error(bank.ERR_NOT_BANKING))
        return
    if event == bank.END:
        state.pop("banking", None)
        send(bank.stop())
    elif event in (bank.TO_BANK, bank.TO_BANK_ANY):
        handle, qty = struct.unpack_from("<ii", data, 0)
        slot = struct.unpack_from("<i", data, 8)[0] if event == bank.TO_BANK else -1
        it = next((i for i in player.items if i[0] == handle), None)
        if it is None:
            return
        if not 0 <= slot < bank.CAPACITY or any(b[4] == slot for b in player.bank):
            slot = bank.free_slot(player.bank)
        if slot is None:
            send(bank.error(bank.ERR_BANK_FULL))
            return
        if 0 < qty < it[3]:
            # Part of a stack: the rest stays in the bag, the part is a new bank item.
            player.items[player.items.index(it)] = it[:3] + (it[3] - qty, it[4])
            send(zone.zone_event(0x1AE, struct.pack("<ii", handle, it[3] - qty)))
            new = (zone.new_item_id(player), it[1], it[2], qty, slot)
            player.bank.append(new)
            send(bank.item(bank_record(*new)))
        else:
            player.items.remove(it)
            player.bank.append(it[:4] + (slot,))
            send(bank.stored(handle, slot))
        save_bank(player)
    elif event in (bank.FROM_BANK, bank.FROM_BANK_ANY):
        handle, qty = struct.unpack_from("<ii", data, 0)
        it = next((i for i in player.bank if i[0] == handle), None)
        if it is None:
            return
        slot = struct.unpack_from("<i", data, 12)[0] if event == bank.FROM_BANK else -1
        if not 0 <= slot < zone.BAG_SLOTS or any(i[4] == slot for i in player.items):
            slot = zone.free_bag_slot(player)
        if slot is None:
            send(bank.error(bank.ERR_BAGS_FULL))
            return
        if 0 < qty < it[3]:
            player.bank[player.bank.index(it)] = it[:3] + (it[3] - qty, it[4])
            send(bank.clear())
            for i in player.bank:
                send(bank.item(bank_record(*i, getattr(player, "durability", {}).get(str(i[0]), 100))))
            new = (zone.new_item_id(player), it[1], it[2], qty, slot)
            player.items.append(new)
            send(zone.zone_event(0x197, vgmsg.inventory_item(new[0], new[1], slot, new[2], qty,
                                                             **zone.item_equip_fields(new[1]))))
        else:
            player.bank.remove(it)
            player.items.append(it[:4] + (slot,))
            send(bank.retrieved(handle, -1, slot))
        save_bank(player)
        quest_items_changed(state)
    elif event == bank.MOVE:
        handle, qty, slot = struct.unpack_from("<iii", data, 0)
        it = next((i for i in player.bank if i[0] == handle), None)
        if it is None or not 0 <= slot < bank.CAPACITY:
            return
        other = next((i for i in player.bank if i[4] == slot), None)
        if other is not None:
            player.bank[player.bank.index(other)] = other[:4] + (it[4],)
        player.bank[player.bank.index(it)] = it[:4] + (slot,)
        send(bank.clear())
        for i in player.bank:
            send(bank.item(bank_record(*i, getattr(player, "durability", {}).get(str(i[0]), 100))))
        save_bank(player)
    elif event in (bank.DEPOSIT_COIN, bank.WITHDRAW_COIN):
        amount = struct.unpack_from("<q", data, 0)[0]
        if event == bank.DEPOSIT_COIN:
            amount = max(0, min(amount, player.coins))
            player.coins -= amount
            player.bank_coins += amount
        else:
            amount = max(0, min(amount, player.bank_coins))
            player.bank_coins -= amount
            player.coins += amount
        send(bank.bank_coins(player.bank_coins))
        send(merchant.coins(player.coins))
        save_bank(player)


def learn_ability(state, n, aid, tag):
    """Add a class ability to the book (0x215) and save it."""
    player, send = state["player"], state["send"]
    learned = getattr(player, "learned", [])
    if aid not in learned:
        learned.append(aid)
    player.learned = learned
    ability = class_abilities.ability_tuple(n, aid, tag)
    ability = (max([a[0] for a in player.abilities] + [0]) + 1,) + ability[1:]
    player.abilities.append(ability)
    send(zone.zone_event(0x215, vgmsg.ability_info(ability[0], aid, ability[2], ability[3],
                                                 ability[4], refresh=ability[5])))
    send(build_system_text(f"You have learned {ability[2]}.", SYSTEM_TEXT_WHITE))
    save_character_field(player.name, "learned_abilities", learned)
    print(f"  {player.name} learned {ability[2]}")


def handle_trainer_event(state, event, data):
    """Ability trainer (trainer.py): list what the class can learn next, sell it."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE trainer event {event:#x}: {data.hex(' ')}")
    learned = getattr(player, "learned", [])
    offers = class_abilities.trainable(ARGS.client_dir, player.klass, learned)
    if event == trainer.START:
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not npc.trainer:
            return
        if state.get("training"):
            send(trainer.end())         # 0x493 appends: clear the earlier list
        state["training"] = True
        for m in trainer.begin([(aid, class_abilities.display_name(tag), f"{class_abilities.display_name(tag)}.",
                                 class_abilities._ICONS[n % len(class_abilities._ICONS)], cost)
                                for n, aid, tag, cost in offers]):
            send(m)
    elif event == trainer.TRAIN:
        aid = struct.unpack_from("<i", data, 0)[0]
        offer = next((o for o in offers if o[1] == aid), None)
        if not state.get("training"):
            send(trainer.result(aid, trainer.NOT_TRAINING))
        elif offer is None:
            send(trainer.result(aid, trainer.NOT_AVAILABLE))
        elif player.coins < offer[3]:
            send(trainer.result(aid, trainer.CANT_AFFORD))
        else:
            n, _, tag, cost = offer
            player.coins -= cost
            send(merchant.coins(player.coins))
            save_character_field(player.name, "coins", player.coins)
            learn_ability(state, n, aid, tag)
            send(trainer.result(aid, trainer.OK))
    elif event == trainer.STOP:
        state.pop("training", None)
        send(trainer.end())


def recipe_offers(player, npc):
    known = getattr(player, "known_recipes", [])
    return [(k, ARGS.content.recipes[k]) for k in npc.recipe_trainer
            if k in ARGS.content.recipes and k not in known]


def handle_recipe_trainer_event(state, event, data):
    """Recipe trainer (trainer.py RECIPE_*): sells recipes with a trainer_cost."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE recipe trainer event {event:#x}: {data.hex(' ')}")
    npc = player.npcs.get(player.target) if player.target else None
    if event == trainer.RECIPE_START:
        if npc is None or not npc.recipe_trainer:
            send(trainer.recipe_end(0))
            return
        offers = recipe_offers(player, npc)
        if not offers:
            send(trainer.recipe_end(2))          # "Your target has nothing to teach you right now."
            return
        if state.get("recipe_training"):
            send(trainer.recipe_end())
        state["recipe_training"] = npc.template_id
        for m in trainer.recipe_begin([(r["id"], r["name"], r.get("description", ""), r.get("icon", 443),
                                        r["trainer_cost"]) for _, r in offers]):
            send(m)
    elif event == trainer.RECIPE_TRAIN:
        rid = struct.unpack_from("<i", data, 0)[0]
        offer = next(((k, r) for k, r in recipe_offers(player, npc) if r["id"] == rid), None) if npc else None
        if not state.get("recipe_training"):
            send(trainer.recipe_result(rid, trainer.NOT_TRAINING))
        elif offer is None:
            send(trainer.recipe_result(rid, trainer.NOT_AVAILABLE))
        elif player.coins < offer[1]["trainer_cost"]:
            send(trainer.recipe_result(rid, trainer.CANT_AFFORD))
        else:
            key, r = offer
            player.coins -= r["trainer_cost"]
            send(merchant.coins(player.coins))
            save_character_field(player.name, "coins", player.coins)
            player.known_recipes = list(getattr(player, "known_recipes", [])) + [key]
            save_character_field(player.name, "known_recipes", player.known_recipes)
            send(craft.learn_recipe(r))
            for n in range(len(craft.all_steps(r))):
                send(craft.learn_action(r, n))
            for c in r.get("complications", []):
                send(craft.learn_counter(c))
            send(trainer.recipe_result(rid, trainer.OK))
            send(build_system_text(f"You have learned the recipe {r['name']}.", SYSTEM_TEXT_WHITE))
    elif event == trainer.RECIPE_STOP:
        state.pop("recipe_training", None)
        send(trainer.recipe_end())


def finish_parley(state, p, result):
    player, send = state["player"], state["send"]
    state.pop("parley", None)
    if result == "lost":
        send(diplomacy.lost())
        print(f"  {player.name} lost a parley with {p.npc.name}")
        return
    send(diplomacy.won())
    reward = dict(p.config.get("reward", {}))
    won = getattr(player, "parleys_won", [])
    if p.npc.template_id in won:
        reward.pop("coin", None)             # coin only for the first win per NPC
    else:
        player.parleys_won = won + [p.npc.template_id]
        save_character_field(player.name, "parleys_won", player.parleys_won)
        cid = reward.get("card")
        deck, _slots = diplomacy_deck(player)
        if cid is not None and cid not in deck and str(cid) in ARGS.content.diplomacy["cards"]:
            deck.append(cid)
            save_character_field(player.name, "diplomacy_deck", deck)
            send(build_system_text(f"You learn a new diplomacy strategy: "
                                   f"{ARGS.content.diplomacy['cards'][str(cid)]['name']}.", SYSTEM_TEXT_WHITE))
    if reward.get("coin"):
        player.coins += reward["coin"]
        send(merchant.coins(player.coins))
        save_character_field(player.name, "coins", player.coins)
    send(combat.experience_reward(reward.get("xp", 0), p.npc.entity_id, kind=2))
    faction_reward(state, reward)
    print(f"  {player.name} won a parley with {p.npc.name}")


def recipe_by_id(rid):
    return next((r for r in ARGS.content.recipes.values() if r["id"] == rid), None)


def has_inputs(player, r):
    have = {}
    for i in player.items:
        have[i[1]] = have.get(i[1], 0) + i[3]
    return all(have.get(name, 0) >= n for name, n in r["inputs"].items())


def handle_craft_event(state, event, data):
    """Crafting at a station (craft.py)."""
    player, send = state["player"], state["send"]
    session = state.get("craft")
    print(f"  >>> ZONE craft event {event:#x}: {data.hex(' ')}")
    if event == craft.USE_STATION:
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not npc.station:
            send(craft.station_error(0))
            return
        state["craft"] = {"recipe": None, "begun": False}
        send(craft.open_window())
    elif session is None:
        return
    elif event in (craft.CANCEL, craft.CANCEL2):
        state.pop("craft", None)
        send(craft.end())
    elif event == craft.SELECT:
        r = recipe_by_id(struct.unpack_from("<i", data, 0)[0])
        if r is None:
            send(craft.recipe_result(0, 0))
        elif not has_inputs(player, r):
            send(craft.recipe_result(craft.RECIPE_MISSING, r["id"]))
        else:
            session.update(recipe=r, begun=False)
            send(craft.recipe_result(craft.RECIPE_OK, r["id"]))
    elif event == craft.CONFIRM and session["recipe"]:
        send(craft.workbench())
    elif event == craft.BEGIN and session["recipe"]:
        session.update(begun=True, stage=0, done=set(), ap=0, quality=500, comp=None, had_comp=False,
                       catalyst_used=False)
        for m in craft.started(session["quality"]):
            send(m)
        cat = session["recipe"].get("catalyst")
        item = next((i for i in player.items if cat and i[1] == cat["item"]), None)
        if item is not None:
            send(craft.catalyst_offer(item[0]))
    elif event == craft.CATALYST and session.get("begun") and len(data) >= 4:
        if not add_catalyst(state, struct.unpack_from("<i", data, 0)[0]):
            send(craft.rejected(7))
    elif event == craft.ACTION:
        if not session.get("begun"):
            send(craft.rejected(craft.NOT_NOW))
            return
        craft_action(state, session, struct.unpack_from("<i", data, 0)[0])


def add_catalyst(state, handle):
    """The recipe's catalyst (0xf7 from the catalyst window, or right-clicking the
    item in the bags while crafting): used once, raises quality."""
    player, send = state["player"], state["send"]
    session = state.get("craft")
    if not session or not session.get("begun"):
        return False
    cat = session["recipe"].get("catalyst")
    item = next((i for i in player.items if i[0] == handle), None)
    if not cat or item is None or item[1] != cat["item"] or session.get("catalyst_used"):
        return False
    session["catalyst_used"] = True
    take_items(state, cat["item"], 1)
    session["quality"] = min(1000, session["quality"] + cat.get("quality", 100))
    send(craft.catalyst_clear())
    send(craft.quality(session["quality"]))
    send(craft.screen_text(f"Quality: Grade {craft.grade_letter(session['quality'])}"))
    send(build_system_text(f"You add {cat['item']} to the mixture.", SYSTEM_TEXT_WHITE))
    return True


def craft_action(state, session, action):
    """One crafting action: a step of the current stage, or a complication's counter."""
    player, send = state["player"], state["send"]
    r = session["recipe"]
    comp = session.get("comp")
    max_ap = r.get("max_ap", craft.MAX_AP)
    if comp and action == comp[0]["counter"]["action"]:
        k = comp[0]["counter"]
        if session["ap"] + k.get("ap", 15) > max_ap:
            send(craft.rejected(6))
            return
        session["ap"] += k.get("ap", 15)
        comp[1] -= k.get("strength", 50)
        send(zone.zone_event(0x2ED))
        send(zone.zone_event(0x2F6, struct.pack("<i", session["ap"])))
        if comp[1] <= 0:
            session["comp"] = None
            send(craft.complications([]))
            send(craft.screen_text("Complication resolved"))
        else:
            send(craft.complications([tuple(comp)]))
        return
    step = next(((n, si, st) for n, si, st in craft.all_steps(r)
                 if st["action"] == action and si == session["stage"] and n not in session["done"]), None)
    if step is None:
        send(craft.rejected(7))
        return
    n, si, st = step
    tool = st.get("tool")
    if tool and not any(i[1] == tool for i in player.items):
        send(craft.rejected(craft.MISSING_TOOL, tool))       # "Missing tool: <tool>"
        return
    if session["ap"] + st.get("ap", 20) > max_ap:
        send(craft.rejected(6))
        return
    session["ap"] += st.get("ap", 20)
    session["done"].add(n)
    gain, grade = random.choice([(150, "Excellent!"), (100, "Great!"), (100, "Great!"), (50, "Good")])
    if comp:
        gain, grade = gain - comp[0].get("penalty", 100), "Poor"
    session["quality"] = max(0, min(1000, session["quality"] + gain))
    stage_steps = [x for x in craft.all_steps(r) if x[1] == si]
    progress = 252 * sum(1 for x in stage_steps if x[0] in session["done"]) // len(stage_steps)
    send(combat.display_ability(player.char_id, combat.NO_ENTITY, 30203))
    for m in craft.action_done(r, n, si, session["ap"], progress, session["quality"], grade):
        send(m)
    # A complication may show up during its stage (once per session).
    for c in r.get("complications", []):
        if (not session["comp"] and not session["had_comp"] and c.get("stage", 0) == si
                and random.random() < c.get("chance", 0.5)):
            session["comp"], session["had_comp"] = [c, 100], True
            send(craft.alert(c["name"]))
            send(craft.complications([(c, 100)]))
    if progress < 252:
        return
    if si + 1 < len(craft.stages(r)):
        session["stage"] = si + 1
        for m in craft.next_stage(si + 1):
            send(m)
        return
    send(craft.screen_text(f"Quality: Grade {craft.grade_letter(session['quality'])}"))
    finish_craft(state, r)


def finish_craft(state, r):
    """All steps done: use the inputs, give the output and crafting XP."""
    player, send = state["player"], state["send"]
    state.pop("craft", None)
    if not has_inputs(player, r):
        send(build_system_text("You no longer have the materials.", SYSTEM_TEXT_ERROR))
        send(craft.end())
        return
    if zone.free_bag_slot(player) is None:
        send(build_system_text("Your bags are full.", SYSTEM_TEXT_ERROR))
        send(craft.end())
        return
    for name, need in r["inputs"].items():
        take_items(state, name, need)
    name = r["output"]
    if give_item(state, name, quiet=True):
        send(build_system_text(f"You create {name}.", SYSTEM_TEXT_WHITE))
        quest_items_changed(state)
    send(combat.experience_reward(r.get("xp", 50), player.char_id, kind=1))
    send(craft.end())
    print(f"  {player.name} crafted {name}")


def leave_world(state, args):
    """A zone connection ended: remove the player from its chunk and close its
    pawn on everyone else's client."""
    w, player = state.get("world"), state.get("player")
    # Trades and trade invites don't survive a zone reconnect (chunk handoff either).
    if state.get("trade"):
        end_trade(state["trade"], trade.cancelled())
    target = state.pop("trade_invite_to", None)
    if target is not None and target.get("trade_invite") is state:
        target.pop("trade_invite", None)
        target["send"](trade.invite_cancelled())
    inviter = state.pop("trade_invite", None)
    if inviter is not None and inviter.get("trade_invite_to") is state:
        inviter.pop("trade_invite_to", None)
        inviter["send"](trade.declined())
    if player is not None and not state.get("handoff"):
        leave_group(state)
        if ONLINE.get(player.name.lower()) is state:
            ONLINE.pop(player.name.lower(), None)
            ANNOUNCED.discard(player.name.lower())
            notify_friends(state, online=False)
            guild_broadcast(player.name, lambda g: guild.member_update(guild_member(g, player.name, online=False)),
                            exclude=state)
    # Only if this connection is still the one in the world (a re-login or a
    # handoff back to this chunk may have replaced it under the same id).
    if w is None or player is None or w.members.get(player.char_id) is not state:
        return
    w.members.pop(player.char_id, None)
    for npc in w.npcs.values():
        if npc.aggro_on is player:
            npc.aggro, npc.aggro_on, npc.moving = False, None, False
    w.broadcast(lambda s: zone.close_actor(s, player.char_id))
    print(f"  {player.name} left {w.level}")


def serve(sock, server, data, addr, clients, args):
    if True:
        stamp = time.strftime("%H:%M:%S")
        print(f"\n[{stamp}] {server} {addr[0]}:{addr[1]} -> {len(data)} bytes")
        print(hexdump(data))
        describe(data)
        key = (server, addr)

        if len(data) >= 14 and data[0] == 0 and data[1] == 0x01:
            protocol, code, max_raw = struct.unpack_from(">III", data, 2)
            name = data[14:].split(b"\0", 1)[0].decode("latin-1")
            print(f"  connect: protocol={protocol} code=0x{code:08x} maxRaw={max_raw} name={name!r}")
            clients[key] = {"out_seq": 0, "seen": set(), "max_raw": min(max_raw, MAX_RAW_PACKET),
                            # UdpLibrary Terminate (reason 6, application) for this connection.
                            "terminate": lambda sock=sock, addr=addr, code=code: sock.sendto(
                                b"\x00\x05" + struct.pack(">IH", code, 6), addr)}
            reply = build_confirm(code, max_raw)
            sock.sendto(reply, addr)
            print(f"  <- sent confirm ({len(reply)} bytes)")
            print(hexdump(reply))
        elif data[:2] == b"\x00\x06":
            # KeepAlive (sent by UdpConnection::GiveTime when idle). The client
            # disconnects with reason 2 (Timeout) after ~90 s of hearing nothing,
            # so answer every keep-alive with one of our own.
            sock.sendto(b"\x00\x06", addr)
            print("  <- sent keep-alive: 00 06")
            if key in clients:
                clients[key]["last_seen"] = time.time()
        elif data[:2] == b"\x00\x05" and len(data) >= 8:
            reason = struct.unpack_from(">H", data, 6)[0]
            print(f"  client disconnected, reason {reason} ({DISCONNECT_REASONS.get(reason, '?')})")
            gone = clients.pop(key, None)
            if gone and server == "ZONE":
                leave_world(gone, args)
        else:
            state = clients.setdefault(key, {"out_seq": 0, "seen": set(), "max_raw": 512})
            state["last_seen"] = time.time()
            if server == "ZONE" and "send" not in state:
                state["send"] = lambda m, sock=sock, addr=addr, state=state: (
                    send_message(sock, addr, state, m) if m is not None else None)
            for kind, seq, payload in reliable_messages(data):
                ack = build_ack_all(kind, seq)
                sock.sendto(ack, addr)
                print(f"  <- sent ack-all seq={seq}: {ack.hex(' ')}")
                if seq in state["seen"]:
                    continue  # client resend; already answered
                state["seen"].add(seq)
                for message in app_messages(payload):
                    try:
                        handle_message(sock, server, addr, state, message, args)
                    except struct.error as e:
                        # A client message shorter than its handler expects.
                        print(f"  >>> malformed message ({e}): {message[:64].hex(' ')}")
                    except Exception:
                        # A bug in one handler must not take the server down for everyone.
                        print(f"  >>> handler error for {message[:16].hex(' ')}")
                        traceback.print_exc()


def app_messages(payload):
    """Split a reliable payload into application messages. The client bundles
    several messages in a Group (00 19, 1-byte lengths) or Multi (00 03)."""
    if len(payload) >= 2 and payload[0] == 0 and payload[1] in (0x03, 0x19):
        pos = 2
        while pos < len(payload):
            if payload[1] == 0x19:
                n, pos = read_group_length(payload, pos)
            else:
                n, pos = payload[pos], pos + 1
            yield from app_messages(payload[pos:pos + n])
            pos += n
    else:
        yield payload


def reliable_messages(data):
    """Yield (type, seq, payload) for every Reliable packet, including ones
    bundled inside Multi (0x03) or Group (0x19) containers."""
    if len(data) < 2 or data[0] != 0:
        return
    kind = data[1]
    if 0x09 <= kind <= 0x0C and len(data) >= 4:
        yield kind, struct.unpack_from(">H", data, 2)[0], data[4:]
    elif kind == 0x03:
        pos = 2
        while pos < len(data):
            n = data[pos]
            yield from reliable_messages(data[pos + 1:pos + 1 + n])
            pos += 1 + n
    elif kind == 0x19:
        pos = 2
        while pos < len(data):
            n, pos = read_group_length(data, pos)
            yield from reliable_messages(data[pos:pos + n])
            pos += n


def send_message(sock, addr, state, message):
    """Send one application message reliably, fragmenting when it doesn't fit."""
    if len(message) + 4 <= state["max_raw"]:
        sock.sendto(build_reliable(state["out_seq"], message), addr)
        state["out_seq"] += 1
        return 1
    packets, state["out_seq"] = build_reliable_fragments(state["out_seq"], message, state["max_raw"])
    for pkt in packets:
        sock.sendto(pkt, addr)
    return len(packets)


def event_message(event_id, data):
    # Type-2 event envelope: u16le 2 | u32le eventId | u32le length | data.
    return struct.pack("<HII", 2, event_id, len(data)) + data


def read_wstrings(data, pos, count):
    """Read `count` NUL-terminated UTF-16LE strings starting at pos."""
    out = []
    for _ in range(count):
        end = pos
        while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
            end += 2
        out.append(data[pos:end].decode("utf-16-le", "replace"))
        pos = end + 2
    return out, pos


def wfield(text, size=128):
    raw = text[:size // 2 - 1].encode("utf-16-le")
    return raw + b"\0" * (size - len(raw))


def build_character_create_result(result, name):
    # VGMessages::MsgCharacterCreateResult (ctor FUN_004904b0, handler FUN_00496c90),
    # read by the reflection deserializer FUN_00cd9da0 in registration order:
    # u8 result (type 7), wstring (type 2), wstring name (type 2; selected on success).
    # Result 0 = "Character creation succeeded!", 1 = name taken, 0x10 = no free slot.
    data = struct.pack("<B", result) + "\0".encode("utf-16-le") + (name + "\0").encode("utf-16-le")
    return event_message(0x386, data)


# Default start: chunk (-19, 12). Chunks are Assets/Maps/chunk_<x>_<y>.vgr with
# negative coordinates written as n<abs>; the client streams the neighbours in.
DEFAULT_CHUNK = (-19, 12)


def chunk_name(x, y):
    def c(v):
        return f"n{-v}" if v < 0 else str(v)
    return f"chunk_{c(x)}_{c(y)}"


def character_chunk(char):
    return tuple(char.get("chunk", DEFAULT_CHUNK))


def character_id(char):
    """Stable 64-bit id for a character (the client echoes it in BECOME_PC)."""
    if "id" not in char:
        import zlib
        char["id"] = 0x1000000 + (zlib.crc32((char["first"] + char.get("world", "")).encode()) & 0xFFFFFF)
    return char["id"]


def build_set_name_id(char):
    # World event 10 (FUN_0062aaf0) becomes the console command
    #   SetNameID "<+0x80>" "<+0x00>" "<+0xe0>" "<+0x130>" "<+0x1b0>" <+0x234> <u64 +0x230> <+0x248>
    # (FUN_00413590), which fills the session object read by BECOME_PC (+0xc0 = id).
    # Strings: +0x00 first name, +0x80 last name, +0xe0 world, +0x1b0 the name
    # shown in the character window (verified: a chunk name put there showed up
    # as the character's name); +0x130 unknown.
    rec = bytearray(0x24C)
    rec[0x000:0x080] = wfield(char["first"], 0x80)
    rec[0x080:0x0e0] = wfield(char.get("last", ""), 0x60)
    rec[0x0e0:0x130] = wfield(char.get("world", WORLD_NAME), 0x50)
    rec[0x1b0:0x230] = wfield(char["first"], 0x80)
    struct.pack_into("<Q", rec, 0x230, character_id(char))
    return event_message(10, bytes(rec))


def build_character_record(char):
    # World event 0x19 (FUN_005f0770) adds one character-select entry. Fixed layout:
    # +0x000/+0x080/+0x100 wchar[64] (the +0x100 one is matched against the world
    # list name), +0x180..+0x1b3 u32 fields (+0x1a4/+0x1a8 chunk coords),
    # +0x1b4..+0x1b6 bytes, +0x1b7 64 bytes, +0x1f7 a narrow string of 180
    # space-separated integers (3 x 60, likely appearance). Field meanings beyond
    # the world name are guesses: first name, last name.
    # Record u32s land in the client object: +0x180 → obj+0x74 (class, names from
    # FUN_00d07120: 0x1c Warrior, 0x19 Sorcerer, ...), +0x184 → obj+0x78 (level,
    # shown with %d), +0x19c → obj+0x90 (race, FUN_00d02540: 0x0e Thestran, 2 Dwarf, ...).
    race, klass = character_race_class(char)
    rec = bytearray(0x1f7)
    rec[0x000:0x080] = wfield(char["first"])
    rec[0x080:0x100] = wfield(char["last"])
    rec[0x100:0x180] = wfield(char["world"])
    struct.pack_into("<I", rec, 0x180, klass)
    struct.pack_into("<I", rec, 0x184, char.get("adventure_level", 10))
    struct.pack_into("<I", rec, 0x19c, race)
    struct.pack_into("<ii", rec, 0x1a4, *character_chunk(char))
    rec[0x1b7:0x1f7] = character_appearance(char)
    rec += (" ".join(["0"] * 180)).encode("ascii") + b"\0"
    return event_message(0x19, bytes(rec))


def character_appearance(char):
    # The create request's bytes after the names are: 4 zero bytes, 5 bytes
    # (… race at +7, class at +8), i32 (-26 seen), i32 (1 seen), then 64 appearance
    # slider bytes. The record copies 64 bytes at +0x1b7 into the slider array
    # Play uses (FUN_0051ca70 → +0x2ac), so store them per character.
    if char.get("appearance"):
        return bytes.fromhex(char["appearance"])
    raw = bytes.fromhex(char.get("raw", ""))
    if len(raw) >= 81:
        return raw[17:81]
    return bytes([0x32] * 64)


def character_race_class(char):
    # In the create request (event 0x139) the bytes after the three names start
    # "00 00 00 00 1f 05 00 0e 1c ..." for a Thestran (0x0e) Warrior (0x1c):
    # race at +7, class at +8. Default to Thestran Warrior when unknown.
    raw = bytes.fromhex(char.get("raw", ""))
    if len(raw) > 8:
        return raw[7], raw[8]
    return 0x0E, 0x1C


MAX_CHARACTER_SLOTS = 8


def build_account_character_list(chars):
    # Login event 0x66 (FUN_0051e960) fills the character-select list (charMgr +0x98):
    # +0x00 128 bytes (unused here), +0x80 u32 count, +0x84 u32 (→ charMgr+0x3b4,
    # compared with the count when creating; assumed slot limit), +0x88 u32
    # (→ +0x3b8; the UI showed "2/16" with 8+8, so the slot total looks like the
    # sum of both), +0x8c 20 x wchar[64] entries "<character name>=<world>"
    # ('=' separator at 0x10757b0; "<world>=<name>" swapped title and world on screen).
    # The client then requests details (world event 0x19).
    data = bytearray(0x80)
    data += struct.pack("<III", len(chars), MAX_CHARACTER_SLOTS, 0)
    for i in range(20):
        entry = f"{chars[i]['first']}={chars[i]['world']}" if i < len(chars) else ""
        data += wfield(entry)
    return event_message(0x66, bytes(data))


def send_account_character_list(sock, addr, state):
    chars = load_characters()
    n = send_message(sock, addr, state, build_account_character_list(chars))
    names = ", ".join(c["first"] for c in chars) or "none"
    print(f"  <- sent account character list 0x66 ({names}) ({n} packets)")


CHARACTERS_FILE =os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters.json")


def load_characters():
    try:
        with open(CHARACTERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_character_position(name, loc):
    chars = load_characters()
    for c in chars:
        if c["first"] == name:
            c["position"] = list(loc)
            c["position_chunk"] = list(character_chunk(c))
            save_characters(chars)
            return


def save_character_progress(name, level, xp):
    chars = load_characters()
    for c in chars:
        if c["first"] == name:
            c["adventure_level"], c["adventure_xp"] = level, xp
            save_characters(chars)
            return


def save_character_field(name, field, value):
    chars = load_characters()
    for c in chars:
        if c["first"] == name:
            c[field] = value
            save_characters(chars)
            return


def save_characters(chars):
    with open(CHARACTERS_FILE, "w", encoding="utf-8") as f:
        json.dump(chars, f, indent=2)


# The most recent world-server / login-server connections, so each side can push
# messages to the other (character records, refreshed account lists).
WORLD_CONN = {}
# Characters chosen with Play, by session key, until their zone connection logs in.
PENDING_PLAYERS = {}
LOGIN_CONN = {}


def dev_command(text, player=None):
    """Developer chat commands (only with --dev-commands), for probing the client:
      !stat id=value[,field=value...] ...   send MsgSingleStatInfo records (0x2d5).
        Field names: kind, category, subtype, base, f<N> (raw wire field N).
      !upd id=value[,field=value...] ...    send MsgStatUpdate (0x2d4) per stat.
      !event id [hexbytes]                  send a raw zone event.
      !anim id [arg] [me]                   play animation id (zone event 0x2e) on
                                            the target, or on yourself with "me"."""
    words = text[1:].split()
    if not words:
        return []
    if words[0] == "move" and len(words) >= 3 and player and player.target in player.npcs:
        # !move dx dy: shift the target NPC (replicated Location).
        npc = player.npcs[player.target]
        npc.location = (npc.location[0] + float(words[1]), npc.location[1] + float(words[2]),
                        npc.location[2])
        print(f"  <- dev: move {npc.name} to {npc.location}")
        return [("npc_update", npc, {"Location": npc.location})]
    if words[0] == "tp" and len(words) >= 4 and player:
        # !tp x y z: move your own pawn (replicated Location); "~" keeps a coordinate.
        cur = getattr(player, "live_position", None) or player.spawned_at or (0.0, 0.0, 0.0)
        loc = tuple(cur[i] if w == "~" else float(w) for i, w in enumerate(words[1:4]))
        print(f"  <- dev: teleport to {loc}")
        return [("pawn_update", None, {"Location": loc, "Velocity": (0.0, 0.0, 0.0)})]
    if words[0] == "ctext" and player:
        # !ctext [kind] [heal] [self]: try the client-built combat text (0x27b).
        kind = int(words[1]) if len(words) > 1 else 1
        heal = len(words) > 2 and words[2] == "1"
        target = player.char_id if len(words) > 3 or not player.target else player.target
        return [effects.combat_text(player.char_id, target, "Test Strike", 12, heal=heal, kind=kind)]
    if words[0] == "mailme" and player:
        # !mailme: a letter to yourself from Orin with 50 copper and a Copper Ore (testing).
        db = load_mail()
        deliver_mail(db, player.name, mail.new(0, "Orin the Trader", "A small gift",
                                               "Thanks for the help around camp.", coin=50,
                                               item_={"name": "Copper Ore", "icon": zone.item_icon("Copper Ore", 443),
                                                      "qty": 1}, from_player=False))
        save_mail(db)
        return []
    if words[0] == "faction" and len(words) >= 3 and player:
        # !faction <id> <amount>: change a faction standing (testing).
        return [("faction", int(words[1]), int(words[2]))]
    if words[0] == "questkill" and player:
        # !questkill: count a kill of the target's kind toward active quests (testing).
        npc = player.npcs.get(player.target)
        return [("quest_kill", npc)] if npc else []
    if words[0] == "give" and len(words) >= 2 and player:
        # !give <item name> [qty]: put an item from items.json in the bags (testing).
        qty = int(words[-1]) if words[-1].isdigit() and len(words) > 2 else 1
        name = " ".join(words[1:-1] if qty > 1 or words[-1] == "1" else words[1:])
        return [("give", name, qty)]
    if words[0] == "guildcreate" and player:
        # !guildcreate: open the client's guild-name dialog (0x4e7; there is no slash command).
        return [guild.name_dialog()]
    if words[0] == "use" and len(words) >= 2 and player:
        # !use <ability name>: use a known ability as if from the hotbar (testing).
        want = " ".join(words[1:]).lower()
        ability = next((a for a in player.abilities if a[2].lower().startswith(want)), None)
        return [("use", ability)] if ability else []
    if words[0] == "learn" and len(words) >= 2 and player:
        # !learn <ability name>: learn a class ability without a trainer (testing).
        want = " ".join(words[1:]).lower()
        for n, (aid, tag) in enumerate(class_abilities.class_ability_list(ARGS.client_dir, player.klass)):
            if class_abilities.display_name(tag).lower().startswith(want):
                if any(a[1] == aid for a in player.abilities):
                    return []
                return [("learn", n, aid, tag)]
        return []
    if words[0] == "wear" and player:
        # !wear [points]: damage equipped gear (testing repairs).
        pts = int(words[1]) if len(words) > 1 else 25
        for item_id, _name, _icon, _slot in player.equipment:
            player.durability[str(item_id)] = max(0, player.durability.get(str(item_id), 100) - pts)
        save_character_field(player.name, "durability", player.durability)
        return [build_system_text(f"Equipment worn by {pts}.", SYSTEM_TEXT_WHITE)]
    if words[0] in ("bankput", "bankget") and len(words) >= 2 and player:
        # !bankput <bag slot> / !bankget <bank slot> [coins]: the client's 0x14d / 0x14f
        # (or 0x93 / 0x94 with "coins <copper>"), for testing without dragging.
        if words[1] == "coins" and len(words) >= 3:
            event = bank.DEPOSIT_COIN if words[0] == "bankput" else bank.WITHDRAW_COIN
            return [("bank", event, struct.pack("<q", int(words[2])))]
        pool = player.items if words[0] == "bankput" else getattr(player, "bank", [])
        it = next((i for i in pool if i[4] == int(words[1])), None)
        if it is None:
            return []
        event = bank.TO_BANK_ANY if words[0] == "bankput" else bank.FROM_BANK_ANY
        return [("bank", event, struct.pack("<ii", it[0], it[3]))]
    if words[0] == "tradeadd" and len(words) >= 2 and player:
        # !tradeadd <bag slot>: offer that bag item in the open trade (what dragging it
        # into the trade window sends: client event 0xc4 {handle, seq, qty}).
        item = next((i for i in player.items if i[4] == int(words[1])), None)
        return [("trade_event", trade.ADD, struct.pack("<iii", item[0], 0, item[3]))] if item else []
    if words[0] == "tradecoin" and len(words) >= 2 and player:
        return [("trade_event", trade.COIN, struct.pack("<qi", int(words[1]), 0))]
    if words[0] == "target" and len(words) >= 2 and player:
        # !target <part of a name>: target the nearest-listed NPC whose name matches.
        want = " ".join(words[1:]).lower()
        npc = next((n for n in player.npcs.values() if want in n.name.lower()), None)
        if npc is None:
            return []
        player.target = npc.entity_id
        print(f"  <- dev: target {npc.name}")
        return [combat.targets(npc)]
    if words[0] == "prop" and len(words) >= 3 and player:
        # !prop <name> <value> [me]: set a replicated pawn property on the target
        # NPC (or yourself with "me"), for probing what the client does with it.
        value = words[2]
        value = float(value) if "." in value else int(value, 0)
        values = {words[1]: value}
        if "me" in words[3:] or player.target not in player.npcs:
            return [("self_prop", None, values)]
        return [("npc_update", player.npcs[player.target], values)]
    if words[0] == "hurt" and len(words) >= 2 and player:
        # !hurt N: lower your own health (the next hit from an NPC can kill you).
        player.health = max(player.health - int(words[1], 0), 1)
        player.last_combat = time.time()
        return [zone.health_update(player)]
    if words[0] == "anim" and len(words) >= 2 and player:
        me = "me" in words[2:]
        nums = [int(w, 0) for w in words[1:] if w != "me"]
        eid = player.char_id if me or not player.target else player.target
        print(f"  <- dev: animation {nums[0]} on {eid:#x}")
        return [zone.zone_event(combat.ANIM_EVENT, struct.pack("<Qii", eid, nums[0],
                                                               nums[1] if len(nums) > 1 else 0))]
    if words[0] == "stat":
        recs = []
        for spec in words[1:]:
            parts = spec.split(",")
            sid, value = (int(x, 0) for x in parts[0].split("="))
            kw = dict(p.split("=") for p in parts[1:])
            raw = {int(k[1:]): int(v, 0) for k, v in kw.items() if k.startswith("f")}
            opts = {k: int(v, 0) for k, v in kw.items() if not k.startswith("f")}
            recs.append(vgmsg.stat_info(sid, value, raw=raw, **opts))
        print(f"  <- dev: {len(recs)} stat record(s)")
        return [zone.zone_event(0x2D5, vgmsg.stat_list(recs))]
    if words[0] == "upd":
        out = []
        for spec in words[1:]:
            parts = spec.split(",")
            sid, value = (int(x, 0) for x in parts[0].split("="))
            kw = dict(p.split("=") for p in parts[1:])
            raw = {int(k[1:]): int(v, 0) for k, v in kw.items() if k.startswith("f")}
            opts = {k: int(v, 0) for k, v in kw.items() if not k.startswith("f")}
            out.append(zone.zone_event(0x2D4, vgmsg.stat_update(sid, value, raw=raw, **opts)))
        print(f"  <- dev: {len(out)} stat update(s)")
        return out
    if words[0] == "chat" and len(words) >= 3:
        # !chat <channel> <text...>: zone event 0x0f from "Tester"
        print(f"  <- dev: chat channel {words[1]}")
        return [build_chat_line("Tester", " ".join(words[2:]), int(words[1], 0))]
    if words[0] == "sys" and len(words) >= 3:
        # !sys <channel> <text...>: zone event 0x192 (wstr text, i32 channel)
        text = " ".join(words[2:])
        print(f"  <- dev: system text channel {words[1]}")
        return [zone.zone_event(0x192, (text + chr(0)).encode("utf-16-le")
                                + struct.pack("<i", int(words[1], 0)))]
    if words[0] == "exec" and len(words) >= 2:
        # !exec <console command>: zone event 0x598 (wstr) runs it on the client
        command = " ".join(words[1:])
        print(f"  <- dev: client exec {command!r}")
        return [zone.zone_event(0x598, (command + chr(0)).encode("utf-16-le"))]
    if words[0] == "item":
        # !item [probe] [N=value ...]: zone event 0x197 (add an item to the inventory)
        probe = "probe" in words[1:]
        raw = {}
        for spec in words[1:]:
            if "=" in spec:
                k, v = spec.split("=", 1)
                t = vgmsg.ITEM_TYPES[int(k)]
                raw[int(k)] = v.replace("_", " ") if t == "w" else (float(v) if t == "f" else int(v, 0))
        print(f"  <- dev: item {raw}")
        return [zone.zone_event(0x197, vgmsg.item_info(raw, probe=probe))]
    if words[0] == "event":
        data = bytes.fromhex("".join(words[2:]))
        print(f"  <- dev: zone event {words[1]} ({len(data)} bytes)")
        return [zone.zone_event(int(words[1], 0), data)]
    return []


# Zone event 0x192 (wstr text, i32 colour/channel): plain server text in the chat
# window. Verified colours: 3 white, 4 red, 5 orange, 6 blue, 7 tan.
SYSTEM_TEXT_WHITE, SYSTEM_TEXT_ERROR, SYSTEM_TEXT_COMBAT = 3, 4, 5


def build_system_text(text, channel=SYSTEM_TEXT_WHITE):
    return event_message(0x192, (text + chr(0)).encode("utf-16-le") + struct.pack("<i", channel))


CHAT_SAY = 3      # "<speaker> says, "text"" (FUN_00621d60; verified live)
CHAT_EMOTE = 5    # "<speaker> text"; other values print "[???][speaker]: text"


def build_chat_line(speaker, text, channel=CHAT_SAY):
    """Zone event 0x0f (MsgTwoStringsAndInt): text, speaker, i32 channel."""
    data = (text + chr(0)).encode("utf-16-le") + (speaker + chr(0)).encode("utf-16-le")
    return event_message(0x0F, data + struct.pack("<i", channel))


def build_zone_connect_event(host, port, name):
    # World event 8 (FUN_0062aaf0 case 8): u32 port, wchar[64] host at +4,
    # wchar[64] name at +0x84. The client formats "%s:%d", logs "Connecting to
    # %s (%s)", travels the Unreal engine there and logs in with ClientZoneApi
    # (FUN_006ed160 → FUN_006ec2f0, same account/session as the world login).
    data = struct.pack("<I", port) + wfield(host) + wfield(name)
    return event_message(8, data)


def send_character_list(sock, addr, state):
    chars = [c for c in load_characters() if c["world"] == WORLD_NAME]
    for char in chars:
        n = send_message(sock, addr, state, build_character_record(char))
        print(f"  <- sent WORLD character record 0x19: {char['first']} {char['last']} ({n} packets)")
    if not chars:
        print("  (no saved characters to send)")


def handle_message(sock, server, addr, state, payload, args):
    if len(payload) < 2:
        return
    (msg_type,) = struct.unpack_from("<H", payload, 0)
    login = try_parse_login_request(payload) if msg_type == 3 else None
    event_id = struct.unpack_from("<I", payload, 2)[0] if msg_type == 2 and len(payload) >= 10 else None
    if server == "WORLD":
        WORLD_CONN.update(sock=sock, addr=addr, state=state)
        data = payload[10:]
        if event_id == 0x19 and not data:
            print("  >>> WORLD event 0x19 (empty): character list request")
            send_character_list(sock, addr, state)
            return
        if event_id == 0x13B:
            # Customize: two names, then 10 bytes, then 64 appearance sliders. Its
            # result is event 0x388 ("Character customization succeeded!",
            # FUN_0048cfe0), but the dispatcher that handles 0x388 is not known yet,
            # so only the new appearance is saved.
            (name, name2), pos = read_wstrings(data, 0, 2)
            chars = load_characters()
            for c in chars:
                if c["first"] == name and len(data) >= pos + 64:
                    c["appearance"] = data[-64:].hex()
                    save_characters(chars)
                    print(f"  >>> WORLD event 0x13b (Customize): saved new appearance for {name!r}")
                    break
            else:
                print(f"  >>> WORLD event 0x13b (Customize) for unknown character {name!r}")
            return
        if event_id == 0x19:
            # Play button: event 0x19 carrying wchar[64] character name + 12 bytes
            # (seen: 01 00 ff ff 01 00 ff ff 00 00 00 00). Reply: connect to zone.
            name = data[:128].decode("utf-16-le", "replace").split("\0")[0]
            print(f"  >>> WORLD event 0x19 (Play): {name!r}, extra={data[128:].hex(' ')}")
            char = next((c for c in load_characters() if c["first"] == name), {"first": name})
            # The zone connection with the same session key claims this player.
            saved = char.get("position")
            same_chunk = tuple(char.get("position_chunk", ())) == character_chunk(char)
            player = zone.Player(
                name=name,
                char_id=character_id(char),
                race=character_race_class(char)[0] if char.get("raw") else 0x0E,
                klass=character_race_class(char)[1] if char.get("raw") else 0x1C,
                level=args.zone_level or chunk_name(*character_chunk(char)),
                position=saved if saved and same_chunk else None,
                save_position=lambda loc, n=name: save_character_position(n, loc))
            player.chunk = character_chunk(char)
            player.level_number = char.get("adventure_level", player.level_number)
            player.appearance = character_appearance(char)
            player.hotbar = char.get("hotbar")
            player.quests = quest.QuestLog(char.get("quests"))
            saved_skills = {int(k): v for k, v in char.get("skills", {}).items()}
            player.skills = [(sid, saved_skills.get(sid, v), sub) for sid, v, sub in player.skills]
            if "items" in char:
                player.items = zone.normalize_items(char["items"])
            if "coins" in char:
                player.coins = char["coins"]
            player.bank = zone.normalize_items(char.get("bank", []))
            player.durability = dict(char.get("durability", {}))
            player.friends = list(char.get("friends", []))
            player.parleys_won = list(char.get("parleys_won", []))
            player.factions = dict(char.get("factions", {}))
            player.work_order = char.get("work_order")
            player.known_recipes = list(char.get("known_recipes", []))
            player.diplomacy_deck = list(char.get("diplomacy_deck", [])) or None
            player.diplomacy_slots = char.get("diplomacy_slots")
            player.ignores = list(char.get("ignores", []))
            player.bank_coins = char.get("bank_coins", 0)
            if "equipment" in char:
                player.equipment = [tuple(e) for e in char["equipment"]]
            player.xp = char.get("adventure_xp", player.xp)
            player.learned = list(char.get("learned_abilities", []))
            player.abilities = (class_abilities.starting_abilities(args.client_dir, player.klass,
                                                                   learned=player.learned)
                                or player.abilities)
            PENDING_PLAYERS[state.get("session", "")] = player
            send_message(sock, addr, state, build_set_name_id(char))
            print(f"  <- sent WORLD event 10 (SetNameID {name!r} id={character_id(char):#x}, "
                  f"{races_classes.race_name(player.race)} {races_classes.class_name(player.klass)})")
            msg = build_zone_connect_event(args.world_address, args.zone_port, player.level)
            n = send_message(sock, addr, state, msg)
            print(f"  <- sent WORLD event 8 (connect to zone {args.world_address}:{args.zone_port}) ({n} packets)")
            return
    if server == "ZONE":
        if login:
            print(f"  >>> ZONE login request: account={login[0]!r} session={login[1]!r}")
            state["player"] = PENDING_PLAYERS.pop(login[1], None)
            state["session"] = login[1]
            ZONE_BY_SESSION[login[1]] = state
            if state["player"]:
                ONLINE[state["player"].name.lower()] = state
            send_message(sock, addr, state, build_login_reply(True))
            if state["player"]:
                social_login(state)
                guild_login(state)
                brotherhood_login(state)
                faction_login(state)
                workorder_login(state)
                mail_login(state)
            print("  <- sent ZONE PacketLoginReply(success=1)")
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x74:
            # Say (client event 0x74): wstr text. The client echoes "You say, ..."
            # itself, so nothing goes back to the speaker. Other players would get
            # zone event 0x0f via build_chat_line (verified live: field order is
            # text, speaker; channel CHAT_SAY = 3 shows "<speaker> says, ...").
            text = payload[10:].decode("utf-16-le", "replace").split(chr(0))[0]
            speaker = state["player"].name if state.get("player") else "Someone"
            print(f"  >>> ZONE say from {speaker!r}: {text!r}")
            hail_target = state.get("player") and state["player"].npcs.get(state["player"].target)
            if text.lower().startswith("hail") and hail_target and hail_target.alive and hail_target.talks():
                for m in npc_dialog(state, hail_target):
                    send_message(sock, addr, state, m)
            w = state.get("world")
            if w is not None and not text.startswith("!"):
                w.broadcast(lambda s: build_chat_line(speaker, text, CHAT_SAY), exclude=state)
            if text.startswith("!") and args.dev_commands:
                for m in dev_command(text, state.get("player")):
                    if isinstance(m, tuple) and m[0] == "npc_update":
                        if state.get("world"):
                            state["world"].broadcast(
                                lambda s, m=m: zone.npc_update(s, args, m[1], m[2]))
                        continue
                    elif isinstance(m, tuple) and m[0] == "faction":
                        adjust_faction(state, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "quest_kill":
                        quest_kill(state, m[1])
                        faction_kill(state, m[1])
                        continue
                    elif isinstance(m, tuple) and m[0] == "use":
                        use_ability(state, args, state["player"], m[1])
                        continue
                    elif isinstance(m, tuple) and m[0] == "learn":
                        learn_ability(state, *m[1:])
                        continue
                    elif isinstance(m, tuple) and m[0] == "bank":
                        handle_bank_event(state, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "give":
                        if give_item(state, m[1], m[2]):
                            quest_items_changed(state)
                        continue
                    elif isinstance(m, tuple) and m[0] == "trade_event":
                        handle_trade_event(state, m[1], bytes(10) + m[2], args)
                        continue
                    elif isinstance(m, tuple) and m[0] == "self_prop":
                        m = zone.player_pawn_update(state, args, m[2])
                    elif isinstance(m, tuple) and m[0] == "pawn_update":
                        loc = m[2]["Location"]
                        send_message(sock, addr, state, zone.player_teleport(loc))
                        # PawnPosition resets the client's ground-stick cache
                        # (LastValidServerPosition); without it the pawn snaps back.
                        m = zone.player_pawn_update(state, args, {"PawnPosition": (
                            loc, (0, 0, 0), (0.0, 0.0, 0.0))})
                    send_message(sock, addr, state, m)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in combat.RELEASE_EVENTS:
            # "Release to Bind" (0x542) on the death popup: back to the bind point
            # (for now the place the player entered the world) at full health.
            player = state.get("player")
            print(f"  >>> ZONE release ({payload[2:6].hex(' ')})")
            if player and player.health <= 0:
                player.health = player.stats["hit_points"]
                for m in (combat.death_popup(0, False),
                          zone.player_pawn_update(state, args, {"Health": 100, "m_bIsDead": 0}),
                          zone.health_update(player),
                          zone.player_teleport(player.spawned_at)):
                    send_message(sock, addr, state, m)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == combat.TARGET_EVENT:
            # Target selected (click, Tab): u64 entity id; 0 = target cleared.
            player = state.get("player")
            eid = struct.unpack_from("<Q", payload, 10)[0] if len(payload) >= 18 else 0
            npc = player.npcs.get(eid) if player else None
            print(f"  >>> ZONE target {eid:#x} ({npc.name if npc else '-'})")
            if player:
                player.target = eid or None
            send_message(sock, addr, state, combat.targets(npc))
            if player:
                # The target window's effect list belongs to the current target.
                send_message(sock, addr, state, effects.target_effects_clear())
                for e in getattr(player, "effects", []):
                    if e["kind"] == "dot" and e["npc"] is npc:
                        send_message(sock, addr, state, effects.target_effect_add(
                            e["id"], e["name"], e["desc"], e["icon"], player.char_id))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0xD0:
            # Use ability (FUN_0042ca80): i32 ability handle (MsgAbilityInfo field 5).
            handle = struct.unpack_from("<i", payload, 10)[0]
            player = state.get("player")
            ability = next((a for a in getattr(player, "abilities", []) if a[0] == handle), None)
            print(f"  >>> ZONE use ability {handle} ({ability[2] if ability else '?'})")
            if ability:
                use_ability(state, args, player, ability)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (
                combat.LOOT_REQUEST, combat.LOOT_TAKE, combat.LOOT_TAKE_ALL, combat.LOOT_CLOSE):
            # Loot window: request (u64 corpse), take one (i32 handle), take all (-1), close.
            event = struct.unpack_from("<I", payload, 2)[0]
            player = state.get("player")
            npc = player.npcs.get(player.target) if player and player.target else None
            print(f"  >>> ZONE loot event {event:#x}: {payload[10:].hex(' ')}")
            if npc and not npc.alive:
                if event == combat.LOOT_REQUEST:
                    msgs = combat.loot_messages(npc)
                elif event in (combat.LOOT_TAKE, combat.LOOT_TAKE_ALL):
                    msgs = combat.take_loot(player, npc, struct.unpack_from("<i", payload, 10)[0])
                    save_character_field(player.name, "items", [list(i) for i in player.items])
                else:
                    msgs = []
                for m in msgs:
                    send_message(sock, addr, state, m)
                if msgs:
                    quest_items_changed(state)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (EQUIP_EVENT, UNEQUIP_EVENT):
            # Right-click: in a bag = equip to the item's default slot (0x8e,
            # FUN_005042b0); on the paper doll = unequip (0x98). i32 handle, u8.
            player = state.get("player")
            event = struct.unpack_from("<I", payload, 2)[0]
            handle = struct.unpack_from("<i", payload, 10)[0]
            print(f"  >>> ZONE {'equip' if event == EQUIP_EVENT else 'unequip'} item {handle}: "
                  f"{payload[10:].hex(' ')}")
            if player and add_catalyst(state, handle):
                pass
            elif player:
                result = (zone.equip_item if event == EQUIP_EVENT else zone.unequip_item)(player, handle)
                if isinstance(result, str):
                    send_message(sock, addr, state, build_system_text(result, SYSTEM_TEXT_ERROR))
                else:
                    for m in result:
                        send_message(sock, addr, state, m)
                    gear_changed(state, args, player)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (
                merchant.REQ_OPEN, merchant.REQ_BUY, merchant.REQ_SELL, merchant.REQ_CLOSE,
                merchant.REQ_CLOSE2):
            event = struct.unpack_from("<I", payload, 2)[0]
            player = state.get("player")
            npc = player.npcs.get(player.target) if player and player.target else None
            print(f"  >>> ZONE merchant event {event:#x}: {payload[10:].hex(' ')}")
            msgs = []
            if event in (merchant.REQ_CLOSE, merchant.REQ_CLOSE2):
                msgs = [merchant.close_window(3)]
            elif npc is None or not npc.merchant or not npc.alive:
                msgs = [merchant.close_window(2)]          # "please target the merchant"
            elif event == merchant.REQ_OPEN:
                msgs = merchant.open_window(args.content, npc)
            elif event == merchant.REQ_BUY:
                handle, qty = struct.unpack_from("<ii", payload, 10)
                msgs = merchant.buy(args.content, npc, player, handle, qty,
                                    lambda iid, name, icon, q, slot: zone.zone_event(
                                        0x197, vgmsg.inventory_item(iid, name, slot, icon, q,
                                                                    **zone.item_equip_fields(name))))
            elif event == merchant.REQ_SELL:
                handle = struct.unpack_from("<i", payload, 10)[0]
                msgs = merchant.sell(args.content, npc, player, handle)
            for m in msgs:
                send_message(sock, addr, state, m)
            if event in (merchant.REQ_BUY, merchant.REQ_SELL) and player is not None:
                save_character_field(player.name, "items", [list(i) for i in player.items])
                save_character_field(player.name, "coins", player.coins)
                if event == merchant.REQ_BUY:
                    quest_items_changed(state)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (
                merchant.REQ_REPAIR_OPEN, merchant.REQ_REPAIR, merchant.REQ_REPAIR_ALL):
            if state.get("player"):
                handle_repair_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in brotherhood.ZONE_EVENTS:
            if state.get("player"):
                handle_brotherhood(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in guild.CLIENT_EVENTS:
            if state.get("player"):
                handle_guild_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in social.ZONE_EVENTS:
            if state.get("player"):
                handle_social_zone(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in mail.CLIENT_EVENTS:
            if state.get("player"):
                handle_mail_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in workorder.CLIENT_EVENTS:
            if state.get("player"):
                handle_workorder_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in faction.CLIENT_EVENTS:
            if state.get("player"):
                handle_faction_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in bank.CLIENT_EVENTS:
            if state.get("player"):
                handle_bank_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in trainer.RECIPE_EVENTS:
            if state.get("player"):
                handle_recipe_trainer_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in trainer.CLIENT_EVENTS:
            if state.get("player"):
                handle_trainer_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in diplomacy.CLIENT_EVENTS:
            if state.get("player"):
                handle_parley_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in craft.CLIENT_EVENTS:
            if state.get("player"):
                handle_craft_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in harvest.CLIENT_EVENTS:
            if state.get("player"):
                handle_harvest_event(state, struct.unpack_from("<I", payload, 2)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in quest.CLIENT_EVENTS:
            if state.get("player"):
                handle_quest_event(state, struct.unpack_from("<I", payload, 2)[0], payload)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in trade.CLIENT_EVENTS:
            if state.get("player"):
                handle_trade_event(state, struct.unpack_from("<I", payload, 2)[0], payload, args)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in group.CLIENT_EVENTS:
            if state.get("player"):
                handle_group_event(state, struct.unpack_from("<I", payload, 2)[0], payload)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x73 and state.get("player"):
            # /sit, /stand: u8 1/0. Pawn m_bResting = 1 sits (verified live).
            player = state["player"]
            player.resting = bool(payload[10]) if len(payload) > 10 else False
            values = {"m_bResting": int(player.resting)}
            send_message(sock, addr, state, zone.player_pawn_update(state, args, values))
            if state.get("world"):
                state["world"].broadcast(lambda s: zone.remote_player_update(s, args, player, values),
                                         exclude=state)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x40B and state.get("player"):
            # /camp: 0x40b starts ("It will take 20 seconds..."), 0x40e {i32 seconds}
            # counts down, 0x40c finishes, 0x40d abandons (moving cancels it).
            state["camp"] = {"until": time.time() + CAMP_SECONDS, "pos": state.get("position"),
                             "next_note": time.time() + 5}
            send_message(sock, addr, state, zone.zone_event(0x40B))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == combat.CONSIDER_REQUEST:
            player = state.get("player")
            npc = player.npcs.get(player.target) if player and player.target else None
            if npc:
                send_message(sock, addr, state, harvest.consider(npc, player_skill(player, harvest.SKILLS[npc.harvest["kind"]])) if npc.harvest
                             else combat.consider(player, npc))
                line = faction_consider(player, npc)
                if line:
                    send_message(sock, addr, state, line)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == CHUNK_CHANGE_EVENT:
            chunk_handoff(state, payload, args)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (0x313, 0x314):
            # 0x314 /emote {wstr}; 0x313 social {eid64 target, wstr name, wstr}. The
            # client prints nothing itself: send the emote line (zone 0x0f type 5) and,
            # for socials, play SOCIAL_ABILITIES_<id> (0x3d1) to everyone nearby.
            event = struct.unpack_from("<I", payload, 2)[0]
            player = state.get("player")
            w = state.get("world")
            if player and event == 0x314:
                text = payload[10:].decode("utf-16-le", "replace").split(chr(0))[0]
                msgs = [build_chat_line(player.name, text, CHAT_EMOTE)]
            elif player:
                target = struct.unpack_from("<Q", payload, 10)[0]
                name = payload[18:].decode("utf-16-le", "replace").split(chr(0))[0].upper()
                aid = chat.social_ids(args.client_dir).get(name)
                print(f"  >>> ZONE social {name} -> {aid}")
                msgs = []
                if aid:
                    msgs.append(combat.display_ability(player.char_id, target, aid))
                    msgs.append(build_chat_line(player.name, name.lower().replace("_", " ") + "s.",
                                                CHAT_EMOTE))
            else:
                msgs = []
            for m in msgs:
                send_message(sock, addr, state, m)
                if w is not None:
                    w.broadcast(lambda s, m=m: m, exclude=state)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x3D8:
            # Auto-attack toggle (` key, /autoattacktoggle): no payload.
            player = state.get("player")
            if player:
                lines = combat.toggle_auto_attack(player)
                print(f"  >>> ZONE auto-attack {'on' if player.auto_attack else 'off'}")
                for m in combat_results(state, args, player, lines, None, player.health > 0,
                                        not player.auto_attack):
                    send_message(sock, addr, state, m)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (0x54B, 0x54C):
            # Hotbar slot changed (0x54b MsgHotkeyAdd) or cleared (0x54c bank+slot).
            # Saved per character and sent back at the next login (zone.ability_messages).
            event = struct.unpack_from("<I", payload, 2)[0]
            print(f"  >>> ZONE hotbar {'set' if event == 0x54B else 'clear'}: {payload[10:].hex(' ')}")
            player = state.get("player")
            (hotbar_bank,), pos = read_wstrings(payload[10:], 0, 1)
            slot = struct.unpack_from("<i", payload, 10 + pos)[0]
            if player is not None:
                if player.hotbar is None:
                    player.hotbar = {f"m_wb:{s}": vgmsg.hotkey(s, a[1]).hex()
                                     for s, a in enumerate(player.abilities[:12])}
                key = f"{hotbar_bank}:{slot}"
                if event == 0x54B:
                    player.hotbar[key] = payload[10:].hex()
                else:
                    player.hotbar.pop(key, None)
                save_character_field(player.name, "hotbar", player.hotbar)
        elif msg_type == 2:
            print_client_log(payload)
        elif msg_type == 1:
            zone.handle_unreal(lambda m: send_message(sock, addr, state, m), state, payload, args)
        elif msg_type == 9:
            # Ping: u16 9 + 64-bit client timestamp. The client's type-9 handler
            # (FUN_006edcd0) computes latency as now - timestamp, so echo it back.
            send_message(sock, addr, state, payload)
            state["pings"] = state.get("pings", 0) + 1
            if state["pings"] == 1:
                print("  <- echoing ZONE pings (type 9); further pings not logged")
        else:
            print(f"  >>> ZONE message type {msg_type} ({len(payload)} bytes): {payload[:64].hex(' ')}")
        return
    if server == "WORLD":
        if login:
            # World login request has the same layout as the login-server one
            # (field1 = account, field2 = session key from event 0x27). ClientWorldApi's
            # dispatcher (FUN_00d9aa60) reads type 4 with the same reader (FUN_00d9a900).
            print(f"  >>> WORLD login request: account={login[0]!r} session={login[1]!r}")
            state["session"] = login[1]
            WORLD_BY_SESSION[login[1]] = (sock, addr, state)
            reply = build_reliable(state["out_seq"], build_login_reply(True))
            state["out_seq"] += 1
            sock.sendto(reply, addr)
            print(f"  <- sent WORLD PacketLoginReply(success=1): {reply.hex(' ')}")

            # World event 1 (dispatcher FUN_0062aaf0): "Successfully logged into
            # WorldServer." and posts UI event 0x19. Empty event data.
            event = struct.pack("<HII", 2, 1, 0)
            reply = build_reliable(state["out_seq"], event)
            state["out_seq"] += 1
            sock.sendto(reply, addr)
            print(f"  <- sent WORLD event 1 (logged in): {reply.hex(' ')}")
        elif msg_type == 2 and event_id == brotherhood.LEAVE:
            # /brotherhoodleave (after its confirm popup) arrives as a world type-2 event.
            zone_state = ZONE_BY_SESSION.get(state.get("session"))
            if zone_state and zone_state.get("player"):
                handle_brotherhood(zone_state, event_id, payload[10:])
        elif msg_type == 2 and event_id != 0x6F and LOGIN_CONN and try_delete_character(
                LOGIN_CONN["sock"], LOGIN_CONN["addr"], LOGIN_CONN["state"], payload):
            pass  # the refreshed account list (0x66) goes out on the login connection
        elif msg_type == 2:
            print_client_log(payload)
        elif msg_type == 5 and len(payload) >= 10:
            event = struct.unpack_from("<I", payload, 2)[0]
            print(f"  >>> WORLD social {event:#x}: {payload[10:42].hex(' ')}")
            zone_state = ZONE_BY_SESSION.get(state.get("session"))
            if zone_state and zone_state.get("player"):
                handle_social_world(zone_state, event, payload[10:],
                                    lambda m: send_message(sock, addr, state, m))
        elif msg_type == 6 and len(payload) >= 10:
            # Slash command text (/shout -> "shout ...", /ooc -> "regionsay ...",
            # /tell X -> 'tell "X" ...', /g -> "gsay ..."): u16 6, u32 0x14, u32 len, wstr.
            text = payload[10:].decode("utf-16-le", "replace").split(chr(0))[0]
            print(f"  >>> WORLD command {struct.unpack_from('<I', payload, 2)[0]:#x}: {text!r}")
            zone_state = ZONE_BY_SESSION.get(state.get("session"))
            if zone_state and zone_state.get("player"):
                world_chat(zone_state, text, lambda m: send_message(sock, addr, state, m))
        else:
            print(f"  >>> WORLD message type {msg_type} ({len(payload)} bytes) - paste this to Claude")
        return
    LOGIN_CONN.update(sock=sock, addr=addr, state=state)
    if login:
        reply = build_reliable(state["out_seq"], build_login_reply(True))
        state["out_seq"] += 1
        sock.sendto(reply, addr)
        print(f"  <- sent PacketLoginReply(success=1): {reply.hex(' ')}")

        # Server-select list entry for our world (event 0x25).
        reply = build_reliable(state["out_seq"], build_world_list_entry_event(WORLD_NAME))
        state["out_seq"] += 1
        sock.sendto(reply, addr)
        print(f"  <- sent world list entry event 0x25 ({WORLD_NAME!r}, status Up)")

        send_account_character_list(sock, addr, state)

        # Tell the client which world server to use (event 0x27).
        event = build_world_server_event(login[0], login[1], WORLD_NAME, args.world_address)
        packets, state["out_seq"] = build_reliable_fragments(state["out_seq"], event, state["max_raw"])
        for pkt in packets:
            sock.sendto(pkt, addr)
        print(f"  <- sent world-server event 0x27 (address={args.world_address!r}) "
              f"in {len(packets)} fragments")
    elif event_id == 0x139:
        # Character create request: event data starts with first name, last name
        # and world name as NUL-terminated UTF-16LE; the rest (race/class/appearance)
        # is not decoded yet and is kept as hex.
        data = payload[10:]
        (first, last, world), pos = read_wstrings(data, 0, 3)
        print(f"  >>> character create request: {first!r} {last!r} on {world!r}; "
              f"rest={data[pos:].hex(' ')}")
        chars = load_characters()
        if any(c["first"].lower() == first.lower() for c in chars):
            result = 1  # "That first name is already taken."
        else:
            result = 0
            chars.append({"first": first, "last": last, "world": world, "raw": data[pos:].hex()})
            save_characters(chars)
        if result == 0 and WORLD_CONN:
            # Put it in the character-select list before the client tries to select it.
            w = WORLD_CONN
            n = send_message(w["sock"], w["addr"], w["state"], build_character_record(chars[-1]))
            print(f"  <- sent WORLD character record 0x19: {first} {last} ({n} packets)")
        if result == 0:
            send_account_character_list(sock, addr, state)
        n = send_message(sock, addr, state, build_character_create_result(result, first))
        print(f"  <- sent character create result 0x386: result={result} ({n} packets)")
    elif msg_type == 2 and event_id != 0x6F and try_delete_character(sock, addr, state, payload):
        pass
    elif msg_type == 2:
        print_client_log(payload)
    else:
        print(f"  >>> UNKNOWN login message type {msg_type} - paste this to Claude")


def try_delete_character(sock, addr, state, payload):
    """VGMessages::MsgClientCharacterDelete (ctor FUN_00490670): two wstrings, the
    first name and an empty string. Verified live: sent as LOGIN event 0x13a after the
    "Confirm Delete" dialog. Matching on the name (not the id) keeps this working if
    other builds number it differently. The delete-result event ("Character
    deleted.", FUN_0048d080) is not known yet; the refreshed 0x66 list is enough."""
    event_id = struct.unpack_from("<I", payload, 2)[0]
    data = payload[10:]
    try:
        (name, other), _ = read_wstrings(data, 0, 2)
    except (UnicodeDecodeError, struct.error):
        return False
    chars = load_characters()
    keep = [c for c in chars if c["first"] != name]
    if not name or len(keep) == len(chars):
        return False
    save_characters(keep)
    print(f"  >>> event 0x{event_id:x} looks like DELETE of {name!r} ({other!r}); removed it")
    send_account_character_list(sock, addr, state)
    return True


def print_client_log(payload):
    # Event envelope u16 2 | u32 eventId | u32 len | data. Event 0x6f is a client
    # log line: u16 0x0c, string file, string text (u32 length-prefixed).
    try:
        _, event_id, _ = struct.unpack_from("<HII", payload, 0)
        if event_id != 0x6F:
            print(f"  >>> client event 0x{event_id:x} ({len(payload)} bytes): {payload[10:].hex(' ')}")
            return
        pos = 2 + 4 + 4 + 2
        (n,) = struct.unpack_from("<I", payload, pos)
        logfile = payload[pos + 4:pos + 4 + n].decode("utf-8", "replace")
        pos += 4 + n
        (n,) = struct.unpack_from("<I", payload, pos)
        text = payload[pos + 4:pos + 4 + n].decode("utf-8", "replace").rstrip()
        print(f"  >>> client log [{logfile}]: {text}")
    except struct.error:
        print("  >>> client log message (unparsed)")


if __name__ == "__main__":
    main()
