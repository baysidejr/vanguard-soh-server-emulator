"""Minimal Vanguard login-server stub: logs every UDP packet and answers the
UdpLibrary connect handshake so the client sends its PacketLoginRequest.

Formats come from static analysis of bin/VGClient.exe (see function addresses
in comments). Run:  python login_stub.py [--port 10101]
"""
import argparse
import json
import os
import select
import socket
import struct
import time

import races_classes
import ue2net
import vgmsg
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
                        help="also spawn a test pawn next to the player (does not render yet)")
    parser.add_argument("--spawn-rotation", action="store_true",
                        help="include an initial rotation in the actor open bunch")
    args = parser.parse_args()
    # Used when a zone connection arrives without going through Play first.
    args.default_player = lambda: zone.Player(name="Someone",
                                              level=args.zone_level or chunk_name(*DEFAULT_CHUNK))
    args.package_maps = {}
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

    while True:
        ready, _, _ = select.select([login_sock, world_sock, zone_sock], [], [])
        for sock in ready:
            data, addr = sock.recvfrom(65535)
            serve(sock, names[sock], data, addr, clients, args)


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
            clients[key] = {"out_seq": 0, "seen": set(), "max_raw": min(max_raw, MAX_RAW_PACKET)}
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
        elif data[:2] == b"\x00\x05" and len(data) >= 8:
            reason = struct.unpack_from(">H", data, 6)[0]
            print(f"  client disconnected, reason {reason} ({DISCONNECT_REASONS.get(reason, '?')})")
            clients.pop(key, None)
        else:
            state = clients.setdefault(key, {"out_seq": 0, "seen": set(), "max_raw": 512})
            for kind, seq, payload in reliable_messages(data):
                ack = build_ack_all(kind, seq)
                sock.sendto(ack, addr)
                print(f"  <- sent ack-all seq={seq}: {ack.hex(' ')}")
                if seq in state["seen"]:
                    continue  # client resend; already answered
                state["seen"].add(seq)
                for message in app_messages(payload):
                    handle_message(sock, server, addr, state, message, args)


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
    struct.pack_into("<I", rec, 0x184, 1)
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


def save_characters(chars):
    with open(CHARACTERS_FILE, "w", encoding="utf-8") as f:
        json.dump(chars, f, indent=2)


# The most recent world-server / login-server connections, so each side can push
# messages to the other (character records, refreshed account lists).
WORLD_CONN = {}
# Characters chosen with Play, by session key, until their zone connection logs in.
PENDING_PLAYERS = {}
LOGIN_CONN = {}


def dev_command(text):
    """Developer chat commands (only with --dev-commands), for probing the client:
      !stat id=value[,field=value...] ...   send MsgSingleStatInfo records (0x2d5).
        Field names: kind, category, subtype, base, f<N> (raw wire field N).
      !upd id=value[,field=value...] ...    send MsgStatUpdate (0x2d4) per stat.
      !event id [hexbytes]                  send a raw zone event."""
    words = text[1:].split()
    if not words:
        return []
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
            if text.startswith("!") and args.dev_commands:
                for m in dev_command(text):
                    send_message(sock, addr, state, m)
        elif msg_type == 2 and struct.unpack_from("<I", payload, 2)[0] == 0xD0:
            # Use ability (FUN_0042ca80): i32 ability handle (MsgAbilityInfo field 5).
            handle = struct.unpack_from("<i", payload, 10)[0]
            player = state.get("player")
            names = {a[0]: a[2] for a in getattr(player, "abilities", [])}
            print(f"  >>> ZONE use ability {handle} ({names.get(handle, '?')})")
            if handle in names:
                send_message(sock, addr, state, build_system_text(
                    f"You use {names[handle]}, but you have no target.", SYSTEM_TEXT_COMBAT))
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
