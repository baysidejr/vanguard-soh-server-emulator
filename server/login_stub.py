"""Minimal Vanguard login-server stub: logs every UDP packet and answers the
UdpLibrary connect handshake so the client sends its PacketLoginRequest.

Formats come from static analysis of bin/VGClient.exe (see function addresses
in comments). Run:  python login_stub.py [--port 10101]
"""
import argparse
import json
import math
import os
import re
import random
import select
import socket
import storage
import accounts
import struct
import sys
import time
import types
import traceback
import zlib

import races_classes
import ue2net
import vgmsg
import class_abilities
import chat
import combat
import aa
import attributes
import hints
import group
import grouploot
import encounter
import reactions
import trade
import quest
import harvest
import craft
import trainer
import faction
import workorder
import mail
import market
import housing
import titles
import travel
import duel
import pets
import caravan
import fishing
import forms
import assembly
import bank
import social
import songs
import effects
import guild
import brotherhood
import bugs
import diplomacy
import content
import merchant
import start_areas
import world
import zone

# Connect request built in UdpConnection::GiveTime (FUN_00c02830):
#   00 01 | u32be protocol(3) | u32be connectCode | u32be maxRawPacketSize | cstring
# Connect confirm parsed in UdpConnection::ProcessCookedPacket case 2 (FUN_00c01e70):
#   00 02 | u32be connectCode | u32be encryptCode | u8 crcBytes |
#   u8 encryptMethod1 | u8 encryptMethod2 | u32be maxRawPacketSize | u32be protocol
from soe import *                 # noqa: F401,F403 (transport: send_message, resend_tick, ...)
from soe import PROTOCOL_VERSION, MAX_RAW_PACKET, MIN_RAW_PACKET, SEND_FAILURES, RECEIVE_GAPS
WORLD_NAME = "Stub World"
CLIENT_IDLE_SECONDS = 180  # a connection silent this long is gone

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
        if len(data) < 4:
            print(f"{indent}  reliable packet too short for a sequence number")
            return
        (seq,) = struct.unpack_from(">H", data, 2)
        print(f"{indent}  reliable seq={seq}")
        describe(data[4:], indent + "  ")


def build_login_reply(success):
    # Client::PacketLoginReply (ctor FUN_00d9a0f0, reader FUN_00d9a840):
    # u16le type=4, u8 success. The client stores the byte as its logged-in flag.
    return struct.pack("<HB", 4, 1 if success else 0)


# Login failure: login event 2 {i32 code} (dispatcher FUN_00617b10 -> FUN_0051d0e0) opens the
# client's own popup: 50 / 51 "Invalid login account name. Please exit and try again.", 52 / 54 /
# 1015 no Vanguard subscription, 53 account suspended, 1002 "Login session timed out. Please exit
# and reenter the game through Launchpad.", anything else "Login failed.".
LOGIN_FAILED_EVENT = 2
LOGIN_BAD_ACCOUNT, LOGIN_SUSPENDED, LOGIN_SESSION_EXPIRED = 50, 53, 1002


def build_login_failure(code):
    return struct.pack("<HIIi", 2, LOGIN_FAILED_EVENT, 4, code)


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--launcher-port", type=int, default=10180,
                        help="HTTP port of the launcher login endpoint (tools/play.py); 0 turns it off")
    parser.add_argument("--anonymous-zone", action="store_true",
                        help="debugging: let a zone connection enter the world without logging in "
                             "(as 'Someone'); never on a public server")
    parser.add_argument("--enforce-movement", action="store_true",
                        help="move players back when they report impossible movement (speed or "
                             "teleport hacks); otherwise it is only logged")
    parser.add_argument("--backup-hours", type=float, default=6.0,
                        help="copy the database to <data folder>/backups this often (0: never); keeps 10")
    parser.add_argument("--data-dir", default=None,
                        help="folder for the saved data (vanguard.db, reports); default: the server folder")
    parser.add_argument("--launcher-cert", default=None,
                        help="PEM certificate: serve the launcher over HTTPS (passwords encrypted)")
    parser.add_argument("--launcher-key", default=None,
                        help="PEM private key for --launcher-cert (if not in the same file)")
    parser.add_argument("--allow-registration", action="store_true",
                        help="let the launcher create accounts (POST /register)")
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
    parser.add_argument("--quest-feedback", action="store_true",
                        help="open the client's Quest Feedback window after each completed quest")
    parser.add_argument("--quiet-packets", action="store_true",
                        help="don't print every packet's hex dump and acks (for a long-running server)")
    parser.add_argument("--camp-start", action="store_true",
                        help="start new characters at the hand-made camp in the Sundering Wastelands (testing) "
                             "instead of the starting area the client's create screen picked (start_areas.py, B-017)")
    parser.add_argument("--start-areas", action="store_true", help=argparse.SUPPRESS)   # the default since B-017
    parser.add_argument("--dev-commands", action="store_true",
                        help="enable !stat / !event chat commands (see dev_command)")
    parser.add_argument("--test-npc", action="store_true",
                        help="no longer needed: NPCs always come from content/spawns/<chunk>.json")
    parser.add_argument("--spawn-rotation", action="store_true",
                        help="include an initial rotation in the actor open bunch")
    args = parser.parse_args()
    # Player text (chat, names, mail) can hold any character. Printing it to a log file with the
    # Windows default code page raised UnicodeEncodeError inside the handler, so the message was
    # never acted on (found by tools/fuzz.py).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    if args.data_dir:
        use_data_dir(args.data_dir)
    global AUDIT_FILE
    AUDIT_FILE = os.path.join(os.path.dirname(CHARACTERS_FILE), "audit.log")
    # Used when a zone connection arrives without going through Play first (--anonymous-zone).
    args.default_player = lambda: zone.Player(name="Someone",
                                              level=args.zone_level or chunk_name(*DEFAULT_CHUNK))
    args.package_maps = {}
    args.content = content.Content()
    args.npc_dialog = npc_dialog
    args.harvest_begin = lambda state: handle_harvest_event(state, harvest.BEGIN)
    args.use_tombstone = use_tombstone
    args.on_move = on_move
    args.open_loot = open_loot
    # The owner's pawn is ROLE_AutonomousProxy on the client (wire Role 3, RemoteRole 4) and is
    # handed over with GivePawn, so the player moves it with the keyboard (docs/MOVEMENT.md).
    # PAWN_ROLE=off restores the old simulated pawn (for comparison).
    args.pawn_role = None if os.environ.get("PAWN_ROLE") == "off" else (3, 4)
    args.placed_objects = placed_objects
    args.craft_event = lambda state, event, data: handle_craft_event(state, event, data)
    global ARGS
    ARGS = args
    quest.WHERE = quest_where           # quest pages carry the turn-in NPC's place
    args.zone_in_events = [int(v, 0) for v in args.zone_in_events.split(",") if v]

    login_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    login_sock.bind((args.host, args.port))
    world_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    world_sock.bind((args.host, args.world_port))
    zone_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    zone_sock.bind((args.host, args.zone_port))
    names = {login_sock: "LOGIN", world_sock: "WORLD", zone_sock: "ZONE"}
    for sock in names:
        # Non-blocking so the loop can drain every waiting packet per wake-up; big buffers
        # so bursts (many players moving) are not dropped.
        sock.setblocking(False)
        for opt in (socket.SO_RCVBUF, socket.SO_SNDBUF):
            try:
                sock.setsockopt(socket.SOL_SOCKET, opt, 4 * 1024 * 1024)
            except OSError:
                pass
    storage.keep_open(os.path.dirname(CHARACTERS_FILE))
    dev_password = accounts.ensure_dev_account()
    if dev_password:
        print(f"Created account '{accounts.DEV_ACCOUNT}' (password {dev_password}); launcher tokens "
              f"12345678 and 22222222 log in as it. Manage accounts with server/accounts.py.")
    chars = load_characters()
    if any("account" not in c for c in chars):
        for c in chars:
            c.setdefault("account", accounts.DEV_ACCOUNT)
        save_characters(chars)
        print(f"Characters without an account were given to '{accounts.DEV_ACCOUNT}'.")
    if args.launcher_port:
        accounts.serve_launcher(args.host, args.launcher_port, args.allow_registration,
                                args.launcher_cert, args.launcher_key)
        print(f"Launcher login on {'HTTPS' if args.launcher_cert else 'HTTP'} {args.host}:{args.launcher_port}"
              f"{' (registration open)' if args.allow_registration else ''}")
    print(f"Login stub listening on UDP {args.host}:{args.port}")
    print(f"World stub listening on UDP {args.host}:{args.world_port}")
    print(f"Zone stub listening on UDP {args.host}:{args.zone_port}")

    # Per-(server, client) state: next outgoing reliable seq, reliable seqs already handled.
    clients = {}

    next_tick = next_move = time.time() + 1
    next_flush = time.time()
    import signal
    stop = []
    for sig in ("SIGTERM", "SIGBREAK"):          # a service stop, or Ctrl+Break on Windows
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), lambda *_: stop.append(1))
    start_console()
    try:
        while not stop:
            for line in console_lines():
                if console_command(line, clients, args) == "stop":
                    stop.append(1)
            t_idle = time.time()
            ready, _, _ = select.select([login_sock, world_sock, zone_sock], [], [],
                                        max(min(next_tick, next_move, next_flush) - time.time(), 0))
            LOOP_STATS[1] += time.time() - t_idle
            for sock in ready:
                # Read everything already waiting (up to a limit, so ticks still run on time):
                # one select per packet was a large share of the time with many players.
                for _ in range(MAX_READS_PER_WAKE):
                    try:
                        data, addr = sock.recvfrom(65535)
                    except BlockingIOError:
                        break
                    except ConnectionResetError:
                        # Windows reports an ICMP "port unreachable" from a client that
                        # went away as an error on the next recvfrom; just carry on.
                        continue
                    LOOP_STATS[0] += 1
                    guarded(serve, sock, names[sock], data, addr, clients, args)
            if time.time() >= next_flush:
                # Queued movement goes out FLUSH_HZ times a second, many bunches per packet.
                next_flush = time.time() + 1.0 / FLUSH_HZ
                guarded(world.flush_bunches, zone.unreal_message)
            if time.time() >= next_move:
                next_move = time.time() + MOVE_TICK
                guarded(movement_tick, zone_sock, clients, args)
                guarded(resend_tick, clients, time.time())
            if time.time() >= next_tick:
                next_tick = time.time() + 1
                guarded(world_tick, zone_sock, clients, args)
    except KeyboardInterrupt:
        pass
    shutdown(clients, args)


import queue as _queue
CONSOLE = _queue.Queue()


def start_console():
    """Read operator commands typed into the server's window (a background thread; the main
    loop runs them). Without a console (output to a file, started as a service) it ends at once."""
    import threading

    def read():
        try:
            for line in sys.stdin:
                CONSOLE.put(line.strip())
        except (OSError, ValueError):
            pass
    if sys.stdin is not None and sys.stdin.isatty():
        threading.Thread(target=read, daemon=True).start()
        print("Console: who, announce <text>, kick <name>, backup, reload, stop (or help)")


# Content reload (for tools/editor.py): every few seconds the server looks at the content files'
# modification times; when one changed and the whole folder still validates, it reloads them.
# Templates, items, dialogs, quests and the rest apply at once; changed spawns apply to chunks
# loaded after the reload (a running chunk keeps its NPCs).
CONTENT_CHECK_SECONDS = 5.0
CONTENT_STAMP = [None, 0.0]


def content_stamp(directory=content.CONTENT_DIR):
    stamp = 0.0
    for base, _dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".json"):
                stamp = max(stamp, os.path.getmtime(os.path.join(base, f)))
    return stamp


def force_content_reload(args):
    """Apply changed content now instead of at the next 5-second check (console `reload`,
    builder `!reload`). Returns the validation problems ([] when it reloaded)."""
    CONTENT_STAMP[0], CONTENT_STAMP[1] = -1.0, 0.0
    problems = content.validate()
    if problems:
        print(f"  !!! content has {len(problems)} problem(s); keeping the old content: {problems[0]}")
        CONTENT_STAMP[1] = time.time() + CONTENT_CHECK_SECONDS
        return problems
    content_reload_tick(args, time.time())
    return []


def content_reload_tick(args, now):
    if now < CONTENT_STAMP[1]:
        return
    CONTENT_STAMP[1] = now + CONTENT_CHECK_SECONDS
    stamp = content_stamp()
    if CONTENT_STAMP[0] is None:
        CONTENT_STAMP[0] = stamp
        return
    if stamp == CONTENT_STAMP[0]:
        return
    CONTENT_STAMP[0] = stamp
    problems = content.validate()
    if problems:
        print(f"  !!! content changed but has {len(problems)} problem(s); keeping the old content: {problems[0]}")
        return
    args.content = content.Content()
    zone.ITEM_CONTENT = args.content
    print("  content reloaded (changed files)")
    mobs_stamp = npc_files_stamp(args.content.directory)
    mobs_changed = SPAWN_STAMPS.get("mobs.json") not in (None, mobs_stamp)
    SPAWN_STAMPS["mobs.json"] = mobs_stamp
    for w in world.all_worlds():
        # A changed file NPCs are built from (NPC_FILES) re-creates the NPCs of every loaded chunk too.
        if w.populated and (mobs_changed or spawn_stamp(args, w.level) != SPAWN_STAMPS.get(w.level)):
            refresh_world_spawns(w, args)


# Spawn files edited while their chunk is loaded (the web editor, by hand) are applied at the
# next reload: the chunk's spawned NPCs are closed and created again from the file for everyone
# there. The builder commands change the world themselves, so they record the new stamp.
NPC_FILES = ("mobs.json", "quests.json", "dialogs.json", "loot.json")   # read by zone.npc_from_template


def npc_files_stamp(directory):
    return max((os.path.getmtime(os.path.join(directory, f)) for f in NPC_FILES
                if os.path.exists(os.path.join(directory, f))), default=None)


SPAWN_STAMPS = world.SPAWN_STAMPS     # level -> spawn file mtime the world matches


def spawn_stamp(args, level):
    path = os.path.join(args.content.directory, "spawns", level + ".json")
    return os.path.getmtime(path) if os.path.exists(path) else None


def refresh_world_spawns(w, args):
    old = [eid for eid in w.npcs if zone.SPAWN_EID_BASE <= eid < zone.SPAWN_EID_BASE + 0x100000]
    for eid in old:
        del w.npcs[eid]
        w.broadcast(lambda s, eid=eid: zone.close_actor(s, eid))
    zone.populate_world(w, args)
    SPAWN_STAMPS[w.level] = spawn_stamp(args, w.level)
    for eid, npc in list(w.npcs.items()):
        if zone.SPAWN_EID_BASE <= eid < zone.SPAWN_EID_BASE + 0x100000:
            w.broadcast(lambda s, npc=npc: zone.open_npc(s, args, npc))
    print(f"  spawns of {w.level} reloaded: {len(old)} NPCs replaced by "
          f"{sum(1 for e in w.npcs if zone.SPAWN_EID_BASE <= e < zone.SPAWN_EID_BASE + 0x100000)}")


def console_lines():
    while True:
        try:
            yield CONSOLE.get_nowait()
        except _queue.Empty:
            return


def console_command(line, clients, args):
    """One operator command. Returns "stop" for stop / quit."""
    word, _, rest = line.partition(" ")
    word = word.lower()
    if word in ("stop", "quit", "shutdown"):
        return "stop"
    if word == "who":
        names = sorted(s["player"].name for s in ONLINE.values() if s.get("player") is not None)
        print(f"{len(names)} online: {', '.join(names) or '-'}")
    elif word in ("announce", "say") and rest:
        for s in list(ONLINE.values()):
            if s.get("send"):
                s["send"](build_system_text(f"Server: {rest}", SYSTEM_TEXT_COMBAT))
        print(f"announced to {len(ONLINE)} players")
    elif word == "kick" and rest:
        s = ONLINE.get(rest.strip().lower())
        if s is None:
            print(f"{rest} is not online")
        else:
            s["send"](build_system_text("You have been disconnected by the server.", SYSTEM_TEXT_ERROR))
            close_session(s, args)
            print(f"kicked {rest}")
    elif word == "backup":
        print(f"database backup: {storage.backup(os.path.dirname(CHARACTERS_FILE))}")
    elif word == "reload":
        force_content_reload(args)
    elif word:
        print("commands: who, announce <text>, kick <name>, backup, reload, stop")
    return None


def shutdown(clients, args):
    """Ctrl+C or a service stop: tell everyone, save every player (position, play time), take
    them out of the world and close their connections, so nothing is lost and clients go back
    to their login screen instead of waiting for a dead server."""
    players = 0
    for state in list(clients.values()):
        player = state.get("player")
        if player is not None and "send" in state and not state.get("closed"):
            try:
                state["send"](build_system_text("The server is shutting down.", SYSTEM_TEXT_ERROR))
                pos = player.live_position
                if pos is not None and player.save_position:
                    player.save_position(pos)
                leave_world(state, args)
                players += 1
            except Exception as e:                  # one bad state must not stop the rest
                print(f"  !!! shutdown: {getattr(player, 'name', '?')}: {e}")
        if callable(state.get("terminate")):
            try:
                state["terminate"]()
            except OSError:
                pass
    print(f"Server stopped: {players} players saved, {len(clients)} connections closed.")


MAX_READS_PER_WAKE = 64
FLUSH_HZ = 20


def audit(kind, **fields):
    """One line of the economy audit log (audit.log next to the database, JSON per line): who
    gave what to whom. For GMs looking into scams or duplication reports."""
    if AUDIT_FILE is None:
        return                          # not a running server (unit tests)
    line = json.dumps(dict({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind}, **fields),
                      ensure_ascii=False)
    try:
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"  !!! audit log: {e}")


AUDIT_FILE = None                # set by main(): audit.log next to the database
DATA_FILES = ("HOUSING_FILE", "CARAVANS_FILE", "GUILDS_FILE", "BROTHERHOODS_FILE", "MAIL_FILE", "BUG_FILE",
              "QUEST_FEEDBACK_FILE", "PLAYER_REPORT_FILE", "MARKET_FILE", "CIVIC_FILE", "CHARACTERS_FILE")


def use_data_dir(folder):
    """Keep the saved data (database, reports) in folder instead of the server folder, e.g. a
    separate disk, or a scratch copy for testing."""
    folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)
    for name in DATA_FILES:
        globals()[name] = os.path.join(folder, os.path.basename(globals()[name]))
    accounts.ACCOUNTS_FILE = os.path.join(folder, os.path.basename(accounts.ACCOUNTS_FILE))
    print(f"Saved data in {folder}")


def guarded(fn, *a):
    """Run one packet or tick; a bug or a malformed packet is logged instead of
    stopping the server for everyone."""
    try:
        fn(*a)
    except Exception:
        import traceback
        print(f"  !!! error in {fn.__name__} (server keeps running):")
        traceback.print_exc(file=sys.stdout)


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
            offer_rescues(state, npc, now)
        pet_tick(state, args, now, MOVE_TICK)
        npc_cast_tick(state, args, now)
        fishing_tick(state, now)
        assembly_tick(state, now)
    for w in world.all_worlds():
        players = w.players()
        for npc in w.npcs.values():
            victim = combat.proximity_aggro(npc, players, lambda p, npc=npc: faction_kos(p, npc))
            if victim is not None:
                vs = w.members.get(victim.char_id)
                if vs is not None:
                    vs["send"](build_system_text(f"{npc.name} notices you!", SYSTEM_TEXT_ERROR))
                if getattr(npc, "aggro_say", None):
                    npc_say(w, npc, npc.aggro_say.replace("{player}", victim.name))
        for npc in list(w.npcs.values()):
            helpers = combat.social_assist(npc, w.npcs.values())
            if helpers:
                victim = w.members.get(npc.aggro_on.char_id) if npc.aggro_on else None
                if victim is not None:
                    victim["send"](zone.zone_event(0x556, struct.pack("<Q", npc.entity_id)))  # "X calls for help!"
                print(f"  {npc.name} calls for help: {', '.join(h.name for h in helpers)}")
        for npc in w.npcs.values():
            combat.after_pet(npc, time.time())
            if npc.aggro_on is not None and npc.aggro_on.health <= 0:
                # Its target died: the next player on its hate list, if any.
                npc.hate.pop(npc.aggro_on.char_id, None)
                nxt = combat.next_target(npc)
                if nxt is not None:
                    npc.aggro_on = nxt
                else:
                    combat.give_up(npc)      # nobody left: walk home and heal, as after a leash
            target = npc.aggro_on.live_position if npc.aggro_on else None
            values = combat.chase_step(npc, target, MOVE_TICK)
            if values:
                zone.queue_npc_move(w, args, npc, values)
                if "Health" in values:
                    # Healed after evading: refresh the target frame of anyone targeting it.
                    msg = combat.target_health(npc)
                    w.broadcast(lambda s, npc=npc, msg=msg: msg if s["player"].target == npc.entity_id else None)


def use_ability(state, args, player, ability):
    """An ability from the hotbar: its effect kind (effects.classify) decides what
    it does; the refresh time starts the hotbar cooldown sweep."""
    send = state["send"]
    handle, _aid, name, icon, _desc, refresh = ability[:6]
    now = time.time()
    cooldowns = player.__dict__.setdefault("cooldowns", {})
    if now < cooldowns.get(handle, 0):
        send(effects.ability_failed(effects.NOT_REFRESHED))
        return
    spec = effects.classify(name, args.content.abilities)
    allowed = forms.allowed_forms(getattr(player, "forms", []), name)
    if allowed and getattr(player, "form", -1) not in allowed:
        # The client switches forms itself first (0x13e) when it can; this catches the rest.
        names = [n for fid, n, _s in player.forms if fid in allowed]
        send(build_system_text(f"{name} can only be used in {' or '.join(names)}.", SYSTEM_TEXT_ERROR))
        return
    if stunned(player):
        send(effects.ability_failed(effects.STUNNED))
        return
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
    if spec["kind"] in GENERAL_KINDS:
        if player.health <= 0:
            send(client_notice(NOT_WHILE_DEAD))
            return
        if general_ability(state, args, player, spec) and refresh > 0:
            cooldowns[handle] = now + refresh
            send(effects.cooldown(ability[1], refresh))
        return
    if spec["kind"] == "pet":
        # A summoning ability (abilities.json "kind": "pet", "pet": {name, race, model, level,
        # health, damage, abilities}): the same companion as a pet item; casting it again
        # replaces the pet.
        if player.health <= 0:
            send(client_notice(NOT_WHILE_DEAD))
            return
        summon_pet(state, args, spec["pet"])
        if refresh > 0:
            cooldowns[handle] = now + refresh
            send(effects.cooldown(ability[1], refresh))
        return
    if spec["kind"] == "fear":
        # abilities.json "kind": "fear", "duration": s: the targeted enemy runs away and doesn't
        # attack until it wears off (it still hates the caster and comes back).
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not npc.alive or getattr(npc, "pet_owner", None) is not None:
            send(client_notice(NEED_TARGET if npc is None else NOT_ATTACKABLE))
            return
        if player.health <= 0:
            send(client_notice(NOT_WHILE_DEAD))
            return
        visual = ability[1] if ability[1] >= 500000 else None
        if visual:
            send(combat.display_ability(player.char_id, npc.entity_id, visual))
        npc.feared_until = now + spec.get("duration", 8.0)
        npc.aggro, npc.aggro_on, npc.casting = True, player, None
        combat.add_hate(npc, player, 10)
        player.last_combat = now
        send(build_system_text(f"{npc.name} flees in terror!", SYSTEM_TEXT_COMBAT))
        if refresh > 0:
            cooldowns[handle] = now + refresh
            send(effects.cooldown(ability[1], refresh))
        return
    if spec["kind"] in ("heal", "buff"):
        if player.health <= 0:
            send(client_notice(NOT_WHILE_DEAD))
            return
        error = combat.pay_cost(player, refresh)
        if error:
            send(effects.ability_failed(error))
            return
        player.endurance_changed = player.energy_changed = False
        send(zone.energy_update(player) if player.klass in combat.ENERGY_CLASSES else zone.endurance_update(player))
        visual = ability[1] if ability[1] >= 500000 else None
        if visual:
            send(combat.display_ability(player.char_id, player.char_id, visual))
        if spec["kind"] == "heal":
            amount = random.randint(*combat.scaled(player, spec["amount"], "heal"))
            ts = heal_target(state)
            who = ts["player"]
            who.health = min(who.health + amount, who.stats["hit_points"])
            send(effects.combat_text(player.char_id, who.char_id, name, amount, heal=True))
            if ts is not state:
                ts["send"](effects.combat_text(player.char_id, who.char_id, name, amount, heal=True))
                send(build_system_text(f"You heal {who.name} for {amount}.", SYSTEM_TEXT_WHITE))
                ts["send"](build_system_text(f"{player.name} heals you for {amount}.", SYSTEM_TEXT_WHITE))
            ts["send"](zone.health_update(who))
            heal_hate(state, who, amount)
            print(f"  {player.name} heals {who.name} for {amount} ({who.health}/{who.stats['hit_points']})")
        else:
            # A friendly target, or yourself (stances like "... Style" and "self" buffs: always you).
            ts = state if spec.get("self") or spec.get("stance") or "Style" in name else heal_target(state)
            if spec.get("stance"):
                apply_stance(state, player, name, spec, now)
            else:
                apply_buff(ts, ts["player"], name, spec, now)
            if ts is not state:
                send(build_system_text(f"You cast {name} on {ts['player'].name}.", SYSTEM_TEXT_WHITE))
                ts["send"](build_system_text(f"{player.name} casts {name} on you.", SYSTEM_TEXT_WHITE))
    elif getattr(player, "duel_opponent", None) is not None and player.target == player.duel_opponent.char_id:
        # A damaging ability on the duel opponent.
        visual = ability[1] if ability[1] >= 500000 else None
        if visual:
            send(combat.display_ability(player.char_id, player.target, visual))
        duel_strike(state, player, player.duel_opponent, name,
                    combat.scaled(player, combat.ABILITY_DAMAGE.get(ability[1], (8, 16))))
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
        send(effects.cooldown(ability[1], refresh))       # keyed by ability id, not the handle
    chain_next(state, player, ability)


HEAL_HATE = 0.5              # hate per point healed, on every NPC fighting the healed player


def heal_target(state):
    """A heal lands on the defensive target (F1 / clicking a player), else on a player
    who is the offensive target, else on the caster (alive and in the same chunk)."""
    player = state["player"]
    w = state.get("world")
    for target in (state.get("def_target"), player.target):
        ts = w.members.get(target) if w is not None and target else None
        if ts is not None and ts.get("player") is not None and ts["player"].health > 0:
            return ts
    return state


def heal_hate(state, healed, amount):
    """Healing someone angers the NPCs that are fighting them."""
    w = state.get("world")
    if w is None:
        return
    for npc in w.npcs.values():
        if npc.alive and healed.char_id in npc.hate:
            combat.add_hate(npc, state["player"], amount * HEAL_HATE)


def chain_next(state, player, ability):
    """The ability went off: if it is part of a chain, open the reaction window for the
    next one (0x391) on the current target."""
    step = reactions.next_step(getattr(player, "chains", []), ability[1])
    if step is None:
        return
    nxt, kind, window = step
    rid, msg = reactions.open_reaction(player.target or 0, nxt, window, kind)
    state.setdefault("reactions", {})[rid] = {"ability": nxt, "ends": time.time() + window,
                                              "target": player.npcs.get(player.target) if player.target else None}
    state["send"](msg)
    print(f"  <- reaction {rid}: {nxt} for {window:g}s ({'finisher' if kind == reactions.FINISHER else 'chain'})")


def activate_reaction(state, args, rid):
    """0x145 {reaction id}: use the ability the window was opened for."""
    player, send = state["player"], state["send"]
    r = state.get("reactions", {}).pop(rid, None)
    print(f"  >>> ZONE activate reaction {rid}")
    if r is None or time.time() > r["ends"]:
        send(reactions.result(reactions.TIMED_OUT))
        send(reactions.close_reaction(rid))
        return
    target = r.get("target") or r.get("counter_of") or r.get("rescue_of")
    if target is not None and not target.alive:
        send(reactions.result(reactions.TARGET_DEAD))     # "...the target of your reaction is dead."
        send(reactions.close_reaction(rid))
        return
    ability = next((a for a in player.abilities if a[1] == r["ability"]), None)
    send(reactions.result(reactions.OK))
    send(reactions.close_reaction(rid))
    if r.get("counter_of") is not None:
        counter_cast(state, r["counter_of"])
    if r.get("rescue_of") is not None:
        rescue(state, r["rescue_of"])
    if ability is not None:
        use_ability(state, args, player, ability)


def reactions_tick(state, now):
    """Close reaction windows that ran out (the client closes its own too); all of them
    when the player dies."""
    open_ = state.get("reactions")
    if not open_:
        return
    if state["player"].health <= 0:
        open_.clear()
        state["send"](reactions.close_all())
        return
    # Expired windows, and windows on an enemy that has died.
    for rid in [k for k, r in open_.items() if now > r["ends"] or
                not getattr(r.get("target") or r.get("counter_of") or r.get("rescue_of"), "alive", True)]:
        open_.pop(rid)
        state["send"](reactions.close_reaction(rid))


def npc_special(state, npc, now):
    """After a melee swing an NPC may use one of its special abilities on the
    player: a DoT/debuff ("Venom Bite") shown in the harmful effects window."""
    player, send = state["player"], state["send"]
    for sp in npc.spells:
        if npc.casting is None and random.random() < sp.get("chance", 0.25):
            npc_cast(state, npc, sp, now)
            return
    for a in npc.abilities:
        if random.random() >= a.get("chance", 0.2):
            continue
        name, eid = a["name"], effect_id(player, a["name"]) + 500
        if random.random() < effects.RESIST_CHANCE_PLAYER:
            send(effects.resisted(npc.entity_id, name, name, you=True))
            print(f"  {player.name} resisted {npc.name}'s {name}")
            return
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
        elif a["kind"] in ("stun", "root"):
            apply_crowd_control(state, npc, a, eid, now)
        return


def apply_crowd_control(state, npc, a, eid, now):
    """An NPC stuns or roots the player (mobs.json ability kind "stun" / "root", "duration").
    The client moves its own pawn, so the server holds it still by replicating GroundSpeed 0;
    a stun also stops abilities and a playing song. Shown in the harmful effects window."""
    player, send = state["player"], state["send"]
    secs = float(a.get("duration", 3.0))
    player.cc = {"kind": a["kind"], "until": now + secs, "eid": eid, "npc": npc, "next": now}
    send(zone.player_pawn_update(state, ARGS, {"GroundSpeed": 0.0}))
    desc = {"stun": "You can't move or act.", "root": "You can't move.",
            "fear": "You flee in terror and can't act."}[a["kind"]]
    send(effects.effect_add(eid, a["name"], desc, a.get("icon", 553), secs, secs, harmful=True))
    verb = {"stun": "stuns", "root": "roots", "fear": "terrifies"}[a["kind"]]
    send(build_system_text(f"{npc.name}'s {a['name']} {verb} you!", SYSTEM_TEXT_ERROR))
    if a["kind"] in ("stun", "fear") and getattr(player, "playing_song", None):
        stop_song(state)
        send(build_system_text("Your song is interrupted.", SYSTEM_TEXT_ERROR))
    print(f"  {npc.name} {verb} {player.name} for {secs:g}s")


def crowd_control_tick(state, now):
    """Once a second: a stun or root wears off; the pawn gets its speed back."""
    player = state["player"]
    cc = getattr(player, "cc", None)
    if cc is None:
        return
    if now < cc["until"]:
        if cc["kind"] == "fear":
            fear_step(state, cc, now)
        return
    player.cc = None
    state["send"](zone.player_pawn_update(state, ARGS, {"GroundSpeed": ground_speed(player)}))
    state["send"](effects.effect_remove(cc["eid"]))
    state["send"](build_system_text("You can move again.", SYSTEM_TEXT_WHITE))


FEAR_STEP = 250.0           # units a feared player is pushed each second (about walking speed)


def fear_step(state, cc, now):
    """A feared player runs from the NPC: the client can't be steered, so the server roots
    the pawn and moves it with a server teleport (0x3e5) each second, facing away."""
    player = state["player"]
    pos = player.live_position or state.get("position")
    src = getattr(cc["npc"], "location", None)
    if pos is None or src is None:
        return
    dx, dy = pos[0] - src[0], pos[1] - src[1]
    d = math.hypot(dx, dy) or 1.0
    x, y = pos[0] + dx / d * FEAR_STEP, pos[1] + dy / d * FEAR_STEP
    gz = ARGS.content.ground_z(player.level, x, y, ARGS.client_dir)
    loc = (x, y, (gz if gz is not None else pos[2]) + 100.0)
    yaw = int(math.degrees(math.atan2(dy, dx)) * 65536 / 360) & 0xFFFF
    state["send"](zone.player_teleport(loc, (0, yaw, 0)))


def stunned(player):
    cc = getattr(player, "cc", None)
    return cc is not None and cc["kind"] in ("stun", "fear") and time.time() < cc["until"]


def npc_cast(state, npc, spell, now):
    """An NPC starts casting a spell at the player: "<npc> begins to cast a spell." (0x248),
    the spell icon by the target frame (0x3a5), and a counter window (0x391 type 2) for the
    player's counter ability, open for the cast time. The NPC doesn't swing meanwhile."""
    player, send = state["player"], state["send"]
    secs = float(spell.get("cast", 3.0))
    fid, icon_msg = reactions.in_flight(spell["name"], spell.get("icon", 553), secs)
    on_row = npc.entity_id in state.get("encounter", {}).get("rows", {})
    npc.casting = {"spell": spell, "ends": now + secs, "victim": player, "fid": fid, "rid": None, "row": on_row}
    send(reactions.begins_to_cast(npc.entity_id))
    if on_row:
        # Not the target: the icon goes on its encounter row instead of beside the target frame.
        send(reactions.row_in_flight(npc.entity_id, fid, spell["name"], spell.get("icon", 553)))
    else:
        send(icon_msg)
    counters = getattr(player, "counters", [])
    if counters:
        rid, msg = reactions.open_reaction(npc.entity_id, counters[0], secs, reactions.COUNTER)
        state.setdefault("reactions", {})[rid] = {"ability": counters[0], "ends": now + secs, "counter_of": npc}
        npc.casting["rid"] = rid
        send(msg)
    print(f"  <- {npc.name} casts {spell['name']} at {player.name} ({secs:g}s){' (on its row)' if on_row else ''}")


def npc_cast_tick(state, args, now):
    """Spells cast at this player that finish now hit (or fizzle if the caster died)."""
    player, send = state["player"], state["send"]
    for npc in list(player.npcs.values()):
        c = npc.casting
        if c is None or c["victim"] is not player or now < c["ends"]:
            continue
        npc.casting = None
        if c["rid"] is not None and state.get("reactions", {}).pop(c["rid"], None) is not None:
            send(reactions.close_reaction(c["rid"]))
        if c.get("row"):
            send(reactions.row_in_flight_done(npc.entity_id, c["fid"]))
        if not npc.alive or player.health <= 0:
            send(reactions.clear_in_flight())
            continue
        lo, hi = c["spell"].get("damage", [8, 16])
        dmg = random.randint(lo, hi)
        was_alive = player.health > 0
        player.health = max(0, player.health - dmg)
        player.last_combat = now
        send(reactions.in_flight_result(c["fid"], reactions.CAST_SUCCESS, dmg))
        send(effects.combat_text(npc.entity_id, player.char_id, c["spell"]["name"], dmg))
        lines = [("You have been slain!", "error")] if player.health == 0 else []
        for m in combat_results(state, args, player, lines, None, was_alive, player.auto_attack):
            send(m)


def offer_rescues(victim_state, npc, now):
    """npc just hit a grouped player: groupmates with a rescue ability get a rescue
    reaction (0x391 type 3) on it. The client never times rescues out, so reactions_tick
    closes them."""
    victim = victim_state["player"]
    if getattr(victim, "group", None) is None or not npc.alive:
        return
    for s in group_states(victim):
        p = s["player"]
        if s is victim_state or p.health <= 0 or not getattr(p, "rescues", None):
            continue
        open_ = s.setdefault("reactions", {})
        if any(r.get("rescue_of") is npc for r in open_.values()):
            continue
        rid, msg = reactions.open_reaction(npc.entity_id, p.rescues[0], reactions.RESCUE_WINDOW, reactions.RESCUE)
        open_[rid] = {"ability": p.rescues[0], "ends": now + reactions.RESCUE_WINDOW, "rescue_of": npc}
        s["send"](msg)
        print(f"  <- rescue {rid} for {p.name}: {npc.name} is hitting {victim.name}")


def rescue(state, npc):
    """The rescuer pulls npc off its victim."""
    player = state["player"]
    if not npc.alive or npc.aggro_on is player:
        return
    victim = npc.aggro_on
    combat.taunt(npc, player)
    state["send"](build_system_text(f"You rescue {victim.name if victim else 'your ally'} from {npc.name}!",
                                    SYSTEM_TEXT_COMBAT))
    vs = online_state(victim) if victim is not None else None
    if vs is not None:
        vs["send"](build_system_text(f"{player.name} rescues you from {npc.name}!", SYSTEM_TEXT_COMBAT))
    print(f"  {player.name} rescued {victim.name if victim else '?'} from {npc.name}")


def counter_cast(state, npc):
    """The player countered npc's spell: it is cancelled ("Countered")."""
    c, send = npc.casting, state["send"]
    if c is None:
        return
    npc.casting = None
    npc.next_attack = time.time() + 1.0
    send(reactions.in_flight_result(c["fid"], reactions.CAST_COUNTERED))
    send(reactions.incoming_result(2))
    send(build_system_text(f"You counter {npc.name}'s {c['spell']['name']}!", SYSTEM_TEXT_COMBAT))
    print(f"  {state['player'].name} countered {npc.name}'s {c['spell']['name']}")


def effect_id(player, name):
    return 7000 + sum(name.encode("utf-8")) % 1000


def apply_stance(state, player, name, spec, now):
    """A stance (abilities.json "stance"): the buff without a timer, one at a time, listed in
    Effects Maintained (0x23e) until replaced or cancelled (0x24e)."""
    send = state["send"]
    for e in getattr(player, "effects", []):
        if e.get("stance") and e["name"] != name:
            e["ends"] = 0                                   # effects_tick takes it off
    apply_buff(state, player, name, dict(spec, duration=effects.STANCE_SECONDS), now)
    e = next(x for x in player.effects if x["id"] == effect_id(player, name))
    e["stance"] = True
    send(effects.effect_remove(e["id"]))          # no timed buff icon ("3650d"): the maintained entry shows it
    send(effects.maintained_add(e["id"], name, e.get("desc", ""), spec.get("icon", 607)))
    send(build_system_text(f"You assume {name}.", SYSTEM_TEXT_WHITE))


def cancel_maintained(state, eid, stance=True):
    """0x24e (a stance, Effects Maintained) or 0x249 (an ordinary buff, right-click): end it."""
    for e in getattr(state["player"], "effects", []):
        if e["id"] == eid and e["kind"] == "buff" and bool(e.get("stance")) == stance:
            e["ends"] = 0


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


def effect_query(state, eid, now):
    """0x24a: the client's timer for effect eid ran out but the effect is still shown."""
    e = next((x for x in getattr(state["player"], "effects", []) if x["id"] == eid), None)
    if e is None:
        state["send"](effects.effect_remove(eid))
    elif "ends" in e:
        state["send"](effects.effect_timer(eid, max(0.0, e["ends"] - now), e.get("duration", 0)))


def apply_dot(state, player, npc, name, spec, now):
    if random.random() < effects.RESIST_CHANCE_NPC:
        state["send"](effects.resisted(npc.entity_id, name, name, you=False))
        return
    eid = effect_id(player, name)
    player.__dict__.setdefault("effects", [])
    player.effects[:] = [e for e in player.effects if not (e["id"] == eid and e.get("npc") is npc)]
    desc = f"Deals damage every {spec['interval']:g} seconds."
    player.effects.append({"kind": "dot", "id": eid, "name": name, "desc": desc, "icon": spec["icon"],
                           "npc": npc, "damage": combat.scaled(player, spec["damage"]), "ticks": spec["ticks"],
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
                if e.get("stance"):
                    send(effects.maintained_remove(e["id"]))
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
                npc.died_at, npc.killer = now, player
                lines.append((f"You have slain {npc.name}!", "white"))
                player.pending_rewards.append(combat.kill_xp(player, npc))
            else:
                combat.add_hate(npc, player, dmg)
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
    out += [effects.ability_failed(text) if kind == "fail" else combat.auto_attack_failed(text)
            if kind == "autofail" else build_system_text(text, colours[kind]) for text, kind in lines]
    out.append(zone.health_update(player))
    if getattr(player, "energy_changed", False):
        player.energy_changed = False
        out.append(zone.energy_update(player))
    if getattr(player, "endurance_changed", False):
        player.endurance_changed = False
        out.append(zone.endurance_update(player))
    if was_alive and player.health == 0:
        player.auto_attack = False
        out += player_death(state, args, player)
    if isinstance(npc, combat.Npc) and npc.alive and getattr(npc, "owner", None) is None \
            and npc.health < npc.max_health \
            and getattr(npc, "pet_owner", None) is None:
        g = getattr(player, "group", None)
        npc.owner = g.id if g else player.char_id      # the first player (or group) to hurt it
        msg = combat.ownership(npc, npc.owner)
        w = state.get("world")
        if w is not None:
            w.broadcast(lambda s: msg, exclude=state)
        out.append(msg)
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
                sparkle = combat.loot_sparkle(npc) if corpse_lootable(npc) else None
                w.broadcast(lambda s: [m for m in (
                    zone.npc_update(s, args, npc, {"Health": 0, "m_bIsDead": 1}),
                    combat.play_animation(npc, combat.ANIM_DEATH), sparkle) if m is not None])
    if player.pending_rewards:
        m = hint(player, "kill")
        if m:
            out.append(m)
    for amount in player.pending_rewards:
        members = [s for s in group_states(player) if s.get("world") is state.get("world")]             or [state]
        share = max(1, amount * (100 + 10 * (len(members) - 1)) // 100 // len(members))
        source = npc.entity_id if npc else player.char_id
        bonuses = brotherhood_bonuses(members, share)
        for m_state in members:
            msgs = award_xp(m_state["player"], share + bonuses.get(id(m_state), 0), source,
                            grouped=len(members) > 1)
            if bonuses.get(id(m_state)):
                msgs.append(build_system_text(f"You gain {bonuses[id(m_state)]} bonus experience "
                                              "from your brotherhood.", SYSTEM_TEXT_WHITE))
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


def set_pawn_pref(state, prop, value):
    """An appearance setting (PAWN_PREFS) changed: saved, and shown to everyone in the chunk."""
    player = state["player"]
    player.pawn_prefs = dict(getattr(player, "pawn_prefs", {}), **{prop: value})
    save_character_field(player.name, "pawn_prefs", player.pawn_prefs)
    pawn_props_changed(state, {prop: value})


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
    """After equipment changed: the model for everyone in the chunk, gear stat bonuses (and the
    character sheet: armor class, attack, maximum health), and save."""
    for name in zone.apply_gear_stats(player):
        state["send"](zone.attribute_update(player, name))
    state["send"](zone.health_update(player))
    state["send"](zone.score_message(player))
    state["send"](combat.combat_info(player))
    values = {"m_AttachmentGroups": zone.gear_attachments(player)}
    state["send"](zone.player_pawn_update(state, args, values))
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.remote_player_update(s, args, player, values), exclude=state)
    save_character_field(player.name, "items", [list(i) for i in player.items])
    save_character_field(player.name, "equipment", [list(e) for e in player.equipment])


def set_mount(state, args, player, mount_id, kind=zone.MOUNT_GROUND):
    """Mount (mount_id) or dismount (None): an m_AttachmentGroups entry plus m_MountType,
    for everyone in the chunk."""
    if getattr(player, "flying", False) and (mount_id is None or kind != zone.MOUNT_FLYING):
        set_flying(state, args, player, False)      # dismounting in the air: fall
    player.mount = mount_id
    player.mount_kind = kind if mount_id else 0
    player.barding = mount_barding(args, player) if mount_id else None
    values = {"m_AttachmentGroups": zone.gear_attachments(player), "m_MountType": kind if mount_id else 0}
    state["send"](zone.player_pawn_update(state, args, values))
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.remote_player_update(s, args, player, values), exclude=state)
    # Riding speed: GroundSpeed in a later bunch (MountUp resets it to the race default).
    speed = ground_speed(player)
    values = {"GroundSpeed": speed}
    if kind == zone.MOUNT_FLYING and mount_id:
        values["AirSpeed"] = speed                 # flying mounts move with AirSpeed in PHYS_Flying
    state["send"](zone.player_pawn_update(state, args, values))


# Usable items (verified live 2026-10-14): items.json "use" {"heal": n, "energy": n,
# "endurance": n} and "cooldown" seconds. Right-clicking one uses up one and starts the reuse
# timer: 0x1e5 {i64 seconds remaining, i32 group, i32 seconds} (FUN_0050f910) on every item whose
# field 107 is that group, so the tooltip shows "Time Remaining: 21.0". Using it again before then
# gets 0x1c5 {u8 7} ("Unable to use that item because the ability is not refreshed.").
ITEM_COOLDOWN, ITEM_USE_FAILED = 0x1E5, 0x1C5
USE_NOT_REFRESHED = 7


item_cooldown = zone.item_cooldown


def use_item(state, args, item):
    player, send = state["player"], state["send"]
    tpl = args.content.item(item[1])
    group = zone.cooldown_group(item[1])
    cooldowns = player.__dict__.setdefault("item_cooldowns", {})
    now = time.time()
    if player.health <= 0:
        return
    if cooldowns.get(group, (0, 0))[0] > now:
        send(zone.zone_event(ITEM_USE_FAILED, struct.pack("<B", USE_NOT_REFRESHED)))
        return
    use = tpl["use"]
    gained = []
    for key, pool in (("heal", "hit_points"), ("energy", "energy"), ("endurance", "endurance")):
        amount = int(use.get(key, 0))
        if not amount or pool not in player.stats:
            continue
        attr = "health" if pool == "hit_points" else pool
        before = getattr(player, attr, 0)
        setattr(player, attr, min(before + amount, player.stats[pool]))
        if getattr(player, attr) > before:
            gained.append(f"{int(getattr(player, attr) - before)} {'health' if key == 'heal' else key}")
    # one off the stack that was clicked
    if item[3] > 1:
        player.items[player.items.index(item)] = item[:3] + (item[3] - 1, item[4])
        send(zone.zone_event(0x1AE, struct.pack("<ii", item[0], item[3] - 1)))
    else:
        player.items.remove(item)
        send(zone.zone_event(0x1A5, struct.pack("<iB", item[0], 0)))
    save_character_field(player.name, "items", [list(i) for i in player.items])
    send(zone.health_update(player))
    if "energy" in use:
        send(zone.energy_update(player))
    if "endurance" in use:
        send(zone.endurance_update(player))
    seconds = float(tpl.get("cooldown", 0))
    if seconds > 0:
        cooldowns[group] = (now + seconds, seconds)
        save_character_field(player.name, "item_cooldowns",
                             {str(g): list(v) for g, v in cooldowns.items() if v[0] > now})
        send(item_cooldown(group, seconds, seconds))
    send(build_system_text(f"You use the {item[1]}" + (f" and gain {', '.join(gained)}." if gained else "."),
                           SYSTEM_TEXT_WHITE))


# Mount barding (verified live 2026-10-14): an m_AttachmentGroups element (500, barding index,
# slot 45 MOUNTBARDING) next to the mount dresses a modular mount (ids under 4000) in
# MOD_MOUNT_ARMOR_<size><index>: 0xx a saddle blanket, 1xx a cloth caparison, 2xx plate. It shows
# when sent with the mount or added while riding. A barding item (items.json "barding": index) is
# put on or taken off by right-clicking it; the choice is saved and shown whenever you ride.
MODULAR_MOUNT_LIMIT = 4000


def mount_barding(args, player):
    test = getattr(player, "barding_test", None)
    if test is not None:
        return test
    name = getattr(player, "barding_item", None)
    if not name or not player.mount or player.mount >= MODULAR_MOUNT_LIMIT:
        return None
    if not any(i[1] == name for i in player.items):
        return None                                  # sold, traded or destroyed since
    return args.content.item(name).get("barding")


def use_barding(state, args, item):
    player = state["player"]
    if getattr(player, "barding_item", None) == item[1]:
        player.barding_item = None
        text = f"You take the {item[1]} off your mount."
    else:
        player.barding_item = item[1]
        text = f"You put the {item[1]} on your mount."
    save_character_field(player.name, "barding", player.barding_item)
    state["send"](build_system_text(text, SYSTEM_TEXT_WHITE))
    if getattr(player, "mount", None):
        set_mount(state, args, player, player.mount, player.mount_kind)


# Flight (verified live 2026-10-14 with tools/winbreak.py): on a flying mount (m_MountType 3) Jump
# sends client event 0x5b standing (FUN_00baf7e0 -> GameClient vfunc 0x174) or 0x5a while falling
# (vfunc 0x170). The server answers with the PlayerController RPC ClientAdjustPosition(newPhysics
# 4 = PHYS_Flying, NewState 'PlayerFlying'): the pawn then keeps its height over the ground and
# flies where the view points. The same events while flying land it (PHYS_Falling, PlayerWalking).
TAKE_OFF_AIR, TAKE_OFF_STANDING = 0x5A, 0x5B
PHYS_FALLING, PHYS_FLYING = 2, 4


def set_flying(state, args, player, on):
    loc = state.get("position") or player.live_position or player.spawned_at
    if loc is None:
        return
    player.flying = on
    player.flying_since = time.time()
    lift = 150.0 if on else 0.0
    state["send"](zone.client_adjust_position(state, args, (loc[0], loc[1], loc[2] + lift),
                                              PHYS_FLYING if on else PHYS_FALLING,
                                              "PlayerFlying" if on else "PlayerWalking"))
    # Other players simulate this pawn too: flying physics there as well, or their copy falls back
    # to the ground between position updates.
    up = (loc[0], loc[1], loc[2] + lift)
    values = {"Physics": PHYS_FLYING if on else PHYS_FALLING, "bSimulateGravity": not on,
              "Location": up, "Velocity": (0.0, 0.0, 0.0), "PawnPosition": (up, (0, 0, 0), (0.0, 0.0, 0.0))}
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.remote_player_update(s, args, player, values), exclude=state)
    print(f"  {player.name} {'takes off' if on else 'lands'}")


LAND_HEIGHT = 80.0               # a flying pawn this close above the ground lands (a rider stands ~52 above it)


def flight_check(state, loc):
    """Flying low over the ground (after the take-off settles) lands: Jump does nothing in the
    air, so this is how a flight ends besides dismounting."""
    player = state["player"]
    if not getattr(player, "flying", False) or time.time() - getattr(player, "flying_since", 0) < 3.0:
        return
    gz = ARGS.content.ground_z(player.level, loc[0], loc[1], ARGS.client_dir)
    if gz is not None and loc[2] - gz < LAND_HEIGHT:
        set_flying(state, ARGS, player, False)


def take_off_event(state, args):
    """0x5a / 0x5b: Jump on a flying mount toggles flight."""
    player = state["player"]
    if not getattr(player, "mount", None) or getattr(player, "mount_kind", 0) != zone.MOUNT_FLYING:
        return
    set_flying(state, args, player, not getattr(player, "flying", False))


BASE_GROUND_SPEED = 337.889       # the client's own value for player races (pawn +0x7f0, read live)
# Walking speed: what the client itself sets for /walk when it can't reach a server
# (FUN_00bb5ae0: mode 1 -> race table +0x50, 185.0 for every playable race, read live).
WALK_GROUND_SPEED = 185.0


def ground_speed(player):
    """The pawn's GroundSpeed: riding, walking (/walk) or the normal run."""
    if getattr(player, "mount", None):
        return BASE_GROUND_SPEED * MOUNT_SPEED
    if getattr(player, "movement_mode", 2) == 1:
        return WALK_GROUND_SPEED
    if getattr(player, "sprint_until", 0) > time.time():
        return BASE_GROUND_SPEED * getattr(player, "sprint_speed", 1.25)
    return BASE_GROUND_SPEED
MOUNT_SPEED = 1.6                 # mounts run 60% faster


# Clearing experience debt with an item (docs/DEATH.md): using an item whose template id is
# DEBT_CLEAR_TEMPLATE opens the client's own "Are you sure you wish to clear all your
# experience debt?" dialog; OK sends 0x5da {i32 item handle}. The reply 0x5db {i32 code}
# (zone dispatcher FUN_00622350, table index 17): 0x16 done (closes the dialog), 0x17 "You are
# not allowed to clear your exp debt.", 0x18 "You have no experience debt.", 0x19 "You may not
# clear your experience debt while you have corpses."
CLEAR_DEBT, CLEAR_DEBT_REPLY, DEBT_CLEAR_TEMPLATE = 0x5DA, 0x5DB, 1454022
DEBT_DONE, DEBT_NOT_ALLOWED, DEBT_NONE, DEBT_CORPSES = 0x16, 0x17, 0x18, 0x19


def clear_debt(state, handle):
    player, send = state["player"], state["send"]
    item = next((i for i in player.items if i[0] == handle), None)
    if item is None or zone.template_id(item[1]) != DEBT_CLEAR_TEMPLATE:
        code = DEBT_NOT_ALLOWED
    elif getattr(player, "xp_debt", 0) <= 0:
        code = DEBT_NONE
    elif getattr(player, "tombstone", None):
        code = DEBT_CORPSES
    else:
        code = DEBT_DONE
        player.xp_debt = 0
        save_character_field(player.name, "xp_debt", 0)
        take_items(state, item[1], 1)
    print(f"  >>> ZONE clear experience debt (item {handle}): reply {code:#x}")
    send(zone.zone_event(CLEAR_DEBT_REPLY, struct.pack("<i", code)))
    if code == DEBT_DONE:          # the client shows "Experience Debt Cleared" itself
        send(zone.score_message(player))


# Gender and race change items (docs/DEATH.md "Character service items"). Using an item with
# template 1454016 / 1454015 opens the client's own dialog; Submit sends 0x5d5 / 0x5d7
# {i32 new gender or race, i32 item handle}. Replies MsgPaidGenderChangeResult 0x5d6 /
# MsgPaidRaceChangeResult 0x5d8 {i32, i32 code, u8, u8 new value}: gender 0xc done (the
# client switches its own gender and prints strGenderSelf), 0x10 "You are not allowed to
# change your gender."; race 0x11 done (strRaceSelf), 0x15 not allowed; anything else
# "... failed. Please retry later."
CHANGE_GENDER, CHANGE_GENDER_REPLY, GENDER_TEMPLATE = 0x5D5, 0x5D6, 1454016
CHANGE_RACE, CHANGE_RACE_REPLY, RACE_TEMPLATE = 0x5D7, 0x5D8, 1454015
GENDER_DONE, GENDER_NOT_ALLOWED, RACE_DONE, RACE_NOT_ALLOWED = 0x0C, 0x10, 0x11, 0x15


def change_gender_race(state, event, value, handle):
    player, send = state["player"], state["send"]
    gender = event == CHANGE_GENDER
    item = next((i for i in player.items if i[0] == handle), None)
    want = GENDER_TEMPLATE if gender else RACE_TEMPLATE
    ok = item is not None and zone.template_id(item[1]) == want and (
        value in (0, 1) if gender else value in races_classes.RACES and value != player.race)
    code = (GENDER_DONE if gender else RACE_DONE) if ok else (GENDER_NOT_ALLOWED if gender else RACE_NOT_ALLOWED)
    print(f"  >>> ZONE {'gender' if gender else 'race'} change to {value} (item {handle}): reply {code:#x}")
    if ok:
        take_items(state, item[1], 1)
        if gender:
            player.gender = value
            save_character_field(player.name, "gender", value)
            pawn_props_changed(state, {"m_Gender": value})
        else:
            player.race = value
            save_character_field(player.name, "race", value)
            pawn_props_changed(state, {"m_iRaceId": value})
            zone.apply_gear_stats(player)          # race attribute bonuses
            for m in zone.stat_messages(player):
                send(m)
        send(zone.score_message(player))
    send(zone.zone_event(CHANGE_GENDER_REPLY if gender else CHANGE_RACE_REPLY,
                         struct.pack("<iiBB", 0, code, 0, value & 0xFF)))


# Character rename item (template 1463295): the client's "Character Rename" window sends
# 0x5d3 {wstr first, wstr last, i32 item handle} (seen live). Reply 0x5d4 {i32, i32 code, u8,
# wstr first, wstr last}: 6 done (the client renames itself and prints strNameSelf /
# strNameFullSelf), 7 "That first name is not available.", 0xb "You are not allowed to change
# your name.", anything else "Rename failed. Please retry later."
RENAME, RENAME_REPLY, RENAME_TEMPLATE = 0x5D3, 0x5D4, 1463295
# /claim (account rewards): 0x18e asks for the list. The claim dispatcher (FUN_004458f0) takes
# 0x5ed clear, 0x5ee/0x5ef/0x5f1 entries and results, 0x5f0 end of list; an empty list prints
# "You don't qualify to claim any account rewards." A private server has no account rewards.
CLAIM_LIST, CLAIM_CLEAR, CLAIM_END = 0x18E, 0x5ED, 0x5F0
FORCE_STANCE = 0x571
# Appearance settings the client applies to its own pawn before telling the server:
# /hidehood 0x113, /hidehelm 0x114, /hidecloak 0x59e {u8 hidden} (FUN_005e2d00 / FUN_005e2e60 /
# FUN_005e2db0, pawn +0x3a8..+0x3aa), /setwearpreference 0x110 {i32 sphere: 0 Adventuring,
# 1 Crafting, 2 Diplomacy, 3 Harvesting} (FUN_00608d40), /setwieldpreference 0x111 {i32, the
# typed number clamped to 0-3} (FUN_00608f10). The server shows them to everyone else (the
# SGOPCPawn properties below) and saves them.
PAWN_PREFS = {0x113: ("m_bHideHood", "B", 1), 0x114: ("m_bHideHelm", "B", 1), 0x59E: ("m_bHideCloak", "B", 1),
              0x110: ("m_WearPreference", "i", 3), 0x111: ("m_WieldPreference", "i", 3)}
# /cyclewieldpreference, the Z key: 0x112, no payload. Steps m_WieldPreference 0 -> 1 -> 2 -> 3 -> 0.
# Seen live: 0 every weapon sheathed, 3 the bow drawn in hand (1 and 2 are the melee settings).
CYCLE_WIELD = 0x112


def next_wield_preference(player):
    return (int(getattr(player, "pawn_prefs", {}).get("m_WieldPreference", 0)) + 1) % 4
# /walk, /run: 0x72 {u8 1 walk, 2 run} (FUN_005fccf0). The client switches its own pawn only
# when the send fails, so the server answers with the walking GroundSpeed (ground_speed), the
# replicated Pawn.bIsWalking for everyone else, and MsgScore field 28 (the character sheet's
# "walking"/"running").
MOVE_MODE = 0x72
# /lockouttimerlist [name]: 0x4fc {wstr name, empty = yourself}. The answer 0x4fd {wstr name}
# (dispatcher FUN_00588c50, ids 0x4f2-0x502 -> FUN_00583b70) prints "Displaying lockout timers
# for %s:" and lists the timers the client already holds; this server has no raid lockouts.
LOCKOUT_LIST, LOCKOUT_LIST_REPLY = 0x4FC, 0x4FD
# /sharelockouttimer <id>: 0x4fb {i32 id}; /lockoutaccept, /lockoutdecline: 0x273 {u8 accept}.
# With no lockouts the answers are the client's notices InvalidLockout and NoLockoutOffer.
LOCKOUT_SHARE, LOCKOUT_ANSWER = 0x4FB, 0x273
INVALID_LOCKOUT, NO_LOCKOUT_OFFER = 159, 158
# Clicking an item link in chat runs /itemlinkrequest <link text>: 0x158 {wstr}. The answer is
# s2c 0x158 with the item's full record (FUN_005de090 -> FUN_00516610), which opens the
# examine popup (FUN_0068e220).
ITEM_LINK_REQUEST = 0x158
# /cleartargets: 0x5e, no payload (FUN_005fcd70).
CLEAR_TARGETS = 0x5E
# /cancelability (also /stopcasting, /cancelattack, FUN_005fc8a0): first FUN_005f3d00 cancels
# what is running, by sending 0x25f while casting, else 0xe2 while a bar runs (+0xe0c/+0xe14),
# else 0xe1 after clearing a queued ability on the client; then 0x144. None has a payload. The
# server queues no abilities, so each just drops the pending cast.
CANCEL_CAST = (0x144, 0x25F, 0xE2, 0xE1)
RENAME_DONE, RENAME_TAKEN, RENAME_NOT_ALLOWED = 6, 7, 0x0B
# Saved files that refer to characters by name (mail boxes use the lower-case name).
def name_stores():
    return (HOUSING_FILE, CARAVANS_FILE, GUILDS_FILE, BROTHERHOODS_FILE, MAIL_FILE, MARKET_FILE, CIVIC_FILE)


def rename_refs(obj, old, new):
    """obj with every string (value or key) equal to old, or to old in lower case, renamed."""
    def one(s):
        if s == old:
            return new
        if s == old.lower():
            return new.lower()
        return s
    if isinstance(obj, str):
        return one(obj)
    if isinstance(obj, list):
        return [rename_refs(v, old, new) for v in obj]
    if isinstance(obj, dict):
        return {one(k) if isinstance(k, str) else k: rename_refs(v, old, new) for k, v in obj.items()}
    return obj


def valid_first_name(name):
    return 3 <= len(name) <= 20 and name.isalpha()


def rename_character(state, data):
    player, send = state["player"], state["send"]
    try:
        (first, last), pos = read_wstrings(data, 0, 2)
        handle = struct.unpack_from("<i", data, pos)[0]
    except (struct.error, ValueError):
        return
    first, last = first.strip(), last.strip()
    item = next((i for i in player.items if i[0] == handle), None)
    chars = load_characters()
    old = player.name
    if item is None or zone.template_id(item[1]) != RENAME_TEMPLATE:
        code = RENAME_NOT_ALLOWED
    elif not valid_first_name(first) or (last and not last.isalpha()) or any(
            c["first"].lower() == first.lower() and c["first"] != old for c in chars):
        code = RENAME_TAKEN
    else:
        code = RENAME_DONE
    print(f"  >>> ZONE rename {old!r} -> {first!r} {last!r} (item {handle}): reply {code:#x}")
    if code == RENAME_DONE:
        take_items(state, item[1], 1)
        for c in chars:
            if c["first"] == old:
                character_id(c)                # keep the id: it is derived from the first name
                c["first"], c["last"] = first, last
        save_characters(rename_refs(chars, old, first))
        for path in name_stores():
            data_ = load_json_file(path, None)
            if data_ is not None:
                renamed = rename_refs(data_, old, first)
                if renamed != data_:
                    save_json_file(path, renamed)
        player.name = first
        if ONLINE.get(old.lower()) is state:
            ONLINE.pop(old.lower())
            ONLINE[first.lower()] = state
        pawn_props_changed(state, {"m_PlayerDisplayName": first})
    send(zone.zone_event(RENAME_REPLY, struct.pack("<iiB", 0, code, 0)
                         + (first + "\0").encode("utf-16-le") + (last + "\0").encode("utf-16-le")))


# Unbind tool (template 1464359): using it puts the cursor in targeting mode 5; clicking an
# item sends 0x5e3 {i32 target item handle, i32 tool handle} (FUN_004fbf00). Template 1464362
# does the same for "unlock" (mode 6, 0x5e5). No reply message is known: the server resends
# the item and says what happened.
UNBIND, UNBIND_TEMPLATE = 0x5E3, 1464359
# The client's own bind messages, {i32 item handle} (it looks the item up and words the line by
# its flags): 0x1e3 "%s has been bound to you and will remain with you even through death."
# (FUN_005069b0), 0x5e4 "%s has been unbound from you and will be lost upon death." (FUN_00506b90).
ITEM_BOUND, ITEM_UNBOUND = 0x1E3, 0x5E4


def unbind_item(state, target, tool):
    player, send = state["player"], state["send"]
    t = next((i for i in player.items if i[0] == tool), None)
    item = next((i for i in player.items if i[0] == target), None)
    print(f"  >>> ZONE unbind item {target} with {tool}")
    if t is None or zone.template_id(t[1]) != UNBIND_TEMPLATE:
        send(build_system_text("That can't unbind anything.", SYSTEM_TEXT_ERROR))
    elif item is None or target not in getattr(player, "bound", set()):
        send(build_system_text("That item is not bound to you.", SYSTEM_TEXT_ERROR))
    else:
        player.bound = set(player.bound) - {target}
        save_character_field(player.name, "bound", sorted(player.bound))
        take_items(state, t[1], 1)
        # (The client itself refuses worn items: "Cannot unbind an equipped item.")
        send(zone.zone_event(0x197, vgmsg.inventory_item(item[0], item[1], item[4], zone.item_icon(item[1], item[2]),
                                                         item[3], **zone.item_equip_fields(item[1]))))
        send(zone.zone_event(ITEM_UNBOUND, struct.pack("<i", item[0])))


# The client's own GM commands (only with --dev-commands): /chunk <name | x y> loads the chunk
# itself, then sends 0x770 {i32 x, i32 y} (FUN_00613440); /gotoplayer and /summonplayer send
# 0x79d / 0x7c7 {wstr name}; /hideme [on|off] sends 0x76c {u8 1 on, 2 off, 3 toggle}.
GM_CHUNK, GM_GOTO, GM_SUMMON, GM_HIDE = 0x770, 0x79D, 0x7C7, 0x76C
# /summongroup <name> (FUN_00613cd0, access level 8): 0x7c6 {wstr name}, the whole group of that
# player (or just them) is brought to the GM.
GM_SUMMON_GROUP = 0x7C6
# GM test tools on the defensive target (FUN_005fe180 / FUN_005fe230 / FUN_006143c0):
# /.learnabilities 0x582 {u64 target}, /.maxskills 0x583 {u64 target},
# /.setupall <level> 0x589 {u64 target, i32 level}.
GM_LEARN_ALL, GM_MAX_SKILLS, GM_SETUP_ALL = 0x582, 0x583, 0x589
GM_EVENTS = (GM_CHUNK, GM_GOTO, GM_SUMMON, GM_HIDE, GM_LEARN_ALL, GM_MAX_SKILLS, GM_SETUP_ALL, GM_SUMMON_GROUP)


def state_by_char_id(char_id):
    return next((s for s in ONLINE.values() if s.get("player") is not None and s["player"].char_id == char_id), None)


def gm_learn_all(s):
    p = s["player"]
    known = set(getattr(p, "learned", [])) | {a[1] for a in p.abilities}
    for n, (aid, tag) in enumerate(class_abilities.class_ability_list(ARGS.client_dir, p.klass)):
        if aid not in known:
            learn_ability(s, n, aid, tag)


def gm_max_skills(s):
    p = s["player"]
    p.skills = [(sid, zone.SKILL_CAP, sub) for sid, _v, sub in p.skills]
    for sid, v, _sub in p.skills:
        s["send"](zone.zone_event(0x2D4, vgmsg.stat_update(sid, v, maximum=zone.SKILL_CAP)))
    save_character_field(p.name, "skills", {str(sid): v for sid, v, _ in p.skills})
    s["send"](build_system_text(f"All skills raised to {zone.SKILL_CAP}.", SYSTEM_TEXT_WHITE))


def gm_set_level(s, level):
    p = s["player"]
    p.level_number, p.xp = max(1, min(zone.LEVEL_CAP, level)), 0
    save_character_progress(p.name, p.level_number, p.xp)
    zone.apply_gear_stats(p)
    p.health = p.stats["hit_points"]
    s["send"](zone.score_message(p))
    s["send"](zone.health_update(p))
    for name in vgmsg.ATTRIBUTES:
        s["send"](zone.attribute_update(p, name))
    s["send"](build_system_text(f"You are now level {p.level_number}.", SYSTEM_TEXT_WHITE))


def place_player(state, args, loc, chunk):
    """Teleport within the chunk, or travel to another chunk."""
    player = state["player"]
    if tuple(chunk) == tuple(getattr(player, "chunk", None) or DEFAULT_CHUNK):
        state["send"](zone.player_teleport(tuple(loc)))
        state.setdefault("move_check", {})["teleport_at"] = time.time()
    else:
        travel_to_chunk(state, args, chunk[0], chunk[1], loc[0], loc[1], loc[2])


# Rescue rope: /rope [name] (FUN_0060d340) checks for a target, prints "Attempting to throw %s
# a rope." and sends 0x190 (no payload: the server uses the thrower's target). The target gets
# 0x58a {wstr thrower} (FUN_005ed620): "%s would like to toss you a rope." with Accept
# (/ropeaccept, 0x191, no payload) and Decline (client only). Accepting hauls them next to the
# thrower: notice 465 "You grab the rope and are hauled to safety.", or 464 "No one is holding
# the other end of the rope." when the thrower is gone or in another chunk.
ROPE_THROW, ROPE_ACCEPT, ROPE_OFFER = 0x190, 0x191, 0x58A
NO_ONE_HOLDING_ROPE, GRABBED_ROPE = 464, 465


def rope_event(state, args, event):
    player = state["player"]
    if event == ROPE_THROW:
        other = next((s for s in (state_by_char_id(state.get("def_target")), state_by_char_id(player.target))
                      if s is not None and s is not state and s.get("player") is not None), None)
        if other is None:
            return
        other["rope_from"] = player.char_id
        other["send"](zone.zone_event(ROPE_OFFER, (player.name + "\0").encode("utf-16-le")))
        return
    thrower = state_by_char_id(state.pop("rope_from", None))
    if thrower is None or thrower.get("player") is None or thrower.get("world") is not state.get("world"):
        state["send"](client_notice(NO_ONE_HOLDING_ROPE))
        return
    dest = thrower.get("position") or thrower["player"].live_position or thrower["player"].spawned_at
    if dest is None:
        state["send"](client_notice(NO_ONE_HOLDING_ROPE))
        return
    place_player(state, args, (dest[0] + 100.0, dest[1], dest[2] + 50.0),
                 getattr(thrower["player"], "chunk", None) or DEFAULT_CHUNK)
    state["send"](client_notice(GRABBED_ROPE))


# Summoning a player ("call"): S->C 0x270 {wstr caller} (FUN_005eb7d0) opens Call Confirmation,
# "<caller> is attempting to summon you." with Accept / Decline, which run /callpcaccept and
# /callpcdecline: 0x271 {u8 1 / 0} (FUN_005e2a10 / FUN_005e2aa0). Accepting moves the player
# next to the caller with notice 45 "You have been summoned!". Which abilities summon players is
# server content (docs/CONTENT_EDITOR.md); the dev command !call <name> sends the offer.
CALL_OFFER, CALL_ANSWER = 0x270, 0x271
HOTKEYS_REQUEST = 0x54D
# Options window "Auto Defensive Target Me" (setter FUN_00657530, registered by FUN_006671f0):
# 0x117 {u8 on} whenever it changes (FUN_005e2c70 keeps it at manager +0x33c). Saved per character.
AUTO_DEF_TARGET_ME = 0x117
AUTO_DEF_TARGET_ME_SET = 0x11B   # server -> client {bool8}: sets the option (FUN_005e15d0)
YOU_HAVE_BEEN_SUMMONED = 45


def call_offer(caller, target):
    target["call_from"] = caller["player"].char_id
    target["send"](zone.zone_event(CALL_OFFER, (caller["player"].name + "\0").encode("utf-16-le")))


def call_answer(state, args, data):
    caller = state_by_char_id(state.pop("call_from", None))
    if not data or not data[0] or caller is None or caller.get("player") is None or caller is state:
        return
    dest = caller.get("position") or caller["player"].live_position or caller["player"].spawned_at
    if dest is None:
        return
    place_player(state, args, (dest[0] + 100.0, dest[1], dest[2] + 50.0),
                 getattr(caller["player"], "chunk", None) or DEFAULT_CHUNK)
    state["send"](client_notice(YOU_HAVE_BEEN_SUMMONED))


def gm_command(state, args, event, data):
    player, send = state["player"], state["send"]
    if not (getattr(args, "dev_commands", False) or getattr(player, "access_level", 0) > 0):
        send(build_system_text("You are not a GM on this server.", SYSTEM_TEXT_ERROR))
        return
    if event == GM_CHUNK and len(data) >= 8:
        cx, cy = struct.unpack_from("<ii", data)
        # The client's /chunk already sent the ordinary chunk change (0x9) before this.
        if (cx, cy) != tuple(getattr(player, "chunk", None) or DEFAULT_CHUNK) and not state.get("handoff"):
            travel_to_chunk(state, args, cx, cy, *chunk_arrival(cx, cy))
    elif event in (GM_GOTO, GM_SUMMON, GM_SUMMON_GROUP):
        name = social.read_name(data).strip()
        other = ONLINE.get(name.lower())
        if other is None or other.get("player") is None or other is state:
            send(build_system_text(f"{name or 'That player'} is not online.", SYSTEM_TEXT_ERROR))
            return
        if event == GM_GOTO:
            movers, to = [state], other
        else:
            movers = [other] if event == GM_SUMMON else [s for s in group_states(other["player"]) or [other]
                                                        if s is not state]
            to = state
        dest = to.get("position") or to["player"].live_position or to["player"].spawned_at
        if dest is None:
            return
        for n, mover in enumerate(movers):
            place_player(mover, args, (dest[0] + 100.0 + 60.0 * n, dest[1], dest[2] + 50.0),
                         getattr(to["player"], "chunk", None) or DEFAULT_CHUNK)
            if event != GM_GOTO:
                mover["send"](client_notice(YOU_HAVE_BEEN_SUMMONED))
    elif event in (GM_LEARN_ALL, GM_MAX_SKILLS, GM_SETUP_ALL) and len(data) >= 8:
        target = state_by_char_id(struct.unpack_from("<Q", data)[0])
        if target is None:
            send(client_notice(DEF_TARGET_NOT_PC))
            return
        if event == GM_SETUP_ALL and len(data) >= 12:
            gm_set_level(target, struct.unpack_from("<i", data, 8)[0])
        if event in (GM_LEARN_ALL, GM_SETUP_ALL):
            gm_learn_all(target)
        if event in (GM_MAX_SKILLS, GM_SETUP_ALL):
            gm_max_skills(target)
    elif event == GM_HIDE and data:
        mode = data[0]
        hidden = (not getattr(player, "gm_hidden", False)) if mode == 3 else mode == 1
        player.gm_hidden = hidden
        pawn_props_changed(state, {"m_bGMHide": hidden})
        send(build_system_text("You are now hidden." if hidden else "You are now visible.", SYSTEM_TEXT_WHITE))


def save_aa(player):
    save_character_field(player.name, "aa_ranks", {str(k): v for k, v in player.aa_ranks.items()})
    save_character_field(player.name, "aa_points", player.aa_points)
    save_character_field(player.name, "aa_spent", player.aa_spent)


def aa_changed(state, before):
    """After ranks changed: the attributes they raise, the points (MsgScore) and abilities
    whose prerequisites flipped (0x861)."""
    player, send = state["player"], state["send"]
    for name in zone.apply_gear_stats(player):
        if name in vgmsg.ATTRIBUTES:
            send(zone.attribute_update(player, name))
    send(zone.score_message(player))
    for a in zone.aa_abilities(player):
        ok = aa.eligible(a, player.aa_ranks)
        if ok != aa.eligible(a, before):
            send(aa.eligible_update(a, ok))


def handle_aa_event(state, args, event, data):
    """Alternate advancement (aa.py): train (0x85a / /aatrain), /aalist, and the GM /aaclear
    and /aaadd."""
    player, send = state["player"], state["send"]
    abilities = zone.aa_abilities(player)
    if event == aa.LIST:
        for m in aa.list_messages(abilities, player.aa_ranks):
            send(m)
        return
    if event in (aa.TRAIN, aa.TRAIN_NAME):
        if event == aa.TRAIN and len(data) >= 4:
            aid = struct.unpack_from("<i", data)[0]
            a = next((x for x in abilities if x["id"] == aid), None)
        else:
            name = data.decode("utf-16-le", "replace").split(chr(0))[0].strip().lower()
            a = next((x for x in abilities if x["title"].lower() == name), None)
        if a is None:
            send(build_system_text("There is no such alternate advancement ability.", SYSTEM_TEXT_ERROR))
            return
        rank = player.aa_ranks.get(a["id"], 0)
        why = aa.train_error(a, rank, player.aa_ranks, player.aa_points, player.aa_spent, player.level_number)
        if why:
            send(build_system_text(why, SYSTEM_TEXT_ERROR))
            return
        before = dict(player.aa_ranks)
        price = aa.cost(a, rank)
        player.aa_points -= price
        player.aa_spent += price
        player.aa_ranks[a["id"]] = rank + 1
        save_aa(player)
        send(aa.trained(a, rank + 1))
        aa_changed(state, before)
        send(build_system_text(f"You have trained {a['title']} to rank {rank + 1}.", SYSTEM_TEXT_WHITE))
        print(f"  {player.name} trains AA {a['title']} rank {rank + 1} ({player.aa_points} points left)")
        return
    # /aaclear and /aaadd are GM tools
    if not (getattr(args, "dev_commands", False) or getattr(player, "access_level", 0) > 0):
        send(build_system_text("You are not a GM on this server.", SYSTEM_TEXT_ERROR))
        return
    if event == aa.CLEAR:
        before = dict(player.aa_ranks)
        player.aa_points += player.aa_spent
        player.aa_spent = 0
        player.aa_ranks = {}
        save_aa(player)
        for m in aa.list_messages(abilities, player.aa_ranks):
            send(m)
        aa_changed(state, before)
        send(build_system_text("Your alternate advancement abilities have been cleared and the points refunded.",
                               SYSTEM_TEXT_WHITE))
    elif event == aa.GRANT and len(data) >= 12:
        target_id, n = struct.unpack_from("<Qi", data)
        ts = next((s for s in ONLINE.values() if s.get("player") is not None
                   and s["player"].char_id == target_id), None)
        if ts is None:
            send(build_system_text("Your defensive target is not a player who is online.", SYSTEM_TEXT_ERROR))
            return
        p = ts["player"]
        p.aa_points = max(0, getattr(p, "aa_points", 0) + n)
        save_character_field(p.name, "aa_points", p.aa_points)
        ts["send"](zone.score_message(p))
        send(build_system_text(f"{p.name} now has {p.aa_points} AA points.", SYSTEM_TEXT_WHITE))


def hint(player, key):
    """The hint popup for a trigger (hints.py), once per character; None if not due."""
    content = getattr(ARGS, "content", None)
    seen = player.__dict__.setdefault("hints_seen", [])
    h = hints.pick(getattr(content, "hints", {}) or {}, key, seen, getattr(player, "hints_off", False))
    if h is None:
        return None
    seen.append(key)
    save_character_field(player.name, "hints_seen", seen)
    return hints.show(*h)


def handle_hint_event(state, event):
    """0x17f closed with "Do not show me any more hints", /hintsenable, /craftinghintsenable,
    /hintsreset."""
    player = state["player"]
    if event == hints.CLOSED_NO_MORE:
        player.hints_off = True
    elif event in (hints.ENABLE, hints.ENABLE_CRAFTING):
        player.hints_off = False
        state["send"](build_system_text("Hints are turned on.", SYSTEM_TEXT_WHITE))
    elif event == hints.RESET:
        player.hints_off = False
        player.hints_seen = []
        save_character_field(player.name, "hints_seen", [])
        state["send"](build_system_text("Hints you have already seen will be shown again.", SYSTEM_TEXT_WHITE))
    save_character_field(player.name, "hints_off", player.hints_off)


def handle_craft_allocate(state, stat_id, mode):
    """The crafting tab's + / Max: crafting attribute points come with crafting levels."""
    player, send = state["player"], state["send"]
    name = next((n for n, sid in attributes.CRAFT_STATS.items() if sid == stat_id), None)
    alloc = player.__dict__.setdefault("craft_alloc", {})
    level = zone.sphere(player, zone.CRAFTING)[0]
    n, code = attributes.allocate(name, mode, level, alloc, attributes.CRAFTING)
    if n:
        save_character_field(player.name, "craft_alloc", alloc)
    value = attributes.CRAFT_BASE + alloc.get(name, 0) if name else 0
    send(attributes.result(code, stat_id, value, attributes.pool(level, alloc), attributes.CRAFTING))
    if n:
        send(attributes.craft_update(name, alloc))
        print(f"  {player.name} puts {n} crafting point(s) into {name}")


def handle_skill_direction(state, data):
    """0xe3 from a crafting skill's - / lock / + button: remember it and light that button."""
    player = state["player"]
    if len(data) < 12:
        return
    sid, direction, category = struct.unpack_from("<iii", data)
    if direction not in attributes.DIRECTIONS:
        return
    if category != attributes.CRAFTING or sid not in {s for s, _sub in attributes.CRAFT_SKILLS}:
        state["send"](attributes.direction_result(attributes.DIRECTION_NO_SKILL, sid, category,
                                                  getattr(player, "skill_dirs", {}).get(sid, 0)))
        return
    player.skill_dirs = {**getattr(player, "skill_dirs", {}), sid: direction}
    save_character_field(player.name, "skill_dirs", {str(k): v for k, v in player.skill_dirs.items()})
    state["send"](attributes.craft_skill_update(sid, zone.sphere(player, zone.CRAFTING)[0], direction))
    state["send"](attributes.direction_result(attributes.DIRECTION_OK, sid, category, direction))


def handle_allocate(state, data):
    """0xe4 from the Attributes tab's + / Max buttons (attributes.py)."""
    player, send = state["player"], state["send"]
    if len(data) < 12:
        return
    stat_id, mode, category = struct.unpack_from("<iii", data)
    name = next((n for n, sid in vgmsg.STAT_IDS.items() if sid == stat_id), None)
    if category == attributes.CRAFTING:
        handle_craft_allocate(state, stat_id, mode)
        return
    alloc = player.__dict__.setdefault("attr_alloc", {})
    if category != attributes.ADVENTURING:
        n, code = 0, attributes.NOT_ALLOWED
    else:
        n, code = attributes.allocate(name, mode, player.level_number, alloc)
    if n:
        save_character_field(player.name, "attr_alloc", alloc)
        zone.apply_gear_stats(player)
    left = attributes.pool(player.level_number, alloc)
    base = zone.stat_base(player, name) if name in player.stats else 0
    send(attributes.result(code, stat_id, base, left))
    if n:
        send(zone.attribute_update(player, name))
        if name in ("constitution", "vitality", "intelligence", "wisdom"):
            send(zone.score_message(player))         # pools and health follow the attributes
        print(f"  {player.name} puts {n} point(s) into {name} ({left} left)")


def award_xp(player, amount, source, grouped=False):
    """Experience for one player (0x3d5, level ups, XP bar via MsgScore); saved.
    While the player has experience debt, half of what they earn pays it off."""
    out = [combat.experience_reward(amount, source, group=1 if grouped else 0)]
    debt = getattr(player, "xp_debt", 0)
    if debt > 0:
        paid = min(debt, amount // 2)
        amount -= paid
        player.xp_debt = debt - paid
        save_character_field(player.name, "xp_debt", player.xp_debt)
        if player.xp_debt == 0:
            out.append(build_system_text("You have paid off your experience debt.", SYSTEM_TEXT_WHITE))
    player.xp += amount
    player.aa_xp, player.aa_points, aa_got = aa.gain(player.xp, getattr(player, "aa_xp", 0),
                                                     getattr(player, "aa_points", 0), amount,
                                                     player.level_number)
    if aa_got:
        out.append(build_system_text(f"You have gained {aa_got} alternate advancement point"
                                     f"{'s' if aa_got > 1 else ''}!", SYSTEM_TEXT_WHITE))
        save_character_field(player.name, "aa_points", player.aa_points)
    if player.level_number >= aa.MIN_LEVEL:
        save_character_field(player.name, "aa_xp", player.aa_xp)
    leveled = False
    while player.xp >= zone.xp_for_level(player.level_number) and player.level_number < zone.LEVEL_CAP:
        player.xp -= zone.xp_for_level(player.level_number)
        player.level_number += 1
        out.append(build_system_text(f"You have reached level {player.level_number}!",
                                     SYSTEM_TEXT_WHITE))
        leveled = True
    out.append(zone.score_message(player))           # recomputes maximum health for the new level
    if leveled:
        out.append(attributes.set_pool(attributes.pool(player.level_number, getattr(player, "attr_alloc", {}))))
        out.append(attributes.gained())
        m = hint(player, "level")
        if m:
            out.append(m)
        player.health = player.stats["hit_points"]  # a level up heals you fully
        out.append(zone.health_update(player))
        for name in vgmsg.ATTRIBUTES:                # class attributes grew with the level
            out.append(zone.attribute_update(player, name))
    save_character_progress(player.name, player.level_number, player.xp)
    return out


def set_combat_stance(state, args, player, on, out):
    """m_CombatState = 1 draws weapons (verified live); everyone in the chunk sees it.
    /forcecombatstance keeps them drawn."""
    on = on or getattr(player, "forced_stance", False)
    if getattr(player, "stance", False) == on:
        return
    player.stance = on
    values = {"m_CombatState": int(on)}
    if "ue" in state:                       # not before the Unreal channel is open
        out.append(zone.player_pawn_update(state, args, values))
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.remote_player_update(s, args, player, values), exclude=state)


def broadcast_npc(state, args, npc, values):
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.npc_update(s, args, npc, values))


DEBT_PER_DEATH = 100          # experience debt per death (of zone.XP_PER_LEVEL a level)
DEBT_CAP = 500


def player_death(state, args, player):
    """The player's pawn falls (m_bIsDead + death animation) and the release
    popup opens. Death adds experience debt; the tombstone appears on release."""
    print(f"  <- {player.name} died")
    m = hint(player, "death")
    if m:
        state["send"](m)
    for s in group_states(player):
        if s is not state:
            s["send"](zone.zone_event(0x691, struct.pack("<Q", player.char_id)))   # "<name> died!!"
    player.xp_debt = min(DEBT_CAP, getattr(player, "xp_debt", 0) + DEBT_PER_DEATH)
    save_character_field(player.name, "xp_debt", player.xp_debt)
    player.died_at = state.get("position") or player.live_position or player.spawned_at
    drop_form_on_death(state, player)
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
    out.append(zone.score_message(player))
    out.append(build_system_text("You have gained experience debt. Recover your tombstone to win some of "
                                 "it back.", SYSTEM_TEXT_ERROR))
    return out


CORPSE_CATEGORY = -2          # the client's built-in "Corpses" journal category


def tombstone_marker(player, show=True):
    """Travel journal entry type 1 = tombstone icon on the map (0x382), or remove it (0x383)."""
    eid = zone.tombstone_eid(player)
    if not show:
        return [zone.zone_event(0x383, struct.pack("<i", eid))]
    x, y, z = player.tombstone["loc"]
    cx, cy = (int(p[1:]) * -1 if p.startswith("n") else int(p) for p in player.level.split("_")[1:3])
    out = []
    if not getattr(player, "journal_ready", False):
        # The first 0x2ae creates the built-in categories (All Locations, Corpses, Player Housing).
        out.append(zone.zone_event(0x2AE, ("Locations\0").encode("utf-16-le") + struct.pack("<ii", 1, 0)))
        player.journal_ready = True
    out.append(zone.zone_event(0x382, struct.pack("<iifff", eid, 0, x, y, z)
                               + (f"{player.name}'s tombstone\0").encode("utf-16-le")
                               + struct.pack("<iiiB", cx, cy, 0, 1) + ("\0").encode("utf-16-le")
                               + struct.pack("<iBi", CORPSE_CATEGORY, 0, 0)))
    return out


def place_tombstone(state, args, player):
    """Release: leave the tombstone where the player died, for everyone in the chunk."""
    w = state.get("world")
    loc = getattr(player, "died_at", None)
    if w is None or loc is None:
        return
    old = getattr(player, "tombstone", None)
    if old:
        remove_tombstone(state, player, quiet=True)
    player.tombstone = {"level": player.level, "loc": [float(loc[0]), float(loc[1]), float(loc[2])],
                        "placed": int(time.time())}
    save_character_field(player.name, "tombstone", player.tombstone)
    npc = zone.tombstone_spawn(w, args, player)
    if npc is not None:
        w.broadcast(lambda s, npc=npc: zone.open_npc(s, args, npc))
    for m in tombstone_marker(player):
        state["send"](m)


# Consent and corpse drag (docs/DEATH.md "Consent and corpse drag"): /consent <name> 0x17b
# {wstr}, /revoke <name> 0x17c {wstr}, /corpsedrag and /tombstonedrag 0x17a, /decaytime 0x3dd.
CONSENT, REVOKE, CORPSE_DRAG, DECAY_TIME = 0x17B, 0x17C, 0x17A, 0x3DD
CORPSE_EVENTS = (CONSENT, REVOKE, CORPSE_DRAG, DECAY_TIME)
DRAG_RANGE = 1500.0
TOMBSTONE_DECAY = 48 * 3600           # seconds a tombstone lasts (reported by /decaytime)


UNSTUCK = 0x44C                       # the Help window's "Unstuck" button (no payload)
UNSTUCK_COOLDOWN = 300


def unstuck(state):
    """Move a stuck player to their bind spot (an altar) in this chunk, else to where they
    entered the chunk; once every UNSTUCK_COOLDOWN seconds."""
    player, send = state["player"], state["send"]
    now = time.time()
    if now - state.get("unstuck_at", 0) < UNSTUCK_COOLDOWN:
        left = int(UNSTUCK_COOLDOWN - (now - state["unstuck_at"]))
        send(build_system_text(f"You can use Unstuck again in {left // 60}m {left % 60}s.", SYSTEM_TEXT_ERROR))
        return
    if player.health <= 0:
        send(client_notice(NOT_WHILE_DEAD))
        return
    state["unstuck_at"] = now
    bind = getattr(player, "bind", None)
    if bind and bind.get("level") == player.level:
        loc = tuple(bind["loc"])
    else:
        loc = player.spawned_at
    if loc is None:              # not in the world yet
        state.pop("unstuck_at", None)
        return
    send(zone.player_teleport((float(loc[0]), float(loc[1]), float(loc[2]) + 50.0)))
    send(build_system_text("You have been moved to safety.", SYSTEM_TEXT_WHITE))
    print(f"  {player.name} used Unstuck -> {loc}")


def handle_corpse_event(state, event, data):
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE corpse event {event:#x}: {data.hex(' ')}")
    if event in (CONSENT, REVOKE):
        name = data.decode("utf-16-le", "replace").split("\0")[0].strip()
        other = ONLINE.get(name.lower())
        if other is None or other.get("player") is None or other is state:
            send(build_system_text(f"{name or 'That player'} is not online.", SYSTEM_TEXT_ERROR))
            return
        consents = player.__dict__.setdefault("consents", set())
        oname = other["player"].name
        if event == CONSENT:
            consents.add(oname.lower())
            send(zone.zone_event(0x55C, (oname + "\0").encode("utf-16-le")))           # ConsentEchoGave
            other["send"](zone.zone_event(0x55A, (player.name + "\0").encode("utf-16-le")))  # ConsentAdded
        elif oname.lower() in consents:
            consents.discard(oname.lower())
            send(zone.zone_event(0x55D, (oname + "\0").encode("utf-16-le")))           # ConsentEchoRevoked
            other["send"](zone.zone_event(0x55B, (player.name + "\0").encode("utf-16-le")))  # ConsentLost
    elif event == CORPSE_DRAG:
        w = state.get("world")
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not getattr(npc, "tombstone_of", None):
            npc = w.npcs.get(zone.tombstone_eid(player)) if w is not None else None
        result = 0
        if npc is None or not getattr(npc, "tombstone_of", None):
            result = 3                                             # CorpseDragFailNoTarget
        else:
            owner = npc.tombstone_of
            os_ = ONLINE.get(owner.lower())
            allowed = owner.lower() == player.name.lower() or (
                os_ is not None and player.name.lower() in getattr(os_["player"], "consents", set()))
            pos = state.get("position") or player.live_position
            if not allowed:
                result = 2                                         # CorpseDragFailConsent
            elif pos is None or math.hypot(pos[0] - npc.location[0], pos[1] - npc.location[1]) > DRAG_RANGE:
                result = 6                                         # TooFarAway
        if result:
            send(zone.zone_event(0x5FA, struct.pack("<B", result)))
            return
        npc.location = npc.home = (pos[0], pos[1], pos[2] - 90.0)
        values = {"Location": npc.location, "PawnPosition": (npc.location, (0, npc.yaw, 0), (0.0, 0.0, 0.0))}
        w.broadcast(lambda s: zone.npc_update(s, ARGS, npc, values))
        owner_player = os_["player"] if os_ is not None else None
        if owner_player is not None and getattr(owner_player, "tombstone", None):
            owner_player.tombstone["loc"] = [float(v) for v in npc.location]
            save_character_field(owner_player.name, "tombstone", owner_player.tombstone)
            for m in tombstone_marker(owner_player):
                os_["send"](m)
        send(build_system_text(f"You drag {owner}'s tombstone.", SYSTEM_TEXT_WHITE))
    elif event == DECAY_TIME:
        stone = getattr(player, "tombstone", None)
        left = max(0, TOMBSTONE_DECAY - (int(time.time()) - stone.get("placed", int(time.time())))) if stone else 0
        send(zone.zone_event(0x688, struct.pack("<i", left)))       # "CorpseDecayTimeSeconds"


def remove_tombstone(state, player, quiet=False):
    # The stone stands in its own region's world, which need not be the player's (a corpse
    # summoned from another region, or recovered after travelling).
    level = (getattr(player, "tombstone", None) or {}).get("level")
    w = next((x for x in world.all_worlds() if x.level == level), None) if level else state.get("world")
    eid = zone.tombstone_eid(player)
    if w is not None and eid in w.npcs:
        del w.npcs[eid]
        w.broadcast(lambda s: zone.close_actor(s, eid))
    for m in tombstone_marker(player, show=False):
        state["send"](m)
    player.tombstone = None
    save_character_field(player.name, "tombstone", None)


ALTAR_RANGE = 800
CORPSE_MOVED, NO_CORPSES = 0x48, 300


def bind_here(state, altar):
    """Set the bind (respawn) point at the player's position next to an altar."""
    player = state["player"]
    pos = player.live_position or player.spawned_at
    player.bind = {"level": player.level, "loc": [float(pos[0]), float(pos[1]), float(pos[2])]}
    save_character_field(player.name, "bind", player.bind)
    state["send"](zone.zone_event(0x40A, struct.pack("<B", 0)))        # "You have set your bind location."
    state["send"](zone.score_message(player))


def near_altar(player):
    return next((n for n in player.npcs.values() if getattr(n, "altar", False)
                 and player_distance(player, n) <= ALTAR_RANGE), None)


def handle_altar_use(state, npc):
    """0x2b0 on an altar: bind there, and offer the player's tombstone for summoning (0x2bc)."""
    player, send = state["player"], state["send"]
    if player.health <= 0:
        send(client_notice(NOT_WHILE_DEAD))                # no binding while dead (release first)
        return
    if player_distance(player, npc) > ALTAR_RANGE:
        send(client_notice(TOO_FAR_AWAY))
        return
    bind_here(state, npc)
    stone = getattr(player, "tombstone", None)
    if not stone:
        send(zone.zone_event(0x0E, struct.pack("<h", NO_CORPSES)))
        return
    where = chunk_display_name(stone["level"])        # the zone's name ("Khal") for the corpse list
    send(zone.zone_event(0x2BC, struct.pack("<i", 1) + (f"{where}\0").encode("utf-16-le")
                         + struct.pack("<ii", zone.tombstone_eid(player), 0)))


def summon_tombstone(state, cid):
    """0x188 {corpse id} from the corpse list: the tombstone moves next to the altar."""
    player, send = state["player"], state["send"]
    altar = near_altar(player)
    if altar is None or cid != zone.tombstone_eid(player) or not getattr(player, "tombstone", None):
        send(zone.zone_event(0x0E, struct.pack("<h", NO_CORPSES)))
        return
    player.died_at = (altar.location[0] + 150.0, altar.location[1], altar.location[2])
    place_tombstone(state, ARGS, player)
    send(zone.zone_event(0x0E, struct.pack("<h", CORPSE_MOVED)))
    send(build_system_text("Your tombstone has been summoned to the altar.", SYSTEM_TEXT_WHITE))


REZ_SECONDS = 60
NO_ONE_REZZING, REZ_DECLINED, REZ_EXPIRED = 0x9A, 0x9B, 0x9D


def offer_rez(state, caster, ability, refund=0.5, caster_state=None):
    """0x26e: "<caster> is trying to resurrect you with <ability>." + Accept/Decline (0xe0)."""
    player = state["player"]
    state["rez"] = {"caster": caster, "until": time.time() + REZ_SECONDS, "refund": refund,
                    "caster_state": caster_state,
                    "spot": getattr(player, "died_at", None) or player.live_position}
    state["send"](zone.zone_event(0x26E, (caster + "\0").encode("utf-16-le") + (ability + "\0").encode("utf-16-le")
                                  + struct.pack("<i", REZ_SECONDS)))


def answer_rez(state, args, accept):
    """0xe0 {u8}: accept (stand up where you died with half health, win back debt) or decline."""
    player, send = state["player"], state["send"]
    rez = state.pop("rez", None)
    if rez is None or time.time() > rez["until"]:
        send(zone.zone_event(0x0E, struct.pack("<h", REZ_EXPIRED if rez else NO_ONE_REZZING)))
        return
    cs = rez.get("caster_state")
    if not accept:
        if cs is not None:
            cs["send"](zone.zone_event(0x0E, struct.pack("<h", REZ_DECLINED)))
        return
    if getattr(player, "tombstone", None):
        remove_tombstone(state, player, quiet=True)
    debt = getattr(player, "xp_debt", 0)
    back = int(debt * rez["refund"])
    player.xp_debt = debt - back
    save_character_field(player.name, "xp_debt", player.xp_debt)
    player.health = max(1, player.stats["hit_points"] // 2)
    for m in (combat.death_popup(0, True),
              zone.player_pawn_update(state, args, {"Health": 50, "m_bIsDead": 0}),
              zone.health_update(player), zone.score_message(player)):
        send(m)
    if rez.get("spot"):
        send(zone.player_teleport(tuple(rez["spot"])))
    send(build_system_text(f"You have been resurrected by {rez['caster']} and win back {back} experience.",
                           SYSTEM_TEXT_WHITE))
    restore_form_after_death(state, player)


RIFT_PRICES = {"green": 50, "blue": 500, "yellow": 2000, "red": 5000, "purple": 0}
RIFT_RANGE = 800


def handle_rift(state, args, data):
    """0x597 {wstr NAME} from the map's Riftway tab or /rift NAME: travel from a riftway
    stone to an open destination for the color's price (the client checks nothing)."""
    player, send = state["player"], state["send"]
    name = data.decode("utf-16-le", "replace").split("\0")[0].strip().upper()
    say = lambda t: send(build_system_text(t, SYSTEM_TEXT_ERROR))
    dest = ARGS.content.riftways.get(name)
    if dest is None:
        say("There is no riftway by that name.")
        return
    stone = next((n for n in player.npcs.values() if getattr(n, "riftway", None) is not None
                  and player_distance(player, n) <= RIFT_RANGE), None)
    if stone is None:
        say("You must stand at a riftway to travel.")
        return
    if not dest.get("chunk"):
        say(f"The riftway to {dest['name']} is not open on this server yet.")
        return
    price = RIFT_PRICES.get(dest.get("color"), 0)
    if player.coins < price:
        say("You can't afford to travel there.")
        return
    if price:
        player.coins -= price
        send(merchant.coins(player.coins))
        save_character_field(player.name, "coins", player.coins)
    if dest["chunk"] != player.level:
        # Another region: a full chunk change, landing at the destination (riftways.json "z" for
        # a raised hub, else the ground there).
        send(build_system_text(f"The riftway carries you to {dest['name']}.", SYSTEM_TEXT_WHITE))
        cx, cy = level_chunk(dest["chunk"])
        travel_to_chunk(state, ARGS, cx, cy, float(dest["x"]), float(dest["y"]),
                        float(dest["z"]) if dest.get("z") is not None else None)
        return
    z = dest.get("z") if dest.get("z") is not None else ARGS.content.ground_z(player.level, dest["x"], dest["y"], ARGS.client_dir)
    send(zone.player_teleport((float(dest["x"]), float(dest["y"]), float(z) + 100.0)))
    send(build_system_text(f"The riftway carries you to {dest['name']}.", SYSTEM_TEXT_WHITE))


HOUSING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "housing.json")
PLOT_OBJECT_BASE = 0x5000000


def load_housing():
    """{plot id: {owner, bought, building (type), built}}"""
    return storage.read_json(HOUSING_FILE, {})


def save_housing(db):
    storage.write_json(HOUSING_FILE, db)


def plot_object(pid, plot, st):
    """The world object for a plot: its house when built, else a For Sale / owner sign."""
    b = next((o for o in plot.get("buildings", []) if st and o["type"] == st.get("building")), None)
    yaw = int(plot.get("yaw", 0))
    if b:
        return {"id": PLOT_OBJECT_BASE + int(pid), "prefab": b["prefab"], "type": zone.HOUSE_BUILDING,
                "building": int(pid), "loc": plot["loc"], "rot": (0, yaw, 0),
                "hover": f"{st['owner']}'s {b['name']}"}
    owner = (st or {}).get("owner")
    return {"id": PLOT_OBJECT_BASE + int(pid), "prefab": housing.SIGN_PREFAB, "type": zone.HOUSE_PLOT,
            "building": int(pid), "loc": plot["loc"], "rot": (0, yaw, 0),
            "hover": f"{plot['name']} ({owner})" if owner else f"{plot['name']} - for sale"}


def fixture_object(pid, f):
    return {"id": housing.FIXTURE_ID_BASE + f["id"], "prefab": f["prefab"],
            "type": zone.HOUSE_CHEST if "items" in f else zone.HOUSE_FIXTURE,
            "building": housing.FIXTURE_ID_BASE + f["id"], "loc": f["loc"], "rot": (0, f.get("yaw", 0), 0),
            "hover": f["item"]}


def placed_objects(level):
    db = load_housing()
    out = []
    for pid, p in ARGS.content.plots.items():
        if p["chunk"] == level:
            out.append(plot_object(pid, p, db.get(pid)))
            out += [fixture_object(pid, f) for f in (db.get(pid) or {}).get("fixtures", [])]
    return out


def my_house_here(player):
    """(plot id, plot) of the built plot the player stands in and may place furniture in
    (owner, or a PlaceFixture permission), or (None, None)."""
    db = load_housing()
    pos = player.live_position or player.spawned_at
    for pid, p in ARGS.content.plots.items():
        st = db.get(pid)
        if (st and st.get("building") and housing.allowed(st, player.name, housing.PLACE_FIXTURE, guild_of)
                and p["chunk"] == player.level
                and math.hypot(pos[0] - p["loc"][0], pos[1] - p["loc"][1]) <= housing.HOUSE_RADIUS):
            return pid, p
    return None, None


NEED_OPEN_SPACE = 0x714      # no payload: "You need more open space around you to do that."


def inside_a_house(player):
    """True when the player stands inside any built house (within housing.HOUSE_RADIUS of a
    built plot's centre in their chunk), whoever owns it."""
    db = load_housing()
    pos = player.live_position or player.spawned_at
    if pos is None:
        return False
    return any(db.get(pid, {}).get("building") and p["chunk"] == player.level
               and math.hypot(pos[0] - p["loc"][0], pos[1] - p["loc"][1]) <= housing.HOUSE_RADIUS
               for pid, p in ARGS.content.plots.items())


def broadcast_object(state, obj, close=False):
    w = state.get("world")
    if w is None:
        return
    for s in list(w.members.values()):
        m = zone.close_actor(s, obj["id"])
        if m:
            s["send"](m)
        if not close:
            s["send"](zone.open_placed_object(s, ARGS, obj))


def place_fixture(state, item, pose=None):
    """Right-click a furniture item (items.json "fixture": prefab) inside your house: it is
    placed where you stand, facing your way. With the client's placement ghost (0x46d), `pose`
    is the clicked ((x, y, z), yaw), which must be inside the house."""
    player, send = state["player"], state["send"]
    pid, plot = my_house_here(player)
    if pid is None or (pose is not None and math.hypot(pose[0][0] - plot["loc"][0], pose[0][1] - plot["loc"][1])
                       > housing.HOUSE_RADIUS):
        send(build_system_text("You can only place items when in your house.", SYSTEM_TEXT_ERROR))
        return
    db = load_housing()
    st = db[pid]
    b = next((o for o in plot["buildings"] if o["type"] == st["building"]), {})
    fixtures = st.setdefault("fixtures", [])
    if len(fixtures) >= b.get("fixtures", 20):
        send(zone.zone_event(0x0E, struct.pack("<h", 0x168)))          # BldgCantHoldMoreFixtures
        return
    pos = player.live_position or player.spawned_at
    z = pos[2] - 90.0                    # the pawn stands its collision height above the floor
    f = {"id": st.get("next_fixture", 1), "item": item[1], "prefab": ARGS.content.item(item[1])["fixture"],
         "loc": [pos[0], pos[1], z], "yaw": int(getattr(player, "yaw", 0) or 0)}
    if pose is not None:
        f["loc"], f["yaw"] = list(pose[0]), pose[1] & 0xFFFF
    if ARGS.content.item(item[1]).get("chest"):
        f["items"] = []
    st["next_fixture"] = f["id"] + 1
    fixtures.append(f)
    save_housing(db)
    take_items(state, item[1], 1)
    broadcast_object(state, fixture_object(pid, f))
    send(build_system_text(f"You place the {item[1]}.", SYSTEM_TEXT_WHITE))
    refresh_fixture_list(pid, st)


def chest_record(it):
    """A stored chest item [id, name, icon, qty, slot] as a client item record."""
    return vgmsg.inventory_item(it[0], it[1], it[4], it[2], it[3], **zone.item_equip_fields(it[1]))


def chest_redraw(send, f):
    """Redraw an open chest as on opening (clear, every item silently, refresh): removing and
    re-adding items prints "... was removed from your chest" for each."""
    send(housing.chest_clear())
    for it in f["items"]:
        send(housing.chest_item(chest_record(it)))
    send(housing.chest_refresh())


def chest_new_handle(player, f):
    return max([x[0] for x in f["items"]] + [zone.new_item_id(player)]) + 1


def handle_chest(state, event, vals):
    player, send = state["player"], state["send"]
    notice = lambda code: send(zone.zone_event(0x0E, struct.pack("<h", code)))
    if event == housing.CHEST_CLOSE:
        state.pop("chest", None)
        send(housing.chest_close())
        return
    cid = vals[0] if vals else 0
    db, pid, st, f = fixture_by_object(cid)
    if f is None or "items" not in f:
        return
    slot = {housing.CHEST_DEPOSIT: housing.CHEST_DEPOSIT_SLOT, housing.CHEST_WITHDRAW: housing.CHEST_WITHDRAW_SLOT,
            housing.CHEST_MOVE: housing.CHEST_WITHDRAW_SLOT}.get(event, housing.CHEST_VIEW)
    if not (housing.chest_allowed(st, f, player.name, housing.CHEST_VIEW, guild_of)
            and housing.chest_allowed(st, f, player.name, slot, guild_of)):
        notice(0x1ad)                                    # NoPermissionToUseChest
        return
    cap = ARGS.content.item(f["item"]).get("chest", 20)
    if event == housing.CHEST_OPEN:
        state["chest"] = cid
        send(housing.chest_open(cid, cap))
        send(housing.chest_clear())
        for it in f["items"]:
            send(housing.chest_item(chest_record(it)))
        send(housing.chest_refresh())
    elif state.get("chest") != cid:
        return
    elif event == housing.CHEST_DEPOSIT and len(vals) >= 2:
        # {chest, bag item, count (-1 = the whole stack), slot (-1 = any)}: the dropped slot when
        # it is free, else the first free one; a count below the stack splits it.
        item = next((i for i in player.items if i[0] == vals[1]), None)
        used = {it[4] for it in f["items"]}
        want = vals[3] if len(vals) >= 4 else -1
        slot = want if 0 <= want < cap and want not in used else next((s for s in range(cap) if s not in used), None)
        if item is None:
            return
        if slot is None:
            send(client_notice(CHEST_FULL))
            return
        count = vals[2] if len(vals) >= 3 and 0 < vals[2] < item[3] else item[3]
        if count == item[3]:
            player.items.remove(item)
            send(zone.zone_event(0x1A5, struct.pack("<iB", item[0], 0)))
            it = [item[0], item[1], item[2], item[3], slot]
        else:
            player.items[player.items.index(item)] = item[:3] + (item[3] - count, item[4])
            send(zone.zone_event(0x1AE, struct.pack("<ii", item[0], item[3] - count)))
            it = [chest_new_handle(player, f), item[1], item[2], count, slot]
        save_character_field(player.name, "items", [list(i) for i in player.items])
        f["items"].append(it)
        save_housing(db)
        send(housing.chest_item(chest_record(it), draw=True))
        send(housing.chest_refresh())
    elif event == housing.CHEST_MOVE and len(vals) >= 4:
        changed = housing.chest_move(f["items"], vals[1], vals[2], vals[3], cap, chest_new_handle(player, f))
        if changed:
            save_housing(db)
            chest_redraw(send, f)        # (removing the new split handle is a client "Programmer error")
    elif event == housing.CHEST_WITHDRAW and len(vals) >= 2:
        # {chest, chest item, count (-1 = all), container, slot}: the items land in the first free
        # bag slot; a count below the stack leaves the rest in the chest.
        it = next((x for x in f["items"] if x[0] == vals[1]), None)
        count = vals[2] if it is not None and len(vals) >= 3 and 0 < vals[2] < it[3] else (it[3] if it else 0)
        if it is None or not give_item(state, it[1], count, escrow=False):
            return
        if count < it[3]:
            it[3] -= count
            save_housing(db)
            chest_redraw(send, f)
            return
        f["items"].remove(it)
        save_housing(db)
        send(housing.chest_removed(it[0]))
        send(housing.chest_refresh())


def house_npc_options(plot, st):
    """The mobs.json keys the built house may hold (plots.json building "npcs")."""
    b = next((o for o in plot.get("buildings", []) if o["type"] == st.get("building")), {})
    return [k for k in b.get("npcs", []) if k in ARGS.content.mobs]


def house_npc_lists(pid, plot, st):
    mobs = ARGS.content.mobs
    avail = [(n + 1, mobs[k]["name"], mobs[k].get("title", "")) for n, k in enumerate(house_npc_options(plot, st))]
    placed = [(e["id"], mobs.get(e["mob"], {}).get("name", e["mob"]), "") for e in st.get("npcs", [])]
    return housing.npc_list(housing.AVAILABLE_NPCS, avail) + housing.npc_list(housing.PLACED_NPCS, placed)


def house_npc(w, pid, entry):
    """The world NPC for a placed house NPC entry {id, mob, loc, yaw}."""
    spawn = {"mob": entry["mob"], "x": entry["loc"][0], "y": entry["loc"][1], "z": entry["loc"][2], "yaw": entry["yaw"]}
    npc = zone.npc_from_template(w, ARGS, housing.NPC_EID_BASE + int(pid) * 64 + entry["id"], spawn,
                                 ARGS.content.mobs[entry["mob"]])
    npc.wander, npc.path = 0.0, []
    return npc


def house_npc_event(state, event, data, vals):
    """Manage NPCs: list, place where the owner stands, remove, go to (owner only, own house)."""
    player, send = state["player"], state["send"]
    pid = state.get("plot_window")
    db = load_housing()
    st = db.get(str(pid)) if pid is not None else None
    plot = ARGS.content.plots.get(str(pid)) if pid is not None else None
    if st is None or plot is None or not st.get("building") or st.get("owner", "").lower() != player.name.lower():
        return
    w = state.get("world")
    if event == housing.SPAWN_NPC:
        spawn = housing.parse_spawn_npc(data)
        options = house_npc_options(plot, st)
        if spawn is None or not 1 <= spawn[0] <= len(options) or w is None:
            return
        if my_house_here(player)[0] != str(pid):
            send(build_system_text("You can only place items when in your house.", SYSTEM_TEXT_ERROR))
            return
        entry = {"id": st.get("next_npc", 1), "mob": options[spawn[0] - 1], "loc": list(spawn[2]), "yaw": spawn[1]}
        if entry["id"] >= 64:
            return
        st["next_npc"] = entry["id"] + 1
        st.setdefault("npcs", []).append(entry)
        save_housing(db)
        npc = house_npc(w, pid, entry)
        w.npcs[npc.entity_id] = npc
        w.broadcast(lambda s, npc=npc: zone.open_npc(s, ARGS, npc))
    elif event in (housing.REMOVE_NPC, housing.GOTO_NPC):
        entry = next((e for e in st.get("npcs", []) if vals and e["id"] == vals[0]), None)
        if entry is None:
            return
        if event == housing.GOTO_NPC:
            loc = entry["loc"]
            place_player(state, ARGS, (loc[0] + 100.0, loc[1], loc[2] + 50.0), getattr(player, "chunk", None) or DEFAULT_CHUNK)
            return
        st["npcs"].remove(entry)
        save_housing(db)
        eid = housing.NPC_EID_BASE + int(pid) * 64 + entry["id"]
        if w is not None and w.npcs.pop(eid, None) is not None:
            for s in list(w.members.values()):
                m = zone.close_actor(s, eid)
                if m:
                    s["send"](m)
    for m in house_npc_lists(pid, plot, st):
        send(m)


def house_npcs_login(state):
    """Put the chunk's placed house NPCs into its world (once per world)."""
    w = state.get("world")
    if w is None or getattr(w, "house_npcs", False):
        return
    w.house_npcs = True
    for pid, st in load_housing().items():
        plot = ARGS.content.plots.get(pid)
        if not plot or plot.get("chunk") != w.level:
            continue
        for entry in st.get("npcs", []):
            if entry["mob"] in ARGS.content.mobs:
                npc = house_npc(w, pid, entry)
                w.npcs[npc.entity_id] = npc
                w.broadcast(lambda s, npc=npc: zone.open_npc(s, ARGS, npc))


def refresh_fixture_list(pid, st):
    """Redraw the Building Inventory list for everyone with this plot's window open."""
    for s in list(ONLINE.values()):
        p = s.get("player")
        if p and s.get("plot_window") == pid and housing.allowed(st, p.name, housing.VIEW_FIXTURE_LIST, guild_of):
            for m in housing.fixture_list(st.get("fixtures", [])):
                s["send"](m)


def fixture_by_object(oid):
    db = load_housing()
    for pid, st in db.items():
        for f in st.get("fixtures", []):
            if housing.FIXTURE_ID_BASE + f["id"] == oid:
                return db, pid, st, f
    return db, None, None, None


_housing_checked = [0.0]


def housing_tick(now):
    """Once a minute: charge due upkeep on every plot; a plot with REPOSSESS_AFTER missed
    payments is taken back: the owner gets a letter and their furniture and chest contents
    by mail, and the For Sale sign comes back."""
    if now - _housing_checked[0] < 60:
        return
    _housing_checked[0] = now
    db = load_housing()
    changed, gone = False, []
    for pid, st in list(db.items()):
        plot = ARGS.content.plots.get(pid)
        if plot is None:
            continue
        changed |= bool(housing.charge_upkeep(plot, st, now))
        if housing.repossess_due(st):
            gone.append((pid, plot, db.pop(pid)))
            changed = True
    if changed:
        save_housing(db)
    if not gone:
        return
    mdb = load_mail()
    for pid, plot, st in gone:
        owner = st.get("owner", "")
        print(f"  plot {pid} repossessed from {owner} (missed upkeep)")
        deliver_mail(mdb, owner, mail.new(0, "Housing Office", f"Repossessed: {plot['name']}"[:mail.MAX_SUBJECT],
                                          f"Your plot {plot['name']} was repossessed after "
                                          f"{housing.REPOSSESS_AFTER} missed upkeep payments.", from_player=False))
        for name in housing.returned_items(st):
            deliver_mail(mdb, owner, mail.new(0, "Housing Office", f"Returned: {name}"[:mail.MAX_SUBJECT],
                                              "From your repossessed house.",
                                              item_={"name": name, "icon": ARGS.content.item(name).get("icon", 443),
                                                     "qty": 1}, from_player=False))
        s = next((x for x in ONLINE.values() if x.get("player") and x["player"].level == plot["chunk"]), None)
        if s is not None:
            refresh_plot(s, pid)
    save_mail(mdb)


def transfer_plot(state, name):
    """Give the player's plot (with its building, fixtures and chests) to another player."""
    player, send = state["player"], state["send"]
    db = load_housing()
    pid = next((k for k, v in db.items() if v.get("owner", "").lower() == player.name.lower()), None)
    other = ONLINE.get(name.lower())
    if pid is None:
        send(client_notice(DONT_OWN_PLOT))
    elif other is None or other.get("player") is None or other is state:
        send(build_system_text(f"{name or 'That player'} must be online to receive your plot.", SYSTEM_TEXT_ERROR))
    elif any(v.get("owner", "").lower() == name.lower() for v in db.values()):
        send(build_system_text(f"{other['player'].name} already owns a plot.", SYSTEM_TEXT_ERROR))
    else:
        new_owner = other["player"].name
        db[pid]["owner"] = new_owner
        save_housing(db)
        plot_name = ARGS.content.plots.get(pid, {}).get("name", "your plot")
        send(build_system_text(f"You have transferred {plot_name} to {new_owner}.", SYSTEM_TEXT_WHITE))
        other["send"](build_system_text(f"{player.name} has transferred {plot_name} to you.", SYSTEM_TEXT_WHITE))
        print(f"  {player.name} transferred plot {pid} to {new_owner}")
        refresh_plot(state, pid)


def refresh_plot(state, pid):
    """Re-create a plot's world object for everyone in its chunk (sign <-> house)."""
    w = state.get("world")
    plot = ARGS.content.plots[pid]
    if w is None or plot["chunk"] != state["player"].level:
        return
    obj = plot_object(pid, plot, load_housing().get(pid))

    def build(s, obj=obj):
        out = [m for m in (zone.close_actor(s, obj["id"]),) if m]
        return out + [zone.open_placed_object(s, ARGS, obj)]
    for s in list(w.members.values()):
        for m in build(s):
            s["send"](m)


def send_plot_window(state, pid):
    player, send = state["player"], state["send"]
    plot = ARGS.content.plots[pid]
    db = load_housing()
    st = db.get(pid)
    if st and housing.charge_upkeep(plot, st, time.time()):
        save_housing(db)
    mine = bool(st) and st.get("owner", "").lower() == player.name.lower()
    state["plot_window"] = pid
    send(housing.plot_info(int(pid), plot, st, mine))
    if st and st.get("hq_guild") is not None:
        g = load_guilds().get(str(st["hq_guild"]))
        if g:
            send(housing.hq_name(g["name"]))
    if st and st.get("building"):
        send(housing.building_info(int(pid), plot, st, mine))
        if housing.allowed(st, player.name, housing.VIEW_FIXTURE_LIST, guild_of):
            for m in housing.fixture_list(st.get("fixtures", [])):
                send(m)
    if mine:
        for p in st.get("permissions", []):
            send(housing.permission_message(p))
            for row, name in enumerate(p.get("friends", [])):
                send(housing.friend_message(p["id"], row, name))
    send(housing.show())


def chest_friend_event(state, event, data):
    """Add / Remove Player in Edit Chest Permission (permission ids from CHEST_PERM_ID_BASE).
    True when the event was about a chest."""
    player, send = state["player"], state["send"]
    try:
        if event == housing.PERM_ADD_FRIEND:
            end = 0
            while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
                end += 2
            name = data[:end].decode("utf-16-le", "replace").strip()
            perm_id = struct.unpack_from("<i", data, end + 2)[0]
        else:
            perm_id, fid = struct.unpack_from("<ii", data)
    except struct.error:
        return False
    slot = housing.chest_slot_of(perm_id)
    if slot is None:
        return False
    db, pid, st, f = fixture_by_object(state.get("managed_chest", -1))
    if f is None or st["owner"].lower() != player.name.lower():
        return True
    p = f.setdefault("perms", {}).setdefault(str(slot), {"rank": 0, "all_players": False, "all_guild": False})
    friends = p.setdefault("friends", [])
    if event == housing.PERM_ADD_FRIEND:
        if name and name.lower() not in [x.lower() for x in friends] and len(friends) < housing.MAX_FRIENDS:
            friends.append(name)
            send(build_system_text(f"{name} added to the chest's {housing.CHEST_SLOT_NAMES[slot]} permission.",
                                   SYSTEM_TEXT_WHITE))
    elif 0 < fid <= len(friends):
        friends.pop(fid - 1)
    save_housing(db)
    for m in housing.chest_permissions(state["managed_chest"], f):
        send(m)
    return True


def handle_plot_permission(state, event, data):
    """The owner's building permissions (housing.PERMISSION_EVENTS) on their plot."""
    player, send = state["player"], state["send"]
    db = load_housing()
    pid = next((k for k, v in db.items() if v.get("owner", "").lower() == player.name.lower()), None)
    if pid is None:
        send(zone.zone_event(0x0E, struct.pack("<h", 0x175)))          # CantFindPlot
        return
    st = db[pid]
    perms = st.setdefault("permissions", [])
    try:
        if event in (housing.PERM_CREATE, housing.PERM_EDIT):
            p = housing.parse_permission(data)
            old = next((q for q in perms if q["id"] == p["id"]), None) if event == housing.PERM_EDIT else None
            if old is not None:
                old.update({k: v for k, v in p.items() if k != "plot"})
                p = old
            else:
                if len(perms) >= housing.MAX_PERMISSIONS:
                    send(build_system_text("This building has too many permissions.", SYSTEM_TEXT_ERROR))
                    return
                p.pop("plot")
                p["id"] = max([q["id"] for q in perms] + [0]) + 1
                p["friends"] = []
                perms.append(p)
            send(build_system_text(f"Permission \"{p['name']}\" saved.", SYSTEM_TEXT_WHITE))
        elif event == housing.PERM_DELETE:
            perm_id = struct.unpack_from("<ii", data)[1]
            st["permissions"] = [q for q in perms if q["id"] != perm_id]
        elif event == housing.PERM_ADD_FRIEND:
            end = 0
            while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
                end += 2
            name = data[:end].decode("utf-16-le", "replace").strip()
            perm_id = struct.unpack_from("<i", data, end + 2)[0]
            p = next((q for q in perms if q["id"] == perm_id), None)
            if p is None or not name or len(p["friends"]) >= housing.MAX_FRIENDS:
                return
            if name.lower() not in [f.lower() for f in p["friends"]]:
                p["friends"].append(name)
            send(build_system_text(f"{name} added to \"{p['name']}\".", SYSTEM_TEXT_WHITE))
        elif event == housing.PERM_REMOVE_FRIEND:
            perm_id, fid = struct.unpack_from("<ii", data)      # friend id = row + 1 (housing.friend_message)
            p = next((q for q in perms if q["id"] == perm_id), None)
            if p is not None and 0 < fid <= len(p["friends"]):
                p["friends"].pop(fid - 1)
    except (struct.error, IndexError):
        print(f"  bad permission event {event:#x}: {data.hex(' ')}")
        return
    save_housing(db)
    send_plot_window(state, pid)


def construction_window(pid, plot, st):
    c = st["construction"]
    b = next(o for o in plot["buildings"] if o["type"] == c["type"])
    return housing.construction_info(int(pid), b["name"], housing.construction_rows(b["materials"], c["added"],
                                                                                   zone.template_id))


def finish_building(state, db, pid, st, building_type):
    st.update(building=building_type, built=int(time.time()))
    save_housing(db)
    send = state["send"]
    send(zone.zone_event(0x0E, struct.pack("<h", housing.BUILT)))
    send(housing.has_construction(False))
    refresh_plot(state, pid)
    send_plot_window(state, pid)


def handle_housing_event(state, event, data):
    """Plots (housing.py): inspect, buy, build (instantly, or by adding materials), tear down, sell."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE housing event {event:#x}: {data.hex(' ')}")
    notice = lambda code: send(zone.zone_event(0x0E, struct.pack("<h", code)))
    vals = struct.unpack_from(f"<{len(data) // 4}i", data) if len(data) >= 4 else ()
    if event in (housing.CHEST_OPEN, housing.CHEST_CLOSE, housing.CHEST_DEPOSIT, housing.CHEST_WITHDRAW, housing.CHEST_MOVE):
        handle_chest(state, event, vals)
        return
    if event == housing.TRANSFER:
        transfer_plot(state, social.read_name(data).strip())
        return
    if event == housing.BUILDING_DETAILS:
        plot = ARGS.content.plots.get(str(state.get("plot_window")))
        b = next((o for o in (plot or {}).get("buildings", []) if vals and o["type"] == vals[0]), None)
        if b is not None:
            rows = housing.construction_rows(b.get("materials", {}), {}, zone.template_id)
            send(housing.construction_info(int(state["plot_window"]), b["name"], rows, housing.BUILDING_DETAILS))
        return
    if event == housing.HQ_LEADER_RESPONSE:
        hq_leader_response(state, data)
        return
    if event in housing.NPC_WINDOW + (housing.SPAWN_NPC, housing.REMOVE_NPC, housing.GOTO_NPC):
        house_npc_event(state, event, data, vals)
        return
    if event in (housing.PLACE_REQUEST, housing.SPAWN_FIXTURE):
        handle = vals[0] if vals else None
        item = next((i for i in player.items if i[0] == handle), None)
        prefab = ARGS.content.item(item[1]).get("fixture") if item else None
        if event == housing.PLACE_REQUEST:
            state.pop("placing", None)
            if prefab is None:
                return
            if my_house_here(player)[0] is None:
                send(build_system_text("You can only place items when in your house.", SYSTEM_TEXT_ERROR))
                return
            state["placing"] = handle
            send(housing.placement_preview(prefab))
            return
        spawn = housing.parse_spawn_fixture(data)
        if prefab is not None and spawn is not None and state.pop("placing", None) == handle:
            place_fixture(state, item, (spawn[2], spawn[3]))
        return
    if event in (housing.CHEST_MANAGE, housing.CHEST_PERMISSION) and vals:
        # 0x467 carries chest id -1: it is the chest whose Manage Chest window is open.
        cid = vals[0] if event == housing.CHEST_MANAGE or vals[0] != -1 else state.get("managed_chest", -1)
        db, pid, st, f = fixture_by_object(cid)
        if f is None or "items" not in f or st["owner"].lower() != player.name.lower():
            notice(0x1ad)                                # NoPermissionToUseChest
            return
        state["managed_chest"] = cid
        if event == housing.CHEST_PERMISSION and len(data) >= 22:
            _, slot, perm = housing.parse_chest_permission(data)
            if 0 <= slot < len(housing.CHEST_SLOT_NAMES):
                old = (f.get("perms") or {}).get(str(slot))
                perm["friends"] = old.get("friends", []) if isinstance(old, dict) else []
                f.setdefault("perms", {})[str(slot)] = perm
                save_housing(db)
                send(build_system_text(f"{housing.CHEST_SLOT_NAMES[slot]} permission saved.", SYSTEM_TEXT_WHITE))
        for m in housing.chest_permissions(cid, f, st):
            send(m)
        if event == housing.CHEST_MANAGE:
            send(housing.chest_info(cid, f.get("name", f["item"]), f["item"]))
        return
    if event == housing.SEND_TO_OWNER and vals:
        db, pid, st, f = fixture_by_object(vals[0])
        if f is not None:
            send(client_notice(housing.CANT_SEND_NOT_TROPHY
                               if housing.allowed(st, player.name, housing.SEND_TROPHIES, guild_of)
                               else housing.NO_PERMISSION_TO_SEND))
        return
    if event in (housing.PICK_UP, housing.NUDGE, housing.MOVE_TO_ME) and vals:
        db, pid, st, f = fixture_by_object(vals[0])
        need = housing.PICKUP_FIXTURE if event == housing.PICK_UP else housing.MOVE_FIXTURE
        if f is None or not housing.allowed(st, player.name, need, guild_of):
            notice(0x17a)                                # NoPermissionToPickupFixture
            return
        obj = fixture_object(pid, f)
        if event == housing.PICK_UP and f.get("items"):
            notice(0x177)                                # RemoveChestItems
        elif event == housing.PICK_UP:
            st["fixtures"].remove(f)
            save_housing(db)
            broadcast_object(state, obj, close=True)
            give_item(state, f["item"])
            notice(0x178)                                # RemovedFixtureFromBldg
            refresh_fixture_list(pid, st)
        elif event == housing.MOVE_TO_ME:
            here, _ = my_house_here(player)
            if here != pid:
                send(build_system_text("You can only place items when in your house.", SYSTEM_TEXT_ERROR))
                return
            pos = player.live_position or player.spawned_at
            f["loc"] = [pos[0], pos[1], pos[2] - 90.0]
            f["yaw"] = int(getattr(player, "yaw", 0) or 0)
            save_housing(db)
            broadcast_object(state, fixture_object(pid, f))
        elif len(data) >= 32:
            dx, dy, dz = struct.unpack_from("<fff", data, 8)
            dyaw = struct.unpack_from("<i", data, 20)[0]
            f["loc"] = [f["loc"][0] + dx, f["loc"][1] + dy, f["loc"][2] + dz]
            f["yaw"] = (f.get("yaw", 0) + dyaw) & 0xFFFF
            save_housing(db)
            broadcast_object(state, fixture_object(pid, f))
        return
    if event in (housing.PERM_ADD_FRIEND, housing.PERM_REMOVE_FRIEND) and chest_friend_event(state, event, data):
        return
    if event in housing.PERMISSION_EVENTS:
        handle_plot_permission(state, event, data)
        return
    pid = str(vals[1] if event == housing.INSPECT and len(vals) > 1 else vals[0]) if vals else ""
    plot = ARGS.content.plots.get(pid)
    if plot is None:
        notice(0x175)                                    # CantFindPlot
        return
    db = load_housing()
    st = db.get(pid)
    mine = bool(st) and st.get("owner", "").lower() == player.name.lower()
    if event == housing.INSPECT:
        send_plot_window(state, pid)
    elif event == housing.BUY:
        if st:
            notice(0x16b)                                # PlotNotForPurchase
        elif any(v.get("owner", "").lower() == player.name.lower() for v in db.values()):
            notice(housing.ONE_PLOT)
        elif player.coins < plot["cost"]:
            send(client_notice(CANT_PURCHASE_PLOT))
        else:
            player.coins -= plot["cost"]
            send(merchant.coins(player.coins))
            save_character_field(player.name, "coins", player.coins)
            db[pid] = {"owner": player.name, "bought": int(time.time())}
            save_housing(db)
            notice(housing.PURCHASED)
            refresh_plot(state, pid)
            send_plot_window(state, pid)
    elif event == housing.BUILD and len(vals) >= 2:
        b = next((o for o in plot.get("buildings", []) if o["type"] == vals[1]), None)
        if not mine or b is None or st.get("building") or st.get("construction"):
            notice(0x1a1 if not mine else 0x19e)         # NoPermissionToStartConst / BldgExistsForPlot
            return
        if b.get("materials"):
            # Staged construction: the building goes up once its materials are added.
            st["construction"] = {"type": b["type"], "added": {}}
            save_housing(db)
            send(housing.has_construction(True))
            send(construction_window(pid, plot, st))
            send(build_system_text(f"Construction of a {b['name']} has begun. Add the materials to finish it.",
                                   SYSTEM_TEXT_WHITE))
            return
        finish_building(state, db, pid, st, b["type"])
    elif event == housing.VIEW_CONSTRUCTION and st and st.get("construction"):
        send(construction_window(pid, plot, st))
    elif (event == housing.ADD_MATERIAL and len(vals) >= 2 and st and st.get("construction")
          and housing.allowed(st, player.name, housing.MANAGE_CONSTRUCTION, guild_of)):
        c = st["construction"]
        b = next(o for o in plot["buildings"] if o["type"] == c["type"])
        item = next((i for i in player.items if i[0] == vals[1]), None)
        need = b["materials"].get(item[1], 0) - c["added"].get(item[1], 0) if item else 0
        if item is None or need <= 0:
            send(build_system_text("That material isn't needed for this building.", SYSTEM_TEXT_ERROR))
            return
        n = min(need, item[3])
        take_items(state, item[1], n)
        c["added"][item[1]] = c["added"].get(item[1], 0) + n
        save_housing(db)
        send(build_system_text(f"You add {n} {item[1]} to the construction.", SYSTEM_TEXT_WHITE))
        send(construction_window(pid, plot, st))
    elif event == housing.COMPLETE_CONSTRUCTION and mine and st.get("construction"):
        c = st["construction"]
        b = next(o for o in plot["buildings"] if o["type"] == c["type"])
        if not housing.construction_done(housing.construction_rows(b["materials"], c["added"])):
            send(client_notice(SITE_MISSING_MATERIALS))
            return
        st.pop("construction")
        send(housing.close_construction())
        finish_building(state, db, pid, st, c["type"])
    elif event == housing.ABANDON_CONSTRUCTION and mine and st.get("construction"):
        c = st.pop("construction")
        save_housing(db)
        for name, n in c["added"].items():
            give_item(state, name, n)                    # the materials come back
        send(housing.close_construction())
        send(housing.has_construction(False))
        send(build_system_text("You abandon the construction.", SYSTEM_TEXT_WHITE))
        send_plot_window(state, pid)
    elif event == housing.UPKEEP_DEPOSIT and housing.allowed(st, player.name, housing.PAY_UPKEEP, guild_of) and len(vals) >= 2:
        amount = vals[1]
        if amount <= 0 or player.coins < amount:
            send(build_system_text("You don't have that much coin.", SYSTEM_TEXT_ERROR))
            return
        player.coins -= amount
        send(merchant.coins(player.coins))
        save_character_field(player.name, "coins", player.coins)
        st["upkeep_balance"] = st.get("upkeep_balance", 0) + amount
        save_housing(db)
        send(housing.upkeep_balance(st["upkeep_balance"]))
        notice(0x17c)                                    # DepositSuccess
    elif event == housing.GUILD_USABLE and mine and st.get("building"):
        st["guild_usable"] = not st.get("guild_usable", False)
        save_housing(db)
        send(housing.guild_usable(st["guild_usable"]))
        send(client_notice(housing.NOW_GUILD_USABLE if st["guild_usable"] else housing.NO_LONGER_GUILD_USABLE))
    elif event == housing.GUILD_HQ and st and st.get("building"):
        guild_hq_request(state, db, pid, plot, st)
    elif event == housing.TEAR_DOWN and mine and st.get("building"):
        st.pop("building", None)
        st.pop("built", None)
        save_housing(db)
        notice(housing.REMOVED)
        refresh_plot(state, pid)
        send_plot_window(state, pid)
    elif event == housing.SELL and mine:
        if st.get("building"):
            notice(housing.SELL_BUILDINGS_FIRST)
            return
        del db[pid]
        save_housing(db)
        player.coins += plot["cost"] // 2
        send(merchant.coins(player.coins))
        save_character_field(player.name, "coins", player.coins)
        notice(housing.SOLD)
        refresh_plot(state, pid)


HQ_LEADER_RANGE = 2000.0           # how close the guild leader must be to the plot (server choice)


def guild_hq_request(state, db, pid, plot, st):
    """0x47b from the plot window: the owner asks for guild HQ (the leader confirms), or the
    guild leader clears it."""
    player, send = state["player"], state["send"]
    guilds = load_guilds()
    mine = guild_of(player.name, guilds)
    if st.get("hq_guild") is not None:
        if not housing.is_hq_leader(st, player.name, mine):
            send(build_system_text("Only the guild leader can clear the Guild Headquarters.", SYSTEM_TEXT_ERROR))
            return
        set_guild_hq(db, pid, st, None, guilds)
        return
    if st.get("owner", "").lower() != player.name.lower():
        return
    if mine is None:
        send(client_notice(housing.NO_GUILD))
        return
    if any(v.get("hq_guild") == mine["id"] for v in db.values()):
        send(build_system_text("Only one plot can be flagged as the Guild Headquarters.", SYSTEM_TEXT_ERROR))
        return
    leader = next((m for m, r in mine["members"].items() if r == guild.LEADER), None)
    ls = ONLINE.get((leader or "").lower())
    pos = ls and (ls.get("position") or ls["player"].live_position or ls["player"].spawned_at)
    if (not ls or not ls.get("player") or pos is None or ls["player"].level != plot["chunk"]
            or math.hypot(pos[0] - plot["loc"][0], pos[1] - plot["loc"][1]) > HQ_LEADER_RANGE):
        send(build_system_text("The Guild Leader must be present at the plot to confirm the action.",
                               SYSTEM_TEXT_ERROR))
        return
    ls["hq_offer"] = (int(pid), mine["id"])
    ls["send"](housing.hq_leader_confirm(int(pid), mine["id"], st["owner"]))


def hq_leader_response(state, data):
    """The guild leader's Accept / Decline of a plot as the guild's headquarters (0x47c)."""
    player, send = state["player"], state["send"]
    r = housing.parse_hq_response(data)
    offer = state.pop("hq_offer", None)
    if r is None or offer is None or (r[0], r[1]) != offer:
        return
    db = load_housing()
    pid = str(r[0])
    st = db.get(pid)
    guilds = load_guilds()
    g = guilds.get(str(r[1]))
    owner = ONLINE.get((st or {}).get("owner", "").lower())
    if not r[2]:
        if owner:
            owner["send"](build_system_text(f"{player.name} declined to make your plot the Guild Headquarters.",
                                            SYSTEM_TEXT_ERROR))
        return
    if (st is None or g is None or guild_of(player.name, guilds) is not g or g["members"].get(player.name) != guild.LEADER
            or guild_of(st.get("owner", ""), guilds) is not g
            or any(v.get("hq_guild") == g["id"] for v in db.values())):
        return
    set_guild_hq(db, pid, st, g["id"], guilds)


def set_guild_hq(db, pid, st, guild_id, guilds):
    """Make plot pid guild guild_id's headquarters (None clears it). Either way the plot's
    permissions are replaced; every online guild member is told."""
    old = st.get("hq_guild")
    if guild_id is None:
        st.pop("hq_guild", None)
        st["permissions"] = []
    else:
        st["hq_guild"] = guild_id
        st["permissions"] = [housing.hq_guild_permission()]
    save_housing(db)
    g = guilds.get(str(guild_id if guild_id is not None else old))
    for name in (g or {}).get("members", {}):
        s = ONLINE.get(name.lower())
        if s and s.get("player"):
            s["send"](client_notice(housing.HQ_ADDED if guild_id is not None else housing.HQ_REMOVED))
            s["send"](housing.hq_state(guild_id or 0, guild_id is not None))
            if s.get("plot_window") == pid:
                send_plot_window(s, pid)


def owned_titles(player):
    t = ARGS.content.titles
    ids = [int(k) for k, v in t.items() if v.get("start")] + list(getattr(player, "titles", []))
    return [(i, t[str(i)]["name"], bool(t[str(i)].get("suffix"))) for i in dict.fromkeys(ids) if str(i) in t]


def title_props(player):
    t = ARGS.content.titles
    pre = t.get(str(getattr(player, "title_prefix", -1)), {}).get("name", "")
    post = t.get(str(getattr(player, "title_suffix", -1)), {}).get("name", "")
    if not getattr(player, "show_title", True):
        pre = post = ""
    return {"m_PlayerDisplayTitlePre": pre, "m_PlayerDisplayTitlePost": post}


def show_titles(state):
    player = state["player"]
    values = title_props(player)
    player.title_values = values               # also in the pawn's spawn properties
    if "ue" not in state:
        return
    state["send"](zone.player_pawn_update(state, ARGS, values))
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.remote_player_update(s, ARGS, player, values), exclude=state)


# /toggleeppearancegear (the equipment window's appearance-gear switch): 0x115, no payload. The
# server flips the setting and answers 0x116 {bool8 shown} (FUN_004f9ea0: inventory manager
# +0x6c0, then gamevars bAppGearVisible / bAppGearInvisible). Saved; resent at login.
APP_GEAR_TOGGLE, APP_GEAR_STATE = 0x115, 0x116


def app_gear_toggle(state):
    player = state["player"]
    player.app_gear_visible = not getattr(player, "app_gear_visible", False)
    save_character_field(player.name, "app_gear_visible", player.app_gear_visible)
    state["send"](zone.zone_event(APP_GEAR_STATE, struct.pack("<B", int(player.app_gear_visible))))


# Wounds: 0x44b MsgWoundsUpdate {5 x u8 severity} (FUN_005ef110, verified live 2026-10-15) sets
# nWoundsHead / Torso / LeftArm / RightArm / Leg and prints the changes ("Your head was just
# wounded! The severity of the wound is up to Minor", "Some of your wounds have been cured!").
WOUNDS = 0x44B
WOUND_HEAL_SECONDS = 20              # one level off the worst wound per 20 s of resting out of combat


# In-game builder (dev commands): !spawn <mob key> [wander] appends {mob, x, y, yaw, respawn,
# wander} at the player's feet to content/spawns/<chunk>.json and opens the NPC for everyone in
# the chunk at once (entity id SPAWN_EID_BASE + its index, as after a restart). !despawn removes
# the targeted spawned NPC's entry (matched by mob and position) and its actor.
def spawn_file(args, level):
    return os.path.join(args.content.directory, "spawns", level + ".json")


def write_spawn_file(path, doc):
    old = open(path, encoding="utf-8", newline="").read() if os.path.exists(path) else ""
    nl = "\r\n" if "\r\n" in old else "\n"
    text = json.dumps(doc, indent=2, ensure_ascii=False) + ("\n" if old.endswith(("\n", "\r\n")) else "")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", nl))
    os.replace(tmp, path)
    SPAWN_STAMPS[os.path.basename(path)[:-5]] = os.path.getmtime(path)   # the world is already in step


def build_spawn(state, args, key, wander=0):
    player, send = state["player"], state["send"]
    w = state.get("world")
    template = args.content.mobs.get(key)
    pos = state.get("position") or player.live_position
    if template is None:
        send(build_system_text(f"No mob template {key!r} in mobs.json.", SYSTEM_TEXT_ERROR))
        return
    if w is None or pos is None:
        return
    path = spawn_file(args, player.level)
    old_text = read_text(path)
    doc = json.loads(old_text) if old_text else {"spawns": []}
    entry = {"mob": key, "x": int(pos[0]), "y": int(pos[1]), "yaw": int(getattr(player, "yaw", 0)) & 0xFFFF,
             "respawn": 60}
    if wander:
        entry["wander"] = int(wander)
    doc.setdefault("spawns", []).append(entry)
    write_spawn_file(path, doc)
    n = len(doc["spawns"]) - 1
    spawn = dict(entry, z=args.content.ground_z(player.level, entry["x"], entry["y"], args.client_dir))
    npc = zone.npc_from_template(w, args, zone.SPAWN_EID_BASE + n, spawn, template, n)
    w.npcs[npc.entity_id] = npc
    w.broadcast(lambda s, npc=npc: zone.open_npc(s, args, npc))
    send(build_system_text(f"Spawned {template.get('name', key)} (spawn {n}) and saved it to {os.path.basename(path)}.",
                           SYSTEM_TEXT_WHITE))
    if zone.npc_blocked(player.level, entry["x"], entry["y"], spawn["z"] + 50):
        send(build_system_text("Warning: that spot is inside an obstacle (rock or wall); the mob may get stuck. "
                               "!undo takes it back.", SYSTEM_TEXT_ERROR))

    def undo(npc=npc):
        w.npcs.pop(npc.entity_id, None)
        w.broadcast(lambda s, eid=npc.entity_id: zone.close_actor(s, eid))
    push_undo(state, path, old_text, undo, f"spawn of {template.get('name', key)}")
    print(f"  builder: {player.name} spawned {key} at {entry['x']}, {entry['y']} (spawn {n})")
    audit("builder_spawn", by=player.name, chunk=player.level, mob=key, x=entry["x"], y=entry["y"])


BUILD_UNDO_DEPTH = 20


def read_text(path):
    return open(path, encoding="utf-8", newline="").read() if os.path.exists(path) else ""


def push_undo(state, path, old_text, live_undo, label):
    """Remember how to take back one builder change: the file's previous text and a function
    that reverses the live change (!undo)."""
    stack = state.setdefault("build_undo", [])
    stack.append((path, old_text, live_undo, label))
    del stack[:-BUILD_UNDO_DEPTH]


def build_undo(state):
    stack = state.get("build_undo") or []
    if not stack:
        state["send"](build_system_text("Nothing to undo.", SYSTEM_TEXT_ERROR))
        return
    path, old_text, live_undo, label = stack.pop()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(old_text)
    os.replace(tmp, path)
    SPAWN_STAMPS[os.path.basename(path)[:-5]] = os.path.getmtime(path)
    live_undo()
    state["send"](build_system_text(f"Undid the {label}.", SYSTEM_TEXT_WHITE))
    print(f"  builder: {state['player'].name} undid the {label}")
    audit("builder_undo", by=state["player"].name, undid=label)


def targeted_spawn(state, args):
    """(npc, spawn file path, parsed file, entry index) for the targeted spawned NPC, or None
    (after telling the player why). Entries are matched by mob key and spawn position."""
    player, send = state["player"], state["send"]
    npc = player.npcs.get(player.target) if player.target else None
    if state.get("world") is None or npc is None or not getattr(npc, "template_id", None) or \
            not zone.SPAWN_EID_BASE <= npc.entity_id < zone.SPAWN_EID_BASE + 0x100000:
        send(build_system_text("Target a spawned NPC first.", SYSTEM_TEXT_ERROR))
        return None
    path = spawn_file(args, player.level)
    doc = json.load(open(path, encoding="utf-8"))
    home = npc.home or npc.location
    match = next((i for i, s in enumerate(doc.get("spawns", []))
                  if s.get("mob") == npc.template_id and abs(s["x"] - home[0]) < 2 and abs(s["y"] - home[1]) < 2), None)
    if match is None:
        send(build_system_text(f"{npc.name} is not in {os.path.basename(path)}.", SYSTEM_TEXT_ERROR))
        return None
    return npc, path, doc, match


def build_edit(state, args, what, value=None):
    """!wander <radius>, !respawn <seconds>, !path add / !path clear on the targeted spawn:
    saved to the spawn file and applied to the live NPC."""
    found = targeted_spawn(state, args)
    if found is None:
        return
    npc, path, doc, i = found
    entry, send = doc["spawns"][i], state["send"]
    old_text = read_text(path)
    before = (npc.wander, npc.respawn, list(npc.path))
    if what == "wander":
        entry["wander"] = int(value)
        npc.wander = float(value)
        text = f"{npc.name} now wanders {int(value)} units."
    elif what == "respawn":
        entry["respawn"] = int(value)
        npc.respawn = int(value)
        text = f"{npc.name} now respawns after {int(value)} seconds."
    elif what == "path add":
        pos = state.get("position") or state["player"].live_position
        entry.setdefault("path", []).append([int(pos[0]), int(pos[1])])
        npc.path = [tuple(p[:2]) for p in entry["path"]]
        text = f"Added waypoint {len(entry['path'])} ({int(pos[0])}, {int(pos[1])}) to {npc.name}'s patrol."
    elif what == "path clear":
        entry.pop("path", None)
        npc.path = []
        text = f"Cleared {npc.name}'s patrol."
    else:
        return
    write_spawn_file(path, doc)
    send(build_system_text(text + f" (spawn {i}, saved)", SYSTEM_TEXT_WHITE))
    audit("builder_edit", by=state["player"].name, chunk=state["player"].level, mob=npc.template_id, change=what, value=value)

    def undo(npc=npc, before=before):
        npc.wander, npc.respawn, npc.path = before
    push_undo(state, path, old_text, undo, f"{what} on {npc.name}")


def build_despawn(state, args):
    player, send = state["player"], state["send"]
    w = state.get("world")
    found = targeted_spawn(state, args)
    if found is None:
        return
    npc, path, doc, match = found
    old_text = read_text(path)
    removed = doc["spawns"].pop(match)
    write_spawn_file(path, doc)
    del w.npcs[npc.entity_id]
    w.broadcast(lambda s, eid=npc.entity_id: zone.close_actor(s, eid))
    send(build_system_text(f"Removed {npc.name} (spawn {match}) from {os.path.basename(path)}.", SYSTEM_TEXT_WHITE))

    def undo(eid=npc.entity_id, entry=removed, n=match, level=player.level):
        template = args.content.mobs.get(entry["mob"])
        if template is None:
            return
        spawn = dict(entry, z=entry.get("z") or args.content.ground_z(level, entry["x"], entry["y"], args.client_dir))
        back = zone.npc_from_template(w, args, eid, spawn, template, n)
        w.npcs[eid] = back
        w.broadcast(lambda s, back=back: zone.open_npc(s, args, back))
    push_undo(state, path, old_text, undo, f"removal of {npc.name}")
    print(f"  builder: {player.name} removed {npc.template_id} spawn {match}")
    audit("builder_despawn", by=player.name, chunk=player.level, mob=npc.template_id, x=removed["x"], y=removed["y"])


# Builder commands without --dev-commands: characters with access_level >= BUILDER_LEVEL
# (`python storage.py set <character> access_level N`, docs/HOSTING.md) may use the in-game
# builder and the lookups it needs on any server; every other ! command still needs
# --dev-commands.
BUILDER_COMMANDS = {"spawn", "despawn", "wander", "respawn", "path", "undo", "mobs", "reload", "npclist", "tp", "target"}
BUILDER_LEVEL = 1


def dev_allowed(args, player, text):
    if getattr(args, "dev_commands", False):
        return True
    word = text[1:].split(" ", 1)[0].lower()
    return word in BUILDER_COMMANDS and getattr(player, "access_level", 0) >= BUILDER_LEVEL


def wounds_message(player):
    return zone.zone_event(WOUNDS, bytes(getattr(player, "wounds", None) or [0] * 5))


def wounds_login(state):
    if any(getattr(state["player"], "wounds", None) or []):
        state["send"](wounds_message(state["player"]))


def set_wounds(state, wounds):
    player = state["player"]
    player.wounds = list(wounds)
    player.wounds_dirty = True
    wounds_tick(state, time.time())


def wounds_tick(state, now):
    player = state["player"]
    w = getattr(player, "wounds", None)
    if not w:
        return
    if any(w) and getattr(player, "resting", False) and not combat.in_combat(player) and player.health > 0:
        due = getattr(player, "wound_heal_at", 0)
        if not due:
            player.wound_heal_at = now + WOUND_HEAL_SECONDS
        elif now >= due:
            worst = max(range(5), key=lambda i: w[i])
            w[worst] -= 1
            player.wounds_dirty = True
            player.wound_heal_at = now + WOUND_HEAL_SECONDS
    else:
        player.wound_heal_at = 0
    if getattr(player, "wounds_dirty", False):
        player.wounds_dirty = False
        state["send"](wounds_message(player))
        save_character_field(player.name, "wounds", list(w))


def combat_sheet_login(state):
    """The character sheet's dodge / parry / block lines (combat.combat_info)."""
    state["send"](combat.combat_info(state["player"]))


def title_login(state):
    player = state["player"]
    state["send"](titles.title_list(owned_titles(player), getattr(player, "title_prefix", -1),
                                    getattr(player, "title_suffix", -1), getattr(player, "show_title", True)))
    if getattr(player, "app_gear_visible", False):
        state["send"](zone.zone_event(APP_GEAR_STATE, struct.pack("<B", 1)))
    if getattr(player, "title_prefix", -1) != -1 or getattr(player, "title_suffix", -1) != -1:
        show_titles(state)


def grant_title(state, tid):
    player = state["player"]
    t = ARGS.content.titles.get(str(tid))
    if t is None or any(i == tid for i, _n, _s in owned_titles(player)):
        return
    player.titles = list(getattr(player, "titles", [])) + [tid]
    save_character_field(player.name, "titles", player.titles)
    state["send"](titles.new_title(tid, t["name"], bool(t.get("suffix"))))


def handle_title_event(state, event, data):
    """/titleset (0x185), remove (0x186), /togglemytitle (0x187). Idempotent: 0x185/0x186
    also come back as echoes of the server's 0x363/0x362."""
    player = state["player"]
    if event == titles.SET and len(data) >= 4:
        tid = struct.unpack_from("<i", data)[0]
        own = {i: s for i, _n, s in owned_titles(player)}
        if tid not in own:
            return
        field = "title_suffix" if own[tid] else "title_prefix"
        if getattr(player, field, -1) == tid:
            return
        setattr(player, field, tid)
        save_character_field(player.name, field, tid)
    elif event == titles.REMOVE and data:
        field = "title_suffix" if data[0] else "title_prefix"
        setattr(player, field, -1)
        save_character_field(player.name, field, -1)
    elif event == titles.TOGGLE:
        player.show_title = not getattr(player, "show_title", True)
        save_character_field(player.name, "show_title", player.show_title)
    show_titles(state)


DUEL_DAMAGE = (6, 12)


def online_state(player):
    return ONLINE.get(player.name.lower())


def handle_duel_event(state, event, data):
    """Duels (duel.py): challenge the defensive target, countdown, fight to 1 HP."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE duel event {event:#x}: {data.hex(' ')}")
    notice = lambda code: send(zone.zone_event(0x0E, struct.pack("<h", code)))
    if event == duel.DEFENSIVE_TARGET:
        state["def_target"] = struct.unpack_from("<Q", data)[0] if len(data) >= 8 else 0
        return
    if event == duel.CHALLENGE:
        if getattr(player, "duel_opponent", None) is not None:
            end_duel(online_state(player.duel_opponent), state)        # forfeit
            return
        pending = state.pop("duel_challenge", None)
        if pending is not None:                          # /duelcancel
            target = ONLINE.get(pending["to"].lower())
            if target is not None:
                target.pop("duel_from", None)
                target["send"](build_system_text(f"{player.name} has cancelled the duel challenge.",
                                                 SYSTEM_TEXT_WHITE))
            send(build_system_text("You cancel your duel challenge.", SYSTEM_TEXT_WHITE))
            return
        w = state.get("world")
        tid = state.get("def_target") or player.target
        other = w.members.get(tid) if w is not None and tid else None
        if other is None or other is state:
            notice(0xB5 if other is None else 0xB6)       # need a defensive target / can't duel yourself
            return
        o = other["player"]
        if refused_by_ignore(state, o):
            return
        if getattr(o, "duel_opponent", None) is not None or other.get("duel_from"):
            send(duel.busy())
            return
        state["duel_challenge"] = {"to": o.name, "until": time.time() + duel.CHALLENGE_SECONDS}
        other["duel_from"] = {"from": player.name, "until": time.time() + duel.CHALLENGE_SECONDS}
        send(duel.challenge(o.name, False))
        other["send"](duel.challenge(player.name, True))
    elif event == duel.ANSWER and len(data) >= 4:
        offer = state.pop("duel_from", None)
        if offer is None:
            notice(0xB7)                                  # no pending duel
            return
        cs = ONLINE.get(offer["from"].lower())
        if cs is None or cs.get("duel_challenge", {}).get("to", "").lower() != player.name.lower():
            return
        cs.pop("duel_challenge", None)
        if struct.unpack_from("<i", data)[0] != 0 or time.time() > offer["until"]:
            cs["send"](duel.declined() if time.time() <= offer["until"] else duel.timed_out())
            return
        a, b = cs["player"], player
        for s, opp in ((cs, b), (state, a)):
            s["send"](duel.countdown(opp.name))
        DUELS.append({"a": cs, "b": state, "starts": time.time() + duel.COUNTDOWN})


DUELS = []


def duel_tick(now):
    # Unanswered challenges time out (0x403 to the challenger: the client prints the timeout).
    for s in list(ONLINE.values()):
        c = s.get("duel_challenge")
        if c is not None and now > c["until"]:
            s.pop("duel_challenge", None)
            s["send"](duel.timed_out())
            target = ONLINE.get(c["to"].lower())
            if target is not None and target.get("duel_from", {}).get("from", "").lower() == s["player"].name.lower():
                target.pop("duel_from", None)
    for d in list(DUELS):
        if now >= d["starts"]:
            DUELS.remove(d)
            a, b = d["a"], d["b"]
            if a.get("player") is None or b.get("player") is None:
                continue
            pa, pb = a["player"], b["player"]
            pa.duel_opponent, pb.duel_opponent = pb, pa
            for s, me, opp in ((a, pa, pb), (b, pb, pa)):
                me.target = opp.char_id
                s["send"](duel.start(opp.char_id))
                pet = getattr(opp, "pet", None)
                s["send"](duel.attackable([pet.entity_id] if pet is not None else []))
                s["send"](combat.targets(duel.Target(opp)))


def duel_strike(state, player, opp, ability="", damage=DUEL_DAMAGE):
    """A swing (or an ability) at the duel opponent; at 1 HP the duel is over."""
    os_ = online_state(opp)
    if os_ is None:
        end_duel(state, None)
        return
    dmg = random.randint(*damage)
    opp.health = max(1, opp.health - dmg)
    player.last_combat = opp.last_combat = time.time()
    for s in (state, os_):
        s["send"](effects.combat_text(player.char_id, opp.char_id, ability, dmg, kind=1 if ability else 0,
                                      dmg_type=combat.HITS))
    os_["send"](zone.health_update(opp))
    state["send"](combat.targets(duel.Target(opp)))
    if opp.health <= 1:
        end_duel(state, os_)


def end_duel(winner, loser):
    """winner/loser: zone states (either may be None if they left)."""
    for s, won in ((winner, True), (loser, False)):
        if s is None or s.get("player") is None:
            continue
        p = s["player"]
        p.duel_opponent = None
        p.auto_attack = False
        s["send"](duel.result(won))
        s["send"](duel.attackable([]))
        for m in combat.auto_attack_state(False):
            s["send"](m)


def summon_pet(state, args, spec):
    """A pet item (items.json "pet": {name, race, model, level, health, damage}): an NPC that
    follows its owner and fights its target; one pet at a time."""
    player, send = state["player"], state["send"]
    w = state.get("world")
    if w is None:
        return
    if getattr(player, "pet", None) is not None:
        dismiss_pet(state)
    pos = player.live_position or player.spawned_at
    eid = pets.EID_BASE + (player.char_id & 0xFFFFF)
    npc = combat.Npc(eid, spec["name"], None, f"{content.PAWN_PACKAGE}.SGONPCPawn",
                     max_health=spec.get("health", 300),
                     location=(pos[0] + 100.0, pos[1], pos[2]))
    npc.race = spec["race"]
    npc.level = spec.get("level", 1)
    npc.damage = tuple(spec.get("damage", (5, 10)))
    npc.template_id = "pet"
    npc.pet_owner = player
    npc.pet_mode = "follow"
    npc.pet_target = None
    npc.ground_z = lambda x, y, lvl=w.level: args.content.ground_z(lvl, x, y, args.client_dir)
    npc.blocked = lambda x, y, z, lvl=w.level: npc_blocked(lvl, x, y, z)
    npc.props = {"m_GameplayLevel": npc.level, "m_iModelNum": spec.get("model", 1),
                 "m_OwnerEntityIDLowInt": player.char_id & 0xFFFFFFFF,
                 "m_OwnerEntityIDHighInt": player.char_id >> 32, "m_bIsAggro": 0}
    w.npcs[eid] = npc
    player.pet = npc
    w.broadcast(lambda s, npc=npc: zone.open_npc(s, args, npc))
    send(pets.new(eid, npc.name))
    send(pets.health(npc))
    npc.pet_abilities = {}
    for n, a in enumerate(spec.get("abilities", [])):
        aid, msg = pets.ability(n, a)
        npc.pet_abilities[aid] = dict(a, ready=0.0, auto=bool(a.get("default")))
        send(msg)
        if a.get("default"):
            send(pets.default_attack(aid))
    send(build_system_text(f"{npc.name} answers your call.", SYSTEM_TEXT_WHITE))


MINION_LIMIT = 4


def summon_minions(state, args, spec):
    """A minion item (items.json "minions": {name, race, model, level, health, damage, count,
    seconds}): timed helpers listed in the Minions window that follow and fight like a pet."""
    player, send = state["player"], state["send"]
    w = state.get("world")
    if w is None:
        return
    minions = player.__dict__.setdefault("minions", [])
    pos = player.live_position or player.spawned_at
    now = time.time()
    for _ in range(spec.get("count", 1)):
        if len(minions) >= MINION_LIMIT:
            send(build_system_text("You can't control any more minions.", SYSTEM_TEXT_ERROR))
            break
        slot = next(i for i in range(MINION_LIMIT) if all(m.minion_slot != i for m in minions))
        eid = pets.MINION_EID_BASE + ((player.char_id & 0xFFFF) << 3) + slot
        npc = combat.Npc(eid, spec["name"], None, f"{content.PAWN_PACKAGE}.SGONPCPawn",
                         max_health=spec.get("health", 150),
                         location=(pos[0] + 80.0 * (slot + 1), pos[1] + 60.0, pos[2]))
        npc.race = spec["race"]
        npc.level = spec.get("level", 1)
        npc.damage = tuple(spec.get("damage", (3, 6)))
        npc.template_id = "minion"
        npc.pet_owner, npc.pet_mode, npc.pet_target = player, "follow", None
        npc.minion_slot, npc.expires = slot, now + spec.get("seconds", 60)
        # Minions have no ability bar: their specials ("abilities": [{name, damage, chance}])
        # fire by themselves on a swing.
        npc.auto_abilities = list(spec.get("abilities", []))
        npc.ground_z = lambda x, y, lvl=w.level: args.content.ground_z(lvl, x, y, args.client_dir)
        npc.blocked = lambda x, y, z, lvl=w.level: npc_blocked(lvl, x, y, z)
        npc.props = {"m_GameplayLevel": npc.level, "m_iModelNum": spec.get("model", 0),
                     "m_OwnerEntityIDLowInt": player.char_id & 0xFFFFFFFF,
                     "m_OwnerEntityIDHighInt": player.char_id >> 32, "m_bIsAggro": 0}
        w.npcs[eid] = npc
        minions.append(npc)
        w.broadcast(lambda s, npc=npc: zone.open_npc(s, args, npc))
        send(pets.minion_new(eid, npc.name, spec.get("seconds", 60)))
        send(pets.minion_health(npc))
    send(build_system_text(f"{spec['name']} rises to serve you.", SYSTEM_TEXT_WHITE))


def dismiss_minion(state, npc, text=None):
    player = state["player"]
    if npc in getattr(player, "minions", []):
        player.minions.remove(npc)
    w = state.get("world")
    if w is not None and npc.entity_id in w.npcs:
        del w.npcs[npc.entity_id]
        w.broadcast(lambda s: zone.close_actor(s, npc.entity_id))
    state["send"](pets.minion_gone(npc.entity_id))
    if text:
        state["send"](build_system_text(text, SYSTEM_TEXT_WHITE))


def handle_minion_event(state, event):
    """/minions attack | backoff | follow | resumebehavior | dismiss: every minion."""
    player, send = state["player"], state["send"]
    minions = list(getattr(player, "minions", []))
    if not minions:
        return send(build_system_text("You have no minions.", SYSTEM_TEXT_ERROR))
    if event == pets.MINION_DISMISS:
        for m in minions:
            dismiss_minion(state, m)
        return send(build_system_text("Your minions return to dust.", SYSTEM_TEXT_WHITE))
    target = player.npcs.get(player.target) if player.target else None
    if event == pets.MINION_ATTACK and (target is None or not target.alive or target.service()):
        return send(build_system_text("Your minions have no target.", SYSTEM_TEXT_ERROR))
    for m in minions:
        if event == pets.MINION_ATTACK:
            m.pet_mode, m.pet_target = "attack", target
        else:
            m.pet_mode, m.pet_target = "follow", None
    send(build_system_text("Your minions obey.", SYSTEM_TEXT_WHITE))


def pet_use_ability(state, aid):
    """0x88: the pet uses one of its abilities on its target (or the owner's)."""
    player, send = state["player"], state["send"]
    npc = getattr(player, "pet", None)
    a = getattr(npc, "pet_abilities", {}).get(aid) if npc else None
    if a is None:
        return
    now = time.time()
    if now < a["ready"]:
        send(build_system_text(f"{a['name']} is not ready yet.", SYSTEM_TEXT_ERROR))
        return
    t = npc.pet_target if npc.pet_target is not None and npc.pet_target.alive else \
        player.npcs.get(player.target) if player.target else None
    if t is None or not t.alive or t.service():
        send(build_system_text(f"{npc.name} has no target for {a['name']}.", SYSTEM_TEXT_ERROR))
        return
    d = math.hypot(t.location[0] - npc.location[0], t.location[1] - npc.location[1])
    if d > PET_ABILITY_CHASE:
        send(build_system_text(f"{npc.name} is too far away from {t.name}.", SYSTEM_TEXT_ERROR))
        return
    npc.pet_mode, npc.pet_target = "attack", t
    if d > combat.MELEE_RANGE + 200:
        # Run in and use it on arrival (pet_tick).
        npc.queued_ability = aid
        send(build_system_text(f"{npc.name} moves in to use {a['name']}.", SYSTEM_TEXT_WHITE))
        return
    pet_fire_ability(state, npc, aid, t, now)


PET_ABILITY_CHASE = 3000.0


def pet_fire_ability(state, npc, aid, t, now):
    player, send = state["player"], state["send"]
    a = npc.pet_abilities[aid]
    npc.queued_ability = None
    a["ready"] = now + float(a.get("refresh", 10))
    send(pets.ability_timer(aid, a.get("refresh", 10)))
    send(build_system_text(f"{npc.name} uses {a['name']}!", SYSTEM_TEXT_COMBAT))
    lines, _ = combat.strike(player, t, f"Your {npc.name}'s {a['name']}", None, *a.get("damage", (10, 20)))
    for m in combat_results(state, ARGS, player, lines, t, True, player.auto_attack):
        send(m)


def dismiss_pet(state, dust=True):
    player = state["player"]
    npc = getattr(player, "pet", None)
    if npc is None:
        return
    player.pet = None
    w = state.get("world")
    if w is not None and npc.entity_id in w.npcs:
        del w.npcs[npc.entity_id]
        w.broadcast(lambda s: zone.close_actor(s, npc.entity_id))
    if dust:
        state["send"](pets.reply(pets.DUST))
    state["send"](pets.gone())


def handle_pet_event(state, event, data):
    player, send = state["player"], state["send"]
    npc = getattr(player, "pet", None)
    print(f"  >>> ZONE pet event {event:#x}: {data.hex(' ')}")
    if npc is None:
        send(pets.reply(pets.NO_PET))
        return
    if event == pets.DISMISS:
        dismiss_pet(state)
        return
    if event == pets.RENAME:
        name = data.decode("utf-16-le", "replace").split("\0")[0].strip()[:24]
        if name:
            npc.name = name
            send(pets.renamed(name))
        return
    if event in (pets.ATTACK, pets.ASSIST, pets.ASSIST_ALWAYS):
        target = player.npcs.get(player.target) if player.target else None
        if target is None or not target.alive or target.service():
            send(pets.reply(pets.CANT))
            return
        npc.pet_mode, npc.pet_target = "attack", target
    elif event == pets.STAY:
        npc.pet_mode, npc.pet_target = "stay", None
    elif event in (pets.FOLLOW, pets.BACKOFF, pets.GUARD, pets.DEFEND):
        npc.pet_mode, npc.pet_target = "follow", None
    send(pets.reply(pets.YES))


def pet_tick(state, args, now, dt):
    """Move the pet and the minions (follow the owner, or close in on a target) and let them hit."""
    player = state.get("player")
    if player is None or state.get("world") is None:
        return
    if getattr(player, "pet", None) is not None:
        companion_tick(state, args, player.pet, now, dt, pets.health, lambda: dismiss_pet(state, dust=False))
    for n, m in enumerate(list(getattr(player, "minions", []))):
        if now >= m.expires:
            dismiss_minion(state, m, f"{m.name} returns to dust.")
            continue
        companion_tick(state, args, m, now, dt, pets.minion_health, lambda m=m: dismiss_minion(state, m),
                       stop=pets.FOLLOW_DISTANCE + 80 * n)


def companion_tick(state, args, npc, now, dt, health_msg, on_death, stop=pets.FOLLOW_DISTANCE):
    player, w = state["player"], state["world"]
    goal = None
    if npc.pet_mode == "attack":
        t = npc.pet_target
        if t is None or not t.alive:
            npc.pet_mode, npc.pet_target = "follow", None
        else:
            goal, stop = t.location, combat.MELEE_RANGE
            if (getattr(npc, "queued_ability", None) is not None and math.hypot(
                    t.location[0] - npc.location[0], t.location[1] - npc.location[1]) <= combat.MELEE_RANGE + 200):
                pet_fire_ability(state, npc, npc.queued_ability, t, now)
                if not t.alive:
                    return
            auto = next((aid for aid, a in getattr(npc, "pet_abilities", {}).items()
                         if a.get("auto") and now >= a["ready"]), None)
            if auto is not None and math.hypot(t.location[0] - npc.location[0],
                                               t.location[1] - npc.location[1]) <= combat.MELEE_RANGE + 200:
                pet_fire_ability(state, npc, auto, t, now)      # the default attack, when ready
                if not t.alive:
                    return
            if (math.hypot(t.location[0] - npc.location[0], t.location[1] - npc.location[1])
                    <= combat.MELEE_RANGE + 40 and now >= npc.next_attack):
                npc.next_attack = now + pets.ATTACK_SECONDS
                special = next((a for a in getattr(npc, "auto_abilities", [])
                                if random.random() < a.get("chance", 0.25)), None)
                if special is not None:
                    print(f"  {npc.name} uses {special['name']} on {t.name}")
                    lines, _ = combat.strike(player, t, f"Your {npc.name}'s {special['name']}", None,
                                             *special.get("damage", npc.damage))
                else:
                    lines, _ = combat.strike(player, t, f"Your {npc.name}", None, *npc.damage)
                for m in combat_results(state, args, player, lines, t, True, player.auto_attack):
                    state["send"](m)
                if t.alive:
                    # The enemy turns on the pet while the pet holds its attention.
                    t.aggro, t.aggro_on = False, None
                    t.fighting_pet_until = now + 2 * pets.ATTACK_SECONDS
                    t.next_attack = now + combat.NPC_ATTACK_SECONDS
                    dmg = random.randint(*t.damage)
                    npc.health = max(0, npc.health - dmg)
                    # 0x27b is only written when the player is the source or target.
                    state["send"](build_system_text(f"{t.name} hits {npc.name} for {dmg} damage.",
                                                    SYSTEM_TEXT_COMBAT))
                    state["send"](health_msg(npc))
                    if npc.health <= 0:
                        state["send"](build_system_text(f"{npc.name} has been slain!", SYSTEM_TEXT_ERROR))
                        on_death()
                        return
    if npc.pet_mode == "follow":
        pos = player.live_position or player.spawned_at
        if pos is not None:
            goal = pos
    if goal is not None:
        values = combat.move_toward(npc, goal, dt, pets.SPEED, stop)
        if values:
            w.broadcast(lambda s, values=values: zone.npc_update(s, args, npc, values))


CARAVANS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "caravans.json")


def load_caravans():
    return storage.read_json(CARAVANS_FILE, [])


def save_caravans(cs):
    storage.write_json(CARAVANS_FILE, cs)


def caravan_of(name, cs=None):
    return next((c for c in (cs if cs is not None else load_caravans())
                 if name.lower() in [m.lower() for m in c["members"]]), None)


def caravan_location(c):
    """The leader's position (live if online, else saved)."""
    s = ONLINE.get(c["leader"].lower())
    if s is not None and s.get("player") is not None:
        p = s["player"]
        pos = p.live_position or p.spawned_at or p.position
        if pos is not None:
            c["loc"] = {"level": p.level, "x": pos[0], "y": pos[1], "z": pos[2]}
    return c.get("loc")


def caravan_rows(c):
    chars = {ch["first"].lower(): ch for ch in load_characters()}
    now = time.time()
    rows = []
    for name in c["members"]:
        ch = chars.get(name.lower(), {})
        klass = character_race_class(ch)[1] if ch else 0
        online = ONLINE.get(name.lower()) is not None
        if name.lower() == c["leader"].lower():
            st, left = caravan.IS_LEADER, 0
        elif online:
            st, left = caravan.MUST_LOGOUT, caravan.TRAVEL_SECONDS
        else:
            left = max(0, caravan.TRAVEL_SECONDS - (now - ch.get("last_logout", now)))
            st = caravan.TRAVELING if left > 0 else caravan.CAN_LOGIN
        rows.append(caravan.member(name, social_uid(name), klass, left, st))
    return rows


def caravan_window(state, c):
    """Full caravan state for one member: role, every member row, the location."""
    send, me = state["send"], state["player"].name
    send(caravan.role(caravan.LEADER if c["leader"].lower() == me.lower() else caravan.MEMBER))
    for m in caravan_rows(c):
        send(m)
    loc = caravan_location(c)
    if loc:
        cx, cy = (int(p[1:]) * -1 if p.startswith("n") else int(p) for p in loc["level"].split("_")[1:3])
        send(caravan.location(cx, cy, loc["x"], loc["y"], loc["z"]))


def caravan_all(c, fn):
    for name in c["members"]:
        s = ONLINE.get(name.lower())
        if s is not None and s.get("player") is not None:
            fn(s)


def caravan_drop(cs, c, name):
    """name leaves c (or is removed); a caravan of one is disbanded."""
    mid = social_uid(name)
    c["members"] = [m for m in c["members"] if m.lower() != name.lower()]
    s = ONLINE.get(name.lower())
    if s is not None and s.get("send"):
        s["send"](caravan.role(caravan.NONE))
        s["send"](zone.zone_event(0x0E, struct.pack("<h", caravan.LEFT)))
    if c["leader"].lower() == name.lower() and c["members"]:
        c["leader"] = c["members"][0]
    if len(c["members"]) < 2:
        caravan_all(c, lambda s: s["send"](caravan.role(caravan.NONE)))
        cs.remove(c)
    else:
        caravan_all(c, lambda s: (s["send"](caravan.removed(mid)), caravan_window(s, c)))
    save_caravans(cs)


def handle_caravan_event(state, event, data):
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE caravan event {event:#x}: {data.hex(' ')}")
    notice = lambda code: send(zone.zone_event(0x0E, struct.pack("<h", code)))
    cs = load_caravans()
    mine = caravan_of(player.name, cs)
    if event == caravan.INVITE:
        name = caravan.read_name(data)
        target = ONLINE.get(name.lower())
        if target is state:
            notice(caravan.SELF)
        elif mine is not None and mine["leader"].lower() != player.name.lower():
            send(build_system_text("Only the caravan leader can invite.", SYSTEM_TEXT_ERROR))
        elif target is None or target.get("player") is None:
            send(build_system_text(f"{name} is not online.", SYSTEM_TEXT_ERROR))
        elif target["player"].health <= 0:
            notice(caravan.DEAD)
        elif caravan_of(target["player"].name, cs):
            send(build_system_text(f"{target['player'].name} is already in a caravan.", SYSTEM_TEXT_ERROR))
        else:
            target["caravan_invite"] = player.name
            target["send"](caravan.invite(player.name))
            send(build_system_text(f"You invite {target['player'].name} to join your caravan.", SYSTEM_TEXT_WHITE))
    elif event == caravan.ACCEPT:
        inviter = state.pop("caravan_invite", None)
        if inviter is None or inviter.lower() != caravan.read_name(data).lower() or mine:
            return
        c = caravan_of(inviter, cs)
        if c is not None and c["leader"].lower() != inviter.lower():
            # The inviter joined someone else's caravan since inviting: only leaders invite.
            send(build_system_text(f"{inviter} can no longer invite you to a caravan.", SYSTEM_TEXT_ERROR))
            return
        if c is None:
            c = {"leader": inviter, "members": [inviter]}
            cs.append(c)
        c["members"].append(player.name)
        save_caravans(cs)
        notice(caravan.JOINED)
        caravan_all(c, lambda s: caravan_window(s, c))
    elif event == caravan.DECLINE:
        inviter = state.pop("caravan_invite", None)
        s = ONLINE.get((inviter or "").lower())
        if s is not None and s.get("send"):
            s["send"](build_system_text(f"{player.name} declined your caravan invite.", SYSTEM_TEXT_WHITE))
    elif event == caravan.LEAVE:
        if mine is None:
            notice(caravan.NOT_IN)
            return
        caravan_drop(cs, mine, player.name)
    elif event == caravan.REMOVE and len(data) >= 4 and mine:
        if mine["leader"].lower() != player.name.lower():
            return
        who = next((m for m in mine["members"] if social_uid(m) == struct.unpack_from("<i", data)[0]), None)
        if who and who.lower() != player.name.lower():
            caravan_drop(cs, mine, who)


def caravan_login(state):
    c = caravan_of(state["player"].name)
    if c is not None:
        caravan_window(state, c)
        caravan_all(c, lambda s: caravan_window(s, c) if s is not state else None)


FISH = [("Sand Carp", 0.7), ("Mud Eel", 0.3)]


# Display names of chunks (the client has its own, FUN_00b70e80; the server only needs a few).
CHUNK_NAMES = {"chunk_n19_12": "Sundering Wastelands", "chunk_n19_13": "Sundering Wastelands"}


def chunk_display_name(level):
    """A chunk's zone name from the client's bin/Resources/Texts/ChunkNames.txt (read once), e.g.
    chunk_n13_n9 -> "Khal"; CHUNK_NAMES or the level name when the file has none."""
    if "_loaded" not in CHUNK_NAMES:
        CHUNK_NAMES["_loaded"] = True
        path = os.path.join(ARGS.client_dir if ARGS else "", "bin", "Resources", "Texts", "ChunkNames.txt")
        try:
            data = open(path, "rb").read()
            text = data.decode("utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else data.decode("latin-1")
        except OSError:
            text = ""
        for m in re.finditer(r'DISPLAYNAME="([^"]+)" X=(-?\d+) Y=(-?\d+)', text):
            CHUNK_NAMES.setdefault(chunk_name(int(m.group(2)), int(m.group(3))), m.group(1))
    return CHUNK_NAMES.get(level, level)


def fish_fresh(name):
    return bool(ARGS.content.item(name).get("fish", {}).get("fresh_water"))


def record_catch(state, name, bait, combo=None):
    """Weigh a caught fish and update the Fishing achievements row (combo: the pattern the
    player completed, now shown on the page)."""
    player, send = state["player"], state["send"]
    lo, hi = ARGS.content.item(name).get("fish", {}).get("weight", [0.5, 3.0])
    weight = round(random.uniform(lo, hi), 1)
    records = player.__dict__.setdefault("fish_records", {})
    rec, best = fishing.add_catch(records, name, weight, chunk_display_name(player.level), bait,
                                  time.strftime("%Y-%m-%d"))
    if combo and not rec.get("combo"):
        rec["combo"] = list(combo)
        send(build_system_text(f"You have learned the {name}'s combo.", SYSTEM_TEXT_WHITE))
    send(build_system_text(f"Your {name} weighs {weight:g} pounds."
                           + (" A personal best!" if best and rec["caught"] > 1 else ""), SYSTEM_TEXT_WHITE))
    send(fishing.achievement_update(name, rec, fish_fresh(name)))
    save_character_field(player.name, "fish_records", records)


def fishing_login(state):
    """The Achievements tab's Fishing page: one row per fish the player has caught."""
    records = getattr(state["player"], "fish_records", {})
    for m in fishing.achievement_list(records, fish_fresh):
        state["send"](m)


def fishing_best(state, data):
    """0x5a4: the Best catches board for the fish picked on the Fishing page."""
    if len(data) < 9:
        return
    _, fish_id, today = struct.unpack_from("<iiB", data)
    player = state["player"]
    fish = next((n for n, r in getattr(player, "fish_records", {}).items() if r["id"] == fish_id), None)
    if fish is None:
        return
    chars = {c["first"]: c.get("fish_records", {}) for c in load_characters()}
    chars[player.name] = getattr(player, "fish_records", {})
    board = fishing.leaderboard(chars.items(), fish, time.strftime("%Y-%m-%d") if today else None)
    for m in fishing.best_messages(board):
        state["send"](m)


def equipped_kind(player, kind):
    """The equipped fishing pole or bait (items.json "fishing": "pole" / "bait")."""
    for e in player.equipment:
        if ARGS.content.item(e[1]).get("fishing") == kind:
            return e
    return None


def handle_fishing_event(state, event, data):
    player, send = state["player"], state["send"]
    s = state.get("fishing")
    now = time.time()
    print(f"  >>> ZONE fishing event {event:#x}: {data.hex(' ')} phase={s and s['phase']}")
    if event == fishing.CAST:
        if s is not None:
            return
        if equipped_kind(player, "pole") is None or equipped_kind(player, "bait") is None:
            send(build_system_text("You need a fishing pole in your primary hand and bait in your secondary hand.",
                                   SYSTEM_TEXT_ERROR))
            return
        state["fishing"] = {"phase": "cast", "since": now}
        send(fishing.cast())
        send(build_system_text("You cast your line.", SYSTEM_TEXT_WHITE))
    elif s is None:
        return
    elif event == fishing.BOBBER and s["phase"] == "cast":
        s.update(phase="wait", bite=now + fishing.bite_delay())
    elif event == fishing.STATE and data[:4] == b"\0\0\0\0":
        state.pop("fishing", None)
    elif event == fishing.KEY and s["phase"] == "fight" and s.get("pull") is not None and len(data) >= 4:
        key = struct.unpack_from("<i", data)[0]
        good = key == s["pull"]
        s["pull"] = None
        send(fishing.event(player.char_id, fishing.GOOD if good else fishing.OOPS, key))
        s["good" if good else "miss"] += 1
        fishing_combo(state, good, key)
        s["next"] = now + 1.0
        fishing_finish(state)


def fishing_combo(state, good, key):
    """A good answer moves the fish's combo on (0x59c ev 0 "Combo part n/4"); a miss breaks it
    (ev 1); four in a row complete it (ev 2): one extra good pull, and the player learns it."""
    player, send, s = state["player"], state["send"], state["fishing"]
    if not good:
        if s.get("streak"):
            send(fishing.event(player.char_id, fishing.COMBO_FAILED))
        s["streak"] = 0
        return
    s["streak"] = s.get("streak", 0) + 1
    send(fishing.event(player.char_id, fishing.COMBO_PART, key))
    if s["streak"] >= fishing.COMBO_LENGTH:
        s["streak"] = 0
        s["good"] += fishing.COMBO_BONUS
        s["combo_done"] = True
        send(fishing.event(player.char_id, fishing.COMBO_DONE))


def fishing_finish(state):
    """Land the fish or lose it once the fight is decided."""
    player, send, s = state["player"], state["send"], state["fishing"]
    if s["good"] >= fishing.NEEDED:
        state.pop("fishing")
        send(fishing.event(player.char_id, fishing.CAUGHT))
        name = s["fish"]
        give_item(state, name)
        bait = equipped_kind(player, "bait")
        record_catch(state, name, bait[1] if bait else None, s["combo"] if s.get("combo_done") else None)
        if bait is not None:
            player.equipment.remove(bait)
            send(zone.zone_event(0x1A5, struct.pack("<iB", bait[0], 0)))
            gear_changed(state, ARGS, player)
            send(build_system_text("Your bait is used up.", SYSTEM_TEXT_WHITE))
        skill_up(state, fishing.SKILL, "Fishing", 300)
    elif s["miss"] >= fishing.MISSES:
        state.pop("fishing")
        send(fishing.event(player.char_id, fishing.GOT_AWAY))


def fishing_tick(state, now):
    s = state.get("fishing")
    if s is None:
        return
    player, send = state["player"], state["send"]
    if s["phase"] == "cast" and now - s["since"] > fishing.LAND_TIMEOUT:
        state.pop("fishing")
        send(fishing.state(fishing.STOP))
        send(build_system_text("Your line needs to land in water.", SYSTEM_TEXT_ERROR))
    elif s["phase"] == "wait" and now >= s["bite"]:
        # The fish is chosen at the bite: its combo decides the order of its pulls.
        fish = random.choices([f for f, _w in FISH], [w for _f, w in FISH])[0]
        s.update(phase="fight", good=0, miss=0, pull=None, next=now + 1.0, fish=fish, step=0, streak=0,
                 combo=fishing.combo_for(fish, ARGS.content.item(fish).get("fish")))
        send(fishing.state(fishing.FISH_ON))
    elif s["phase"] == "fight":
        if s.get("pull") is not None and now > s["pull_until"]:
            s["pull"] = None
            s["miss"] += 1
            send(fishing.event(player.char_id, fishing.OOPS))
            fishing_combo(state, False, 0)
            s["next"] = now + 1.0
            fishing_finish(state)
        elif s.get("pull") is None and now >= s["next"]:
            s["pull"] = s["combo"][s["step"] % fishing.COMBO_LENGTH]
            s["step"] += 1
            s["pull_until"] = now + fishing.PULL_SECONDS
            print(f"  <- fishing pull {s['pull']}")
            send(fishing.event(player.char_id, fishing.PULL, s["pull"]))


def asm_recipes(player):
    known = getattr(player, "assembly_known", [])
    return {k: r for k, r in ARGS.content.assembly.items() if k in known}


def asm_by_id(rid):
    return next(((k, r) for k, r in ARGS.content.assembly.items() if r["id"] == rid), (None, None))


def asm_template(name):
    rec = vgmsg.inventory_item(zone.template_id(name), name, 0, zone.item_icon(name, 443), 1,
                               **zone.item_equip_fields(name))
    return assembly.template(rec)


def asm_candidates(player, r):
    names = {i["item"] for i in r["ingredients"]}
    return [(it[0], r["id"]) for it in player.items if it[1] in names]


def asm_categories(player):
    paths = sorted({tuple(r.get("category", ["Assembly", "General", "General", "All"]))
                    for r in ARGS.content.assembly.values()})
    return assembly.categories(paths)


def asm_tree(player, node=None):
    """0x350 for the tertiary category `node` (the client's 0x121): the learned recipes in it,
    parented to that node id (the client hangs them under its "Assembly Recipes" root)."""
    _msgs, ids = asm_categories(player)
    nodes = [(r["name"], r["id"], node) for r in asm_recipes(player).values()
             if node is not None and ids.get(tuple(r.get("category", []))) == node]
    return assembly.tree(nodes)


def level_chunk(level):
    """chunk_n19_12 -> (-19, 12)."""
    return tuple(-int(p[1:]) if p.startswith("n") else int(p) for p in level.split("_")[1:3])


# /applyformondeath [on|off]: 0x5b2 {u8 on} (FUN_00611610; the client prints "Your forms will
# (NOT) automatically re-apply after death."). Death ends the active form; with the option on,
# releasing or being resurrected puts it back.
APPLY_FORM_ON_DEATH = 0x5B2


def drop_form_on_death(state, player):
    if getattr(player, "form", -1) == -1:
        return
    for e in getattr(player, "effects", []):
        if e.get("form"):
            e["ends"] = 0
    player.lost_form, player.form = player.form, -1
    state["send"](forms.current(-1))


def restore_form_after_death(state, player):
    fid = getattr(player, "lost_form", -1)
    player.lost_form = -1
    form = next((f for f in getattr(player, "forms", []) if f[0] == fid), None)
    if form is not None and getattr(player, "apply_form_on_death", False):
        apply_form(state, form, time.time())


def forms_login(state):
    """Combat forms / Psionicist mindsets (forms.py): the Forms bar, no form active."""
    player = state["player"]
    if getattr(player, "forms", None):
        for m in forms.form_list(player.forms):
            state["send"](m)
        state["send"](forms.current(-1))


def handle_form_event(state, event, data):
    """0x13e choose a form: it becomes the one stance of that kind (Effects Maintained)."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE form event {event:#x}: {data.hex(' ')}")
    if event != forms.CHOOSE:
        send(forms.priority_result(0))
        return
    if len(data) < 4:
        return
    fid = struct.unpack_from("<i", data)[0]
    form = next(((f, n, s) for f, n, s in getattr(player, "forms", []) if f == fid), None)
    now = time.time()
    if form is None:
        send(forms.result(3))                           # not a valid form
        return
    if now < getattr(player, "form_ready", 0):
        send(forms.result(2))                           # not ready yet
        send(forms.current(getattr(player, "form", -1)))
        return
    apply_form(state, form, now)


def apply_form(state, form, now):
    """Make form (id, name, spec) the active stance and tell the Forms bar."""
    player, send = state["player"], state["send"]
    fid, name, spec = form
    for e in getattr(player, "effects", []):
        if e.get("form") and e["name"] != name:
            e["ends"] = 0
    apply_stance(state, player, name, dict(spec, kind="buff", stance=True), now)
    e = next(x for x in player.effects if x["id"] == effect_id(player, name))
    e["form"] = True
    player.form, player.form_ready = fid, now + forms.CHANGE_SECONDS
    send(forms.result(0))
    send(forms.current(fid))
    send(forms.cooldown(1.0))                      # the main bar's "can't change form" bar, full


def songs_login(state):
    """Bard songs (songs.py): slot counts, saved songs, nothing playing."""
    player, send = state["player"], state["send"]
    if not getattr(player, "song_parts", None):
        return
    send(songs.slots())
    for n, song in enumerate(getattr(player, "songs", [])):
        send(songs.compose(n + 1, song))
    send(songs.now_playing(""))


def stop_song(state, quiet=False):
    player = state["player"]
    for e in getattr(player, "effects", []):
        if e.get("song"):
            e["ends"] = 0                                   # effects_tick takes it off
    if getattr(player, "playing_song", None):
        player.playing_song = None
        state["send"](songs.now_playing(""))
        if not quiet:
            state["send"](build_system_text("You stop singing.", SYSTEM_TEXT_WHITE))


def play_song(state, song):
    player, send = state["player"], state["send"]
    cc = getattr(player, "cc", None)
    if cc is not None and time.time() < cc["until"] and cc["kind"] in ("stun", "fear"):
        # The client's own refusals: 483 CantUseSongFeared, or the stunned ability failure.
        send(client_notice(CANT_USE_SONG_FEARED) if cc["kind"] == "fear" else effects.ability_failed(effects.STUNNED))
        return
    by_id = {aid: spec for _, aid, _, spec in player.song_parts}
    stop_song(state, quiet=True)
    spec = songs.effect(song, by_id)
    apply_buff(state, player, song["name"], dict(spec, duration=effects.STANCE_SECONDS), time.time())
    e = next(x for x in player.effects if x["id"] == effect_id(player, song["name"]))
    e.update(stance=True, song=True, energy_cost=spec["energy"])   # Effects Maintained; stops with the song
    send(effects.effect_remove(e["id"]))                # no "3650d" timed icon
    send(effects.maintained_add(e["id"], song["name"], e.get("desc", ""), spec["icon"]))
    player.playing_song = song["name"]
    send(songs.now_playing(song["name"]))
    send(build_system_text(f"You begin to sing {song['name']}.", SYSTEM_TEXT_WHITE))


def handle_song_event(state, event, data):
    """The Song window and /playsong, /stopsong (songs.py)."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE song event {event:#x}: {data[:40].hex(' ')}")
    if not getattr(player, "song_parts", None):
        return
    known = {aid for _, aid, _, _ in player.song_parts}
    saved = player.__dict__.setdefault("songs", [])
    error = lambda text: send(build_system_text(text, SYSTEM_TEXT_ERROR))
    try:
        if event in (songs.SAVE, songs.PLAY_COMPOSED):
            song = songs.parse_compose(data)
            why = songs.problem(song, known, saved if event == songs.SAVE else ())
            if why:
                return error(why)
            if event == songs.PLAY_COMPOSED:
                return play_song(state, song)
            old = next((n for n, s in enumerate(saved) if s["name"].lower() == song["name"].lower()), None)
            if old is None:
                saved.append(song)
                old = len(saved) - 1
            else:
                saved[old] = song
            send(songs.compose(old + 1, song))
            send(build_system_text(f"Song saved: {song['name']}.", SYSTEM_TEXT_WHITE))
        elif event == songs.PLAY:
            sid = struct.unpack_from("<i", data)[0]
            if not 0 < sid <= len(saved):
                return error("You can't find that song.")
            play_song(state, saved[sid - 1])
        elif event == songs.STOP:
            stop_song(state)
            return
        elif event == songs.DELETE:
            sid = struct.unpack_from("<i", data)[0]
            if 0 < sid <= len(saved):
                if saved[sid - 1]["name"] == getattr(player, "playing_song", None):
                    stop_song(state)
                saved.pop(sid - 1)
                # Ids are list positions: resend the list so the client's ids match again.
                send(songs.clear_all())
                send(songs.slots())
                for n, s in enumerate(saved):
                    send(songs.compose(n + 1, s))
        elif event == songs.SWAP:
            a, b = struct.unpack_from("<ii", data)
            if 0 < a <= len(saved) and 0 < b <= len(saved):
                saved[a - 1], saved[b - 1] = saved[b - 1], saved[a - 1]
    except (struct.error, IndexError):
        print(f"  bad song event {event:#x}: {data.hex(' ')}")
        return
    save_character_field(player.name, "songs", saved)


def journal_login(state):
    """Travel journal (travel.py): the chunk's merchants, trainers, services, stations and
    riftways, and the player's house, on the Adventure Journal's Locations tab and the map."""
    player = state["player"]
    try:
        spawns = ARGS.content.spawns(player.level, ARGS.client_dir)
        chunk = level_chunk(player.level)
    except (ValueError, IndexError):
        return
    house = None
    removed = journal_removed(player)
    for pid, st in load_housing().items():
        plot = ARGS.content.plots.get(pid)
        if (st.get("owner", "").lower() == player.name.lower() and st.get("building") and plot
                and travel.HOUSE_ENTRY_ID not in removed):
            house = (plot["name"], plot["loc"], level_chunk(plot["chunk"]))
    known = {int(k.split(":")[1]) for k in getattr(player, "discovered", []) if k.startswith(player.level + ":")}
    msgs = travel.login_messages(spawns, chunk, house, known - removed)
    known |= removed                                     # removed sites are not rediscovered
    for m in msgs:
        state["send"](m)
    state["journal_cats"] = {struct.unpack_from("<i", m, 10 + len(m[10:]) - 8)[0]
                             for m in msgs if struct.unpack_from("<I", m, 2)[0] == 0x2AE}
    state["journal_sites"] = (player.level, travel.chunk_sites(spawns), known)
    player.journal_ready = True                          # the built-in categories exist now


def journal_removed(player):
    """Entry ids the player removed from the journal in their current chunk (the house entry's
    id is the same in every chunk)."""
    out = set()
    for k in getattr(player, "journal_removed", []):
        level, _, eid = k.rpartition(":")
        if level in (player.level, "*"):
            out.add(int(eid))
    return out


def journal_remove(state, eid):
    """0x138 Remove > Yes on the Locations tab: gone now (0x383) and at the next login."""
    player = state["player"]
    key = f"{'*' if eid == travel.HOUSE_ENTRY_ID else player.level}:{eid}"
    if key not in getattr(player, "journal_removed", []):
        player.journal_removed = getattr(player, "journal_removed", []) + [key]
        save_character_field(player.name, "journal_removed", player.journal_removed)
    js = state.get("journal_sites")
    if js is not None:
        js[2].add(eid)
    state["send"](travel.remove(eid))


def form_bar_tick(state, now):
    """Once a second: the main bar's form-change bar (0x140, AdvCannotChangeFormStatus) runs
    down to empty while the change cooldown lasts."""
    player = state["player"]
    ready = getattr(player, "form_ready", 0)
    if ready and (ready > now or state.get("form_bar_left")):
        left = max(0.0, (ready - now) / forms.CHANGE_SECONDS)
        state["form_bar_left"] = left
        state["send"](forms.cooldown(left))


def journal_tick(state):
    """Once a second: service locations the player walks near are added to the journal."""
    player = state["player"]
    js = state.get("journal_sites")
    pos = player.live_position
    if js is None or pos is None or js[0] != player.level:
        return
    level, sites, known = js
    for eid, cid, loc, name, desc in travel.discover(sites, known, pos):
        known.add(eid)
        if cid not in state.setdefault("journal_cats", set()):
            state["journal_cats"].add(cid)
            state["send"](travel.category(next(n for c, n, _ in travel.CATEGORIES if c == cid), cid))
        state["send"](travel.entry(eid, loc, name, level_chunk(level), cid, desc))
        state["send"](build_system_text(f"Location discovered: {name}.", SYSTEM_TEXT_WHITE))
        player.discovered = getattr(player, "discovered", []) + [f"{level}:{eid}"]
        save_character_field(player.name, "discovered", player.discovered)


def assembly_login(state):
    send = state["send"]
    for k, r in asm_recipes(state["player"]).items():
        for name in [r["reward"]] + [i["item"] for i in r["ingredients"]]:
            send(asm_template(name))
        send(assembly.learn(r, zone.template_id))
    for m in asm_categories(state["player"])[0]:
        send(m)


def handle_assembly_event(state, event, data):
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE assembly event {event:#x}: {data[:24].hex(' ')}")
    vals = struct.unpack_from(f"<{len(data) // 4}i", data) if len(data) >= 4 else ()
    npc = player.npcs.get(player.target) if player.target else None
    if event == assembly.TRAIN_BEGIN:
        if npc is None or not getattr(npc, "assembly_trainer", None):
            send(assembly.trainer_end(0))
            return
        offers = [(r["name"], r["id"], ARGS.content.item(r["reward"]).get("icon", 443), r["trainer_cost"],
                   r.get("description", ""))
                  for k, r in ARGS.content.assembly.items()
                  if k in npc.assembly_trainer and k not in getattr(player, "assembly_known", [])]
        if not offers:
            send(assembly.trainer_end(2))
            return
        state["asm_training"] = set(npc.assembly_trainer)      # only this trainer's recipes
        for m in assembly.trainer_begin(offers):
            send(m)
    elif event == assembly.TRAIN_DONE:
        state.pop("asm_training", None)
        send(assembly.trainer_end())
    elif event == assembly.TRAIN_BUY and vals:
        key, r = asm_by_id(vals[0])
        if not state.get("asm_training"):
            send(assembly.trainer_result(vals[0], 1))
        elif r is None or key in getattr(player, "assembly_known", []) or key not in state["asm_training"]:
            send(assembly.trainer_result(vals[0], 2))
        elif player.coins < r["trainer_cost"]:
            send(assembly.trainer_result(vals[0], 3))
        else:
            player.coins -= r["trainer_cost"]
            send(merchant.coins(player.coins))
            save_character_field(player.name, "coins", player.coins)
            player.assembly_known = list(getattr(player, "assembly_known", [])) + [key]
            save_character_field(player.name, "assembly_known", player.assembly_known)
            for name in [r["reward"]] + [i["item"] for i in r["ingredients"]]:
                send(asm_template(name))
            send(assembly.learn(r, zone.template_id, announce=True))
            send(assembly.trainer_result(r["id"], 0))
    elif event == assembly.TREE and vals:
        send(asm_tree(player, vals[0]))
    elif event in (assembly.DETAILS, assembly.TEMPLATES, assembly.CANDIDATES) and vals:
        key, r = asm_by_id(vals[0])
        if r is None:
            return
        if event == assembly.DETAILS:
            send(assembly.details(r, zone.template_id))
            send(assembly.recheck(r["id"]))
        elif event == assembly.TEMPLATES:
            for name in [r["reward"]] + [i["item"] for i in r["ingredients"]]:
                send(asm_template(name))
            send(assembly.recheck(r["id"]))
        else:
            send(assembly.candidates(asm_candidates(player, r)))
    elif event == assembly.ASSEMBLE and vals:
        key, r = asm_by_id(vals[0])
        if r is None or key not in getattr(player, "assembly_known", []):
            send(assembly.failure(assembly.NO_KNOWLEDGE))
            return
        if state.get("assembling"):
            send(assembly.failure(assembly.BUSY))
            return
        bench = next((n for n in player.npcs.values()
                      if n.props.get("EntityTypes", 0) & assembly.STATION), None)
        if bench is None or player_distance(player, bench) > 800:
            send(assembly.failure(assembly.WRONG_STATION if bench is None else assembly.TOO_FAR))
            return
        if any(have_items(player)(i["item"]) < i.get("qty", 1) for i in r["ingredients"]):
            send(assembly.failure(assembly.NOTHING))
            return
        state["assembling"] = {"recipe": key, "done": time.time() + r.get("seconds", 3)}
        send(assembly.timer(f"Assembling {r['name']}", r.get("seconds", 3)))


def assembly_tick(state, now):
    a = state.get("assembling")
    if a is None or now < a["done"]:
        return
    state.pop("assembling")
    player, send = state["player"], state["send"]
    r = ARGS.content.assembly[a["recipe"]]
    if any(have_items(player)(i["item"]) < i.get("qty", 1) for i in r["ingredients"]):
        send(assembly.failure(assembly.FAILED))
        return
    for i in r["ingredients"]:
        take_items(state, i["item"], i.get("qty", 1))
    give_item(state, r["reward"])
    send(assembly.success())
    send(assembly.candidates(asm_candidates(player, r)))


SAFE_FALL = 500.0             # units a player can drop without harm
FALL_DAMAGE = 0.3             # health per unit beyond that
_water_cache = {}


def in_water(level, loc):
    if level not in _water_cache:
        try:
            import water
            _water_cache[level] = water.water_boxes(level, os.path.join(ARGS.client_dir, "Assets", "Maps"))
        except Exception:
            _water_cache[level] = []
    return any(lo[0] <= loc[0] <= hi[0] and lo[1] <= loc[1] <= hi[1] and lo[2] <= loc[2] <= hi[2]
               for _n, lo, hi in _water_cache[level])


HEAD_HEIGHT = 60.0            # pawn location (collision centre) to the eyes
BREATH_REFILL = 10            # breath regained per second above water
DROWN_DAMAGE = 0.1            # share of max health lost per second without breath


def breath_step(breath, underwater):
    """(new breath, drowning) after one second."""
    if underwater:
        return max(0, breath - 1), breath <= 0
    return min(zone.BREATH_MAX, breath + BREATH_REFILL), False


def energy_tick(state, now):
    """Once a second: a playing song costs its energy per second (songs.effect); without
    enough energy it stops. Otherwise energy regenerates."""
    player = state["player"]
    if now < state.get("energy_next", 0):
        return
    state["energy_next"] = now + 1.0
    maximum = player.stats.get("energy", 100)
    old = getattr(player, "energy", maximum)
    song = next((e for e in getattr(player, "effects", []) if e.get("song") and e["ends"] > now), None)
    energy, singing = songs.energy_step(old, maximum, song.get("energy_cost", 0) if song else None)
    player.energy = energy
    if song and not singing:
        state["send"](build_system_text("You do not have enough energy to keep singing.", SYSTEM_TEXT_ERROR))
        stop_song(state, quiet=True)
    elif song and now >= state.get("song_pulse", 0):
        state["song_pulse"] = now + songs.PULSE_SECONDS
        song_pulse(state, song, now)
    if energy != old:
        state["send"](zone.energy_update(player))


def song_pulse(state, song, now):
    """A playing song's buff on the groupmates in range (a short buff, refreshed each pulse)."""
    player = state["player"]
    pos = player.live_position or player.spawned_at
    spec = {"stat": song["stat"], "bonus": song["bonus"], "icon": song["icon"], "duration": songs.GROUP_BUFF_SECONDS}
    for s in group_states(player):
        other = s.get("player")
        if s is state or other is None or s.get("world") is not state.get("world"):
            continue
        opos = other.live_position or other.spawned_at
        if pos is None or opos is None or math.hypot(opos[0] - pos[0], opos[1] - pos[1]) > songs.SONG_RANGE:
            continue
        first = not any(e["name"] == song["name"] for e in getattr(other, "effects", []))
        apply_buff(s, other, song["name"], spec, now)
        if first:
            s["send"](build_system_text(f"{player.name}'s {song['name']} fills you with strength.", SYSTEM_TEXT_WHITE))


def breath_tick(state):
    """Once a second: breath runs out with the head inside a WaterVolume, then the
    player drowns (DROWN_DAMAGE of max health a second) until they surface."""
    player, loc = state["player"], state.get("position")
    if loc is None or player.health <= 0:
        return
    head = (loc[0], loc[1], loc[2] + HEAD_HEIGHT)
    old = state.get("breath", zone.BREATH_MAX)
    breath, drowning = breath_step(old, in_water(player.level, head))
    state["breath"] = breath
    send = state["send"]
    if breath != old:
        send(zone.breath_update(breath))
        if breath == 0:
            send(build_system_text("You are out of breath!", SYSTEM_TEXT_ERROR))
    if drowning:
        dmg = max(1, int(player.stats["hit_points"] * DROWN_DAMAGE))
        player.health = max(0, player.health - dmg)
        send(build_system_text(f"You are drowning! You take {dmg} damage.", SYSTEM_TEXT_ERROR))
        send(zone.health_update(player))
        if player.health == 0:
            print(f"  {player.name} drowned")
            for m in player_death(state, ARGS, player):
                send(m)


def fall_drop(fs, loc):
    """One movement report through the fall tracker fs (a dict). Returns the height fallen
    when a fall ends on this report, else None. Falls only count once the player has stood
    still on the ground since logging in or being teleported (fs["armed"]): the drop from a
    server-placed spawn point to the terrain is not a fall."""
    prev = fs.get("last")
    fs["last"] = loc
    if prev is None:
        fs.pop("top", None)
        fs["armed"] = False
        return None
    dz = loc[2] - prev[2]
    if abs(dz) > 1200 or math.hypot(loc[0] - prev[0], loc[1] - prev[1]) > 2000:
        fs.pop("top", None)                  # teleported
        fs["armed"] = False
        return None
    if dz < -4:
        if fs.get("armed"):
            fs["top"] = max(fs.get("top", prev[2]), prev[2])
        return None
    fs["armed"] = True                       # on the ground (or going up)
    top = fs.pop("top", None)
    return None if top is None else top - loc[2]


TELEPORT_GRACE = 5.0          # seconds after the client echoes a server teleport (0x3e5)
SPEED_WINDOW = 2.0            # seconds of movement measured at a time
JUMP_LIMIT = 2000.0           # one report moving further than this is a jump


def speed_limit():
    """Fastest legitimate horizontal speed (riding), with room for lag."""
    return BASE_GROUND_SPEED * MOUNT_SPEED * 1.3


def movement_warning(ms, loc, now):
    """Movement sanity check (log only) for one report through the tracker ms (a dict).
    Returns a warning string, or None. Server teleports are excused for TELEPORT_GRACE
    seconds after the client's 0x3e5 echo (ms["teleport_at"])."""
    prev, start = ms.get("last"), ms.get("start")
    ms["last"] = loc
    if prev is None or start is None or now - ms.get("teleport_at", -1e9) < TELEPORT_GRACE:
        ms.update(start=loc, t0=now)
        return None
    if math.hypot(loc[0] - prev[0], loc[1] - prev[1]) > JUMP_LIMIT:
        ms.update(start=loc, t0=now)
        return f"jumped {math.hypot(loc[0] - prev[0], loc[1] - prev[1]):.0f} units without a teleport"
    dt = now - ms["t0"]
    if dt < SPEED_WINDOW:
        return None
    speed = math.hypot(loc[0] - start[0], loc[1] - start[1]) / dt
    ms.update(start=loc, t0=now)
    if speed > speed_limit():
        return f"moved at {speed:.0f} units/s (limit {speed_limit():.0f})"
    return None


def service_range_check(state, player):
    """Walking away from the banker, mailbox or broker ends that session (and closes its
    window), so it can't be used from across the map."""
    for key, close in (("banking", bank.stop), ("mail_session", mail.close), ("market", market.close)):
        npc = state.get(key)
        if hasattr(npc, "location") and player_distance(player, npc) > SERVICE_RANGE:
            state.pop(key, None)
            state["send"](close())
            print(f"  {player.name} walked away from {npc.name}: {key} ended")


def on_move(state, loc):
    """Every movement report: fall damage, service ranges, then the movement sanity check."""
    check_fall(state, loc)
    player = state.get("player")
    if player is None:
        return
    service_range_check(state, player)
    flight_check(state, loc)
    ms = state.setdefault("move_check", {})
    warning = movement_warning(ms, loc, time.time())
    if not warning:
        ms["good"] = loc
        return
    player.move_warnings = getattr(player, "move_warnings", 0) + 1
    print(f"  MOVEMENT WARNING {player.name}: {warning} at ({loc[0]:.0f}, {loc[1]:.0f}, {loc[2]:.0f})")
    good = ms.get("good")
    if getattr(ARGS, "enforce_movement", False) is True and good is not None:
        # --enforce-movement: back to the last position that passed (a server teleport, whose
        # echo excuses the jump back from the check).
        state["send"](zone.player_teleport(tuple(good)))
        player.live_position = state["position"] = good
        ms["last"] = ms["start"] = good
        print(f"  {player.name} moved back to ({good[0]:.0f}, {good[1]:.0f}, {good[2]:.0f})")


def check_fall(state, loc):
    """Fall damage from the reported heights (fall_drop) for drops over SAFE_FALL that
    don't end in water."""
    player = state.get("player")
    fs = state.setdefault("fall", {})
    if player is None or player.health <= 0:
        fs.clear()
        return
    if getattr(player, "flying", False):
        # A flier coming down is not falling (verified live: a griffon descent from 6600 units
        # killed the rider with "You fall and take 585 damage"); start fresh from the landing.
        fs.clear()
        fs["last"] = loc
        return
    drop = fall_drop(fs, loc)
    if drop is None or drop <= SAFE_FALL or in_water(player.level, loc):
        return
    dmg = int((drop - SAFE_FALL) * FALL_DAMAGE)
    player.health = max(0, player.health - dmg)
    send = state["send"]
    send(build_system_text(f"You fall and take {dmg} damage.", SYSTEM_TEXT_ERROR))
    send(zone.health_update(player))
    print(f"  {player.name} fell {drop:.0f} units: {dmg} damage")
    if player.health == 0:
        for m in player_death(state, ARGS, player):
            send(m)


def use_tombstone(state):
    """U (the pawn's ServerUse RPC) on your tombstone: the target, or your own one if you
    stand at it. True when handled."""
    p = state["player"]
    npc = p.npcs.get(p.target) if p.target else None
    if npc is None or not getattr(npc, "tombstone_of", None):
        npc = p.npcs.get(zone.tombstone_eid(p))
        if npc is None or player_distance(p, npc) > 600:
            return False
    if player_distance(p, npc) > 600:
        state["send"](client_notice(TOO_FAR_AWAY))
    else:
        recover_tombstone(state, p, npc)
    return True


# Corpse summoning (verified live 2026-10-15): an NPC with mobs.json "corpse_summoner" offers the
# client's dialog option 0x2b9 (type 0xb, "summon my corpse") while the player has a tombstone;
# choosing it sends 0x167 (no payload). The tombstone moves to the player's feet, from any region.
SUMMON_CORPSE_OPTION, SUMMON_CORPSE = 0x2B9, 0x167


def summon_corpse(state, args):
    player, send = state["player"], state["send"]
    npc = player.npcs.get(player.target) if player.target else None
    if npc is None or not getattr(npc, "corpse_summoner", False):
        return
    send(zone.zone_event(quest.END_CONVERSATION))
    if not getattr(player, "tombstone", None):
        send(build_system_text("You have no tombstone to summon.", SYSTEM_TEXT_ERROR))
        return
    pos = state.get("position") or player.live_position
    if pos is None or player_distance(player, npc) > SERVICE_RANGE:
        send(client_notice(TOO_FAR_AWAY))
        return
    player.died_at = (pos[0] + 80.0, pos[1], pos[2])
    place_tombstone(state, args, player)
    send(build_system_text(f"{npc.name} summons your tombstone to you.", SYSTEM_TEXT_WHITE))


def recover_tombstone(state, player, npc):
    """Looting your own tombstone: it crumbles and half the experience debt comes back."""
    if getattr(npc, "tombstone_of", "").lower() != player.name.lower():
        state["send"](build_system_text("That is not your tombstone.", SYSTEM_TEXT_ERROR))
        return
    remove_tombstone(state, player)
    debt = getattr(player, "xp_debt", 0)
    back = debt // 2
    player.xp_debt = debt - back
    save_character_field(player.name, "xp_debt", player.xp_debt)
    state["send"](zone.score_message(player))
    state["send"](build_system_text(f"You recover your tombstone and win back {back} experience.",
                                    SYSTEM_TEXT_WHITE))


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
    for key, state in list(clients.items()):
        # Every live connection sends keep-alives; a silent one (or a connect that never
        # went further) is dropped so the table can't grow without limit.
        if now - state.setdefault("last_seen", now) > CLIENT_IDLE_SECONDS:
            clients.pop(key, None)
            if key[0] == "ZONE" and state.get("player") is not None and not state.get("closed"):
                leave_world(state, args)
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
            breath_tick(state)
            energy_tick(state, now)
            journal_tick(state)
            crowd_control_tick(state, now)
            wounds_tick(state, now)
            form_bar_tick(state, now)
            for m in encounter.sync(state.setdefault("encounter", {}), player, player.npcs):
                state["send"](m)
            refresh_quest_icons(state)
            reactions_tick(state, now)
        for action in combat.tick(player, now):
            if action[0] == "swing":
                _, lines, npc = action
                for m in combat_results(state, args, player, lines, npc, True, True):
                    send_message(zone_sock, addr, state, m)
            elif action[0] == "pvp":
                duel_strike(state, player, action[1])
            elif action[0] == "health":
                send_message(zone_sock, addr, state, zone.health_update(player))
            elif action[0] == "endurance":
                send_message(zone_sock, addr, state, zone.endurance_update(player))
    STATUS[1] += LOOP_STATS[0]
    STATUS[2] += 1.0 - min(1.0, LOOP_STATS[1])
    if now >= STATUS[0]:
        if STATUS[0]:
            secs = STATUS_SECONDS
            print(f"  status {time.strftime('%H:%M')}: {len(ONLINE)} players online, {len(clients)} connections, "
                  f"{STATUS[1] / secs:.0f} packets/s in, loop busy {100 * STATUS[2] / secs:.0f}%, "
                  f"{sum(s.get('resent', 0) for s in clients.values())} packets resent to current connections")
        STATUS[0], STATUS[1], STATUS[2] = now + STATUS_SECONDS, 0, 0.0
    if PING_AGE[0] > 0.2:
        print(f"  !!! load: a ping took {PING_AGE[0]:.1f} s to reach the server; {LOOP_STATS[0]} packets read, "
              f"{LOOP_STATS[1]:.2f} s idle this second")
    LOOP_STATS[0], LOOP_STATS[1] = 0, 0.0
    PING_AGE[0] = 0.0
    if SEND_FAILURES[0] or RECEIVE_GAPS[0]:
        print(f"  !!! network: {SEND_FAILURES[0]} packets not sent (send buffer full), {RECEIVE_GAPS[0]} client "
              f"packets arrived after a lost one, this second")
        SEND_FAILURES[0] = RECEIVE_GAPS[0] = 0
    hours = getattr(args, "backup_hours", 0)
    if isinstance(hours, (int, float)) and hours > 0:
        if now >= BACKUP_DUE[0]:
            BACKUP_DUE[0] = now + hours * 3600
            try:
                print(f"  database backup: {storage.backup(os.path.dirname(CHARACTERS_FILE))}")
            except Exception as e:                      # a full disk must not stop the game
                print(f"  !!! database backup failed: {e}")
    group_tick()
    for s in list(ONLINE.values()):
        if s.get("player") is not None and getattr(s["player"], "sprint_until", 0):
            sprint_tick(s, args, now)
    if isinstance(getattr(args, "content", None), content.Content):
        content_reload_tick(args, now)
    housing_tick(now)
    duel_tick(now)
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
        npc_chatter_tick(w, now)
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


# NPC speech (mobs.json "chatter": [lines], "chatter_every": seconds, "aggro_say": line): the
# normal say line (0x0f, channel CHAT_SAY: "Thestran Guard says, ...") to the players within
# SAY_RANGE of the NPC. Chatter waits a random part of chatter_every first, then about
# chatter_every between lines (+/- 25%), and only while someone is near.
SAY_RANGE = 1500


def npc_say(w, npc, text):
    msg = build_chat_line(npc.name, text)
    for s in list(w.members.values()):
        p = s.get("player")
        if p is not None and npc.location and player_distance(p, npc) <= SAY_RANGE:
            s["send"](msg)


def npc_chatter_tick(w, now, rng=random):
    for npc in list(w.npcs.values()):
        if not getattr(npc, "chatter", None) or not npc.alive or npc.aggro:   # (tombstones, pets: none)
            continue
        due = getattr(npc, "next_chatter", None)
        if due is None:
            npc.next_chatter = now + rng.uniform(0, npc.chatter_every)
        elif now >= due:
            npc.next_chatter = now + npc.chatter_every * rng.uniform(0.75, 1.25)
            npc_say(w, npc, rng.choice(npc.chatter))


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


def refused_by_ignore(state, target_player):
    """Group invites, trade requests and duel challenges to someone who ignores the sender are
    refused (the server's own wording); True when refused. Tells are dropped silently instead."""
    if not ignores(target_player, state["player"].name):
        return False
    state["send"](build_system_text(f"{target_player.name} is ignoring you.", SYSTEM_TEXT_ERROR))
    return True


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
                "lfm": bool(getattr(p, "lfm", False) or (getattr(p, "group", None) and p.group.leader is p)),
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
    return storage.read_json(GUILDS_FILE, {})


def save_guilds(guilds):
    storage.write_json(GUILDS_FILE, guilds)


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
    char = load_character(name, ignore_case=True) or {}
    extra = g.get("member_info", {}).get(char.get("first", name), {})
    return {"id": character_id(char) if char else social_uid(name), "name": char.get("first", name),
            "rank": rank, "online": p is not None if online is None else online,
            "klass": p.klass if p else 0, "level": p.level_number if p else 1,
            "chunk": tuple(p.chunk) if p else (0, 0), "last_online": char.get("last_logout", 0), **extra}


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
    send(guild.info(g["name"], g.get("ranks"), g))
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
            gid, inviter = state.pop("guild_invite")
            g = guilds.get(str(gid))
            if g is None or g["members"].get(inviter, -1) < guild.OFFICER:
                # Gone, or the inviter was kicked or demoted since inviting.
                send(build_system_text("That guild invitation is no longer valid.", SYSTEM_TEXT_ERROR))
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
            target["guild_invite"] = (mine["id"], player.name)
            target["guild_invite_at"] = (time.time(), mine["name"])
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
    if event == guild.LFM_LIST:
        listed = [g for g in guilds.values() if g.get("recruiting")]
        recs = []
        for g in listed:
            for n, info in g.get("member_info", {}).items():
                if info.get("recruiter"):
                    recs.append((g["id"], guild_member(g, n)["id"] & 0x7FFFFFFF, n, ONLINE.get(n.lower()) is not None))
        # The guild dispatcher (FUN_004f1610) is a zone message handler: reply on the zone connection.
        for m in guild.lfm_list([(g["id"], g["name"], g.get("recruit_notes", ""), g.get("tags")) for g in listed], recs):
            state["send"](m)
        return
    if mine is None:
        state["send"](zone.zone_event(0x0E, struct.pack("<h", 0x1A)))          # NoGuild
        return
    rank = mine["members"][next(m for m in mine["members"] if m.lower() == player.name.lower())]
    if event == guild.MEMBER_LIST:
        # Asked on the world connection, answered on the zone one: the guild dispatcher
        # (FUN_004f1610) is a zone handler, and on the world connection the client logs
        # "Received unhandled message id 1259/1260/1261".
        for m in guild.member_list([guild_member(mine, n) for n in mine["members"]]):
            state["send"](m)
    elif event in (guild.TOGGLE_RECRUITING, guild.RECRUIT_NOTES, guild.TAGS, guild.RANK_INVITE,
                   guild.RANK_REMOVE, guild.RANK_MOTD):
        if rank < 9:
            state["send"](build_system_text("Only the guild's leaders can change that.", SYSTEM_TEXT_ERROR))
            return
        if event == guild.TOGGLE_RECRUITING:
            mine["recruiting"] = not mine.get("recruiting", False)
        elif event == guild.RECRUIT_NOTES:
            mine["recruit_notes"] = guild.read_name(data).strip()[:256]
        elif event == guild.TAGS:
            mine["tags"] = list(data[:20])
        else:
            key = {guild.RANK_INVITE: "rank_invite", guild.RANK_REMOVE: "rank_remove",
                   guild.RANK_MOTD: "rank_motd"}[event]
            mine[key] = [int(b != 0) for b in data[:10]] + [1] * max(0, 10 - len(data))
            mine[key][8] = mine[key][9] = 1                  # ranks 9 and 10 always can
        save_guilds(guilds)
        guild_broadcast(player.name, lambda g: guild.info(g["name"], g.get("ranks"), g))
    elif event in (guild.MY_NOTE, guild.GUILD_NOTE, guild.POINTS, guild.OFFICER_NOTE, guild.RECRUITER):
        who = player.name
        if event == guild.MY_NOTE:
            field, value = "note", guild.read_name(data).strip()[:64]
        elif event == guild.RECRUITER:
            uid = struct.unpack_from("<i", data)[0] if len(data) >= 4 else 0
            who = next((n for n in mine["members"] if guild_member(mine, n)["id"] & 0xFFFFFFFF == uid & 0xFFFFFFFF), None)
            if who is None or rank < guild.OFFICER:
                return
            field = "recruiter"
            value = not mine.get("member_info", {}).get(who, {}).get("recruiter", False)
        else:
            (target,), used = guild.read_strings(data, 1)
            who = next((n for n in mine["members"] if n.lower() == target.strip().lower()), None)
            if who is None or rank < guild.OFFICER:
                state["send"](build_system_text("You can't change that member's notes.", SYSTEM_TEXT_ERROR))
                return
            if event == guild.POINTS:
                field, value = "points", struct.unpack_from("<f", data, used)[0] if len(data) >= used + 4 else 0.0
            else:
                field = "guild_note" if event == guild.GUILD_NOTE else "officer_note"
                value = guild.read_name(data[used:]).strip()[:64]
        mine.setdefault("member_info", {}).setdefault(who, {})[field] = value
        save_guilds(guilds)
        rec = guild_member(mine, who)
        guild_broadcast(player.name, lambda g: guild.member_update(rec))
    elif event == guild.MOTD_SET:
        if rank < guild.OFFICER:
            state["send"](build_system_text("You don't have permission to set the guild MOTD.", SYSTEM_TEXT_ERROR))
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
            state["send"](build_system_text("You can't rename that rank.", SYSTEM_TEXT_ERROR))
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
        guild_broadcast(player.name, lambda g: guild.info(g["name"], ranks, g))


BROTHERHOODS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brotherhoods.json")


def load_brotherhoods():
    return storage.read_json(BROTHERHOODS_FILE, [])


def save_brotherhoods(bhs):
    storage.write_json(BROTHERHOODS_FILE, [b for b in bhs if len(b["members"]) > 1])


def brotherhood_of(name, bhs=None):
    """The brotherhood {leader, members: [names]} name belongs to, or None."""
    return next((b for b in (bhs if bhs is not None else load_brotherhoods())
                 if name.lower() in [m.lower() for m in b["members"]]), None)


def brotherhood_bonuses(members, share):
    """{id(state): bonus XP} for group members grouped with others of their brotherhood; the
    bonus is added to their exp contribution and the member lists are updated."""
    if len(members) < 2:
        return {}
    bhs = load_brotherhoods()
    out, changed = {}, []
    for s in members:
        name = s["player"].name
        b = brotherhood_of(name, bhs)
        if b is None:
            continue
        mates = sum(1 for o in members if o is not s and o["player"].name.lower() in
                    [m.lower() for m in b["members"]])
        bonus = brotherhood.xp_bonus(share, mates)
        if bonus > 0:
            out[id(s)] = bonus
            b.setdefault("exp", {})[name] = b.get("exp", {}).get(name, 0) + bonus
            changed.append((b, name))
    if changed:
        save_brotherhoods(bhs)
        for b, name in changed:
            bh_send_all(b, lambda _m, b=b, name=name: brotherhood.member_add(bh_member(b, name)))
    return out


def bh_member(b, name):
    s = ONLINE.get(name.lower())
    p = s["player"] if s and s.get("player") else None
    return {"id": social_uid(name), "name": name, "level": p.level_number if p else 1,
            "klass": p.klass if p else 0, "online": p is not None,
            "leader": name.lower() == b["leader"].lower(), "note": b.get("notes", {}).get(name, ""),
            "exp": b.get("exp", {}).get(name, 0)}


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
        if b is not None and b["leader"].lower() != inviter.lower():
            send(build_system_text(f"{inviter} can no longer invite you to a brotherhood.", SYSTEM_TEXT_ERROR))
            return
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
    if event in (social.FIND_LFG, social.FIND_LFM) and len(data) >= 2 and data[0] == 1:
        # Find window Search: groups looking for members (LFG page, mode 1) or players
        # looking for a group (LFM page, mode 2).
        lfg_page = event == social.FIND_LFG
        found = []
        for s in ONLINE.values():
            p = s.get("player")
            if p is None or p is player:
                continue
            g = getattr(p, "group", None)
            if (lfg_page and (getattr(p, "lfm", False) or (g and g.leader is p))) or                     (not lfg_page and getattr(p, "lfg", False) and g is None):
                found.append(social_entry(p.name))
        for m in social.who_messages(found, 1 if lfg_page else 2):
            reply(m)
        return
    if event == social.FIND_LFM and len(data) >= 2:
        player.lfm = bool(data[1])
        return
    if event == fishing.BEST_REQUEST:
        fishing_best(zone_state, data)
        return
    if event in (group.REQUEST_JOIN, group.REQUEST_DECLINE):
        name = data.decode("utf-16-le", "replace").split(chr(0))[0].strip()
        other = ONLINE.get(name.lower())
        if event == group.REQUEST_DECLINE:
            # The leader turned the request down (or the client auto-declined it).
            if other is not None:
                other["send"](group.join_declined(player.name))
            return
        g = getattr(other["player"], "group", None) if other else None
        if other is None or other is zone_state:
            zone_state["send"](build_system_text(f"{name or 'That player'} is not online.", SYSTEM_TEXT_ERROR))
        elif getattr(player, "group", None) is not None:
            zone_state["send"](client_notice(ALREADY_IN_GROUP))
        elif g is not None and (g.leader is not other["player"] or len(g.members) >= group.MAX_MEMBERS):
            zone_state["send"](build_system_text(f"{name} cannot take you into a group right now.", SYSTEM_TEXT_ERROR))
        else:
            other["send"](group.join_request(other["player"].name, player))
            zone_state["send"](build_system_text(f"You ask {other['player'].name} to join their group.",
                                                 SYSTEM_TEXT_WHITE))
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
        msg = social.random_result(player.char_id, lo, hi, random.randint(lo, hi))
        w = state.get("world")
        if w is not None:
            w.broadcast(lambda s: msg)
        else:
            send(msg)
    elif event == social.INSPECT:
        name = social.read_name(data).strip()
        target = ONLINE.get(name.lower()) if name else None
        if target is None and player.target is not None:
            target = next((s for s in ONLINE.values() if s.get("player") and s["player"].char_id == player.target),
                          None)
        if target is None or target.get("world") is not state.get("world"):
            send(client_notice(PLEASE_TARGET_PC))
            return
        t = target["player"]
        dur = getattr(t, "durability", {})
        records = [vgmsg.inventory_item(item_id, n, slot, zone.item_icon(n, icon), equip_slot=slot,
                                        **zone.item_equip_fields(n, dur.get(str(item_id), 100)))
                   for item_id, n, icon, slot in t.equipment]
        for m in social.inspect_messages(t.name, races_classes.class_name(t.klass), t.level_number, records):
            send(m)


# Target marks: /mark <STAR, FIST, DIAMOND, SPADE, COG, FIRE, TRIDENT, PLUS or CLEAR>
# [DEFENSIVE or OFFENSIVE] (FUN_0060c150 -> FUN_004d5400) sends 0x592 MsgTwoEntityIdsAndInt
# {eid64 (group manager +0x30), eid64 target, i32 mark}. The group gets the same record back as
# 0x593 (FUN_004e1640: finds the target's pawn and sets its mark, FUN_004d0420).
MARK_REQUEST, MARK = 0x592, 0x593
# Deconstruction refusals: 0x590 {i32 handle, i32 code} (FUN_00506ee0) prints "You are not high
# enough level to deconstruct %s." for -2, else "%s can not be deconstructed." (handle_deconstruct).
DECONSTRUCT_RESULT, CANT_DECONSTRUCT = 0x590, -1


def mark_target(state, data):
    if len(data) < 20:
        return
    msg = zone.zone_event(MARK, data[:20])
    for s in group_states(state["player"]) or [state]:
        s["send"](msg)


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
        elif g and g.leader is not player and ONLINE.get(g.leader.name.lower()) is None:
            send(group.error(1))
        elif refused_by_ignore(state, target["player"]):
            pass
        elif getattr(target["player"], "group", None):
            send(group.error(2))
        elif g and len(g.members) >= g.limit():
            send(group.error(3))
        elif g and g.leader is not player:
            # not the leader: refer the invite to the leader (0x727)
            ONLINE[g.leader.name.lower()]["send"](group.referral(player, target["player"].char_id,
                                                                 target["player"].name))
            send(build_system_text(f"You ask {g.leader.name} to invite {target['player'].name} to the group.",
                                   SYSTEM_TEXT_WHITE))
        else:
            target["player"].pending_invite = state
            target["player"].pending_invite_at = time.time()
            target["send"](group.invite_popup(player, g.members if g else [player]))
        print(f"  >>> ZONE group invite {name!r} from {player.name}")
    elif event in (group.ACCEPT, group.DECLINE):
        inviter = getattr(player, "pending_invite", None)
        player.pending_invite = None
        if inviter is None or inviter.get("player") is None:
            return
        print(f"  >>> ZONE group {'accept' if event == group.ACCEPT else 'decline'} by {player.name}")
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
        if g is not None and g.leader is not leader:
            send(build_system_text(f"{leader.name} no longer leads that group.", SYSTEM_TEXT_ERROR))
            return
        if g and len(g.members) >= g.limit():
            send(group.error(3))
            return
        if g is None:
            g = leader.group = group.Group(leader)
            inviter["send"](group.formed(g))
        sub = g.free_subgroup() if g.raid else 0
        g.sub[player.char_id] = sub
        if g.raid:
            send(group.prejoin(g, sub))
        for m_state in group_states(leader):
            m_state["send"](group.member_added(player, sub))
            send(group.member_added(m_state["player"], g.sub.get(m_state["player"].char_id, 0)))
        g.members.append(player)
        player.group = g
        send(group.leader_is(g.leader))
        send(grouploot.mode_message(g))
    elif event in (group.RAID_CREATE, group.RAID_ALERT, group.READY_CHECK, group.READY_ANSWER,
                   group.RAID_MOVE, group.RAID_ROLE):
        handle_raid_event(state, event, payload[10:])
    elif event == group.LEAVE:
        leave_group(state)
    elif event in (group.BOOT, group.PROMOTE):
        g = getattr(player, "group", None)
        name = text.strip()
        if not name and player.target:
            other = state_by_char_id(player.target)
            name = other["player"].name if other else ""
        target = next((s for s in group_states(player) if s["player"].name.lower() == name.lower()), None) if g else None
        if g is None:
            send(client_notice(NOT_IN_GROUP))
        elif g.leader is not player:
            send(group.must_be_leader())
        elif target is None or target is state:
            send(build_system_text(f"{name or 'That player'} is not in your group.", SYSTEM_TEXT_ERROR))
        elif event == group.BOOT:
            leave_group(target, booted=True)
        else:
            g.leader = target["player"]
            for m_state in group_states(player):
                if m_state is not target:        # the new leader's own row: 0x6cb is a "programmer error"
                    m_state["send"](group.leader_is(g.leader))
            target["send"](group.you_are_leader())
    elif event == group.DISBAND:
        g = getattr(player, "group", None)
        if g and g.leader is player:
            for m_state in group_states(player):
                m_state["send"](group.disbanded())
                m_state["player"].group = None


def set_mentor_level(state, level):
    """Mentoring: the effective level (None = the real one) for the sheet, the pawn and the group."""
    player = state["player"]
    player.mentor_level = level
    shown = level or player.level_number
    state["send"](zone.score_message(player))
    show_pawn_values(state, {"m_GameplayLevel": shown})
    for s in group_states(player):
        s["send"](group.member_level(player, shown))


def show_pawn_values(state, values):
    player = state["player"]
    if "ue" in state:
        state["send"](zone.player_pawn_update(state, ARGS, values))
    w = state.get("world")
    if w is not None:
        w.broadcast(lambda s: zone.remote_player_update(s, ARGS, player, values), exclude=state)


def handle_mentor_event(state, event, data):
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE mentor event {event:#x}: {data.hex(' ')}")
    say = lambda s, t: s["send"](build_system_text(t, SYSTEM_TEXT_WHITE))
    if event == group.MENTOR_REQUEST:
        name = data.decode("utf-16-le", "replace").split("\0")[0].strip()
        t = ONLINE.get(name.lower())
        g = getattr(player, "group", None)
        if t is None or g is None or t["player"] not in g.members:
            send(build_system_text("You can only ask a member of your group to mentor you.", SYSTEM_TEXT_ERROR))
            return
        if t["player"].level_number <= player.level_number:
            send(build_system_text(f"{t['player'].name} is not higher level than you.", SYSTEM_TEXT_ERROR))
            return
        t["mentor_request"] = player.name
        t["send"](group.mentor_popup(player.name))
        say(state, f"You ask {t['player'].name} to mentor you.")
    elif event == group.MENTOR_ANSWER:
        who = state.pop("mentor_request", None)
        r = ONLINE.get((who or "").lower())
        if r is None:
            return
        if not data or data[0] == 0:
            say(r, f"{player.name} declined to mentor you.")
            return
        set_mentor_level(state, r["player"].level_number)
        state["mentoring"] = who
        say(state, f"You are now mentoring {who}. Your level is {r['player'].level_number}.")
        say(r, f"{player.name} is now mentoring you.")
    elif event == group.MENTOR_STOP and getattr(player, "mentor_level", None):
        set_mentor_level(state, None)
        say(state, f"You stop mentoring. Your level is {player.level_number} again.")
        state.pop("mentoring", None)


def open_loot(state, npc):
    """Open a corpse's loot window (U or 0xbb), if the player has loot rights."""
    assign_loot_turn(npc)                 # Round Robin: whose corpse it is, before the check
    if not group_loot_allowed(state, npc):
        return []
    msgs = combat.loot_messages(npc)
    group_loot_opened(state, npc)
    loot_coin(state, npc)
    corpse_emptied(state, npc)
    msgs = msgs + grouploot.loot_buttons(getattr(state["player"], "group", None), npc)
    m = hint(state["player"], "loot")
    return msgs + ([m] if m else [])


def assign_loot_turn(npc):
    """Round Robin: the first look at a group kill picks the member whose turn it is (the
    others get 0x6cd "It is <name>'s turn to loot.")."""
    killer = getattr(npc, "killer", None)
    g = getattr(killer, "group", None)
    if g is None or grouploot.settings(g)["mode"] != grouploot.ROUND_ROBIN or getattr(npc, "loot_owner", None):
        return
    npc.loot_owner = grouploot.next_turn(g)
    for m in group_states(killer):
        if m["player"] is not npc.loot_owner:
            m["send"](grouploot.other_turn(npc.loot_owner.char_id))


def corpse_lootable(npc):
    """A corpse with items or coin left (the loot sparkle shows on it)."""
    if npc.prop or getattr(npc, "tombstone_of", None) or npc.merchant:
        return False
    return npc.loot is None or bool(npc.loot) or combat.corpse_coin(npc) > 0


def corpse_emptied(state, npc):
    """The last coin or item came off: the sparkle stops for everyone in the chunk."""
    if getattr(npc, "sparkle_off", False) or corpse_lootable(npc):
        return
    npc.sparkle_off = True
    w = state.get("world")
    msg = combat.loot_sparkle(npc, False)
    if w is not None:
        w.broadcast(lambda s: msg)
    else:
        state["send"](msg)


def loot_coin(state, npc):
    """The corpse's coin goes to whoever opens it first: split between the group members
    online when the leader turned Coin Split on (0x6ce lines), else all to the looter."""
    if npc.prop or getattr(npc, "tombstone_of", None) or npc.merchant:
        return
    total = combat.corpse_coin(npc)
    if total <= 0:
        return
    npc.coin_left = 0
    player = state["player"]
    g = getattr(player, "group", None)
    members = [state]
    if g is not None and grouploot.settings(g)["split"]:
        members += [s for s in group_states(player) if s is not state]
    for s, share in zip(members, grouploot.split_coin(total, len(members))):
        p = s["player"]
        p.coins += share
        s["send"](merchant.coins(p.coins))                  # "You receive ..."
        save_character_field(p.name, "coins", p.coins)
        if len(members) > 1:
            # "<name> receives N due to cash loot sharing." for the others (0x1aa above
            # already told p; the client's own-share line errors out).
            for m in members:
                if m is not s:
                    m["send"](grouploot.coin_share(p, grouploot.coin_text(share)))


def npc_blocked(level, x, y, z):
    return zone.npc_blocked(level, x, y, z)


def group_loot_allowed(state, npc):
    """Loot rights on a corpse (grouploot.may_loot); sends the refusal."""
    code = grouploot.may_loot(state["player"], npc)
    # U sends both the pawn's ServerUse and 0xbb: tell the player once.
    if code is not None and time.time() - state.get("loot_refused_at", 0) > 1.0:
        state["loot_refused_at"] = time.time()
        state["send"](zone.zone_event(0x0E, struct.pack("<h", code)))   # the client prints the reason
    return code is None


def group_loot_opened(state, npc):
    """First look at a group kill: Need Before Greed starts the roll on the items at or
    above the rarity threshold."""
    killer = getattr(npc, "killer", None)
    g = getattr(killer, "group", None)
    if g is None:
        return
    s = grouploot.settings(g)
    if s["mode"] == grouploot.NEED_BEFORE_GREED and not getattr(npc, "rolled", False):
        start_roll(g, npc)


def roll_items(g, npc):
    """The corpse's items that go to a roll (rarity at or above the group threshold)."""
    rarity = grouploot.settings(g)["rarity"]
    pending = getattr(npc, "pending", set())
    return [i for i in (npc.loot or []) if i[0] not in pending
            and grouploot.qualifies(grouploot.rarity_index(ARGS.content.item(i[1]).get("rarity")), rarity)]


def start_roll(g, npc):
    npc.rolled = True
    if getattr(g, "lottery", None):
        return                                    # one roll at a time per group
    items = roll_items(g, npc)
    if not items:
        return
    npc.pending = set(getattr(npc, "pending", set())) | {i[0] for i in items}
    g.lottery = {"npc": npc, "queue": items, "first": True}
    present_roll(g)


def present_roll(g):
    import vgmsg
    lot = g.lottery
    item_id, name, icon, qty = lot["queue"][0]
    nxt = lot["queue"][1][1] if len(lot["queue"]) > 1 else ""
    data = vgmsg.inventory_item(item_id, name, 0, icon=icon, quantity=qty, **zone.item_equip_fields(name))
    lot["answers"] = {}
    lot["voters"] = [s["player"].name for s in group_states(g.leader)]
    lot["deadline"] = time.time() + grouploot.ROLL_SECONDS
    for s in group_states(g.leader):
        s["send"](grouploot.roll_popup(data, nxt, lot["first"]))
    lot["first"] = False


def answer_roll(state, need):
    """0xb9 need/greed or 0xba pass (need None) for the group's current roll."""
    player = state["player"]
    g = getattr(player, "group", None)
    lot = getattr(g, "lottery", None)
    if lot is None or player.name not in lot["voters"] or player.name in lot["answers"]:
        return
    if need is None:
        lot["answers"][player.name] = None
        state["send"](grouploot.your_roll(0, False))
    else:
        roll = random.randint(1, 100)
        lot["answers"][player.name] = (need, roll)
        state["send"](grouploot.your_roll(roll, need))
    if all(v in lot["answers"] for v in lot["voters"]):
        finish_roll(g)


def finish_roll(g):
    """Resolve the current item (unanswered = pass), give it to the winner, go on."""
    lot = g.lottery
    npc = lot["npc"]
    item = lot["queue"].pop(0)
    npc.pending.discard(item[0])
    result = grouploot.resolve(lot["answers"])
    members = group_states(g.leader)
    for s in members:
        s["send"](grouploot.roll_result(*(result or ("", False, 0))))
    winner = ONLINE.get(result[0].lower()) if result else None
    if winner is not None and item in (npc.loot or []):
        p = winner["player"]
        for m in combat.take_loot(p, npc, item[0]):
            winner["send"](m)
        corpse_emptied(winner, npc)
        save_character_field(p.name, "items", [list(i) for i in p.items])
        for s in members:
            s["send"](grouploot.looted(p, item[1], item[3]))
        print(f"  group loot: {p.name} won {item[1]} ({'need' if result[1] else 'greed'} {result[2]})")
    if lot["queue"]:
        present_roll(g)
    else:
        g.lottery = None
        g.lottery_close = time.time() + 6
        for s in members:
            s["send"](grouploot.rolls_over())


def handle_grouploot_event(state, event, data):
    """Group loot settings and rolls (grouploot.py)."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE group loot event {event:#x}: {data.hex(' ')}")
    g = getattr(player, "group", None)
    notice = lambda code: send(zone.zone_event(0x0E, struct.pack("<h", code)))
    if g is None:
        notice(0xC5)                                     # NotInGroup
        return
    s = grouploot.settings(g)
    members = group_states(player)

    def announce_ml():
        for m in members:
            m["send"](grouploot.you_master_looter() if m["player"].char_id == s["ml"]
                      else grouploot.other_master_looter(s["ml"]))

    if event in (grouploot.SET_MODE, grouploot.PROMOTE_ML, grouploot.CANCEL_ROLLS) and g.leader is not player:
        notice(grouploot.MUST_BE_LEADER)
    elif event == grouploot.SET_MODE:
        ml, mode, rarity, split, cash = grouploot.parse_set_mode(data)
        if not 0 <= mode <= grouploot.NEED_BEFORE_GREED:
            notice(grouploot.INVALID_MODE)
            return
        if all(m.char_id != ml for m in g.members):
            ml = g.leader.char_id
        s.update(mode=mode, ml=ml, rarity=rarity if rarity in grouploot.RARITIES else grouploot.DEFAULT_RARITY,
                 split=split, cash=cash)
        for m in members:
            m["send"](grouploot.mode_message(g))
        if mode == grouploot.MASTER_LOOTER:
            announce_ml()
    elif event == grouploot.PROMOTE_ML:
        name = data.decode("utf-16-le", "replace").split("\0")[0].strip().lower()
        who = next((m for m in g.members if m.name.lower() == name), None)
        if who is None:
            notice(0xCF)                                 # MustSelectGroupMember
            return
        s["ml"] = who.char_id
        announce_ml()
        for m in members:
            m["send"](grouploot.mode_message(g))
    elif event in (grouploot.ALLOW_GROUP, grouploot.START_RANDOM):
        npc = player.npcs.get(struct.unpack_from("<Q", data, 0)[0]) if len(data) >= 8 else None
        if npc is None or npc.alive or grouploot.may_loot(player, npc) is not None:
            notice(grouploot.NO_PERMISSION)
        elif event == grouploot.ALLOW_GROUP:
            npc.open_to_group = True
            send(grouploot.loot_button(grouploot.SHOW_SHARE, False))
            send(grouploot.unlock_result())             # "...unlocked for everyone that is allowed to loot it."
            for m in members:
                if m is not state:
                    m["send"](grouploot.unlocked_to_you(player.name, npc.name))
        elif s["mode"] == grouploot.RANDOM_FOR_MAGICAL:
            if npc.loot is None:
                combat.loot_messages(npc)                # roll the corpse's items
            start_roll(g, npc)
            send(grouploot.loot_button(grouploot.SHOW_START_ROLLING, False))
        else:
            notice(grouploot.INVALID_MODE)
    elif event == grouploot.NEED_GREED:
        answer_roll(state, bool(data[0]) if data else False)
    elif event == grouploot.PASS:
        answer_roll(state, None)
    elif event == grouploot.GIVE_LOOT and len(data) >= 8:
        corpse, name, what = grouploot.parse_give_loot(data)
        npc = player.npcs.get(corpse) or (player.npcs.get(player.target) if player.target else None)
        if s["mode"] != grouploot.MASTER_LOOTER or s["ml"] != player.char_id:
            notice(grouploot.NO_PERMISSION)
            return
        killer = getattr(npc, "killer", None) if npc is not None else None
        if npc is None or npc.alive or (killer is not None and getattr(killer, "group", None) is not g):
            # Only corpses this group killed (or nobody's): not another group's or player's kill.
            notice(grouploot.NO_PERMISSION)
            return
        if npc.loot is None:
            combat.loot_messages(npc)
        item = grouploot.match_loot(npc.loot or [], what)
        to = next((m for m in members if m["player"].name.lower() == name.lower()), None)
        if to is None:
            notice(0xCF)                                 # MustSelectGroupMember
            return
        if item is None or item[0] in getattr(npc, "pending", set()):
            send(build_system_text("That item is not on the corpse.", SYSTEM_TEXT_ERROR))
            return
        p = to["player"]
        for m in combat.take_loot(p, npc, item[0]):
            to["send"](m)
        corpse_emptied(to, npc)
        if to is not state:
            send(zone.zone_event(combat.LOOT_TAKEN_EVENT, struct.pack("<iB", item[0], 1)))
        save_character_field(p.name, "items", [list(i) for i in p.items])
        quest_items_changed(to)
        if to is not state:
            to["send"](build_system_text(f"{player.name} gives you {item[1]}." if item[3] == 1 else
                                         f"{player.name} gives you {item[3]} {item[1]}.", SYSTEM_TEXT_WHITE))
        for m in members:
            m["send"](grouploot.looted(p, item[1], item[3]))
    elif event == grouploot.CANCEL_ROLLS and getattr(g, "lottery", None):
        g.lottery["npc"].pending = set()
        g.lottery = None
        for m in members:
            m["send"](grouploot.rolls_over())
            m["send"](grouploot.hide_popup())


def handle_raid_event(state, event, data):
    """Raids: a group of up to 24 in four raid groups (group.py RAID_*)."""
    player, send = state["player"], state["send"]
    g = getattr(player, "group", None)
    print(f"  >>> ZONE raid event {event:#x}: {data.hex(' ')}")
    if g is None:
        send(client_notice(NOT_IN_GROUP))
        return
    members = group_states(player)
    officer = g.leader is player or 2 in g.roles.get(player.char_id, set())
    vals = struct.unpack_from(f"<{len(data) // 4}i", data) if len(data) >= 4 and event != group.RAID_ALERT else ()
    by_row = {group.row_id(s["player"]): s["player"] for s in members}
    if event == group.RAID_CREATE:
        if g.leader is not player or g.raid:
            return
        g.raid = True
        for s in members:
            s["send"](group.raid_formed())
    elif event == group.RAID_ALERT and officer:
        text = data.decode("utf-16-le", "replace").split("\0")[0].strip()
        for s in members:
            s["send"](group.alert(f"{player.name}: {text}"))
    elif event == group.READY_CHECK and officer:
        g.ready_initiator = player
        send(group.ready_requested())
        for s in members:
            if s is not state:
                s["send"](group.ready_popup(player))
    elif event == group.READY_ANSWER and len(vals) >= 2:
        init = getattr(g, "ready_initiator", None)
        s = online_state(init) if init else None
        if s is not None:
            s["send"](group.ready_status(player, vals[1]))
    elif event == group.RAID_MOVE and len(vals) >= 2 and officer and g.raid:
        who = by_row.get(vals[0])
        if who is not None and 0 <= vals[1] <= 3:
            g.sub[who.char_id] = vals[1]
            for s in members:
                s["send"](group.raid_moved(who, vals[1]))
    elif event == group.RAID_ROLE and len(vals) >= 2:
        who, role = by_row.get(vals[0]), vals[1]
        if who is None or role not in (1, 2, 3) or (role == 2 and g.leader is not player) or not officer:
            return
        roles = g.roles.setdefault(who.char_id, set())
        roles.symmetric_difference_update({role})
        for s in members:
            s["send"](group.raid_role(who, role))


def leave_group(state, booted=False):
    player = state["player"]
    g = getattr(player, "group", None)
    if g is None:
        return
    player.group = None
    g.members.remove(player)
    if "send" in state:
        state["send"](group.you_booted() if booted else group.you_left())
    if len(g.members) <= 1:
        for m_state in [ONLINE[m.name.lower()] for m in g.members if m.name.lower() in ONLINE]:
            if booted:
                m_state["send"](group.member_booted(player))
            m_state["send"](group.disbanded())
            m_state["player"].group = None
        return
    if g.leader is player:
        g.leader = g.members[0]
    for m_state in [ONLINE[m.name.lower()] for m in g.members if m.name.lower() in ONLINE]:
        m_state["send"](group.member_booted(player) if booted else group.member_left(player))
        m_state["send"](group.leader_is(g.leader))


INVITE_TIMEOUT = 60                  # seconds a group invitation stays open


def group_cast_sync(state, player, now):
    """The rest of the group sees the spell a member is casting by the member's row (0x3b3),
    until it goes off or is interrupted (0x3b4). Synced once a second, so every way a cast
    ends (finished, moved, stunned, /stopcast) clears it."""
    cast = state.get("casting")
    shown = state.get("cast_shown")
    key = (cast["ability"][3], cast["ability"][2]) if cast else None
    if key == shown:
        return
    others = [s for s in group_states(player) if s is not state]
    if shown is not None:
        for s in others:
            s["send"](group.member_cast_over(player, shown[0]))
    if key is not None:
        for s in others:
            s["send"](group.member_casting(player, key[0], key[1], max(0.0, cast["ends"] - now)))
    state["cast_shown"] = key


# Outposts (verified live 2026-10-15): 0x552 {bool8} sets bInOutpost, which shows the Outpost
# icon (VgrdMiniIconOutpost) on the player's portrait (VGUIPlayerStatus.xml). The server turns it
# on inside an outposts.json area and off on leaving it.
IN_OUTPOST = 0x552
OUTPOST_DELAY = 5.0                     # seconds after entering the world before the first update


def outpost_at(level, pos):
    """The outposts.json entry containing pos in chunk level, or None."""
    if not pos:
        return None
    for o in getattr(ARGS.content, "outposts", {}).values():
        if o.get("chunk") == level and math.hypot(pos[0] - o["loc"][0], pos[1] - o["loc"][1]) <= o.get("radius", 1500):
            return o
    return None


def outpost_sync(state):
    player = state["player"]
    if state.get("position") is None or "ue" not in state:
        return                          # not in the world yet
    if time.time() < state.setdefault("outpost_after", time.time() + OUTPOST_DELAY):
        return                          # the UI resets the icon while it loads; tell it after
    inside = outpost_at(player.level, state.get("position")) is not None
    if inside != state.get("in_outpost"):
        if state.get("in_outpost") is None and not inside:
            # The icon starts visible while the game var starts false, and the client only
            # redraws on a change: switch it on, then off (seen live).
            state["send"](zone.zone_event(IN_OUTPOST, bytes([1])))
        state["in_outpost"] = inside
        state["send"](zone.zone_event(IN_OUTPOST, bytes([int(inside)])))


# Defensive target panel (verified live 2026-10-15): 0x3e2 {eid64 entity, u8 health 0-255}
# (FUN_005eaa00) fills DefTargetLifePoints, the health bar of the defensive target panel by the
# portrait, when the entity is the player's defensive target; otherwise the bar stays empty.
DEF_TARGET_HEALTH = 0x3E2


def def_target_sync(state):
    tid = state.get("def_target")
    if not tid:
        state.pop("def_target_shown", None)
        return
    w = state.get("world")
    ts = w.members.get(tid) if w is not None else None
    who = ts["player"] if ts is not None and ts.get("player") is not None else None
    if who is None:
        return
    hp = max(0, min(255, round(255 * who.health / max(1, who.stats.get("hit_points", 1)))))
    if state.get("def_target_shown") != (tid, hp):
        state["def_target_shown"] = (tid, hp)
        state["send"](zone.zone_event(DEF_TARGET_HEALTH, struct.pack("<QB", tid, hp)))


def pawn_level_sync(state):
    """The pawn's m_GameplayLevel (the defensive target panel's level shield and /con) follows
    level ups; it is set at spawn and by mentoring."""
    player = state["player"]
    if "ue" not in state:
        return
    shown = getattr(player, "mentor_level", None) or player.level_number
    if state.setdefault("pawn_level", shown) != shown:
        state["pawn_level"] = shown
        show_pawn_values(state, {"m_GameplayLevel": shown})


def group_tick():
    """Once a second: members' positions and vitals to the rest of the group;
    group loot rolls that ran out of time; group invitations that expired (0x6b7)."""
    now = time.time()
    for s in list(ONLINE.values()):
        p = s.get("player")
        inviter = getattr(p, "pending_invite", None) if p is not None else None
        if inviter is not None and now - getattr(p, "pending_invite_at", now) > INVITE_TIMEOUT:
            p.pending_invite = None
            s["send"](zone.zone_event(0x6B7, struct.pack("<i", 0)))      # "GroupInviteTimedOut"
            if inviter.get("player") is not None and ONLINE.get(inviter["player"].name.lower()) is inviter:
                inviter["send"](build_system_text(f"Your group invitation to {p.name} has expired.",
                                                  SYSTEM_TEXT_WHITE))
        if s.get("guild_invite") and now - s.get("guild_invite_at", (now, ""))[0] > INVITE_TIMEOUT:
            # 0x4e8 {wstr guild, i32} (FUN_004e9d20) closes the invite popup and prints
            # "Your guild invite to <guild> has expired."
            gid, inviter_name = s.pop("guild_invite")
            guild_name = s.pop("guild_invite_at")[1]
            s["send"](zone.zone_event(0x4E8, (guild_name + chr(0)).encode("utf-16-le") + struct.pack("<i", 0)))
            inviter = ONLINE.get(inviter_name.lower())
            if inviter is not None and p is not None:
                inviter["send"](build_system_text(f"Your guild invitation to {p.name} has expired.",
                                                  SYSTEM_TEXT_WHITE))
        if p is not None and getattr(p, "group", None) is not None:
            group_cast_sync(s, p, now)
        if p is not None and s.get("send") and ARGS is not None:
            outpost_sync(s)
            def_target_sync(s)
            pawn_level_sync(s)
    for g in {id(s["player"].group): s["player"].group for s in ONLINE.values()
              if getattr(s.get("player"), "group", None)}.values():
        lot = getattr(g, "lottery", None)
        if lot and now >= lot["deadline"]:
            finish_roll(g)
        if getattr(g, "lottery_close", 0) and now >= g.lottery_close:
            g.lottery_close = 0
            for s in group_states(g.leader):
                s["send"](grouploot.hide_popup())
    for state in list(ONLINE.values()):
        player = state.get("player")
        if not getattr(player, "group", None) or "send" not in state:
            continue
        for m_state in group_states(player):
            if m_state is not state:
                state["send"](group.member_position(m_state["player"]))
                for m in group.member_vitals(m_state["player"]):
                    state["send"](m)


SERVICE_RANGE = 1500           # loot and merchant trades only this close to the corpse / merchant
CHUNK_CHANGE_EVENT = 0x9
CHUNK_SIZE = 204800.0
GM_CHUNK_LEVEL = 20             # the client's /chunk needs access level 20


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
    if not chunk_exists(cx, cy):
        print(f"  >>> ZONE chunk change to ({cx}, {cy}) ignored: no such chunk")
        return
    if (abs(dx) > 1 or abs(dy) > 1) and not (getattr(args, "dev_commands", False)
                                            or getattr(player, "access_level", 0) >= GM_CHUNK_LEVEL):
        print(f"  >>> ZONE chunk jump to ({cx}, {cy}) ignored: {player.name} is not a GM")
        return
    # The last ClientLoc is usually still on the old side of the edge, so keep the
    # new position just inside the new chunk (the client logs its own TRAVLoc).
    edge = CHUNK_SIZE / 2 - 1000    # the heightmap ends one cell (400) before the edge
    x = max(-edge, min(edge, loc[0] - dx * CHUNK_SIZE))
    y = max(-edge, min(edge, loc[1] + dy * CHUNK_SIZE))
    if abs(dx) > 1 or abs(dy) > 1:
        x, y = chunk_arrival(cx, cy)    # not a walk across an edge (a GM /chunk jump)
    travel_to_chunk(state, args, cx, cy, x, y)


_ARRIVALS = {}


def chunk_arrival(cx, cy):
    """Where a jump into a chunk lands: the chunk's map label from the client's PoINames.txt (a
    plain town label before a "[levels]" one), else the centre (which can be off the terrain)."""
    if not _ARRIVALS:
        path = os.path.join(ARGS.client_dir if ARGS else "", "bin", "Resources", "Texts", "PoINames.txt")
        try:
            data = open(path, "rb").read()
            text = data.decode("utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else data.decode("latin-1")
        except OSError:
            text = ""
        for m in re.finditer(r'PoIName="([^"]*)" ChunkX=(-?\d+) ChunkY=(-?\d+) X=(-?\d+) Y=(-?\d+)', text):
            key = (int(m.group(2)), int(m.group(3)))
            plain = "[" not in m.group(1)
            if key not in _ARRIVALS or (plain and not _ARRIVALS[key][0]):
                _ARRIVALS[key] = (plain, (float(m.group(4)), float(m.group(5))))
        _ARRIVALS.setdefault(None, (False, (0.0, 0.0)))
    return _ARRIVALS.get((cx, cy), (False, (0.0, 0.0)))[1]


def find_npc_spawn(content, name):
    """(level, NPC name, x, y, z or None) of the first spawn whose template is named `name`
    (exact, else the start of a name, else anywhere in it; any case), or None."""
    norm = lambda t: " ".join(re.sub(r"[^a-z0-9]+", " ", t.lower()).split())   # "Hive-King" = "hive king"
    want = norm(name)
    folder = os.path.join(content.directory, "spawns")
    found = {}
    for fn in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(folder, fn), encoding="utf-8") as f:
            spawns = json.load(f).get("spawns", [])
        for sp in spawns:
            n = (content.mobs.get(sp.get("mob")) or {}).get("name", "")
            low = norm(n)
            rank = 0 if low == want else 1 if low.startswith(want) else 2 if want in low else None
            if rank is not None and rank not in found:
                found[rank] = (fn[:-5], n, float(sp["x"]), float(sp["y"]), sp.get("z"))
    return found[min(found)] if found else None


def travel_to_chunk(state, args, cx, cy, x, y, z=None):
    """Move the player to (x, y) in chunk (cx, cy) with a full zone re-connect (as a walk
    across a chunk edge). z defaults to the ground there."""
    player = state["player"]
    old = getattr(player, "chunk", None) or DEFAULT_CHUNK
    level = chunk_name(cx, cy)
    if not chunk_exists(cx, cy):
        state["send"](build_system_text(f"There is no chunk {cx}, {cy}.", SYSTEM_TEXT_ERROR))
        return
    if z is None:
        z = args.content.ground_z(level, x, y, args.client_dir)
        z = z if z is not None else 0.0
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
        if refused_by_ignore(state, target["player"]):
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
            if item and zone.bag_items(player.items, handle):
                send(build_system_text(BAG_NOT_EMPTY, SYSTEM_TEXT_ERROR))
            elif item and zone.item_restriction(player, item, "trade"):
                send(build_system_text(zone.item_restriction(player, item, "trade"), SYSTEM_TEXT_ERROR))
            elif item and handle not in side.items and len(side.items) < trade.MAX_ITEMS:
                side.items.append(handle)
                side.offered[handle] = (item[1], item[3])
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
            if item is None or (item[1], item[3]) != side.offered.get(handle, (item[1], item[3])):
                # Split, destroyed or swapped since it was offered: the partner accepted
                # something else, so the trade is off.
                for s_state in (a, b):
                    s_state["send"](build_system_text("The offered items changed; the trade is cancelled.",
                                                      SYSTEM_TEXT_ERROR))
                end_trade(t, trade.cancelled())
                return
            moves.append((giver, item, taker))
    # Check both bags first so a full bag cancels the whole trade, not half of it.
    for s_state in (a, b):
        p = s_state["player"]
        incoming = sum(1 for _, _, tk in moves if tk is s_state)
        outgoing = sum(1 for gv, _, _ in moves if gv is s_state)
        if len(p.items) - outgoing + incoming > zone.BAG_SLOTS:
            s_state["send"](client_notice(TRADE_NO_SPACE))
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
        items = [[it[1], it[3]] for gv, it, _ in moves if gv is giver]
        if items or amount:
            audit("trade", giver=giver["player"].name, taker=taker["player"].name, items=items, coins=amount)
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
                opts.append((f"{q['name']} (complete)", q["id"], quest.OPTION_COMPLETE))
            elif q.get("giver") == tpl:
                opts.append((f"{q['name']} (in progress)", q["id"], quest.OPTION_PROGRESS))
        elif q.get("giver") == tpl and quest.offerable(q) and all(r in log.done for r in q.get("requires", [])):
            opts.append((q["name"], q["id"], quest.OPTION_AVAILABLE))
            greeting = greeting or q.get("greeting")
    # Start clean: 0x55f closes an open Dialogue window and frees all its options
    # (0x2bf only replaces quest options), and an empty 0x3ea clears the text
    # (0x3ea appends). Not during a parley: 0x55f would ask to leave it.
    if not state.get("parley"):
        out.append(zone.zone_event(quest.END_CONVERSATION))
    out.append(quest.npc_text(npc.entity_id, ""))
    dl = getattr(npc, "dialog", None)
    if dl and not greeting:
        node = dl["nodes"][dl["start"]]
        out.append(zone.zone_event(0x2BB, struct.pack("<Q", npc.entity_id)))   # open the Dialogue window
        out.append(quest.npc_text(npc.entity_id, node["text"]))
        out.append(quest.responses(npc.entity_id, list(dl["nodes"]).index(dl["start"]),
                                   [r["text"] for r in visible_responses(player, node)]))
    else:
        out.append(quest.npc_text(npc.entity_id, greeting or f"Greetings, {player.name}."))
    for i, cfg in enumerate(parley_configs(npc) if npc.parley else []):
        opts.append((cfg.get("offer", "Let's talk business.") + " (Parley)", diplomacy.PARLEY_OPTION_ID + i,
                     diplomacy.OPTION_TYPE))
    if task_master_option(npc):
        opts.append(task_master_option(npc))
    if opts:
        out.append(quest.options(npc.entity_id, opts))
    if npc.parley and parley_configs(npc):
        out.append(diplomacy.parley_offer(npc.entity_id, parley_configs(npc)))
    if npc.merchant:
        out.append(zone.zone_event(merchant.DIALOG_WARES))
    if npc.repairs:
        out.append(zone.zone_event(merchant.DIALOG_REPAIR))
    if trains(npc, player):
        out.append(zone.zone_event(trainer.OPTION))
    if npc.recipe_trainer:
        out.append(zone.zone_event(trainer.RECIPE_OPTION))
    if getattr(npc, "assembly_trainer", None):
        out.append(zone.zone_event(assembly.OPTION))
    if npc.broker:
        out.append(zone.zone_event(market.OPTION))
    if npc.banker:
        out.append(zone.zone_event(bank.OPTION))
        out.append(zone.zone_event(merchant.DIALOG_ESCROW))
    if getattr(npc, "corpse_summoner", False) and getattr(player, "tombstone", None):
        out.append(zone.zone_event(SUMMON_CORPSE_OPTION))
    if not state.get("parley"):
        out.append(zone.zone_event(NPC_GREET, struct.pack("<i", greet_kind(npc, opts))))
    return out


# NPC greeting voice (FUN_004c64d0): 0x581 {i32 kind} plays the talking NPC's voice-set line
# 1 QuesterGreet, 2 QuesterProgress, 3 TrainerGreet, 4 MerchantGreet, else GeneralGreet; only for
# NPCs of a humanoid race (pawn race 2-22, 186-206 or 348-368).
NPC_GREET = 0x581
GREET_GENERAL, GREET_QUESTER, GREET_PROGRESS, GREET_TRAINER, GREET_MERCHANT = range(5)


def greet_kind(npc, opts):
    kinds = [o[2] for o in opts if len(o) > 2 and o[2] in quest.OPTION_TYPES]
    if any(k in (quest.OPTION_COMPLETE, quest.OPTION_PROGRESS) for k in kinds):
        return GREET_PROGRESS
    if kinds:
        return GREET_QUESTER
    if npc.merchant:
        return GREET_MERCHANT
    if npc.trainer or npc.recipe_trainer or getattr(npc, "assembly_trainer", None):
        return GREET_TRAINER
    return GREET_GENERAL


def add_escrow(state, name, qty=1):
    player = state["player"]
    player.escrow = list(getattr(player, "escrow", [])) + [[name, zone.item_icon(name, 443), qty]]
    save_character_field(player.name, "escrow", player.escrow)
    what = name if qty == 1 else f"{qty} {name}"
    state["send"](build_system_text(f"Your bags are full: {what} is waiting for you in escrow. "
                                    "Any banker can hand it over.", SYSTEM_TEXT_ERROR))


def handle_escrow_event(state, event, data):
    """The Escrow Merchant window at a banker (merchant.escrow_window)."""
    player, send = state["player"], state["send"]
    npc = player.npcs.get(player.target) if player.target else None
    if npc is None or not npc.banker:
        send(merchant.close_window(2))
        return
    if player_distance(player, npc) > SERVICE_RANGE:
        send(merchant.close_window(1))
        return
    escrow = list(getattr(player, "escrow", []))
    if event == merchant.REQ_ESCROW_OPEN:
        send(zone.zone_event(0x55F))          # the window replaces the dialogue
        for m in merchant.escrow_window([tuple(e) for e in escrow]):
            send(m)
        return
    n = struct.unpack_from("<i", data, 0)[0] - merchant.ESCROW_HANDLE_BASE if len(data) >= 4 else -1
    if not 0 <= n < len(escrow):
        return
    name, _icon, qty = escrow[n]
    if not give_item(state, name, qty, escrow=False):
        return
    escrow.pop(n)
    player.escrow = escrow
    save_character_field(player.name, "escrow", escrow)
    # Handles are list positions: redraw the list so they stay in step.
    for m in merchant.escrow_window([tuple(e) for e in escrow]):
        send(m)
    quest_items_changed(state)


def task_master_option(npc):
    return ("I'm looking for work. (Work orders)", workorder.OPTION_ID, workorder.OPTION_TYPE) \
        if getattr(npc, "task_master", False) else None


def parley_configs(npc):
    """The diplomacy.json parleys an NPC offers (mobs.json "parley": a key, a list of keys, or
    true for the first one). Each is a dialogue option of its own (PARLEY_OPTION_ID + index)."""
    parleys = ARGS.content.diplomacy["parleys"]
    if isinstance(npc.parley, list):
        return [parleys[k] for k in npc.parley if k in parleys]
    if isinstance(npc.parley, str):
        return [parleys[npc.parley]] if npc.parley in parleys else []
    return [next(iter(parleys.values()))] if npc.parley else []


def parley_config(npc, option_id=None):
    """The parley behind a clicked option id (the first one without an id)."""
    configs = parley_configs(npc)
    i = (option_id or diplomacy.PARLEY_OPTION_ID) - diplomacy.PARLEY_OPTION_ID
    return configs[i] if 0 <= i < len(configs) else (configs[0] if configs else None)


def visible_responses(player, node):
    """A dialogue node's responses this player may see: "requires_flag" hides one until the
    player has earned that flag (e.g. a parley reward "flag"). The client answers by position
    in this list."""
    flags = set(getattr(player, "flags", []))
    return [r for r in node.get("responses", []) if r.get("requires_flag") in (None, *flags)]


# Crafting trade (verified live 2026-10-15): MsgScore field 43 (0 Blacksmith, 2 Artificer,
# 4 Outfitter, 0xff none) shows that trade's skill lists on the crafting Skills tab
# (CraTradeBlacksmith / Artificer / Outfitter). 0x311 (no payload) prints "Primary crafting trade
# set.". Chosen in a crafting trainer's conversation (dialogs.json action "trade:<name>").
CRAFT_TRADES = {"blacksmith": 0, "artificer": 2, "outfitter": 4}
PRIMARY_TRADE_SET = 0x311


def set_craft_trade(state, name):
    player = state["player"]
    if name not in CRAFT_TRADES:
        return
    player.craft_trade = CRAFT_TRADES[name]
    save_character_field(player.name, "craft_trade", player.craft_trade)
    state["send"](zone.score_message(player))
    state["send"](zone.skill_pool_caps(player))          # the trade's group headers
    state["send"](zone.zone_event(PRIMARY_TRADE_SET))
    state["send"](build_system_text(f"You are now a {name.capitalize()}.", SYSTEM_TEXT_WHITE))


def handle_dialog_response(state, data):
    """0x15b {i32 dialog index (= node position), u8 response}: follow a conversation."""
    player, send = state["player"], state["send"]
    npc = player.npcs.get(player.target) if player.target else None
    dl = getattr(npc, "dialog", None) if npc else None
    print(f"  >>> ZONE dialog reply {data[:5].hex(' ')} to {getattr(npc, 'name', None)}"
          + ("" if dl else " (no conversation)"))
    if not dl or len(data) < 5:
        return
    idx, ri = struct.unpack_from("<iB", data)
    names = list(dl["nodes"])
    if not 0 <= idx < len(names):
        return
    rs = visible_responses(player, dl["nodes"][names[idx]])
    if ri >= len(rs):
        return
    r = rs[ri]
    send(build_system_text(f"You say, \"{r['text']}\"", SYSTEM_TEXT_WHITE))
    action = r.get("action", "")
    if action.startswith(("faction:", "give:")):
        key = f"{npc.template_id}:{names[idx]}:{ri}"           # rewards are paid once per character
        done = list(getattr(player, "dialog_rewards", []))
        if key in done:
            action = "end"
        else:
            player.dialog_rewards = done + [key]
            save_character_field(player.name, "dialog_rewards", player.dialog_rewards)
    if action.startswith("faction:"):
        _, fid, amount = action.split(":")
        adjust_faction(state, fid, int(amount))
    elif action.startswith("give:"):
        give_item(state, action.split(":", 1)[1])
    elif action.startswith("trade:"):
        set_craft_trade(state, action.split(":", 1)[1])
    elif action == "wares" and npc.merchant:
        send(zone.zone_event(merchant.DIALOG_WARES))
    elif action.startswith("quest:"):
        dialog_quest(state, action.split(":", 1)[1], npc.entity_id)
        return
    if "goto" in r:
        node = dl["nodes"][r["goto"]]
        send(quest.npc_text(npc.entity_id, ""))
        send(quest.npc_text(npc.entity_id, node["text"]))
        send(quest.responses(npc.entity_id, names.index(r["goto"]), [x["text"] for x in visible_responses(player, node)]))
    elif not action or action == "end":
        send(zone.zone_event(quest.END_CONVERSATION))


_FIRST_SPAWN = {}


def first_spawns(content):
    """{mob template: (level, spawn)} of each template's first spawn in the spawn files (sorted by
    file name), built once per content load."""
    cached = _FIRST_SPAWN.get("index")
    if cached is not None and cached[0] is content:
        return cached[1]
    index = {}
    directory = os.path.join(content.directory, "spawns")
    for fn in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, fn), encoding="utf-8") as f:
                spawns = json.load(f).get("spawns", [])
        except (OSError, ValueError):
            continue
        for sp in spawns:
            index.setdefault(sp.get("mob"), (fn[:-5], sp))
    _FIRST_SPAWN["index"] = (content, index)
    return index


def quest_where(q):
    """(chunk x, chunk y, x, y, z) of the NPC a quest is turned in to: its first spawn in the
    spawn files (quest page fields 22-26, the completion zone and location), or None. The
    spawn's own height when it has one (cities above or below the terrain), else the ground."""
    mob = quest.turn_in(q)
    found = first_spawns(ARGS.content).get(mob) if mob else None
    if found is None:
        return None
    level, sp = found
    cx, cy = level_chunk(level)
    z = sp.get("z")
    if z is None:
        z = ARGS.content.ground_z(level, sp["x"], sp["y"], ARGS.client_dir) or 0
    return cx, cy, int(sp["x"]), int(sp["y"]), int(z)


def dialog_quest(state, key, npc_eid):
    """dialogs.json action "quest:<key>": a reply that opens the quest's page from the
    conversation. A quest not taken yet shows its offer (Accept is allowed even when this NPC is
    not the giver, like a shared quest); one in progress shows its progress; one already done or
    still locked by "requires" ends the conversation."""
    player, send = state["player"], state["send"]
    q = ARGS.content.quests.get(key)
    log = player.quests
    if q is None or key in log.done or not all(r in log.done for r in q.get("requires", [])):
        send(zone.zone_event(quest.END_CONVERSATION))
    elif key in log.active:
        send(quest.page(q, npc_eid, quest.IN_PROGRESS, log.active[key], have=have_items(player)))
    elif not quest.offerable(q):
        send(zone.zone_event(quest.END_CONVERSATION))
    else:
        state.setdefault("shared_quests", set()).add(key)
        send(quest.page(q, npc_eid, quest.OFFER))


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
                if q.get("reward", {}).get("choice"):
                    show_quest_rewards(state, key, q, npc_eid, prog, have)
                else:
                    finish_quest(state, key, q)
            else:
                send(quest.page(q, npc_eid, quest.IN_PROGRESS, prog, have=have))
        elif key not in log.done and tpl == q.get("giver") and quest.offerable(q):
            send(quest.page(q, npc_eid, quest.OFFER))
    elif event == quest.ABANDON and key in log.active:
        del log.active[key]
        send(quest.abandoned(q))
        save_character_field(player.name, "quests", log.to_json())
        quest_items_changed(state)
    elif event == quest.SHARE and key in log.active:
        shared = 0
        for s in group_states(player):
            p = s["player"]
            if s is state or key in p.quests.active or key in p.quests.done or not quest.offerable(q) \
                    or not all(r in p.quests.done for r in q.get("requires", [])):
                continue
            s.setdefault("shared_quests", set()).add(key)
            s["send"](quest.page(q, 0, quest.OFFER))
            s["send"](build_system_text(f"{player.name} shares the quest {q['name']} with you.", SYSTEM_TEXT_WHITE))
            shared += 1
        send(build_system_text(f"You share {q['name']} with {shared} group member{'s' if shared != 1 else ''}."
                               if shared else "Nobody in your group can take that quest.", SYSTEM_TEXT_WHITE))
    elif event == quest.ACCEPT and key not in log.active and key not in log.done:
        # Only from the giver (or a quest a groupmate shared), and only once the quests it
        # requires are done.
        offered = (tpl == q.get("giver") or key in state.get("shared_quests", set())) and quest.offerable(q)
        if not offered or not all(r in log.done for r in q.get("requires", [])):
            return
        state.get("shared_quests", set()).discard(key)
        log.active[key] = quest.new_progress()
        # The journal entry (0x2cb, which also caches the quest) before the accept result:
        # 0x2c1 for an uncached quest is logged as unhandled and leaves the offer page open.
        send(quest.page(q, npc_eid, quest.IN_PROGRESS, log.active[key], journal=True, have=have))
        send(quest.accepted(q))
        send(zone.zone_event(quest.END_CONVERSATION))    # the offer page otherwise stays open
        save_character_field(player.name, "quests", log.to_json())
        quest_advance(state, key, q, npc_eid, quiet=True)
    elif event == quest.SELECT_REWARD and key in log.active and len(payload) >= 18:
        item_id = struct.unpack_from("<i", payload, 14)[0]
        names = {i: name for i, name, _, _, choice in quest.reward_slots(q) if choice}
        if item_id in names and state.get("quest_reward_choice") == (key, names[item_id]):
            # Clicking the chosen reward again takes the choice back.
            state.pop("quest_reward_choice")
            send(quest.reward_deselected(q, item_id))
            send(quest.show_complete_button(q, False))
        elif item_id in names:
            prev = state.get("quest_reward_choice")
            if prev and prev[0] == key:
                old = next((i for i, n in names.items() if n == prev[1]), None)
                if old is not None:
                    send(quest.reward_deselected(q, old))
            state["quest_reward_choice"] = (key, names[item_id])
            send(quest.reward_selected(q, item_id))
            send(quest.show_complete_button(q))
    elif event == quest.REWARD_INFO:
        # The page named reward items the client had not cached: send them, then the page again.
        if key in log.active and quest.ready(q, log.active[key], have) and tpl == quest.turn_in(q):
            if state.get("reward_info_asked") != key:
                state["reward_info_asked"] = key
                show_quest_rewards(state, key, q, npc_eid, log.active[key], have)
        else:
            for m in quest_reward_items(q):
                send(m)
    elif event == quest.COMPLETE and key in log.active and q.get("reward", {}).get("choice"):
        item_id = struct.unpack_from("<i", payload, 14)[0] if len(payload) >= 18 else -1
        names = {i: name for i, name, _, _, choice in quest.reward_slots(q) if choice}
        chosen = names.get(item_id)
        if chosen is None and state.get("quest_reward_choice", (None,))[0] == key:
            chosen = state["quest_reward_choice"][1]
        if chosen is None:
            send(build_system_text("Choose one of the rewards first.", SYSTEM_TEXT_ERROR))
        elif quest.ready(q, log.active[key], have) and tpl == quest.turn_in(q):
            state.pop("quest_reward_choice", None)
            finish_quest(state, key, q, chosen)
    elif event == quest.REQUEST_INFO and key in log.active:
        send(quest.page(q, npc_eid, quest.IN_PROGRESS, log.active[key], journal=True, have=have))
    elif event in (quest.CONTINUE, quest.COMPLETE) and key in log.active:
        if quest.ready(q, log.active[key], have) and tpl == quest.turn_in(q):
            if q.get("reward", {}).get("choice"):
                show_quest_rewards(state, key, q, npc_eid, log.active[key], have)
            else:
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


def quest_reward_items(q):
    """0x2c7 item records for a quest's reward slots, so the client can show them."""
    out = []
    for item_id, name, qty, _, _ in quest.reward_slots(q):
        fields = zone.item_equip_fields(name)
        fields["raw"][1] = item_id       # the cache key the reward slot names (else the template id)
        out.append(zone.zone_event(0x2C7, vgmsg.inventory_item(
            item_id, name, -1, zone.item_icon(name, 443), qty,
            description=ARGS.content.item(name).get("description", ""), **fields)))
    return out


def show_quest_rewards(state, key, q, npc_eid, prog, have):
    """The state-4 page: the rewards, with the choice items to pick from."""
    send = state["send"]
    state.pop("quest_reward_choice", None)
    for m in quest_reward_items(q):
        send(m)
    send(quest.page(q, npc_eid, quest.DONE, prog, have=have, rewards=True))


def finish_quest(state, key, q, chosen=None):
    player, send = state["player"], state["send"]
    # Items gathered for "collect" steps are handed over.
    have = have_items(player)
    for step in quest.steps(q):
        for name, n in step.get("collect", {}).items():
            if have(name) < n:
                send(build_system_text(f"You need {n} {name}.", SYSTEM_TEXT_ERROR))
                return
    reward_items = q.get("reward", {}).get("items", []) + ([chosen] if chosen else [])
    if zone.BAG_SLOTS - len(player.items) < len(reward_items):
        send(client_notice(NO_ROOM_FOR_REWARD))
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
    for name in reward_items:
        give_item(state, name)
    if reward.get("xp"):
        for m in award_xp(player, reward["xp"], player.char_id):
            send(m)
    faction_reward(state, reward)
    if reward.get("title") is not None:
        grant_title(state, reward["title"])
    save_character_field(player.name, "quests", player.quests.to_json())
    send(zone.zone_event(quest.END_CONVERSATION))     # the turn-in page otherwise stays open
    print(f"  {player.name} completed quest {q['name']}")
    if getattr(ARGS, "quest_feedback", False):
        state["feedback_quest"] = key
        send(zone.zone_event(0x598, ('SGOUI toggle "Quest Feedback"' + chr(0)).encode("utf-16-le")))


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


def refresh_quest_icons(state):
    """Keep the quest icons over this player's NPCs up to date (sends only changes)."""
    player = state.get("player")
    if player is None or "send" not in state:
        return
    shown = state.setdefault("quest_icons", {})
    have = have_items(player)
    quests = ARGS.content.quests
    # The icons only change with the quest log, the bags, the level, the content or the NPCs in
    # view; skip the per-NPC work (most of this tick's cost with many players) when none did.
    log = player.quests
    sig = (id(ARGS.content), player.level_number, repr(sorted(log.active.items())), len(log.done),
           tuple(sorted((i[1], i[3]) for i in player.items)),
           tuple((e, n.alive) for e, n in player.npcs.items()))
    if state.get("quest_icons_sig") == sig:
        refresh_quest_nodes(state, have)
        return
    state["quest_icons_sig"] = sig
    for npc in list(player.npcs.values()):
        if not npc.alive or not getattr(npc, "template_id", None):
            continue
        kind = quest.npc_icon(quests, npc.template_id, player.quests, have, player.level_number)
        if kind == shown.get(npc.entity_id):
            continue
        if kind is None:
            shown.pop(npc.entity_id, None)
            state["send"](quest.clear_icon(npc.entity_id))
        else:
            shown[npc.entity_id] = kind
            state["send"](quest.show_icon(npc.entity_id, kind))
    refresh_quest_nodes(state, have)


# Quest harvest nodes (FUN_0058e580): 0x56a {eid64} starts the "mystical" interactive-object
# particles (FXmystical_IOParticle001fx) on an entity, 0x56b {eid64} stops them. The server
# puts them on the harvest nodes whose item a current quest step still collects.
QUEST_NODE_ON, QUEST_NODE_OFF = 0x56A, 0x56B


def quest_wanted_items(player, have):
    """Item names the current steps of the player's quests still need."""
    out = set()
    for key, prog in getattr(getattr(player, "quests", None), "active", {}).items():
        q = ARGS.content.quests.get(key)
        st = quest.steps(q) if q else []
        if prog["step"] < len(st):
            for name, n in st[prog["step"]].get("collect", {}).items():
                if have(name) < n:
                    out.add(name)
    return out


def refresh_quest_nodes(state, have):
    player = state["player"]
    wanted = quest_wanted_items(player, have)
    lit = state.setdefault("quest_nodes", set())
    lit &= set(player.npcs)               # out of range: the actor (and its effect) is gone
    now = time.time()
    for npc in list(player.npcs.values()):
        on = bool(npc.harvest) and npc.harvest.get("item") in wanted and \
            getattr(npc, "depleted_until", 0) <= now
        if on and npc.entity_id not in lit:
            lit.add(npc.entity_id)
            print(f"  <- quest node: {npc.name} ({npc.entity_id:#x}) for {player.name}")
            quest_node_flag(state, npc, True)
            state["send"](zone.zone_event(QUEST_NODE_ON, struct.pack("<Q", npc.entity_id)))
        elif not on and npc.entity_id in lit:
            lit.discard(npc.entity_id)
            quest_node_flag(state, npc, False)
            state["send"](zone.zone_event(QUEST_NODE_OFF, struct.pack("<Q", npc.entity_id)))


def quest_node_flag(state, npc, on):
    """The client only attaches the particles to a pawn whose m_bShowIOParticle (SGONPCPawn,
    bit 0 of pawn +0xb18) is set (FUN_0058ddf0, checked with winbreak); this player only."""
    if "ue" in state:
        m = zone.npc_update(state, ARGS, npc, {"m_bShowIOParticle": int(on)})
        if m is not None:
            state["send"](m)


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


def give_item(state, name, qty=1, quiet=False, escrow=True):
    """Put a new item in the player's bags. When they are full the item goes to escrow (any
    banker hands it over), or with escrow=False nothing happens and the result is False."""
    player, send = state["player"], state["send"]
    slot = zone.free_bag_slot(player)
    if slot is None and escrow:
        add_escrow(state, name, qty)
        return True
    if slot is None:
        send(client_notice(NO_SPACE))
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


BAG_NOT_EMPTY = "You need to empty that bag first."


def handle_bag_event(state, event, data):
    """Bag management: move / swap / stack (0x92), unstack (0x97) and destroy (0x89)."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE bag event {event:#x}: {data.hex(' ')}")
    if event == zone.MOVE_ITEM and len(data) >= 12:
        handle, container, slot = struct.unpack_from("<iii", data)
        target = zone.move_target(player.items, player.equipment, handle, container, slot)
        if isinstance(target, str):
            send(build_system_text(target, SYSTEM_TEXT_ERROR))
            return
        msgs = zone.move_item(player.items, handle, target)
        for m in msgs or []:
            send(m)
    elif event == zone.UNSTACK and len(data) >= 8:
        result = zone.split_stack(player, *struct.unpack_from("<ii", data))
        if isinstance(result, (str, int)):
            send(zone.item_error(result))
            return
        for m in result:
            send(m)
    elif event == zone.DESTROY_ITEM and len(data) >= 4:
        handle = struct.unpack_from("<i", data)[0]
        item = next((i for i in player.items if i[0] == handle), None)
        if item is None:
            return
        if zone.bag_items(player.items, handle):
            send(build_system_text(BAG_NOT_EMPTY, SYSTEM_TEXT_ERROR))
            return
        if combat.in_combat(player):
            send(client_notice(CANT_DESTROY_IN_COMBAT))
            return
        player.items.remove(item)
        send(zone.zone_event(0x1A5, struct.pack("<iB", handle, 0)))
        send(build_system_text(f"You destroy {item[1]}.", SYSTEM_TEXT_WHITE))
        quest_items_changed(state)
    else:
        return
    save_character_field(player.name, "items", [list(i) for i in player.items])


def sphere_xp(state, which, amount):
    """Crafting / diplomacy XP: level-ups (0x713), the character sheet, and saving."""
    player = state["player"]
    for m in zone.gain_sphere_xp(player, which, amount):
        state["send"](m)
    state["send"](zone.score_message(player))
    save_character_field(player.name, "spheres", player.spheres)


def add_buyback(state, item, price):
    """A sold item shows on the merchant's Buyback tab (the last BUYBACK_SIZE sales)."""
    player = state["player"]
    bb = state.setdefault("buyback", [])
    handle = zone.new_item_id(player) + 500000            # never clashes with bag handles
    while any(b[0] == handle for b in bb):
        handle += 1
    bb.append((handle, item[1], item[2], item[3], max(1, price)))
    out = []
    while len(bb) > merchant.BUYBACK_SIZE:
        out.append(merchant.buyback_removed(bb.pop(0)[0]))
    fields = zone.item_equip_fields(item[1])
    fields["raw"] = {**fields.get("raw", {}), 92: merchant.LOCATION_BUYBACK}
    out.append(zone.zone_event(0x197, vgmsg.inventory_item(handle, item[1], len(bb) - 1, item[2], item[3],
                                                           **fields)))
    out.append(merchant.buyback_price(handle, max(1, price)))
    return out


def buy_back(state, handle):
    """0xe9: buy a sold item back for what it sold for."""
    player = state["player"]
    bb = state.get("buyback", [])
    entry = next((b for b in bb if b[0] == handle), None)
    if entry is None:
        return [merchant.error(merchant.ERR_CANT_SELL)]
    _h, name, icon, qty, price = entry
    if player.coins < price:
        return [merchant.error(merchant.ERR_CANT_AFFORD)]
    slot = zone.free_bag_slot(player)
    if slot is None:
        return [merchant.error(merchant.ERR_NO_SPACE)]
    bb.remove(entry)
    player.coins -= price
    new_id = zone.new_item_id(player)
    player.items.append((new_id, name, icon, qty, slot))
    return [merchant.buyback_removed(handle),
            zone.zone_event(0x197, vgmsg.inventory_item(new_id, name, slot, icon, qty, **zone.item_equip_fields(name))),
            merchant.coins(player.coins)]


# Item conversion (verified live 2026-10-15): items.json "convert": {"count": n, "into":
# [[item, qty], ...]} (up to 3 choices). Right-clicking the item sends 0x1c2 MsgDisplayConversionUI
# {wstr item, i32 count, i32 handle, 3 x {wstr result, i32 qty, i32 kept, i32 0}} (FUN_00507060):
# the Conversion window, "Convert 4 x Copper Ore to:" with one Convert button per choice (a choice
# with qty 0 is hidden; "kept" > 0 adds a second line "<kept> x <item>"). Convert sends 0x9a
# {i32 handle, i32 choice 1-3} (FUN_004fc5b0); Cancel sends nothing.
CONVERSION_UI, CONVERT_REQUEST = 0x1C2, 0x9A


def conversion_ui(item, conv):
    w = lambda s: (s + chr(0)).encode("utf-16-le")
    data = w(item[1]) + struct.pack("<ii", conv["count"], item[0])
    opts = list(conv["into"])[:3]
    for name, qty in opts + [("", 0)] * (3 - len(opts)):
        data += w(name) + struct.pack("<iii", qty, 0, 0)
    return zone.zone_event(CONVERSION_UI, data)


def offer_conversion(state, item):
    conv = ARGS.content.item(item[1])["convert"]
    if item[3] < conv["count"]:
        state["send"](build_system_text(f"You need {conv['count']} {item[1]} to convert them.", SYSTEM_TEXT_ERROR))
        return
    state["send"](conversion_ui(item, conv))


def handle_conversion(state, data):
    player, send = state["player"], state["send"]
    if len(data) < 8:
        return
    handle, choice = struct.unpack_from("<ii", data, 0)
    item = next((i for i in player.items if i[0] == handle), None)
    conv = ARGS.content.item(item[1]).get("convert") if item else None
    if not conv or not 1 <= choice <= len(conv["into"]) or item[3] < conv["count"]:
        send(build_system_text("You can't convert that.", SYSTEM_TEXT_ERROR))
        return
    name, qty = conv["into"][choice - 1]
    if item[3] == conv["count"]:
        player.items.remove(item)
        send(zone.zone_event(0x1A5, struct.pack("<iB", item[0], 0)))
    else:
        player.items[player.items.index(item)] = item[:3] + (item[3] - conv["count"], item[4])
        send(zone.zone_event(0x1AE, struct.pack("<ii", item[0], item[3] - conv["count"])))
    give_item(state, name, qty, quiet=True)
    send(build_system_text(f"You convert {conv['count']} {item[1]} into {qty} {name}.", SYSTEM_TEXT_WHITE))
    save_character_field(player.name, "items", [list(i) for i in player.items])
    quest_items_changed(state)


# Deconstruction (FUN_004f9d50 / FUN_00693980 / FUN_004fcd50): right-clicking an items.json
# "salvage_kit" item gets 0x58d {i32 kit handle}: the client keeps the kit (inventory +0x6c8)
# and puts the cursor in targeting mode 4. Clicking a bag item it allows (not worn; equipment,
# or item fields +0x78/+0x7c/+0x80 above 0; else "This item cannot be deconstructed.") opens
# "Deconstruct: <item>" with two buttons: items sends 0x58e, dust sends 0x58f, both
# {i32 target, i32 kit}. The target goes; items.json "salvage" [[item, qty], ...] (or one
# SALVAGE_DEFAULT) or one SALVAGE_DUST comes back, and the kit loses one charge (stack).
DECONSTRUCT_TARGET, DECONSTRUCT_ITEMS, DECONSTRUCT_DUST = 0x58D, 0x58E, 0x58F
SALVAGE_DEFAULT, SALVAGE_DUST = "Copper Ingot", "Shimmering Dust"


def handle_deconstruct(state, event, data):
    player, send = state["player"], state["send"]
    if len(data) < 8:
        return
    target_h, kit_h = struct.unpack_from("<ii", data, 0)
    target = next((i for i in player.items if i[0] == target_h), None)
    kit = next((i for i in player.items if i[0] == kit_h), None)
    if target is None or kit is None or not ARGS.content.item(kit[1]).get("salvage_kit") or target is kit:
        send(build_system_text("Could not find that item to deconstruct.", SYSTEM_TEXT_ERROR))
        return
    tpl = ARGS.content.item(target[1])
    if zone.bag_items(player.items, target_h) or tpl.get("quest") or "quest" in (tpl.get("flags") or []):
        send(zone.zone_event(DECONSTRUCT_RESULT, struct.pack("<ii", target_h, CANT_DECONSTRUCT)))
        return
    if event == DECONSTRUCT_DUST:
        results = [[SALVAGE_DUST, 1]]
    else:
        results = tpl.get("salvage") or [[SALVAGE_DEFAULT, 1]]
    player.items.remove(target)
    send(zone.zone_event(0x1A5, struct.pack("<iB", target[0], 0)))
    if kit[3] > 1:
        player.items[player.items.index(kit)] = kit[:3] + (kit[3] - 1, kit[4])
        send(zone.zone_event(0x1AE, struct.pack("<ii", kit[0], kit[3] - 1)))
    else:
        player.items.remove(kit)
        send(zone.zone_event(0x1A5, struct.pack("<iB", kit[0], 0)))
    for name, qty in results:
        give_item(state, name, qty, quiet=True)
    got = ", ".join(f"{q} {n}" for n, q in results)
    send(build_system_text(f"You deconstruct {target[1]} into {got}.", SYSTEM_TEXT_WHITE))
    save_character_field(player.name, "items", [list(i) for i in player.items])
    quest_items_changed(state)


# Spyglass (verified live 2026-10-15): items.json "spyglass": {"fov": 20, "seconds": 1} toggles a
# zoom. 0x5c7 {f32 from, f32 to, f32 seconds} (FUN_005e1080) fades the camera field of view
# (90 is the normal view); right-clicking again fades back.
CAMERA_FOV_FADE = 0x5C7
NORMAL_FOV = 90.0                  # the client's default (compared live against fixed views of 85, 90 and 100)


# Fireworks (items.json "fireworks": an ITEM_ABILITIES id, 60002-60022: FIREWORKS_ROCKET_BLUE,
# FIREWORKS_FOUNTAIN_YELLOW, FIREWORKS_SPARKLER_RED ...): right-clicking plays that ability's
# display (0x3d1, docs/ABILITY_VISUALS.md) on the player for everyone in the chunk and uses one up.
# The ability's own Action spawns no emitter in our client (docs/ABILITY_VISUALS.md "Fireworks"),
# so items.json "fireworks_fx" names an emitter class that 0x553 spawns at the player's feet;
# the sparklers (FXspells.FXspells_FireworksCastSparkler..._P001fx) show and keep burning there
# until the chunk is reloaded (no message removes a client-spawned actor).
SPAWN_CLIENT_ACTOR = 0x553


def set_off_fireworks(state, item, ability_id, fx=None):
    player = state["player"]
    msgs = [combat.display_ability(player.char_id, combat.NO_ENTITY, int(ability_id))]
    if fx:
        x, y, z = state.get("position") or player.live_position or player.spawned_at
        msgs.append(zone.zone_event(SPAWN_CLIENT_ACTOR, (fx + "\0").encode("utf-16-le")
                                    + struct.pack("<fff", float(x), float(y), float(z) - 60.0)))
    w = state.get("world")
    for msg in msgs:
        if w is not None:
            w.broadcast(lambda s, m=msg: m)
        else:
            state["send"](msg)
    take_items(state, item[1], 1)


def use_spyglass(state, spec):
    fov, secs = float(spec.get("fov", 20)), float(spec.get("seconds", 1))
    zoomed = not state.get("spyglass")
    state["spyglass"] = zoomed
    a, b = (NORMAL_FOV, fov) if zoomed else (fov, NORMAL_FOV)
    state["send"](zone.zone_event(CAMERA_FOV_FADE, struct.pack("<fff", a, b, secs)))


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
    if stat_id in zone.HARVEST_SKILL_IDS:
        for m in zone.harvest_updates(player):       # the character window's Harvesting tab
            send(m)
        send(zone.score_message(player))              # "Skill N" is read with MsgScore


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
        send(client_notice(NO_SPACE))
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
        if f.get("prestige") and str(fid) not in getattr(player, "factions", {}):
            continue                     # a prestige faction shows once it is unlocked
        state["send"](faction.info(int(fid), f["name"], faction_value(player, fid), bool(f.get("prestige"))))
    state["send"](faction.publish())


def faction_info_request(state, fid):
    """0x35e: the client met a faction id it has no row for; answer 0x35b if it exists."""
    f = ARGS.content.factions.get(str(fid))
    if f is not None and not (f.get("prestige") and str(fid) not in getattr(state["player"], "factions", {})):
        state["send"](faction.info(int(fid), f["name"], faction_value(state["player"], str(fid)),
                                   bool(f.get("prestige"))))
        state["send"](faction.publish())


def adjust_faction(state, fid, delta, quiet=False):
    player = state["player"]
    f = ARGS.content.factions.get(str(fid))
    if f is None or not delta:
        return
    old = faction_value(player, fid)
    new = faction.clamp(old + delta)
    first = f.get("prestige") and str(fid) not in getattr(player, "factions", {})
    if new == old and not first:
        return
    player.factions = dict(getattr(player, "factions", {}), **{str(fid): new})
    save_character_field(player.name, "factions", player.factions)
    if first:
        # Prestige factions (factions.json "prestige": true) stay hidden until the first
        # standing change: 0x35d announces it and adds it to the Prestige Factions list.
        state["send"](faction.unlocked(int(fid), f["name"], new))
        return
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
BUG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bug_reports.json")
QUEST_FEEDBACK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quest_feedback.json")


def submit_quest_feedback(state, data):
    """Quest Feedback window Accept (bugs.QUEST_FEEDBACK), kept per quest for the content editor."""
    try:
        report = bugs.parse_quest_feedback(data)
    except struct.error:
        return
    key = state.pop("feedback_quest", None)
    if report["quest_id"] == -1 and key:
        report["quest_id"] = ARGS.content.quests[key]["id"]
    report.update(quest=key or next((k for k, q in ARGS.content.quests.items() if q["id"] == report["quest_id"]), None),
                  player=state["player"].name)
    n = bugs.save(QUEST_FEEDBACK_FILE, report)
    print(f"  quest feedback #{n}: {report}")
    state["send"](build_system_text("Thank you for your quest feedback.", SYSTEM_TEXT_WHITE))


PLAYER_REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_reports.json")
PLAYER_REPORT_SECONDS = 60          # one report a minute per player (WaitLongerToSubmitPlayerReport)


def submit_player_report(state, data):
    """/report <name> (bugs.PLAYER_REPORT): kept with the chat lines for a GM to read."""
    player, send = state["player"], state["send"]
    now = time.time()
    if now < state.get("next_report", 0):
        send(zone.zone_event(0x0E, struct.pack("<h", bugs.REPORT_WAIT)))
        return
    try:
        report = bugs.parse_player_report(data)
    except struct.error:
        send(zone.zone_event(0x0E, struct.pack("<h", bugs.REPORT_FAILED)))
        return
    report.update(player=player.name, level=player.level)
    n = bugs.save(PLAYER_REPORT_FILE, report)
    state["next_report"] = now + PLAYER_REPORT_SECONDS
    print(f"  player report #{n} from {player.name} about {report['reported']!r} ({len(report['chat'])} chat lines)")
    send(zone.zone_event(0x0E, struct.pack("<h", bugs.REPORT_SUBMITTED)))


def submit_bug_report(state, data):
    """/bug window Submit (bugs.py): keep the report with who and where it was filed."""
    player = state["player"]
    try:
        report = bugs.parse(data)
    except struct.error:
        return
    pos = player.live_position or player.spawned_at or (0.0, 0.0, 0.0)
    report.update(player=player.name, level=player.level, loc=[round(float(c)) for c in pos],
                  target=(player.npcs[player.target].name if player.target in player.npcs else None))
    n = bugs.save(BUG_FILE, report)
    print(f"  bug report #{n} from {player.name}: {report['category']}: {report['description']!r}")
    state["send"](build_system_text(f"Saved as bug report #{n}.", SYSTEM_TEXT_WHITE))
MAILBOX_RANGE = 800


def load_mail():
    """{"next_id": n, "boxes": {lower-case name: [mail dicts]}}"""
    return storage.read_json(MAIL_FILE, {"next_id": 1, "boxes": {}})


def save_mail(db):
    storage.write_json(MAIL_FILE, db)


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
        state["mail_session"] = npc                      # the mailbox (see service_range_check)
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
        if handle != -1 and (it is None or zone.bag_items(player.items, handle)
                             or zone.item_restriction(player, it, "mail")):
            send(mail.result(mail.CANT_MAIL_ITEM))
            return
        if cod and it is None:
            send(build_system_text("Cash on delivery needs an attached item.", SYSTEM_TEXT_ERROR))
            send(mail.result(mail.DB_ERROR))
            return
        cost = mail.POSTAGE * 4 // 5 + (mail.SHIPPING * 4 // 5 if it else 0) + (0 if cod else max(0, copper))
        if player.coins < cost:
            send(client_notice(CANT_AFFORD))
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
        if attached or copper:
            audit("mail", sender=player.name, to=target, item=[attached["name"], attached["qty"]] if attached else None,
                  coins=0 if cod else max(0, copper), cod=max(0, copper) if cod else 0)
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
        if not give_item(state, it["name"], it.get("qty", 1), escrow=False):
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


MARKET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market.json")


def load_market():
    """{"next_id": n, "listings": [{id, seller, name, icon, qty, price, posted}]}"""
    return storage.read_json(MARKET_FILE, {"next_id": market.FIRST_ID, "listings": []})


def save_market(db):
    storage.write_json(MARKET_FILE, db)


def expire_market(db):
    """Listings past their expiry go back to the seller by mail. True if any did."""
    now = time.time()
    old = [x for x in db["listings"] if market.time_left(x) <= now]
    if not old:
        return False
    mdb = load_mail()
    for x in old:
        db["listings"].remove(x)
        deliver_mail(mdb, x["seller"], mail.new(0, "The Market", f"Expired: {x['name']}"[:mail.MAX_SUBJECT],
                                                "Your item did not sell and has been returned.",
                                                item_={"name": x["name"], "icon": x.get("icon", 443),
                                                       "qty": x.get("qty", 1)}, from_player=False))
    save_mail(mdb)
    save_market(db)
    return True


def market_notice(code):
    return zone.zone_event(0x0E, struct.pack("<h", code))


def handle_market_event(state, event, data):
    """Broker (market.py): list items for sale, search, buy (the seller is paid by mail)."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE market event {event:#x}: {data[:24].hex(' ')}")
    db = load_market()
    expire_market(db)
    mine = [x for x in db["listings"] if x["seller"].lower() == player.name.lower()]
    if event == market.OPEN:
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not getattr(npc, "broker", None) or player_distance(player, npc) > 1500:
            return
        if state.get("trade"):
            send(market_notice(0x51))
            return
        state["market"] = npc                            # the broker (see service_range_check)
        send(market.info(npc.broker))
        for m in market.my_listings(mine):
            send(m)
        return
    if event == market.CLOSE:
        state.pop("market", None)
        return
    if not state.get("market"):
        return
    if event == market.SEARCH:
        try:
            name, seller, lo, hi = market.parse_search(data)
            rarity = market.parse_rarity(data)
        except (struct.error, IndexError):
            name, seller, lo, hi, rarity = "", "", 0, 0, None

        def matches(x):
            tpl = ARGS.content.item(x["name"])
            level = tpl.get("level", 1)
            return (name.lower() in x["name"].lower() and seller.lower() in x["seller"].lower()
                    and (lo <= 0 or level >= lo) and (hi <= 0 or level <= hi)
                    and (rarity is None or grouploot.rarity_wire(tpl.get("rarity")) == rarity))
        found = [x for x in db["listings"] if matches(x)]
        for m in market.results(found):
            send(m)
        return
    if event == market.PLACE and len(data) >= 12:
        handle, price = struct.unpack_from("<iq", data)
        it = next((i for i in player.items if i[0] == handle), None)
        if it is None:
            send(market_notice(market.CANT_FIND))
        elif zone.item_restriction(player, it, "market"):
            send(build_system_text(zone.item_restriction(player, it, "market"), SYSTEM_TEXT_ERROR))
        elif price <= 0 or price > market.MAX_PRICE:
            send(market_notice(market.MUST_ENTER_PRICE))
        elif len(mine) >= market.MAX_LISTINGS:
            send(build_system_text("You have too many items on the market.", SYSTEM_TEXT_ERROR))
        elif player.coins < market.deposit(price):
            send(client_notice(CANT_AFFORD))
        else:
            player.coins -= market.deposit(price)
            send(merchant.coins(player.coins))
            save_character_field(player.name, "coins", player.coins)
            player.items.remove(it)
            send(zone.zone_event(0x1A5, struct.pack("<iB", it[0], 0)))
            save_character_field(player.name, "items", [list(i) for i in player.items])
            listing = {"id": db["next_id"], "seller": player.name, "name": it[1], "icon": it[2], "qty": it[3],
                       "price": price, "posted": int(time.time())}
            db["next_id"] += 1
            db["listings"].append(listing)
            save_market(db)
            send(market.listed(listing))
            send(market.clear_price())
            print(f"  {player.name} listed {it[1]} for {price}")
        return
    lid = struct.unpack_from("<i", data, 8 if event in (market.BUY, market.CANCEL) else 0)[0] \
        if len(data) >= (12 if event in (market.BUY, market.CANCEL) else 4) else 0
    listing = next((x for x in db["listings"] if x["id"] == lid), None)
    if listing is None:
        send(market_notice(market.CANT_FIND))
        return
    if event == market.EXAMINE:
        send(market.examined(vgmsg.inventory_item(lid, listing["name"], 0, listing.get("icon", 443),
                                                  listing.get("qty", 1), **zone.item_equip_fields(listing["name"]))))
    elif event == market.RELIST and len(data) >= 12:
        price = struct.unpack_from("<q", data, 4)[0]
        if listing["seller"].lower() != player.name.lower() or not 0 < price <= market.MAX_PRICE:
            send(market_notice(market.MUST_ENTER_PRICE))
            return
        listing["price"] = price
        save_market(db)
        send(market.relisted(listing))
        send(market.clear_price())
    elif event == market.CANCEL:
        if listing["seller"].lower() != player.name.lower():
            return
        db["listings"].remove(listing)
        save_market(db)
        send(market.removed(lid))
        # "The item will be sent to your mailbox." (the client's end-sale confirmation)
        mdb = load_mail()
        deliver_mail(mdb, player.name, mail.new(0, "The Market", f"Unsold: {listing['name']}"[:mail.MAX_SUBJECT],
                                                "Your sale was ended.",
                                                item_={"name": listing["name"], "icon": listing.get("icon", 443),
                                                       "qty": listing.get("qty", 1)}, from_player=False))
        save_mail(mdb)
    elif event == market.BUY:
        cost = listing["price"] + market.commission(listing["price"])
        if listing["seller"].lower() == player.name.lower():
            send(build_system_text("That is your own item; cancel the sale instead.", SYSTEM_TEXT_ERROR))
            return
        if player.coins < cost:
            send(client_notice(CANT_AFFORD))
            return
        player.coins -= cost
        send(merchant.coins(player.coins))
        save_character_field(player.name, "coins", player.coins)
        db["listings"].remove(listing)
        save_market(db)
        send(market.removed(lid))
        # "The item will be sent to your mailbox." (the client's buy confirmation). The
        # client has no text for notice 0x1bd MarketPurchaseSuccess, so print our own.
        send(build_system_text(f"You bought {listing['name']}. It has been sent to your mailbox.",
                               SYSTEM_TEXT_WHITE))
        s = ONLINE.get(listing["seller"].lower())
        if s is not None and s.get("send") and s.get("market"):
            s["send"](market.removed(lid))
        mdb = load_mail()
        deliver_mail(mdb, player.name, mail.new(0, "The Market", f"Bought: {listing['name']}"[:mail.MAX_SUBJECT],
                                                f"You bought {listing['name']} from {listing['seller']}.",
                                                item_={"name": listing["name"], "icon": listing.get("icon", 443),
                                                       "qty": listing.get("qty", 1)}, from_player=False))
        deliver_mail(mdb, listing["seller"], mail.new(0, "The Market", f"Sold: {listing['name']}"[:mail.MAX_SUBJECT],
                                                      f"{player.name} bought your {listing['name']} for "
                                                      f"{listing['price']} copper.", coin=listing["price"],
                                                      from_player=False))
        save_mail(mdb)
        audit("market", buyer=player.name, seller=listing["seller"], item=[listing["name"], listing.get("qty", 1)],
              price=listing["price"], paid=cost)
        print(f"  {player.name} bought {listing['name']} from {listing['seller']} for {cost}")


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
            known = known_action_ids(player)
            set_work_order(state, key)
            send(workorder.select_result(wid, workorder.OK))
            send(workorder.active(wo_record(player, w)))
            send(workorder.needed(w))
            r = ARGS.content.recipes[w["recipe"]]
            send(craft.learn_recipe(r))
            learn_recipe_actions(send, r, known)
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
                sphere_xp(state, zone.CRAFTING, reward["xp"])
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
    r = ARGS.content.recipes[w["recipe"]]
    state["send"](craft.forget_recipe(r))
    # Its step actions too, unless a recipe the player keeps uses the same action.
    kept = {st["action"] for k in zone.book_recipes(ARGS, state["player"]) if k is not r
            for _, _, st in craft.all_steps(k)}
    for _, _, st in craft.all_steps(r):
        if st["action"] not in kept:
            state["send"](craft.forget_action(st["action"]))


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
        config = parley_config(npc, struct.unpack_from("<i", data)[0] if len(data) >= 4 else None)
        if config is None:
            return
        deck, slots = diplomacy_deck(player)
        p = diplomacy.Parley(config, dip["cards"], [c for c in slots if c is not None])
        p.npc = npc
        state["parley"] = p
        for m in diplomacy.deck_messages(dip["cards"], deck, slots, resend=state.get("deck_sent", False)):
            send(m)
        state["deck_sent"] = True
        send(diplomacy.open_parley(npc.entity_id, p))
    elif event in (diplomacy.DECK_LOAD, diplomacy.DECK_CLEAR, diplomacy.SLOT, diplomacy.UNSLOT) and p is not None:
        send(diplomacy.error(diplomacy.ERR_IN_PARLEY))   # the strategy is fixed once a parley starts
    elif event in (diplomacy.DECK_SAVE, diplomacy.DECK_LOAD, diplomacy.DECK_CLEAR):
        deck, slots = diplomacy_deck(player)
        presets = dict(getattr(player, "deck_presets", None) or {})
        n = str(struct.unpack_from("<i", data)[0]) if len(data) >= 4 else ""
        if event == diplomacy.DECK_SAVE:
            presets[n] = list(slots)
            player.deck_presets = presets
            save_character_field(player.name, "deck_presets", presets)
            send(build_system_text(f"Strategy deck {n} saved.", SYSTEM_TEXT_WHITE))
            return
        if event == diplomacy.DECK_LOAD and n not in presets:
            send(build_system_text(f"You have no strategy deck {n}.", SYSTEM_TEXT_ERROR))
            return
        want = [c if c in deck else None for c in presets[n]] if event == diplomacy.DECK_LOAD else []
        want = (want + [None] * len(slots))[:len(slots)]
        for c in slots:
            if c is not None:
                send(diplomacy.unslotted(c))
        for i, c in enumerate(want):
            if c is not None:
                send(diplomacy.slotted(c, i))
        player.diplomacy_slots = want
        save_character_field(player.name, "diplomacy_slots", want)
        if p is not None:
            p.deck = [c for c in want if c is not None]
        send(build_system_text(f"Strategy deck {n} loaded." if n else "Strategy bar cleared.", SYSTEM_TEXT_WHITE))
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
        if event == diplomacy.SLOT and len(data) >= 8 and not 0 <= struct.unpack_from("<i", data, 4)[0] < len(slots):
            send(diplomacy.error(diplomacy.ERR_INVALID_SLOT))
            return
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
            for m in p.tick_refresh():
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
        if player_distance(player, npc) > SERVICE_RANGE:
            send(client_notice(TOO_FAR_AWAY))
            return
        state["banking"] = npc                           # the banker (see service_range_check)
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
        if zone.bag_items(player.items, handle):
            send(build_system_text(BAG_NOT_EMPTY, SYSTEM_TEXT_ERROR))
            return
        if zone.item_restriction(player, it, "bank"):
            send(build_system_text(zone.item_restriction(player, it, "bank"), SYSTEM_TEXT_ERROR))
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


# General abilities (the ability book's General page, verified live 2026-10-15): every
# character has abilities.json entries with "general": true and an "id" (the client's packages
# have no such abilities, so the ids are the server's own). Their record carries wire #34 = 1,
# which puts them on the General page (FUN_00431be0). Kinds: sprint {speed, duration} runs faster
# for a while; recall goes to the bind point; recall_house goes to the character's house.
GENERAL_KINDS = ("sprint", "recall", "recall_house")
GENERAL_HANDLE_BASE = 0x6000


def general_abilities(content):
    """Ability tuples for the general abilities in abilities.json (sorted by id)."""
    out = []
    for name, spec in sorted(content.abilities.items(), key=lambda kv: str(kv[1].get("id", ""))):
        if isinstance(spec, dict) and spec.get("general") and spec.get("id"):
            out.append((GENERAL_HANDLE_BASE + len(out), int(spec["id"]), name, int(spec.get("icon", 443)),
                        spec.get("description", name), float(spec.get("refresh", 0))))
    return out


def house_spot(player):
    """(loc, chunk) by the character's own built house, or None."""
    db = load_housing()
    for pid, st in db.items():
        plot = ARGS.content.plots.get(pid)
        if plot and (st.get("owner") or "").lower() == player.name.lower() and st.get("building") is not None:
            x, y = plot["loc"][0], plot["loc"][1] + 300
            z = ARGS.content.ground_z(plot["chunk"], x, y, ARGS.client_dir) + 50
            return (x, y, z), level_chunk(plot["chunk"])
    return None


def general_ability(state, args, player, spec):
    """Use a general ability; True when it went off (so its refresh starts)."""
    send = state["send"]
    kind = spec["kind"]
    if kind == "sprint":
        player.sprint_until = time.time() + float(spec.get("duration", 45))
        player.sprint_speed = float(spec.get("speed", 1.25))
        state["send"](zone.player_pawn_update(state, args, {"GroundSpeed": ground_speed(player)}))
        send(build_system_text("You start to sprint.", SYSTEM_TEXT_WHITE))
        return True
    if kind == "recall":
        bind = getattr(player, "bind", None)
        if not bind:
            send(build_system_text("You have no bind point. Bind yourself at an altar first.", SYSTEM_TEXT_ERROR))
            return False
        place_player(state, args, (float(bind["loc"][0]), float(bind["loc"][1]), float(bind["loc"][2]) + 50.0),
                     level_chunk(bind["level"]))
        send(build_system_text("You return to your bind point.", SYSTEM_TEXT_WHITE))
        return True
    if kind == "recall_house":
        spot = house_spot(player)
        if spot is None:
            send(build_system_text("You don't have a house to return to.", SYSTEM_TEXT_ERROR))
            return False
        place_player(state, args, spot[0], spot[1])
        send(build_system_text("You return to your house.", SYSTEM_TEXT_WHITE))
        return True
    return False


def sprint_tick(state, args, now):
    player = state.get("player")
    until = getattr(player, "sprint_until", 0) if player is not None else 0
    if until and now >= until:
        player.sprint_until = 0
        if "ue" in state:
            state["send"](zone.player_pawn_update(state, args, {"GroundSpeed": ground_speed(player)}))
        state["send"](build_system_text("You stop sprinting.", SYSTEM_TEXT_WHITE))


def ability_content(ability, overrides):
    """An ability tuple (handle, id, name, icon, description, refresh) with abilities.json's
    "icon", "description" and "refresh" for that name, where given (the class package only has
    the name; placeholders fill the rest)."""
    spec = (overrides or {}).get(ability[2]) or {}
    if not spec:
        return ability
    return (ability[0], ability[1], ability[2], int(spec.get("icon", ability[3])),
            spec.get("description", ability[4]), float(spec.get("refresh", ability[5]))) + tuple(ability[6:])


def learn_ability(state, n, aid, tag):
    """Add a class ability to the book (0x215) and save it."""
    player, send = state["player"], state["send"]
    learned = getattr(player, "learned", [])
    if aid not in learned:
        learned.append(aid)
    player.learned = learned
    ability = ability_content(class_abilities.ability_tuple(n, aid, tag), ARGS.content.abilities)
    ability = (max([a[0] for a in player.abilities] + [0]) + 1,) + ability[1:]
    player.abilities.append(ability)
    send(zone.zone_event(0x215, vgmsg.ability_info(ability[0], aid, ability[2], ability[3],
                                                 ability[4], refresh=ability[5])))
    send(build_system_text(f"You have learned {ability[2]}.", SYSTEM_TEXT_WHITE))
    save_character_field(player.name, "learned_abilities", learned)
    print(f"  {player.name} learned {ability[2]}")


def trains(npc, player):
    """An ability trainer for this player's class: mobs.json "trainer" and, if it has one,
    "trainer_classes" (class names) listing the classes it trains."""
    classes = getattr(npc, "trainer_classes", None) or []
    return bool(npc.trainer) and (not classes or races_classes.class_name(player.klass) in classes)


def handle_trainer_event(state, event, data):
    """Ability trainer (trainer.py): list what the class can learn next, sell it."""
    player, send = state["player"], state["send"]
    print(f"  >>> ZONE trainer event {event:#x}: {data.hex(' ')}")
    learned = getattr(player, "learned", [])
    offers = class_abilities.trainable(ARGS.client_dir, player.klass, learned)
    if event == trainer.START:
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not trains(npc, player):
            return
        if state.get("training"):
            send(trainer.end())         # 0x493 appends: clear the earlier list
        state["training"] = True
        shown = [ability_content(class_abilities.ability_tuple(n, aid, tag), ARGS.content.abilities) + (cost,)
                 for n, aid, tag, cost in offers]
        for m in trainer.begin([(a[1], a[2], a[4], a[3], a[-1]) for a in shown]):
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
            known = known_action_ids(player)
            player.known_recipes = list(getattr(player, "known_recipes", [])) + [key]
            save_character_field(player.name, "known_recipes", player.known_recipes)
            send(craft.learn_recipe(r))
            learn_recipe_actions(send, r, known)
            send(trainer.recipe_result(rid, trainer.OK))
            send(build_system_text(f"You have learned the recipe {r['name']}.", SYSTEM_TEXT_WHITE))
    elif event == trainer.RECIPE_STOP:
        state.pop("recipe_training", None)
        send(trainer.recipe_end())


CIVIC_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "civic.json")


def load_json_file(path, default):
    return storage.read_json(path, default)


def save_json_file(path, data):
    storage.write_json(path, data)


def civic_stats():
    """{stat: value}: every civic stat a parley reward can move (diplomacy.json "civic", at its
    "start" value) with the saved values from civic.json on top."""
    stats = {}
    for parley in ARGS.content.diplomacy.get("parleys", {}).values():
        civ = (parley.get("reward") or {}).get("civic")
        if civ:
            stats.setdefault(civ["stat"], civ.get("start", 50))
    stats.update(load_json_file(CIVIC_FILE, {}))
    return stats


# /citystatus: 0x12d, no payload (FUN_0054cf00 clears the client's civic stats first). The
# stats would fill the CivicDiplomacyStats gamevar, which no window in the shipped UI shows,
# so the server lists them as chat lines (its own wording); with none, the client's own
# "No civic diplomacy here." popup (0x330 code 16).
CITY_STATUS = 0x12D


def city_status(state):
    stats = civic_stats()
    if not stats:
        state["send"](diplomacy.error(diplomacy.NO_CIVIC_STATS))
        return
    for stat, value in sorted(stats.items()):
        state["send"](build_system_text(f"{stat}: {value}", SYSTEM_TEXT_WHITE))


PRESENCE_GAIN = 10                 # presence a won parley adds with the NPC's station (placeholder)


def finish_parley(state, p, result):
    player, send = state["player"], state["send"]
    state.pop("parley", None)
    send(diplomacy.refresh_clear())
    if result == "lost":
        send(diplomacy.lost())
        print(f"  {player.name} lost a parley with {p.npc.name}")
        return
    send(diplomacy.won())
    reward = dict(p.config.get("reward", {}))
    level = (ARGS.content.mobs.get(p.npc.template_id) or {}).get("parley_level")
    if p.config.get("_archive_placeholder") and level:
        # The archive's generic parleys pay for a level-10 NPC; mobs.json "parley_level" (the
        # archive's) scales that (a level-40 parley pays four times as much).
        reward["xp"] = round(reward.get("xp", 0) * int(level) / 10)
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
    sphere_xp(state, zone.DIPLOMACY, reward.get("xp", 0))
    station = (ARGS.content.mobs.get(p.npc.template_id) or {}).get("presence_station")
    if station in zone.PRESENCE_STATS:
        # After a parley the client no longer finds the presence stat for a 0x2d4 (verified live:
        # an update alone left the row unchanged), so 0x2d3 (MsgSingleStatInfo) creates it again
        # with the new value first, then the 0x2d4 refreshes the row.
        # A won parley raises presence with the NPC's station (mobs.json "presence_station", from the
        # archive); PRESENCE_GAIN is a placeholder.
        presence = dict(getattr(player, "presence", None) or {})
        presence[station] = min(zone.PRESENCE_MAX, presence.get(station, zone.PRESENCE_START) + PRESENCE_GAIN)
        player.presence = presence
        save_character_field(player.name, "presence", presence)
        sid = zone.PRESENCE_STATS[station]
        send(zone.zone_event(0x2D3, vgmsg.stat_info(sid, presence[station], category=zone.DIPLOMACY_CATEGORY, kind=2,
                                                    maximum=zone.PRESENCE_MAX,
                                                    raw={1: zone.PRESENCE_INSTANCE + sid})))
        send(zone.zone_event(0x2D4, vgmsg.stat_update(zone.PRESENCE_INSTANCE + sid, presence[station],
                                                      category=zone.DIPLOMACY_CATEGORY,
                                                      maximum=zone.PRESENCE_MAX, raw={12: sid})))
    faction_reward(state, reward)
    if reward.get("flag") and reward["flag"] not in getattr(player, "flags", []):
        # Unlocks dialogue: responses with "requires_flag" equal to this flag now show.
        player.flags = getattr(player, "flags", []) + [reward["flag"]]
        save_character_field(player.name, "flags", player.flags)
        if reward.get("flag_text"):
            send(build_system_text(reward["flag_text"], SYSTEM_TEXT_WHITE))
    if reward.get("civic"):
        # Civic diplomacy: "civic": {"stat": name, "delta": n} moves a server-wide civic value
        # (civic.json, not committed) and tells the player.
        civ = reward["civic"]
        stats = load_json_file(CIVIC_FILE, {})
        stats[civ["stat"]] = stats.get(civ["stat"], civ.get("start", 50)) + civ["delta"]
        save_json_file(CIVIC_FILE, stats)
        send(diplomacy.civic_update(civ["stat"], stats[civ["stat"]], civ["delta"]))
    if reward.get("item"):
        # diplomacy.json "reward": {"item": name or [name, qty]}: every win (the bag must have room).
        name, qty = (reward["item"], 1) if isinstance(reward["item"], str) else reward["item"]
        if give_item(state, name, qty):
            quest_items_changed(state)
    print(f"  {player.name} won a parley with {p.npc.name}")


def known_action_ids(player):
    """Crafting action ids the player already has from the recipes in their book."""
    return {st["action"] for r in zone.book_recipes(ARGS, player) for _, _, st in craft.all_steps(r)}


def learn_recipe_actions(send, r, known):
    """A recipe learned during play: its actions, announcing the ones that are new
    ("New action acquired: Hammer"), then its complication counters."""
    for n, (_, _, st) in enumerate(craft.all_steps(r)):
        send(craft.learn_action(r, n, announce=st["action"] not in known))
        known.add(st["action"])
    for c in r.get("complications", []):
        send(craft.learn_counter(c))


# Using an object (FUN_0054a680): 0x3ca {u8 code} prints 1 "You are already using an object.",
# 2 "That object is already in use.", 3 "You are too far away.", 6 "You cannot do that while
# resting.", 7 "You cannot do that while flying." (4 and 5 print nothing).
OBJECT_USE_ERROR = 0x3CA
USE_BUSY, USE_TAKEN, USE_TOO_FAR, USE_RESTING, USE_FLYING = 1, 2, 3, 6, 7


def object_use_refusal(state):
    """Why the player can't start using a station now (an 0x3ca code), or 0."""
    player = state["player"]
    if (state.get("craft") or {}).get("begun") or state.get("harvest") or state.get("assembling"):
        return USE_BUSY
    if getattr(player, "flying", False):
        return USE_FLYING
    if getattr(player, "resting", False):
        return USE_RESTING
    return 0


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
        if combat.in_combat(player):
            send(client_notice(FINISH_COMBAT_BEFORE_CRAFTING))
            return
        refusal = object_use_refusal(state)
        if refusal:
            send(zone.zone_event(OBJECT_USE_ERROR, struct.pack("<B", refusal)))
            return
        npc = player.npcs.get(player.target) if player.target else None
        if npc is None or not npc.station:
            send(craft.station_error(craft.STATION_INVALID))
            return
        if player_distance(player, npc) > craft.STATION_RANGE:
            send(craft.station_error(craft.STATION_TOO_FAR))
            return
        state["craft"] = {"recipe": None, "begun": False}
        kind = "finishing" if npc.station == "finishing" else "refining"
        send(craft.station_recipes([r["id"] for r in zone.book_recipes(ARGS, player)
                                    if (r.get("kind") or "refining") == kind]))
        send(craft.open_window())
    elif session is None:
        return
    elif event in (craft.CANCEL, craft.CANCEL2):
        state.pop("craft", None)
        send(craft.end())
    elif event == craft.SELECT:
        r = recipe_by_id(struct.unpack_from("<i", data, 0)[0])
        if r is None or r not in zone.book_recipes(ARGS, player):
            send(craft.recipe_result(0, 0))
        elif not has_inputs(player, r):
            send(craft.recipe_result(craft.RECIPE_MISSING, r["id"]))
        else:
            session.update(recipe=r, begun=False)
            send(craft.table_items(craft_table(player, r)))
            send(craft.recipe_result(craft.RECIPE_OK, r["id"]))
    elif event == craft.CONFIRM and session["recipe"]:
        send(craft.workbench())
    elif event == craft.AUTO_FILL:
        send(craft.auto_fill(True))
    elif event == craft.BACK and not session.get("begun"):
        session["recipe"] = None
        send(craft.back_to_recipes())
    elif event == craft.BEGIN and session["recipe"]:
        session.update(begun=True, stage=0, done=set(), ap=0, quality=500, comp=None, had_comp=False,
                       catalyst_used=False)
        for m in craft.started(session["quality"]):
            send(m)
        for sid in craft.missing_steps(session["recipe"], {i[1] for i in player.items}, 0):
            send(craft.step_flag(sid))
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


def craft_table(player, r):
    """Table Setup entries: utilities (and tools) from the bags under the steps that use them,
    the catalyst under -2."""
    out = []
    for n, _si, st in craft.all_steps(r):
        for need in (st.get("utility", {}).get("item"), st.get("tool")):
            out += [(i[0], craft.step_id(r, n), True) for i in player.items if need and i[1] == need]
    cat = r.get("catalyst", {}).get("item")
    out += [(i[0], -2, True) for i in player.items if cat and i[1] == cat]
    return out


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
    util = st.get("utility")
    if util and have_items(player)(util["item"]) < util.get("qty", 1):
        send(craft.rejected(craft.MISSING_ITEM, util["item"]))   # "Missing item: <utility>"
        return
    if session["ap"] + st.get("ap", 20) > max_ap:
        send(craft.rejected(6))
        return
    if util:
        take_items(state, util["item"], util.get("qty", 1))
        send(build_system_text(f"You use {util['item']}.", SYSTEM_TEXT_WHITE))
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
        done_name, next_name = craft.stages(r)[si][0], craft.stages(r)[si + 1][0]
        if done_name and next_name:
            send(craft.banner(f"{done_name} complete. Next: {next_name}"))
        for m in craft.next_stage(si + 1):
            send(m)
        for sid in craft.missing_steps(r, {i[1] for i in state["player"].items}, si + 1):
            send(craft.step_flag(sid))
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
        send(client_notice(NO_SPACE))
        send(craft.end())
        return
    for name, need in r["inputs"].items():
        take_items(state, name, need)
    name = r["output"]
    if give_item(state, name, quiet=True):
        send(build_system_text(f"You create {name}.", SYSTEM_TEXT_WHITE))
        quest_items_changed(state)
    send(combat.experience_reward(r.get("xp", 50), player.char_id, kind=1))
    sphere_xp(state, zone.CRAFTING, r.get("xp", 50))
    send(craft.end())
    print(f"  {player.name} crafted {name}")


def played_seconds(player):
    return int(getattr(player, "played", 0) + time.time() - getattr(player, "session_start", time.time()))


def kick_other_session(state, args):
    """The character of this new zone login is already playing on another connection (a second
    client, or a crashed one the server hasn't timed out yet): end that one, so one character
    never runs twice. A chunk handoff keeps its session and is not a second login."""
    name = state["player"].name.lower()
    old = ONLINE.get(name)
    if old is None or old is state or old.get("closed") or old.get("session") == state.get("session"):
        return False
    print(f"  {state['player'].name} logged in again: closing the older connection")
    close_session(old, args)
    return True


def close_session(old, args):
    """End a zone connection: out of the world, then UdpLibrary Terminate (the client goes back to
    character select)."""
    leave_world(old, args)
    old["closed"] = True
    if callable(old.get("terminate")):
        try:
            old["terminate"]()
        except OSError:
            pass


def release_character(name, args):
    """Before a Play builds a character from its saved record: close any connection still playing
    it and forget any earlier Play nobody claimed, so no stale copy can come back later and save
    old items or coins over newer ones (an item duplication)."""
    old = ONLINE.get(name.lower())
    if old is not None and not old.get("closed"):
        print(f"  {name} is already playing: closing that connection before Play")
        close_session(old, args)
    for key, p in list(PENDING_PLAYERS.items()):
        if getattr(p, "name", "").lower() == name.lower():
            PENDING_PLAYERS.pop(key, None)


def leave_world(state, args):
    """A zone connection ended: remove the player from its chunk and close its
    pawn on everyone else's client."""
    if state.get("player") is not None and getattr(state["player"], "pet", None) is not None:
        dismiss_pet(state, dust=False)
    if state.get("player") is not None and not state.get("handoff"):
        p = state["player"]
        p.played = played_seconds(p)
        p.session_start = time.time()
        save_character_field(p.name, "played", p.played)
        save_character_field(p.name, "last_logout", int(time.time()))
        c = caravan_of(p.name)
        if c is not None:
            caravan_location(c)
            cs = load_caravans()
            for x in cs:
                if x["leader"] == c["leader"]:
                    x["loc"] = c.get("loc")
            save_caravans(cs)
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
    world.grid_remove(state)
    for npc in w.npcs.values():
        npc.hate.pop(player.char_id, None)
        if npc.aggro_on is player:
            npc.aggro_on = combat.next_target(npc)
            if npc.aggro_on is None:
                combat.give_up(npc)          # nobody left: walk home and heal
    w.broadcast(lambda s: zone.close_actor(s, player.char_id))
    print(f"  {player.name} left {w.level}")


def serve(sock, server, data, addr, clients, args):
    if True:
        if not getattr(args, "quiet_packets", False):
            stamp = time.strftime("%H:%M:%S")
            print(f"\n[{stamp}] {server} {addr[0]}:{addr[1]} -> {len(data)} bytes")
            print(hexdump(data))
            describe(data)
        key = (server, addr)

        if len(data) >= 14 and data[0] == 0 and data[1] == 0x01:
            protocol, code, max_raw = struct.unpack_from(">III", data, 2)
            name = data[14:].split(b"\0", 1)[0].decode("latin-1")
            print(f"  connect: protocol={protocol} code=0x{code:08x} maxRaw={max_raw} name={name!r}")
            old = clients.get(key)
            if old is not None and server == "ZONE" and old.get("player") is not None:
                leave_world(old, args)          # a new connection from the same address replaces it
            clients[key] = {"out_seq": 0, "max_raw": max(MIN_RAW_PACKET, min(max_raw, MAX_RAW_PACKET)),
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
            gone = clients.pop(key, None)
            print(f"  client disconnected, reason {reason} ({DISCONNECT_REASONS.get(reason, '?')}); "
                  f"{(gone or {}).get('out_seq', 0)} reliable packets sent, {(gone or {}).get('resent', 0)} resent")
            if gone and server == "ZONE":
                leave_world(gone, args)
        else:
            state = clients.setdefault(key, {"out_seq": 0, "max_raw": 512})
            if state.get("closed"):
                return                         # replaced by a newer login; dropped next tick
            state["last_seen"] = time.time()
            handle_acks(state, data)
            if server == "ZONE" and "send" not in state:
                state["send"] = lambda m, sock=sock, addr=addr, state=state: (
                    send_message(sock, addr, state, m) if m is not None else None)
            for kind, seq, payload in reliable_messages(data):
                for message in receive_reliable(sock, addr, state, kind, seq, payload,
                                                quiet=getattr(args, "quiet_packets", False)):
                    if not allow_message(state, message, args):
                        continue
                    try:
                        handle_message(sock, server, addr, state, message, args)
                    except struct.error as e:
                        # A client message shorter than its handler expects.
                        print(f"  >>> malformed message ({e}): {message[:64].hex(' ')}")
                    except Exception:
                        # A bug in one handler must not take the server down for everyone.
                        print(f"  >>> handler error for {message[:16].hex(' ')}")
                        traceback.print_exc()


# Flood limits. A real client sends a few dozen messages a second (moves, pings, clicks); a
# connection far over that is broken or hostile. Its extra messages are dropped, and one that
# stays over the limit for FLOOD_KICK_SECONDS is disconnected. Chat (say, shout, tell...) has its
# own, tighter limit, since every line goes to many players.
MSG_RATE, MSG_BURST = 300.0, 600.0
CHAT_RATE, CHAT_BURST = 5.0, 10.0
FLOOD_KICK_SECONDS = 10.0
CHAT_EVENTS = (0x74,)            # zone say; world type 6 slash commands (shout, tell, ...) too


def take_token(state, key, rate, burst, now):
    tokens, last = state.get(key, (burst, now))
    tokens = min(burst, tokens + (now - last) * rate)
    if tokens < 1.0:
        state[key] = (tokens, now)
        return False
    state[key] = (tokens - 1.0, now)
    return True


def allow_message(state, message, args):
    """False to drop this client message (flood limits above)."""
    now = time.time()
    if not take_token(state, "msg_bucket", MSG_RATE, MSG_BURST, now):
        # Seconds in a row with drops: a client held at the limit keeps some messages getting
        # through, so "since the first drop" would reset all the time.
        second = int(now)
        if state.get("flood_second") != second:
            state["flood_run"] = state.get("flood_run", 0) + 1 if state.get("flood_second") == second - 1 else 1
            state["flood_second"] = second
        state["flood_drops"] = state.get("flood_drops", 0) + 1
        if state["flood_run"] > FLOOD_KICK_SECONDS and not state.get("closed"):
            who = state["player"].name if state.get("player") is not None else "a connection"
            print(f"  !!! flood: {who} sent too many messages for {FLOOD_KICK_SECONDS:.0f} s; disconnected "
                  f"({state['flood_drops']} dropped)")
            if state.get("player") is not None and "ue" in state:
                close_session(state, args)
            else:
                state["closed"] = True
                if callable(state.get("terminate")):
                    state["terminate"]()
        return False
    is_chat = len(message) >= 6 and (
        (struct.unpack_from("<H", message, 0)[0] == 2 and struct.unpack_from("<I", message, 2)[0] in CHAT_EVENTS)
        or struct.unpack_from("<H", message, 0)[0] == 6)
    if is_chat and not take_token(state, "chat_bucket", CHAT_RATE, CHAT_BURST, now):
        if now - state.get("chat_warned", 0) > 2 and callable(state.get("send")):
            state["chat_warned"] = now
            state["send"](build_system_text("You are sending messages too quickly.", SYSTEM_TEXT_ERROR))
        return False
    return True


BACKUP_DUE = [0.0]               # next automatic database backup (the first one at start)
STATUS_SECONDS = 600            # a status line in the log this often
STATUS = [0.0, 0, 0.0]           # next status time, packets read, busy seconds since the last line
LOOP_STATS = [0, 0.0]            # packets read, seconds idle in select (this second)
PING_AGE = [0.0]                 # oldest load-test ping read this second (seconds in transit)


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


def place_new_character(char, raw):
    """Put a new character in the starting chunk its create request asked for (the Isle of Dawn or
    the race's home town), beside that area's anchor (start_areas.py). Leaves it unset (the camp)
    for anything else; --camp-start skips this altogether."""
    chunk = start_areas.start_chunk(raw)
    if chunk is None or not chunk_exists(*chunk):
        return
    char["chunk"] = list(chunk)
    spot = start_areas.start_position(ARGS.content, chunk, chunk_name(*chunk), ARGS.client_dir, zone.SPAWN_Z_LIFT)
    if spot is not None:
        char["position"], char["position_chunk"] = spot, list(chunk)
    print(f"  >>> new character starts in {start_areas.STARTS[chunk]} {chunk_name(*chunk)} at {spot}")


def character_chunk(char):
    """The saved chunk, or the default start if that chunk has no map (a bad save must not
    leave a character that can never log in again)."""
    chunk = tuple(char.get("chunk", DEFAULT_CHUNK))
    return chunk if chunk_exists(*chunk) else DEFAULT_CHUNK


_MAPS = None


def chunk_exists(cx, cy):
    """Whether the client has a map for chunk (cx, cy) (Assets/Maps/chunk_<x>_<y>.vgr)."""
    global _MAPS
    if _MAPS is None:
        client_dir = getattr(ARGS, "client_dir", None) or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        try:
            _MAPS = {f.lower() for f in os.listdir(os.path.join(client_dir, "Assets", "Maps"))}
        except OSError:
            return True                 # no map folder to check against (unit tests)
    return (chunk_name(cx, cy) + ".vgr").lower() in _MAPS


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
    # as the character's name); +0x130 unknown; +0x248 the access (GM) level: the client
    # offers a command only when its table row's level byte is <= this (FUN_005feba0;
    # /summonplayer needs 5, /gotoplayer 10, /chunk 20). characters.json "access_level".
    rec = bytearray(0x24C)
    rec[0x000:0x080] = wfield(char["first"], 0x80)
    rec[0x080:0x0e0] = wfield(char.get("last", ""), 0x60)
    rec[0x0e0:0x130] = wfield(char.get("world", WORLD_NAME), 0x50)
    rec[0x1b0:0x230] = wfield(char["first"], 0x80)
    struct.pack_into("<Q", rec, 0x230, character_id(char))
    struct.pack_into("<i", rec, 0x248, max(0, min(255, int(char.get("access_level", 0)))))
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
    struct.pack_into("<I", rec, 0x1a0, character_gender(char))   # obj+0x94; 1 = the female preview (verified live)
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
    # race at +7, class at +8. Default to Thestran Warrior when unknown. A race
    # change item saves "race" over it.
    raw = bytes.fromhex(char.get("raw", ""))
    if len(raw) > 8:
        return char.get("race", raw[7]), raw[8]
    return char.get("race", 0x0E), 0x1C


def character_gender(char):
    # MsgClientCharacterCreate (schema FUN_004896a0): wstr first, last, world, wstr,
    # i32, u8 gender, u8 race, u8 class, i32, i32, 64 x u8 sliders. After the names
    # that puts gender at raw +6 (0 male, 1 female). A gender change saves "gender".
    raw = bytes.fromhex(char.get("raw", ""))
    return char.get("gender", raw[6] if len(raw) > 6 else 0)


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


def account_characters(account):
    """The characters belonging to an account (characters.json "account")."""
    return storage.read_characters(CHARACTERS_FILE, account) if account is not None else []


def send_account_character_list(sock, addr, state):
    chars = account_characters(state.get("account"))
    n = send_message(sock, addr, state, build_account_character_list(chars))
    names = ", ".join(c["first"] for c in chars) or "none"
    print(f"  <- sent account character list 0x66 ({names}) ({n} packets)")


CHARACTERS_FILE =os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters.json")


def load_character(name, ignore_case=False):
    """One saved character by first name (None if there is none)."""
    return storage.read_character(CHARACTERS_FILE, name, ignore_case)


def load_characters():
    return storage.read_characters(CHARACTERS_FILE)


def save_character_position(name, loc):
    def move(c):
        c["position"] = list(loc)
        c["position_chunk"] = list(character_chunk(c))
    storage.update_character(CHARACTERS_FILE, name, move)


def save_character_progress(name, level, xp):
    storage.update_character(CHARACTERS_FILE, name, {"adventure_level": level, "adventure_xp": xp})


def save_character_field(name, field, value):
    storage.update_character(CHARACTERS_FILE, name, {field: value})


def save_characters(chars):
    storage.write_characters(CHARACTERS_FILE, chars)


# The most recent world-server / login-server connections, so each side can push
# messages to the other (character records, refreshed account lists).
WORLD_CONN = {}
# Characters chosen with Play, by session key, until their zone connection logs in.
PENDING_PLAYERS = {}
LOGIN_CONN = {}
LOGIN_BY_KEY = {}      # session key issued at login -> (sock, addr, state) of that login connection


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
        loc = tuple(cur[i] if w == "~" else 0.0 if w == "g" else float(w) for i, w in enumerate(words[1:4]))
        if words[3] == "g":
            # "g": stand on the terrain at x, y (z = ground + 100).
            gz = ARGS.content.ground_z(player.level, loc[0], loc[1], ARGS.client_dir)
            loc = (loc[0], loc[1], (gz if gz is not None else cur[2]) + 100.0)
        print(f"  <- dev: teleport to {loc}")
        if len(words) >= 5:
            # !tp x y z yaw: also turn (0 = +x, 16384 = +y, 32768 = -x, 49152 = -y) via 0x3e5.
            return [zone.player_teleport(loc, (0, int(words[4]) & 0xFFFF, 0))]
        return [("pawn_update", None, {"Location": loc, "Velocity": (0.0, 0.0, 0.0)})]
    if words[0] == "ctext" and player:
        # !ctext [kind] [heal] [self]: try the client-built combat text (0x27b).
        kind = int(words[1]) if len(words) > 1 else 1
        heal = len(words) > 2 and words[2] == "1"
        target = player.char_id if len(words) > 3 or not player.target else player.target
        return [effects.combat_text(player.char_id, target, "Test Strike", 12, heal=heal, kind=kind)]
    if words[0] == "plot" and player:
        # !plot [id]: inspect a plot as if its sign were right-clicked (testing).
        return [("housing", housing.INSPECT, struct.pack("<ii", 1, int(words[1]) if len(words) > 1 else 101))]
    if words[0] == "chest" and player and len(words) > 1:
        # !chest <fixture n> [put <bag handle> [count slot] | take <item handle> [count] | close]:
        # the chest's menu and drags (testing).
        cid = housing.FIXTURE_ID_BASE + int(words[1])
        if "put" in words:
            at = words.index("put")
            h, n, s = (list(map(int, words[at + 1:at + 4])) + [-1, -1])[:3]
            return [("housing", housing.CHEST_DEPOSIT, struct.pack("<iiii", cid, h, n, s))]
        if "take" in words:
            at = words.index("take")
            h, n = (list(map(int, words[at + 1:at + 3])) + [-1])[:2]
            return [("housing", housing.CHEST_WITHDRAW, struct.pack("<iiiii", cid, h, n, -1, 0))]
        if "move" in words and len(words) >= 6:
            # !chest <n> move <item handle> <count, -1 = all> <slot>: a drag inside the chest.
            return [("housing", housing.CHEST_MOVE, struct.pack("<iiii", cid, *map(int, words[-3:])))]
        if "close" in words:
            return [("housing", housing.CHEST_CLOSE, struct.pack("<i", cid))]
        if "manage" in words:
            return [("housing", housing.CHEST_MANAGE, struct.pack("<i", cid))]
        if "perm" in words and len(words) >= 5:
            # !chest <n> perm <slot 0 view / 1 deposit / 2 withdraw> <1 all players / 0 nobody>
            return [("housing", housing.CHEST_PERMISSION, struct.pack("<iiiiIBB", cid, int(words[3]), 0,
                                                                      0, 0, int(words[4]), 0) + bytes(2))]
        return [("housing", housing.CHEST_OPEN, struct.pack("<i", cid))]
    if words[0] == "fishbite" and player:
        # !fishbite: as if the bobber landed in water (testing where there is no water).
        return [("fishev", fishing.BOBBER, struct.pack("<fff", 0, 0, 0))]
    if words[0] == "ui" and len(words) > 1:
        # !ui <window name>: toggle a client window (0x598 SGOUI toggle), e.g. !ui Social (testing).
        return [zone.zone_event(0x598, (f'SGOUI toggle "{" ".join(words[1:])}"' + chr(0)).encode("utf-16-le"))]
    if words[0] == "cev" and player and len(words) > 1:
        # !cev <event id> [values...]: handle a client zone event as if the client sent it;
        # values are i32, s:text (wstr, _ = space) or b:N (byte), e.g. !cev 0x479 101 2.
        def token(w):
            if w.startswith("s:"):
                return (w[2:].replace("_", " ") + "\0").encode("utf-16-le")
            if w.startswith("b:"):
                return bytes([int(w[2:], 0)])
            return struct.pack("<I", int(w, 0) & 0xFFFFFFFF)
        return [("cev", int(words[1], 0), b"".join(token(w) for w in words[2:]))]
    if words[0] == "groupinfo" and player:
        # !groupinfo: your group or raid: size, leader and how many are in each raid group.
        g = getattr(player, "group", None)
        if g is None:
            return [build_system_text("You are not in a group.", SYSTEM_TEXT_WHITE)]
        subs = {}
        for m in g.members:
            subs[g.sub.get(m.char_id, 0)] = subs.get(g.sub.get(m.char_id, 0), 0) + 1
        return [build_system_text(f"{'Raid' if g.raid else 'Group'} of {len(g.members)} led by {g.leader.name}; "
                                  f"raid groups: " + ", ".join(f"{k + 1}: {v}" for k, v in sorted(subs.items())),
                                  SYSTEM_TEXT_WHITE)]
    if words[0] == "netstats" and player:
        # !netstats: reliable packets sent to this connection, resent, and waiting for an ack.
        return [("netstats",)]
    if words[0] == "spherexp" and player and len(words) > 2:
        # !spherexp <1 crafting | 2 diplomacy> <amount>: gain sphere XP (testing level-ups).
        return [("spherexp", int(words[1]), int(words[2]))]
    if words[0] == "pet" and player and len(words) > 1:
        # !pet <item name>: summon the pet of a pet item without the item (testing).
        spec = ARGS.content.item(" ".join(words[1:])).get("pet")
        return [("pet", spec)] if spec else []
    if words[0] == "react" and player:
        # !react: activate the newest open reaction, as clicking it (0x145) (testing).
        return [("react",)]
    if words[0] == "kill" and player:
        # !kill: one hit that kills the target (testing loot and kill rewards).
        return [("kill",)]
    if words[0] == "lootmode" and player and len(words) > 1:
        # !lootmode <0-4> [rarity 0-6] [split]: as the leader's loot options popup (0xb6) (testing).
        r = grouploot.RARITIES[int(words[2])] if len(words) > 2 else grouploot.DEFAULT_RARITY
        return [("lootev", grouploot.SET_MODE, struct.pack("<Qi", player.char_id, int(words[1]))
                 + (r + "\0").encode("utf-16-le") + bytes([len(words) > 3 and words[3] == "split", 0]))]
    if words[0] == "roll" and player and len(words) > 1:
        # !roll need|greed|pass: answer the group loot roll popup (testing).
        return [("lootev", grouploot.PASS, b"") if words[1] == "pass"
                else ("lootev", grouploot.NEED_GREED, bytes([words[1] == "need"]))]
    if words[0] == "mentorme" and player and len(words) > 1:
        # !mentorme <member>: as the group window's "Request Mentor" menu (0x5c8) (testing).
        return [("mentorev", group.MENTOR_REQUEST, (words[1] + "\0").encode("utf-16-le"))]
    if words[0] == "deftarget" and player and len(words) > 1:
        # !deftarget <player>: as clicking a friendly player (0x5c), e.g. before /duel (testing).
        s = ONLINE.get(words[1].lower())
        return [("duelev", duel.DEFENSIVE_TARGET, struct.pack("<Q", s["player"].char_id))] if s else []
    if words[0] == "title" and player and len(words) > 1:
        # !title <id>: grant a title (testing).
        return [("title", int(words[1]))]
    if words[0] == "upkeep" and player and len(words) > 1:
        # !upkeep <copper>: deposit into plot 101's upkeep bank, as the Admin tab does (testing).
        return [("housing", housing.UPKEEP_DEPOSIT, struct.pack("<ii", 101, int(words[1])))]
    if words[0] == "pickup" and player and len(words) > 1:
        # !pickup <fixture n>: as the fixture's Pick Up menu (0x462) (testing).
        return [("housing", housing.PICK_UP, struct.pack("<i", housing.FIXTURE_ID_BASE + int(words[1])))]
    if words[0] == "house" and player:
        # !house [prefab] [type]: spawn a housing object 800 units north of you (testing).
        prefab = words[1] if len(words) > 1 else "Ra6001_P1_C1_Grid_PHcity01_Home001root001_lvl10_ver1"
        kind = int(words[2]) if len(words) > 2 else zone.HOUSE_BUILDING
        return [("house", prefab, kind)]
    if words[0] == "mount" and player:
        # !mount [id] [fly]: ride mount id (default 1000); !mount 0 dismounts (testing).
        # !mount 1000 b5: with barding 5 (testing).
        mid = int(words[1]) if len(words) > 1 else 1000
        barding = next((int(w[1:]) for w in words[2:] if w[:1] == "b" and w[1:].isdigit()), None)
        player.barding_test = barding
        return [("mount", mid or None, zone.MOUNT_FLYING if "fly" in words else zone.MOUNT_GROUND)]
    if words[0] == "cc" and player and len(words) > 1 and words[1] in ("stun", "root", "fear"):
        # !cc stun|root|fear [seconds]: be stunned, rooted or feared (by your target) as if by an NPC (testing).
        return [("cc", words[1], float(words[2]) if len(words) > 2 else 4.0)]
    if words[0] == "parleywin" and player:
        # !parleywin: win the open parley at once (testing its rewards).
        return [("parleywin",)]
    if words[0] == "rezme" and player:
        # !rezme: Veyla offers to resurrect you (testing the dialog).
        return [("rezme",)]
    if words[0] == "call" and len(words) >= 2 and player:
        # !call <name>: offer to summon a player (0x270 Call Confirmation; testing).
        return [("callpc", " ".join(words[1:]))]
    if words[0] in ("goto", "summon") and len(words) >= 2 and player:
        # !goto <name> / !summon <name>: the server side of /gotoplayer and /summonplayer.
        return [("gm", GM_GOTO if words[0] == "goto" else GM_SUMMON, (words[1] + "\0").encode("utf-16-le"))]
    if words[0] == "visit" and len(words) >= 2 and player:
        # !visit <NPC name>: travel next to the first spawn of an NPC with that name, in any
        # chunk (testing and GMs: e.g. !visit Ghobad Houri).
        return [("visit", " ".join(words[1:]))]
    if words[0] == "chunk" and len(words) >= 3 and player:
        # !chunk x y: travel to that chunk's centre (the server side of /chunk).
        return [("gm", GM_CHUNK, struct.pack("<ii", int(words[1]), int(words[2])))]
    if words[0] in ("setupall", "maxskills", "learnall") and player:
        # !setupall <level> / !maxskills / !learnall: the GM test tools on yourself.
        ev = {"setupall": GM_SETUP_ALL, "maxskills": GM_MAX_SKILLS, "learnall": GM_LEARN_ALL}[words[0]]
        data = struct.pack("<Q", player.char_id)
        if ev == GM_SETUP_ALL:
            data += struct.pack("<i", int(words[1]) if len(words) > 1 else zone.LEVEL_CAP)
        return [("gm", ev, data)]
    if words[0] == "hide" and player:
        # !hide: toggle GM invisibility (the server side of /hideme).
        return [("gm", GM_HIDE, bytes([3]))]
    if words[0] == "die" and player:
        # !die: drop dead on the spot (testing death, release and resurrection).
        return [("die",)]
    if words[0] == "tombstone" and player:
        # !tombstone: leave your tombstone at your feet (testing).
        return [("tombstone",)]
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
    if words[0] == "forms" and player:
        # !forms [class]: the combat forms of a class (default Psionicist) whatever your class (testing).
        player.forms = forms.class_forms(ARGS.content.forms.get(" ".join(words[1:]) or "Psionicist", {}))
        return forms.form_list(player.forms) + [forms.current(-1)] + zone.ability_messages(player)
    if words[0] == "fishcatch" and player and len(words) > 1:
        # !fishcatch <fish>: count a catch as if landed with the rod (testing the Fishing achievements).
        return [("fishcatch", " ".join(words[1:]))]
    if words[0] == "npclist" and player:
        # !npclist [radius]: the GM NPC list (0x786) of the NPCs near you, nearest first. The
        # EncounterDBId is the spawn's index in content/spawns/<chunk>.json, the tag its mob key.
        radius = float(words[1]) if len(words) > 1 else 3000.0
        pos = player.live_position or player.spawned_at or (0.0, 0.0, 0.0)
        near = sorted(((math.hypot(n.location[0] - pos[0], n.location[1] - pos[1]), n) for n in player.npcs.values()
                       if math.hypot(n.location[0] - pos[0], n.location[1] - pos[1]) <= radius),
                      key=lambda t: t[0])
        rows = [(n.name, str(n.template_id or ""), getattr(n, "level", 1),
                 n.entity_id - zone.SPAWN_EID_BASE if 0 <= n.entity_id - zone.SPAWN_EID_BASE < 0x100000 else -1,
                 n.location) for _, n in near[:40]]
        return [zone.npc_list(rows)]
    if words[0] == "songs" and player:
        # !songs: learn the Bard's song parts whatever your class, and open the Song window (testing).
        player.song_parts = songs.part_abilities(ARGS.content.songs.get("Bard", {}))
        return ([m for m in zone.ability_messages(player)] + [songs.slots()]
                + [songs.compose(n + 1, s) for n, s in enumerate(getattr(player, "songs", []))]
                + [songs.now_playing(""), zone.zone_event(0x598, ('SGOUI toggle "Song"' + chr(0)).encode("utf-16-le"))])
    if words[0] == "lfm" and player:
        # !lfm: list yourself on the Find window's LFG page without being a group leader (testing).
        player.lfm = not getattr(player, "lfm", False)
        return []
    if words[0] == "questreset" and len(words) == 2 and player:
        # !questreset <key>: forget a quest so it can be taken again (testing).
        player.quests.done.discard(words[1])
        player.quests.active.pop(words[1], None)
        save_character_field(player.name, "quests", player.quests.to_json())
        return []
    if words[0] == "spawn" and len(words) >= 2 and player:
        # !spawn <mob key> [wander radius]: builder mode, place a mob at your feet and save it
        # to content/spawns/<chunk>.json (docs/CONTENT_EDITOR.md "In-game builder").
        return [("build_spawn", words[1], int(words[2]) if len(words) > 2 else 0)]
    if words[0] in ("wander", "respawn") and len(words) >= 2 and player:
        # !wander <radius> / !respawn <seconds>: builder mode, on the targeted spawned NPC.
        return [("build_edit", words[0], int(words[1]))]
    if words[0] == "path" and len(words) >= 2 and words[1] in ("add", "clear") and player:
        # !path add (your position as the next waypoint) / !path clear: builder mode.
        return [("build_edit", "path " + words[1], None)]
    if words[0] == "mobs" and player:
        # !mobs [filter]: builder mode, list mobs.json keys (and names) to use with !spawn.
        want = " ".join(words[1:]).lower()
        rows = [f"{k} ({m.get('name', k)})" for k, m in sorted(ARGS.content.mobs.items())
                if isinstance(m, dict) and (want in k.lower() or want in str(m.get("name", "")).lower())]
        shown = rows[:30]
        lines = [build_system_text(f"{len(rows)} mob template(s){' matching ' + repr(want) if want else ''}:", SYSTEM_TEXT_WHITE)]
        lines += [build_system_text("  " + r, SYSTEM_TEXT_WHITE) for r in shown]
        if len(rows) > len(shown):
            lines.append(build_system_text(f"  ... and {len(rows) - len(shown)} more; add a filter.", SYSTEM_TEXT_WHITE))
        return lines
    if words[0] == "reload" and player:
        # !reload: builder mode, apply changed content files now (after validating them).
        return [("build_reload",)]
    if words[0] == "undo" and player:
        # !undo: builder mode, take back your last !spawn / !despawn / !wander / !respawn / !path.
        return [("build_undo",)]
    if words[0] == "despawn" and player:
        # !despawn: builder mode, remove the targeted spawned NPC from the world and the file.
        return [("build_despawn",)]
    if words[0] == "wound" and len(words) >= 3 and player:
        # !wound <part 0-4> <severity 0-4>: set a wound (testing; 0 head ... 4 legs).
        w = list(getattr(player, "wounds", None) or [0] * 5)
        w[int(words[1]) % 5] = max(0, min(4, int(words[2])))
        return [("wounds", w)]
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
        # !learn <ability name>: learn a class ability without a trainer (testing); your own
        # class first, then any class's.
        want = " ".join(words[1:]).lower()
        for klass in [player.klass] + [k for k in class_abilities.CLASS_PREFIX if k != player.klass]:
            for n, (aid, tag) in enumerate(class_abilities.class_ability_list(ARGS.client_dir, klass)):
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
            # Another player (online, by name): as clicking them (defensive target).
            s = ONLINE.get(want)
            if s is None or s.get("player") is None:
                return []
            other = s["player"]
            player.target = other.char_id
            print(f"  <- dev: target player {other.name}")
            return [combat.targets(None, other)]
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
    if words[0] == "adjust" and len(words) >= 2 and player:
        # !adjust <physics> [state]: RPC ClientAdjustPosition at the current position with that
        # physics (1 walking, 2 falling, 4 flying...) and controller state (testing flight).
        return [("adjust", int(words[1], 0), words[2] if len(words) > 2 else None)]
    if words[0] == "gotostate" and len(words) >= 2 and player:
        # !gotostate <state>: RPC ClientGotoState on the player controller (testing).
        return [("gotostate", words[1])]
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
        # !event <id> <hex...>: send a zone event; "T" stands for your target's entity id (eid64).
        tgt = struct.pack("<Q", (player.target or 0) if player else 0).hex()
        data = bytes.fromhex("".join(w.replace("T", tgt) for w in words[2:]))   # "T" anywhere = target eid
        print(f"  <- dev: zone event {words[1]} ({len(data)} bytes)")
        return [zone.zone_event(int(words[1], 0), data)]
    return []


# Zone event 0x192 (wstr text, i32 colour/channel): plain server text in the chat
# window. Verified colours: 3 white, 4 red, 5 orange, 6 blue, 7 tan.
SYSTEM_TEXT_WHITE, SYSTEM_TEXT_ERROR, SYSTEM_TEXT_COMBAT = 3, 4, 5


# The client's own messages (zone event 0x0e {i16 code}, docs/NOTICES.md).
TOO_FAR_AWAY, NOT_WHILE_DEAD, NOT_IN_GROUP, ALREADY_IN_GROUP, CANT_AFFORD, CHEST_FULL = 111, 112, 197, 201, 251, 349
PLEASE_TARGET_PC, TRADE_NO_SPACE, DEF_TARGET_NOT_PC, NO_SPACE, NO_ROOM_FOR_REWARD, CANT_PURCHASE_PLOT = 49, 88, 169, 256, 320, 366
NEED_TARGET, NOT_ATTACKABLE, SITE_MISSING_MATERIALS, DONT_OWN_PLOT = 120, 340, 403, 425
CANT_DESTROY_IN_COMBAT, CANT_CHANGE_EQUIPMENT_WHILE_CRAFTING, CANT_BIND_IN_COMBAT = 94, 95, 130
FINISH_COMBAT_BEFORE_CRAFTING = 144
CANT_USE_SONG_FEARED = 483


def client_notice(code):
    return zone.zone_event(0x0E, struct.pack("<h", code))


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
    chars = [c for c in account_characters(state.get("account")) if c["world"] == WORLD_NAME]
    for char in chars:
        n = send_message(sock, addr, state, build_character_record(char))
        print(f"  <- sent WORLD character record 0x19: {char['first']} {char['last']} ({n} packets)")
    if not chars:
        print("  (no saved characters to send)")


def player_from_character(char, name, args):
    """A zone.Player from a characters.json record (everything saved is read back here)."""
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
    player.gender = character_gender(char)
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
    player.xp_debt = int(char.get("xp_debt", 0))
    player.tombstone = char.get("tombstone")
    player.bind = char.get("bind")
    player.dialog_rewards = list(char.get("dialog_rewards", []))
    player.escrow = [list(e) for e in char.get("escrow", [])]
    player.played = int(char.get("played", 0))
    player.titles = list(char.get("titles", []))
    player.wounds = [int(x) for x in (char.get("wounds") or [0] * 5)][:5]
    player.songs = list(char.get("songs", []))
    player.fish_records = dict(char.get("fish_records", {}))
    player.discovered = list(char.get("discovered", []))
    player.journal_removed = list(char.get("journal_removed", []))
    player.auto_def_target_me = bool(char.get("auto_def_target_me", False))
    player.flags = list(char.get("flags", []))
    player.assembly_known = list(char.get("assembly_known", []))
    player.title_prefix = char.get("title_prefix", -1)
    player.title_suffix = char.get("title_suffix", -1)
    player.show_title = char.get("show_title", True)
    player.session_start = time.time()
    player.known_recipes = list(char.get("known_recipes", []))
    player.diplomacy_deck = list(char.get("diplomacy_deck", [])) or None
    player.diplomacy_slots = char.get("diplomacy_slots")
    player.ignores = list(char.get("ignores", []))
    player.bank_coins = char.get("bank_coins", 0)
    if "equipment" in char:
        player.equipment = [tuple(e) for e in char["equipment"]]
    player.xp = char.get("adventure_xp", player.xp)
    player.learned = list(char.get("learned_abilities", []))
    player.spheres = {k: list(v) for k, v in char.get("spheres", {}).items()}
    player.active_toolbelt = char.get("active_toolbelt")
    player.bound = set(char.get("bound", []))
    player.deck_presets = char.get("deck_presets")
    player.apply_form_on_death = char.get("apply_form_on_death", False)
    player.app_gear_visible = bool(char.get("app_gear_visible", False))
    player.barding_item = char.get("barding")
    player.craft_trade = int(char.get("craft_trade", 0xFF))
    player.skill_dirs = {int(k): int(v) for k, v in (char.get("skill_dirs") or {}).items()}
    player.attr_alloc = {k: int(v) for k, v in (char.get("attr_alloc") or {}).items() if k in attributes.ORDER}
    player.craft_alloc = {k: int(v) for k, v in (char.get("craft_alloc") or {}).items()
                          if k in attributes.CRAFT_STATS}
    player.hints_seen = list(char.get("hints_seen") or [])
    player.hints_off = bool(char.get("hints_off", False))
    player.aa_ranks = {int(k): int(v) for k, v in (char.get("aa_ranks") or {}).items()}
    player.aa_points = int(char.get("aa_points", 0))
    player.aa_spent = int(char.get("aa_spent", 0))
    player.aa_xp = int(char.get("aa_xp", 0))
    player.presence = {k: int(v) for k, v in (char.get("presence") or {}).items() if k in zone.PRESENCE_STATS}
    player.item_cooldowns = {int(g): tuple(v) for g, v in (char.get("item_cooldowns") or {}).items()}
    known = {prop for prop, _, _ in PAWN_PREFS.values()}
    player.pawn_prefs = {k: int(v) for k, v in char.get("pawn_prefs", {}).items() if k in known}
    player.access_level = int(char.get("access_level", 0))
    cname = races_classes.class_name(player.klass)
    chain_names = (reactions.chain_names(args.content.chains, cname)
                   + list(args.content.counters.get(cname, []))
                   + list(args.content.rescues.get(cname, [])))
    chain_ids = [aid for aid, tag in class_abilities.class_ability_list(args.client_dir, player.klass)
                 if class_abilities.display_name(tag) in chain_names]
    player.abilities = [ability_content(a, args.content.abilities) for a in
                        (class_abilities.starting_abilities(args.client_dir, player.klass,
                                                            learned=player.learned + chain_ids)
                         or player.abilities)] + general_abilities(args.content)
    player.chains = reactions.class_chains(args.content.chains, cname, player.abilities)
    player.counters = reactions.class_counters(args.content.counters, cname, player.abilities)
    player.rescues = reactions.class_counters(args.content.rescues, cname, player.abilities)
    player.song_parts = songs.part_abilities(args.content.songs.get(cname, {}))
    player.forms = forms.class_forms(args.content.forms.get(cname, {}))
    return player


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
            mine = any(c["first"] == name for c in account_characters(state.get("account")))
            if mine and len(data) >= pos + 64:
                save_character_field(name, "appearance", data[-64:].hex())
                print(f"  >>> WORLD event 0x13b (Customize): saved new appearance for {name!r}")
            else:
                print(f"  >>> WORLD event 0x13b (Customize) refused: {name!r} is not a character of "
                      f"{state.get('account')!r}")
            return
        if event_id == 0x19:
            # Play button: event 0x19 carrying wchar[64] character name + 12 bytes
            # (seen: 01 00 ff ff 01 00 ff ff 00 00 00 00). Reply: connect to zone.
            name = data[:128].decode("utf-16-le", "replace").split("\0")[0]
            print(f"  >>> WORLD event 0x19 (Play): {name!r}, extra={data[128:].hex(' ')}")
            char = next((c for c in account_characters(state.get("account")) if c["first"] == name), None)
            if char is None:
                print(f"  <- WORLD Play refused: {name!r} is not a character of {state.get('account')!r}")
                return
            release_character(name, args)
            char = next((c for c in account_characters(state.get("account")) if c["first"] == name), char)
            # Caravans: Play mode byte (+136) 0 normal, 3 go to the caravan, 2 own location and
            # leave the caravan. A caravan member's normal Play first gets the choice (world 0x55).
            mode = data[136] if len(data) > 136 else 0
            cs = load_caravans()
            cv = caravan_of(name, cs)
            cv_loc = cv.get("loc") if cv and cv["leader"].lower() != name.lower() else None
            if cv_loc and mode == 0:
                left = max(0, int(caravan.TRAVEL_SECONDS - (time.time() - char.get("last_logout", time.time()))))
                cx, cy = (int(p[1:]) * -1 if p.startswith("n") else int(p) for p in cv_loc["level"].split("_")[1:3])
                send_message(sock, addr, state, event_message(
                    0x55, name.encode("utf-16-le").ljust(128, b"\0")[:128] + struct.pack("<iii", cx, cy, left)))
                print(f"  <- sent WORLD event 0x55 (caravan choice for {name!r}, {left}s left)")
                return
            if cv and mode == 2:
                caravan_drop(cs, cv, name)
            elif cv_loc and mode == 3 and time.time() - char.get("last_logout", 0) >= caravan.TRAVEL_SECONDS:
                char = dict(char, position=[cv_loc["x"], cv_loc["y"], cv_loc["z"]])
                cx, cy = (int(p[1:]) * -1 if p.startswith("n") else int(p) for p in cv_loc["level"].split("_")[1:3])
                char["position_chunk"] = char["chunk"] = [cx, cy]
                print(f"  {name} travels with the caravan to {cv_loc['level']}")
            # The zone connection with the same session key claims this player.
            player = player_from_character(char, name, args)
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
            if state.get("player") is not None:
                print("  >>> ZONE login ignored: this connection is already logged in")
                return
            pending = PENDING_PLAYERS.pop(login[1], None)
            if pending is None and not getattr(args, "anonymous_zone", False):
                # Only a session the world server just sent here (Play) may enter the zone.
                send_message(sock, addr, state, build_login_reply(False))
                print("  <- ZONE login refused: no character is waiting for that session")
                return
            state["player"] = pending
            state["session"] = login[1]
            ZONE_BY_SESSION[login[1]] = state
            if state["player"]:
                if kick_other_session(state, args):
                    # The older connection may have changed the character since Play: start
                    # from the record it just saved, not the copy made at Play.
                    fresh = load_character(state["player"].name)
                    if fresh is not None:
                        state["player"] = player_from_character(fresh, fresh["first"], args)
                ONLINE[state["player"].name.lower()] = state
            send_message(sock, addr, state, build_login_reply(True))
            if state["player"]:
                social_login(state)
                guild_login(state)
                brotherhood_login(state)
                faction_login(state)
                workorder_login(state)
                mail_login(state)
                title_login(state)
                caravan_login(state)
                assembly_login(state)
                journal_login(state)
                songs_login(state)
                fishing_login(state)
                forms_login(state)
                house_npcs_login(state)
                combat_sheet_login(state)
                wounds_login(state)
                m = hint(state["player"], "welcome")
                if m:
                    send_message(sock, addr, state, m)
                # The saved Auto Defensive Target Me option back into the client (0x11b {bool8}).
                send_message(sock, addr, state, zone.zone_event(
                    AUTO_DEF_TARGET_ME_SET, bytes([bool(getattr(state["player"], "auto_def_target_me", False))])))
                world_send(state, titles.game_clock())
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
                if state["player"].health <= 0:
                    send_message(sock, addr, state, client_notice(NOT_WHILE_DEAD))   # the dead don't chat with NPCs
                else:
                    for m in npc_dialog(state, hail_target):
                        send_message(sock, addr, state, m)
            w = state.get("world")
            if w is not None and not text.startswith("!"):
                w.broadcast(lambda s: build_chat_line(speaker, text, CHAT_SAY), exclude=state)
            if text.startswith("!") and dev_allowed(args, state.get("player"), text):
                for m in dev_command(text, state.get("player")):
                    if isinstance(m, tuple) and m[0] == "npc_update":
                        if state.get("world"):
                            state["world"].broadcast(
                                lambda s, m=m: zone.npc_update(s, args, m[1], m[2]))
                        continue
                    elif isinstance(m, tuple) and m[0] == "adjust":
                        loc = state.get("position") or state["player"].live_position
                        if loc is not None:
                            send_message(sock, addr, state, zone.client_adjust_position(
                                state, args, (loc[0], loc[1], loc[2] + 50.0), m[1], m[2]))
                        continue
                    elif isinstance(m, tuple) and m[0] == "gotostate":
                        send_message(sock, addr, state, zone.client_goto_state(state, args, m[1]))
                        continue
                    elif isinstance(m, tuple) and m[0] == "cev":
                        # A client zone event, handled as if the client had sent it.
                        handle_message(sock, server, addr, state,
                                       struct.pack("<HII", 2, m[1], len(m[2])) + m[2], args)
                        continue
                    elif isinstance(m, tuple) and m[0] == "netstats":
                        text = (f"Sent {state.get('out_seq', 0)} reliable packets, resent "
                                f"{state.get('resent', 0)}, {len(state.get('unacked') or ())} waiting for an ack.")
                        send_message(sock, addr, state, build_system_text(text, SYSTEM_TEXT_WHITE))
                        continue
                    elif isinstance(m, tuple) and m[0] == "spherexp":
                        sphere_xp(state, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "fishcatch":
                        record_catch(state, m[1], "Wastes Grub")
                        continue
                    elif isinstance(m, tuple) and m[0] == "pet":
                        summon_pet(state, args, m[1])
                        continue
                    elif isinstance(m, tuple) and m[0] == "react":
                        if state.get("reactions"):
                            activate_reaction(state, args, max(state["reactions"]))
                        continue
                    elif isinstance(m, tuple) and m[0] == "kill":
                        kp = state["player"]
                        npc = kp.npcs.get(kp.target) if kp.target else None
                        if npc is not None and npc.alive:
                            lines, npc = combat.strike(kp, npc, "You", None, npc.health, npc.health)
                            for cm in combat_results(state, ARGS, kp, lines, npc, kp.health > 0, False):
                                send_message(sock, addr, state, cm)
                        continue
                    elif isinstance(m, tuple) and m[0] == "lootev":
                        handle_grouploot_event(state, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "mentorev":
                        handle_mentor_event(state, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "fishev":
                        handle_fishing_event(state, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "duelev":
                        handle_duel_event(state, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "title":
                        grant_title(state, m[1])
                        continue
                    elif isinstance(m, tuple) and m[0] == "housing":
                        handle_housing_event(state, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "house":
                        p = state["player"]
                        pos = p.live_position or p.spawned_at
                        obj = {"id": 0x4000000 + int(time.time()) % 100000, "prefab": m[1], "type": m[2],
                               "loc": (pos[0] + 800.0, pos[1], pos[2]), "hover": "Test house"}
                        send_message(sock, addr, state, zone.open_placed_object(state, args, obj))
                        continue
                    elif isinstance(m, tuple) and m[0] == "mount":
                        set_mount(state, args, state["player"], m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "cc":
                        p = state["player"]
                        fake = (p.npcs.get(p.target) if p.target else None) or types.SimpleNamespace(
                            name="A test", location=(p.live_position or p.spawned_at))
                        apply_crowd_control(state, fake, {"name": "Test " + m[1].title(), "kind": m[1],
                                                          "duration": m[2]}, 0x7E00001, time.time())
                        continue
                    elif isinstance(m, tuple) and m[0] == "parleywin":
                        if state.get("parley"):
                            finish_parley(state, state["parley"], "won")
                        continue
                    elif isinstance(m, tuple) and m[0] == "gm":
                        gm_command(state, args, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "callpc":
                        other = ONLINE.get(m[1].lower())
                        if other is None or other.get("player") is None or other is state:
                            send_message(sock, addr, state, build_system_text(f"{m[1]} is not online.", SYSTEM_TEXT_ERROR))
                        else:
                            call_offer(state, other)
                        continue
                    elif isinstance(m, tuple) and m[0] == "die":
                        p = state["player"]
                        p.health = 0
                        for dm in player_death(state, args, p):
                            send_message(sock, addr, state, dm)
                        continue
                    elif isinstance(m, tuple) and m[0] == "rezme":
                        offer_rez(state, "Veyla Brightsteel", "Rebirth I")
                        continue
                    elif isinstance(m, tuple) and m[0] == "tombstone":
                        p = state["player"]
                        p.died_at = state.get("position") or p.live_position or p.spawned_at
                        place_tombstone(state, args, p)
                        continue
                    elif isinstance(m, tuple) and m[0] == "faction":
                        adjust_faction(state, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "build_spawn":
                        build_spawn(state, args, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "build_reload":
                        problems = force_content_reload(args)
                        text = (f"Content not reloaded: {len(problems)} problem(s). First: {problems[0]}" if problems
                                else "Content reloaded.")
                        send_message(sock, addr, state, build_system_text(text, SYSTEM_TEXT_ERROR if problems else SYSTEM_TEXT_WHITE))
                        continue
                    elif isinstance(m, tuple) and m[0] == "build_undo":
                        build_undo(state)
                        continue
                    elif isinstance(m, tuple) and m[0] == "build_edit":
                        build_edit(state, args, m[1], m[2])
                        continue
                    elif isinstance(m, tuple) and m[0] == "build_despawn":
                        build_despawn(state, args)
                        continue
                    elif isinstance(m, tuple) and m[0] == "wounds":
                        set_wounds(state, m[1])
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
                    elif isinstance(m, tuple) and m[0] == "visit":
                        spot = find_npc_spawn(args.content, m[1])
                        if spot is None:
                            send_message(sock, addr, state, build_system_text(f"No NPC named {m[1]!r} is placed.", SYSTEM_TEXT_ERROR))
                        else:
                            level, name, x, y, z = spot
                            send_message(sock, addr, state, build_system_text(f"Travelling to {name} in {chunk_display_name(level)}.", SYSTEM_TEXT_WHITE))
                            cx, cy = level_chunk(level)
                            travel_to_chunk(state, args, cx, cy, x + 150.0, y, z)
                        continue
                    elif isinstance(m, tuple) and m[0] == "give":
                        if give_item(state, m[1], m[2]):
                            quest_items_changed(state)
                            audit("dev_give", to=state["player"].name, item=[m[1], m[2]])
                        continue
                    elif isinstance(m, tuple) and m[0] == "trade_event":
                        handle_trade_event(state, m[1], bytes(10) + m[2], args)
                        continue
                    elif isinstance(m, tuple) and m[0] == "self_prop":
                        m = zone.player_pawn_update(state, args, m[2])
                    elif isinstance(m, tuple) and m[0] == "pawn_update":
                        loc = m[2]["Location"]
                        send_message(sock, addr, state, zone.player_teleport(loc))
                        state.setdefault("move_check", {})["teleport_at"] = time.time()   # before the echo
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
                place_tombstone(state, args, player)
                if any(getattr(player, "wounds", None) or []):
                    set_wounds(state, [0] * 5)          # a released spirit comes back whole
                bind = getattr(player, "bind", None)
                elsewhere = bool(bind) and bind["level"] != player.level
                spot = bind["loc"] if bind and not elsewhere else player.spawned_at
                for m in (combat.death_popup(0, True),
                          zone.player_pawn_update(state, args, {"Health": 100, "m_bIsDead": 0}),
                          zone.health_update(player)) + (() if elsewhere else (zone.player_teleport(tuple(spot)),)):
                    send_message(sock, addr, state, m)
                restore_form_after_death(state, player)
                if elsewhere:
                    # Bound at an altar in another region: the spirit returns there (a chunk change).
                    cx, cy = level_chunk(bind["level"])
                    travel_to_chunk(state, args, cx, cy, float(bind["loc"][0]), float(bind["loc"][1]),
                                    float(bind["loc"][2]))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x2B0 and state.get("player"):
            # Interact with an "other" entity (altars): {eid64 target, bool8}.
            eid = struct.unpack_from("<Q", payload, 10)[0]
            npc = state["player"].npcs.get(eid)
            print(f"  >>> ZONE interact {eid:#x} ({npc.name if npc else '-'})")
            if npc is not None and getattr(npc, "altar", False):
                handle_altar_use(state, npc)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in housing.CLIENT_EVENTS and state.get("player"):
            handle_housing_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (craft.ACTIVE_TOOLBELT, craft.PICK_TOOLBELT)                 and state.get("player") and not state.get("craft"):
            # Active toolbelt: a slot (0xa4) or a belt's handle (0xf8, mapped to the slot it is worn in).
            p = state["player"]
            ev, v = struct.unpack_from("<I", payload, 2)[0], struct.unpack_from("<i", payload, 10)[0]
            if ev == craft.PICK_TOOLBELT:
                v = next((e[3] for e in p.equipment if e[0] == v), 67)
            if v in craft.TOOLBELT_SLOTS:
                p.active_toolbelt = v
                save_character_field(p.name, "active_toolbelt", v)
                send_message(sock, addr, state, craft.active_toolbelt(v))
                send_message(sock, addr, state, zone.zone_event(0x30E))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (CHANGE_GENDER, CHANGE_RACE) and state.get("player") and len(payload) >= 18:
            change_gender_race(state, struct.unpack_from("<I", payload, 2)[0], *struct.unpack_from("<ii", payload, 10))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == UNBIND and state.get("player") and len(payload) >= 18:
            unbind_item(state, *struct.unpack_from("<ii", payload, 10))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in GM_EVENTS and state.get("player"):
            gm_command(state, args, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == CLAIM_LIST and state.get("player"):
            send_message(sock, addr, state, zone.zone_event(CLAIM_CLEAR))
            send_message(sock, addr, state, zone.zone_event(CLAIM_END))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == APPLY_FORM_ON_DEATH and state.get("player") and len(payload) >= 11:
            state["player"].apply_form_on_death = bool(payload[10])
            save_character_field(state["player"].name, "apply_form_on_death", bool(payload[10]))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in PAWN_PREFS and state.get("player"):
            prop, fmt, top = PAWN_PREFS[struct.unpack_from("<I", payload, 2)[0]]
            if len(payload) >= 10 + struct.calcsize("<" + fmt):
                value = max(0, min(top, struct.unpack_from("<" + fmt, payload, 10)[0]))
                set_pawn_pref(state, prop, value)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == CYCLE_WIELD and state.get("player"):
            set_pawn_pref(state, "m_WieldPreference", next_wield_preference(state["player"]))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (TAKE_OFF_AIR, TAKE_OFF_STANDING) and state.get("player"):
            take_off_event(state, args)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == MOVE_MODE and state.get("player") and len(payload) >= 11:
            p = state["player"]
            p.movement_mode = 1 if payload[10] == 1 else 2
            # bIsWalking alone does not slow the owner's pawn (live test); GroundSpeed does.
            pawn_props_changed(state, {"bIsWalking": p.movement_mode == 1})
            if not getattr(p, "cc", None) and "ue" in state:
                send_message(sock, addr, state, zone.player_pawn_update(state, args, {"GroundSpeed": ground_speed(p)}))
            send_message(sock, addr, state, zone.score_message(p))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == ITEM_LINK_REQUEST and state.get("player"):
            (text,), _ = read_wstrings(payload[10:], 0, 1)
            name = zone.item_link_name(text)
            print(f"  >>> ZONE item link {text!r} -> {name}")
            if name:
                rec = vgmsg.inventory_item(zone.template_id(name), name, 0, zone.item_icon(name, 443), 1,
                                           description=zone.ITEM_CONTENT.item(name).get("description", ""),
                                           **zone.item_equip_fields(name))
                send_message(sock, addr, state, zone.zone_event(ITEM_LINK_REQUEST, rec))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == travel.REMOVE_REQUEST and state.get("player") and len(payload) >= 14:
            journal_remove(state, struct.unpack_from("<i", payload, 10)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == APP_GEAR_TOGGLE and state.get("player"):
            app_gear_toggle(state)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == MARK_REQUEST and state.get("player"):
            print(f"  >>> ZONE mark {payload[10:].hex(' ')}")
            mark_target(state, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == CALL_ANSWER and state.get("player"):
            call_answer(state, args, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (ROPE_THROW, ROPE_ACCEPT) and state.get("player"):
            rope_event(state, args, struct.unpack_from("<I", payload, 2)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == CITY_STATUS and state.get("player"):
            city_status(state)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (LOCKOUT_SHARE, LOCKOUT_ANSWER) and state.get("player"):
            share = struct.unpack_from("<I", payload, 2)[0] == LOCKOUT_SHARE
            send_message(sock, addr, state, client_notice(INVALID_LOCKOUT if share else NO_LOCKOUT_OFFER))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == LOCKOUT_LIST and state.get("player"):
            send_message(sock, addr, state, zone.zone_event(LOCKOUT_LIST_REPLY,
                                                            (state["player"].name + "\0").encode("utf-16-le")))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in CANCEL_CAST and state.get("player"):
            cast = state.pop("casting", None)
            print(f"  >>> ZONE cancel 0x{struct.unpack_from('<I', payload, 2)[0]:x}" + (" (cast dropped)" if cast else ""))
            if cast:
                send_message(sock, addr, state, effects.interrupted())
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == CLEAR_TARGETS and state.get("player"):
            state["player"].target = None
            state["def_target"] = 0
            send_message(sock, addr, state, combat.targets())
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == FORCE_STANCE and state.get("player") and len(payload) >= 11:
            # /forcecombatstance [on|off]: {u8 on} (FUN_00609010). Weapons stay drawn until turned off.
            p = state["player"]
            p.forced_stance = bool(payload[10])
            out = []
            set_combat_stance(state, args, p, p.forced_stance or p.auto_attack, out)
            for m in out:
                send_message(sock, addr, state, m)
            send_message(sock, addr, state, build_system_text(
                "Combat stance forced on." if p.forced_stance else "Combat stance no longer forced.", SYSTEM_TEXT_WHITE))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == RENAME and state.get("player"):
            rename_character(state, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == CLEAR_DEBT and state.get("player") and len(payload) >= 14:
            clear_debt(state, struct.unpack_from("<i", payload, 10)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == effects.CANCEL_MAINTAINED and state.get("player") and len(payload) >= 14:
            cancel_maintained(state, struct.unpack_from("<i", payload, 10)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in pets.MINION_EVENTS and state.get("player"):
            handle_minion_event(state, struct.unpack_from("<I", payload, 2)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (pets.DEFAULT_OFF, pets.DEFAULT_ON) \
                and state.get("player") and len(payload) >= 14:
            pet = getattr(state["player"], "pet", None)
            aid = struct.unpack_from("<i", payload, 10)[0]
            a = getattr(pet, "pet_abilities", {}).get(aid) if pet else None
            if a is not None:
                a["auto"] = struct.unpack_from("<I", payload, 2)[0] == pets.DEFAULT_ON   # the client flipped it already
                send_message(sock, addr, state, build_system_text(
                    f"{pet.name} will {'now' if a['auto'] else 'no longer'} use {a['name']} on its own.", SYSTEM_TEXT_WHITE))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == pets.USE_ABILITY and state.get("player") and len(payload) >= 14:
            pet_use_ability(state, struct.unpack_from("<i", payload, 10)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x249 and state.get("player") and len(payload) >= 14:
            cancel_maintained(state, struct.unpack_from("<i", payload, 10)[0], stance=False)   # right-click a buff
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in forms.CLIENT_EVENTS and state.get("player"):
            handle_form_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in songs.CLIENT_EVENTS and state.get("player"):
            handle_song_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == bugs.PLAYER_REPORT and state.get("player"):
            submit_player_report(state, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == bugs.QUEST_FEEDBACK and state.get("player"):
            submit_quest_feedback(state, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == bugs.SUBMIT and state.get("player"):
            submit_bug_report(state, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == UNSTUCK and state.get("player"):
            unstuck(state)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in CORPSE_EVENTS and state.get("player"):
            handle_corpse_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (zone.MOVE_ITEM, zone.DESTROY_ITEM, zone.UNSTACK) and state.get("player"):
            handle_bag_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x3E5:
            # The client echoes a server teleport (zone.player_teleport) once it has moved.
            state.setdefault("move_check", {})["teleport_at"] = time.time()
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in grouploot.CLIENT_EVENTS and state.get("player"):
            handle_grouploot_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in group.MENTOR_EVENTS and state.get("player"):
            handle_mentor_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in assembly.CLIENT_EVENTS and state.get("player"):
            handle_assembly_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in fishing.CLIENT_EVENTS and state.get("player"):
            handle_fishing_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in caravan.CLIENT_EVENTS and state.get("player"):
            handle_caravan_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in pets.CLIENT_EVENTS and state.get("player"):
            handle_pet_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in duel.CLIENT_EVENTS and state.get("player"):
            handle_duel_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in titles.CLIENT_EVENTS and state.get("player"):
            handle_title_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x10F and state.get("player"):
            # /played: the reply is the same id with the seconds played ("You have played for: ...").
            send_message(sock, addr, state, zone.zone_event(0x10F, struct.pack("<i", played_seconds(state["player"]))))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x597 and state.get("player"):
            handle_rift(state, args, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x57C and state.get("player"):
            # /dismount (no payload).
            if getattr(state["player"], "mount", None):
                set_mount(state, args, state["player"], None)
                send_message(sock, addr, state, zone.zone_event(0x0E, struct.pack("<h", 0xAC)))   # Dismounting
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == quest.DIALOG_RESPONSE and state.get("player"):
            handle_dialog_response(state, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0xE0 and state.get("player"):
            # /rezaccept (u8 1) or /rezdecline (u8 0), also the Resurrection dialog buttons.
            answer_rez(state, args, payload[10:11] == b"\x01")
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x188 and state.get("player"):
            summon_tombstone(state, struct.unpack_from("<i", payload, 10)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x10D and state.get("player"):
            # /bind: only next to an altar (0x40a 3 "You may not bind here.", 4 while dead).
            p = state["player"]
            altar = near_altar(p)
            if p.health <= 0:
                send_message(sock, addr, state, zone.zone_event(0x40A, struct.pack("<B", 4)))
            elif altar is None:
                send_message(sock, addr, state, zone.zone_event(0x40A, struct.pack("<B", 3)))
            else:
                bind_here(state, altar)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (0x3D6, 0x3D7):
            # /targetnearestpccorpse (0x3d6), /targetmynearestcorpse (0x3d7): no payload.
            player = state.get("player")
            if player:
                mine = struct.unpack_from("<I", payload, 2)[0] == 0x3D7
                stones = [n for n in player.npcs.values() if getattr(n, "tombstone_of", None)
                          and (not mine or n.tombstone_of.lower() == player.name.lower())]
                if stones:
                    pos = player.live_position or player.spawned_at
                    npc = min(stones, key=lambda n: (n.location[0] - pos[0]) ** 2 + (n.location[1] - pos[1]) ** 2)
                    player.target = npc.entity_id
                    send_message(sock, addr, state, combat.targets(npc))
                else:
                    send_message(sock, addr, state, zone.zone_event(0x0E, struct.pack("<h", 300)))   # NoCorpses
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == combat.TARGET_EVENT:
            # Target selected (click, Tab): u64 entity id; 0 = target cleared.
            player = state.get("player")
            eid = struct.unpack_from("<Q", payload, 10)[0] if len(payload) >= 18 else 0
            npc = player.npcs.get(eid) if player else None
            print(f"  >>> ZONE target {eid:#x} ({npc.name if npc else '-'})")
            if player:
                player.target = eid or None
            opp = getattr(player, "duel_opponent", None) if player else None
            if opp is not None and eid == opp.char_id:
                npc = duel.Target(opp)
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
            if ability and reactions.locked(getattr(player, "chains", []), ability[1], getattr(player, "counters", ())):
                # A chain step, finisher or counter: only through its reaction window (0x145).
                if ability[1] in player.counters:
                    send_message(sock, addr, state, zone.zone_event(0x242, struct.pack("<B", reactions.ONLY_AS_REACTION)))
                else:
                    send_message(sock, addr, state, effects.ability_failed(effects.NEEDS_CHAIN))
            elif ability:
                use_ability(state, args, player, ability)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == reactions.ACTIVATE and state.get("player"):
            activate_reaction(state, args, struct.unpack_from("<i", payload, 10)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (
                combat.LOOT_REQUEST, combat.LOOT_TAKE, combat.LOOT_TAKE_ALL, combat.LOOT_CLOSE):
            # Loot window: request (u64 corpse), take one (i32 handle), take all (-1), close.
            event = struct.unpack_from("<I", payload, 2)[0]
            player = state.get("player")
            npc = player.npcs.get(player.target) if player and player.target else None
            print(f"  >>> ZONE loot event {event:#x}: {payload[10:].hex(' ')}")
            if npc and getattr(npc, "tombstone_of", None):
                if event == combat.LOOT_REQUEST:
                    recover_tombstone(state, player, npc)
            elif npc and not npc.alive and event != combat.LOOT_CLOSE and not group_loot_allowed(state, npc):
                msgs = []
            elif npc and not npc.alive and event != combat.LOOT_CLOSE and player_distance(player, npc) > SERVICE_RANGE:
                msgs = [client_notice(TOO_FAR_AWAY)]
            elif npc and not npc.alive:
                if event == combat.LOOT_REQUEST:
                    msgs = open_loot(state, npc)
                elif event in (combat.LOOT_TAKE, combat.LOOT_TAKE_ALL):
                    handle = struct.unpack_from("<i", payload, 10)[0]
                    if handle in getattr(npc, "pending", set()):
                        send_message(sock, addr, state, zone.zone_event(0x0E, struct.pack("<h", grouploot.PENDING_RANDOM)))
                    before = list(npc.loot or [])
                    msgs = combat.take_loot(player, npc, handle)
                    save_character_field(player.name, "items", [list(i) for i in player.items])
                    taken = [i for i in before if i not in (npc.loot or [])]
                    corpse_emptied(state, npc)
                    if getattr(player, "group", None):
                        for s in group_states(player):
                            for _id, name, _icon, qty in taken:
                                s["send"](grouploot.looted(player, name, qty))
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
            item = next((i for i in player.items if i[0] == handle), None) if player else None
            mount = args.content.item(item[1]).get("mount") if item else None
            if player and add_catalyst(state, handle):
                pass
            elif item and args.content.item(item[1]).get("fixture"):
                place_fixture(state, item)
            elif item and args.content.item(item[1]).get("barding") is not None:
                use_barding(state, args, item)
            elif item and args.content.item(item[1]).get("convert"):
                offer_conversion(state, item)
            elif item and args.content.item(item[1]).get("fireworks"):
                set_off_fireworks(state, item, args.content.item(item[1])["fireworks"],
                                  args.content.item(item[1]).get("fireworks_fx"))
            elif item and args.content.item(item[1]).get("spyglass"):
                use_spyglass(state, args.content.item(item[1])["spyglass"])
            elif item and args.content.item(item[1]).get("salvage_kit"):
                state["send"](zone.zone_event(DECONSTRUCT_TARGET, struct.pack("<i", item[0])))
            elif item and args.content.item(item[1]).get("use"):
                use_item(state, args, item)
            elif item and args.content.item(item[1]).get("pet"):
                if getattr(player, "pet", None) is not None:
                    dismiss_pet(state)
                else:
                    summon_pet(state, args, args.content.item(item[1])["pet"])
            elif item and args.content.item(item[1]).get("minions"):
                summon_minions(state, args, args.content.item(item[1])["minions"])
            elif mount:
                # A mount item (items.json "mount": {id, type}): right-click summons or dismisses it.
                if getattr(player, "mount", None):
                    set_mount(state, args, player, None)
                    send_message(sock, addr, state, zone.zone_event(0x0E, struct.pack("<h", 0xAC)))
                elif inside_a_house(player):
                    send_message(sock, addr, state, zone.zone_event(NEED_OPEN_SPACE))
                else:
                    set_mount(state, args, player, mount["id"], mount.get("type", zone.MOUNT_GROUND))
                    send_message(sock, addr, state, build_system_text(f"You summon your {item[1]}.", SYSTEM_TEXT_WHITE))
            elif player and state.get("craft"):
                send_message(sock, addr, state, client_notice(CANT_CHANGE_EQUIPMENT_WHILE_CRAFTING))
            elif (player and event == EQUIP_EVENT and item and combat.in_combat(player)
                  and "bind_on_equip" in args.content.item(item[1]).get("flags", ())
                  and item[0] not in getattr(player, "bound", set())):
                send_message(sock, addr, state, client_notice(CANT_BIND_IN_COMBAT))
            elif player:
                result = (zone.equip_item if event == EQUIP_EVENT else zone.unequip_item)(player, handle)
                if isinstance(result, (str, int)):
                    send_message(sock, addr, state, zone.item_error(result))
                else:
                    for m in result:
                        send_message(sock, addr, state, m)
                    gear_changed(state, args, player)
                    if getattr(player, "bound_changed", False):     # a Bind On Equip item was worn
                        player.bound_changed = False
                        save_character_field(player.name, "bound", sorted(player.bound))
                        worn = next((e for e in player.equipment if e[0] == handle), None)
                        if worn:
                            send_message(sock, addr, state, zone.zone_event(ITEM_BOUND, struct.pack("<i", handle)))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (
                merchant.REQ_OPEN, merchant.REQ_BUY, merchant.REQ_SELL, merchant.REQ_CLOSE,
                merchant.REQ_CLOSE2, merchant.REQ_BUYBACK):
            event = struct.unpack_from("<I", payload, 2)[0]
            player = state.get("player")
            npc = player.npcs.get(player.target) if player and player.target else None
            print(f"  >>> ZONE merchant event {event:#x}: {payload[10:].hex(' ')}")
            msgs = []
            if event in (merchant.REQ_CLOSE, merchant.REQ_CLOSE2):
                msgs = [merchant.close_window(3)]
            elif npc is None or not npc.merchant or not npc.alive:
                msgs = [merchant.close_window(2)]          # "please target the merchant"
            elif player_distance(player, npc) > SERVICE_RANGE:
                msgs = [merchant.close_window(3), client_notice(TOO_FAR_AWAY)]
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
                sold = next((i for i in player.items if i[0] == handle), None)
                coins_before = player.coins
                msgs = merchant.sell(args.content, npc, player, handle)
                if sold is not None and sold not in player.items:
                    msgs += add_buyback(state, sold, player.coins - coins_before)
            elif event == merchant.REQ_BUYBACK:
                msgs = buy_back(state, struct.unpack_from("<i", payload, 10)[0])
            for m in msgs:
                send_message(sock, addr, state, m)
            if event in (merchant.REQ_BUY, merchant.REQ_SELL, merchant.REQ_BUYBACK) and player is not None:
                save_character_field(player.name, "items", [list(i) for i in player.items])
                save_character_field(player.name, "coins", player.coins)
                if event == merchant.REQ_BUY:
                    quest_items_changed(state)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (DECONSTRUCT_ITEMS, DECONSTRUCT_DUST):
            if state.get("player"):
                handle_deconstruct(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == SUMMON_CORPSE:
            if state.get("player"):
                summon_corpse(state, args)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == CONVERT_REQUEST:
            if state.get("player"):
                handle_conversion(state, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in (
                merchant.REQ_ESCROW_OPEN, merchant.REQ_ESCROW_TAKE):
            if state.get("player"):
                handle_escrow_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
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
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in market.CLIENT_EVENTS:
            if state.get("player"):
                handle_market_event(state, struct.unpack_from("<I", payload, 2)[0], payload[10:])
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
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == harvest.ITEM_REQUEST:
            if state.get("player"):
                p = state["player"]
                found = [i for i in p.items if i[0] in harvest.parse_item_request(payload[10:])]
                for m in harvest.item_records([vgmsg.inventory_item(i[0], i[1], i[4], i[2], i[3],
                                                                    **zone.item_equip_fields(i[1])) for i in found]):
                    send_message(sock, addr, state, m)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in harvest.CLIENT_EVENTS:
            if state.get("player"):
                handle_harvest_event(state, struct.unpack_from("<I", payload, 2)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in quest.CLIENT_EVENTS:
            if state.get("player"):
                handle_quest_event(state, struct.unpack_from("<I", payload, 2)[0], payload)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in trade.CLIENT_EVENTS:
            if state.get("player"):
                handle_trade_event(state, struct.unpack_from("<I", payload, 2)[0], payload, args)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == UI_LOADED and state.get("player"):
            # The client's UI finished (re)loading (0x6c, also after /reloadui). Its rebuild
            # empties the diplomacy card lists, so the repertoire (the ability book's Diplomacy
            # page and the strategy window) is sent now rather than at login (verified live).
            deck, slots = diplomacy_deck(state["player"])
            for m in diplomacy.deck_messages(ARGS.content.diplomacy["cards"], deck, slots,
                                             resend=state.get("deck_sent", False)):
                send_message(sock, addr, state, m)
            state["deck_sent"] = True
            send_message(sock, addr, state, faction.publish())   # the rebuilt UI's faction lists
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == craft.JOURNAL_RECIPE and len(payload) >= 14:
            if state.get("player"):
                r = recipe_by_id(struct.unpack_from("<i", payload, 10)[0])
                if r is not None and r in zone.book_recipes(ARGS, state["player"]):
                    send_message(sock, addr, state, craft.journal_recipe(r))
                    send_message(sock, addr, state, craft.journal_missing(
                        craft.missing_steps(r, {i[1] for i in state["player"].items})))
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == attributes.SET_DIRECTION:
            if state.get("player"):
                handle_skill_direction(state, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == attributes.ALLOCATE:
            if state.get("player"):
                handle_allocate(state, payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in hints.CLIENT_EVENTS:
            if state.get("player"):
                handle_hint_event(state, struct.unpack_from("<I", payload, 2)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in aa.CLIENT_EVENTS:
            if state.get("player"):
                handle_aa_event(state, args, struct.unpack_from("<I", payload, 2)[0], payload[10:])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] in group.CLIENT_EVENTS:
            if state.get("player"):
                handle_group_event(state, struct.unpack_from("<I", payload, 2)[0], payload)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0x73 and state.get("player"):
            # /sit, /stand: u8 1/0. Pawn m_bResting = 1 sits (verified live).
            player = state["player"]
            player.resting = bool(payload[10]) if len(payload) > 10 else False
            print(f"  >>> ZONE {'sit' if player.resting else 'stand'}")
            pawn_props_changed(state, {"m_bResting": int(player.resting)})
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
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == effects.EXPIRED_QUERY and state.get("player") and len(payload) >= 14:
            effect_query(state, struct.unpack_from("<i", payload, 10)[0], time.time())
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == faction.INFO_REQUEST and state.get("player") and len(payload) >= 14:
            faction_info_request(state, struct.unpack_from("<i", payload, 10)[0])
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == AUTO_DEF_TARGET_ME and state.get("player") and len(payload) > 10:
            p = state["player"]
            p.auto_def_target_me = bool(payload[10])
            save_character_field(p.name, "auto_def_target_me", p.auto_def_target_me)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == HOTKEYS_REQUEST and state.get("player"):
            # /reloadui rebuilds the UI and asks for the hotbars again (0x54d, no payload;
            # FUN_00682b40 after the reload, FUN_005de260): resend them (0x54e) or they stay empty.
            send_message(sock, addr, state, zone.hotbar_message(state["player"]))
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
            if len(payload) >= 10:
                # tools/loadtest.py puts its send time (ns) in the ping: how late did it arrive?
                age = time.time() - struct.unpack_from("<Q", payload, 2)[0] / 1e9
                if 0 <= age < 600:
                    PING_AGE[0] = max(PING_AGE[0], age)
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
            print(f"  >>> WORLD login request: account={login[0]!r}")
            account = accounts.session_account(login[1])
            if account is None:
                reply = build_login_reply(False)
                send_message(sock, addr, state, reply)
                print("  <- WORLD login refused: unknown session key")
                return
            state["account"] = account
            state["session"] = login[1]
            WORLD_BY_SESSION[login[1]] = (sock, addr, state)
            reply = build_login_reply(True)
            send_message(sock, addr, state, reply)
            print(f"  <- sent WORLD PacketLoginReply(success=1): {reply.hex(' ')}")

            # World event 1 (dispatcher FUN_0062aaf0): "Successfully logged into
            # WorldServer." and posts UI event 0x19. Empty event data.
            event = struct.pack("<HII", 2, 1, 0)
            reply = event
            send_message(sock, addr, state, reply)
            print(f"  <- sent WORLD event 1 (logged in): {reply.hex(' ')}")
        elif msg_type == 2 and event_id == brotherhood.LEAVE:
            # /brotherhoodleave (after its confirm popup) arrives as a world type-2 event.
            zone_state = ZONE_BY_SESSION.get(state.get("session"))
            if zone_state and zone_state.get("player"):
                handle_brotherhood(zone_state, event_id, payload[10:])
        elif msg_type == 2 and event_id != 0x6F and LOGIN_BY_KEY.get(state.get("session")) and try_delete_character(
                *LOGIN_BY_KEY[state["session"]], payload):
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
        throttled = accounts.throttled(addr[0])
        account = None if throttled else accounts.login(login[0], login[1])
        if account is None:
            accounts.record_failure(addr[0])      # guessing tokens or passwords: slowed down
        else:
            accounts.FAILURES.pop(addr[0], None)
        if account is not None and accounts.is_suspended(account):
            code, account = LOGIN_SUSPENDED, None
        elif account is None:
            code = LOGIN_SESSION_EXPIRED if login[0] == accounts.LAUNCHER_LOGIN else LOGIN_BAD_ACCOUNT
        if account is None:
            for msg in (build_login_reply(False), build_login_failure(code)):
                send_message(sock, addr, state, msg)
            print(f"  <- login refused for {login[0]!r} (unknown account, wrong password or launcher token)")
            return
        state["account"] = account
        state["login_key"] = accounts.new_session(account)
        LOGIN_BY_KEY[state["login_key"]] = (sock, addr, state)
        print(f"  >>> login: account {account!r}")
        reply = build_login_reply(True)
        send_message(sock, addr, state, reply)
        print(f"  <- sent PacketLoginReply(success=1): {reply.hex(' ')}")

        # Server-select list entry for our world (event 0x25).
        reply = build_world_list_entry_event(WORLD_NAME)
        send_message(sock, addr, state, reply)
        print(f"  <- sent world list entry event 0x25 ({WORLD_NAME!r}, status Up)")

        send_account_character_list(sock, addr, state)

        # Tell the client which world server to use (event 0x27).
        event = build_world_server_event(account, state["login_key"], WORLD_NAME, args.world_address)
        n = send_message(sock, addr, state, event)
        print(f"  <- sent world-server event 0x27 (address={args.world_address!r}) "
              f"in {n} fragments")
    elif event_id == 0x139:
        # Character create request: event data starts with first name, last name
        # and world name as NUL-terminated UTF-16LE; the rest (race/class/appearance)
        # is not decoded yet and is kept as hex.
        data = payload[10:]
        (first, last, world), pos = read_wstrings(data, 0, 3)
        print(f"  >>> character create request: {first!r} {last!r} on {world!r}; "
              f"rest={data[pos:].hex(' ')}")
        chars = load_characters()
        if state.get("account") is None:
            return
        if (not valid_first_name(first) or (last and not last.isalpha())
                or any(c["first"].lower() == first.lower() for c in chars)):
            result = 1  # "That first name is already taken." (also for names the rules refuse)
        else:
            result = 0
            new = {"first": first, "last": last, "world": WORLD_NAME, "raw": data[pos:].hex(),
                   "account": state["account"]}
            if not getattr(ARGS, "camp_start", False):
                place_new_character(new, data[pos:])
            chars.append(new)
            save_characters(chars)
        world = WORLD_BY_SESSION.get(state.get("login_key"))
        if result == 0 and world:
            # Put it in this account's character-select list before the client tries to select it.
            n = send_message(world[0], world[1], world[2], build_character_record(chars[-1]))
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
    keep = [c for c in chars if not (c["first"] == name and c.get("account") == state.get("account"))]
    if not name or len(keep) == len(chars):
        return False
    save_characters(keep)
    print(f"  >>> event 0x{event_id:x} looks like DELETE of {name!r} ({other!r}); removed it")
    send_account_character_list(sock, addr, state)
    return True


# Client notices that need no answer (docs/CLIENT_REQUESTS.md), left out of the "client event"
# log lines so sweeps show only real gaps: 0x6c after the UI loads, 0x71 BECOME_PC, 0x104 / 0x105
# crafting list and filter shown, 0x10e /location, 0x127 NPC dialog built, 0x137 journal
# tracking changed, 0x17e / 0x17f / 0x183 tutorial closed, 0x189 corpse list closed, 0x27a an
# ability's impact frame on an entity (the console command active_ability_self_impact_on, run by
# animation notifies during combat; this server applies damage at use, not at impact), 0x18a
# getting up from feign death (pawn +0x3e9, set while m_bIsDead +0x3e8; FUN_009db5a0 /
# FUN_005eef50; no feign-death ability here yet), 0x3a0 {eid64, bool8} the encounter display's
# entity is gone client-side (FUN_004b3bd0; the client clears the display itself).
UI_LOADED = 0x6C
CLIENT_NOTICES = {0x6C, 0x71, 0x104, 0x105, 0x10E, 0x127, 0x137, 0x17E, 0x183, 0x189, 0x27A,
                  0x18A, 0x3A0}


HARD_LANDING = 0x4A          # client: {f32 landing speed, f32 safe speed 1500, f32 10000} (docs/MOVEMENT.md)


def print_client_log(payload):
    # Event envelope u16 2 | u32 eventId | u32 len | data. Event 0x6f is a client
    # log line: u16 0x0c, string file, string text (u32 length-prefixed).
    try:
        _, event_id, _ = struct.unpack_from("<HII", payload, 0)
        if event_id in CLIENT_NOTICES:
            return
        if event_id == HARD_LANDING and len(payload) >= 22:
            # The client's own hard-landing report; fall damage comes from the reported heights
            # instead (check_fall), so this is only logged.
            speed, safe, limit = struct.unpack_from("<fff", payload, 10)
            print(f"  >>> client reports a hard landing: speed {speed:.0f} (safe {safe:.0f}, limit {limit:.0f})")
            return
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
