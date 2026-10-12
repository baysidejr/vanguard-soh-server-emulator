"""Minimal Vanguard login-server stub: logs every UDP packet and answers the
UdpLibrary connect handshake so the client sends its PacketLoginRequest.

Formats come from static analysis of bin/VGClient.exe (see function addresses
in comments). Run:  python login_stub.py [--port 10101]
"""
import argparse
import json
import os
import random
import select
import socket
import struct
import time

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
import bank
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
    for w in world.all_worlds():
        players = w.players()
        for npc in w.npcs.values():
            victim = combat.proximity_aggro(npc, players)
            if victim is not None:
                vs = w.members.get(victim.char_id)
                if vs is not None:
                    vs["send"](build_system_text(f"{npc.name} notices you!", SYSTEM_TEXT_ERROR))
        for npc in w.npcs.values():
            target = npc.aggro_on.live_position if npc.aggro_on else None
            values = combat.chase_step(npc, target, MOVE_TICK)
            if values:
                w.broadcast(lambda s, npc=npc, values=values: zone.npc_update(s, args, npc, values))


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


def world_chat(zone_state, command, reply):
    """Chat commands from the world connection (see chat.py)."""
    player = zone_state["player"]
    verb, name, text = chat.parse(command)
    if verb == "shout":
        for s in ONLINE.values():
            if s is not zone_state:
                world_send(s, chat.line(text, player.name, chat.SHOUT))
        reply(chat.echo(text, chat.SHOUT))
    elif verb == "tell":
        target = ONLINE.get((name or "").lower())
        if target is zone_state:
            reply(chat.error(chat.ERR_TELL_SELF))
        elif target is None:
            reply(chat.error(chat.ERR_NOT_ONLINE))
        else:
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
    elif verb == "regionsay":
        for s in ONLINE.values():
            if s is not zone_state:
                world_send(s, chat.channel_line(text, player.name, "OOC"))
        reply(chat.echo_to(text, "OOC", chat.CHANNEL))


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
    if opts:
        out.append(quest.options(npc.entity_id, opts))
    if npc.merchant:
        out.append(zone.zone_event(merchant.DIALOG_WARES))
    if npc.repairs:
        out.append(zone.zone_event(merchant.DIALOG_REPAIR))
    if npc.trainer:
        out.append(zone.zone_event(trainer.OPTION))
    if npc.banker:
        out.append(zone.zone_event(bank.OPTION))
    return out


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
        p = diplomacy.Parley(config, dip["cards"], dip["deck"])
        p.npc = npc
        state["parley"] = p
        for m in diplomacy.deck_messages(dip["cards"], dip["deck"], resend=state.get("deck_sent", False)):
            send(m)
        state["deck_sent"] = True
        send(diplomacy.open_parley(npc.entity_id, p))
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
    save_character_field(player.name, "durability", player.durability)


def bank_record(item_id, name, icon, qty, slot):
    return vgmsg.inventory_item(item_id, name, slot, icon, qty, **zone.item_equip_fields(name))


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
            send(bank.item(bank_record(*i)))
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
            send(bank.item(bank_record(*i)))
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
            learned.append(aid)
            player.learned = learned
            ability = class_abilities.ability_tuple(n, aid, tag)
            ability = (max([a[0] for a in player.abilities] + [0]) + 1,) + ability[1:]
            player.abilities.append(ability)
            send(zone.zone_event(0x215, vgmsg.ability_info(ability[0], aid, ability[2], ability[3],
                                                         ability[4], refresh=ability[5])))
            send(trainer.result(aid, trainer.OK))
            send(build_system_text(f"You have learned {ability[2]}.", SYSTEM_TEXT_WHITE))
            save_character_field(player.name, "coins", player.coins)
            save_character_field(player.name, "learned_abilities", learned)
            print(f"  {player.name} learned {ability[2]}")
    elif event == trainer.STOP:
        state.pop("training", None)
        send(trainer.end())


def finish_parley(state, p, result):
    player, send = state["player"], state["send"]
    state.pop("parley", None)
    if result == "lost":
        send(diplomacy.lost())
        print(f"  {player.name} lost a parley with {p.npc.name}")
        return
    send(diplomacy.won())
    reward = p.config.get("reward", {})
    if reward.get("coin"):
        player.coins += reward["coin"]
        send(merchant.coins(player.coins))
        save_character_field(player.name, "coins", player.coins)
    send(combat.experience_reward(reward.get("xp", 0), p.npc.entity_id, kind=2))
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
        state["craft"] = {"recipe": None, "step": 0, "ap": 0}
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
            session["recipe"] = r
            send(craft.recipe_result(craft.RECIPE_OK, r["id"]))
    elif event == craft.CONFIRM and session["recipe"]:
        send(craft.workbench())
    elif event == craft.BEGIN and session["recipe"]:
        session.update(stage=0, done=set(), ap=0, quality=500, comp=None, had_comp=False)
        for m in craft.started(session["quality"]):
            send(m)
    elif event == craft.ACTION and session["recipe"]:
        craft_action(state, session, struct.unpack_from("<i", data, 0)[0])


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
    if words[0] == "questkill" and player:
        # !questkill: count a kill of the target's kind toward active quests (testing).
        npc = player.npcs.get(player.target)
        return [("quest_kill", npc)] if npc else []
    if words[0] == "give" and len(words) >= 2 and player:
        # !give <item name> [qty]: put an item from items.json in the bags (testing).
        qty = int(words[-1]) if words[-1].isdigit() and len(words) > 2 else 1
        name = " ".join(words[1:-1] if qty > 1 or words[-1] == "1" else words[1:])
        return [("give", name, qty)]
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
            if text.lower().startswith("hail") and hail_target and hail_target.alive                     and (hail_target.merchant or hail_target.quests or hail_target.trainer
                                       or hail_target.banker):
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
                    elif isinstance(m, tuple) and m[0] == "quest_kill":
                        quest_kill(state, m[1])
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
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0xD0:
            # Use ability (FUN_0042ca80): i32 ability handle (MsgAbilityInfo field 5).
            handle = struct.unpack_from("<i", payload, 10)[0]
            player = state.get("player")
            ability = next((a for a in getattr(player, "abilities", []) if a[0] == handle), None)
            print(f"  >>> ZONE use ability {handle} ({ability[2] if ability else '?'})")
            if ability:
                was_alive, attacking = player.health > 0, player.auto_attack
                lines, npc = combat.use_ability(player, ability)
                for m in combat_results(state, args, player, lines, npc, was_alive, attacking):
                    send_message(sock, addr, state, m)
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
            if player:
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
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in bank.CLIENT_EVENTS:
            if state.get("player"):
                handle_bank_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
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
        elif msg_type == 2 and event_id != 0x6F and LOGIN_CONN and try_delete_character(
                LOGIN_CONN["sock"], LOGIN_CONN["addr"], LOGIN_CONN["state"], payload):
            pass  # the refreshed account list (0x66) goes out on the login connection
        elif msg_type == 2:
            print_client_log(payload)
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
