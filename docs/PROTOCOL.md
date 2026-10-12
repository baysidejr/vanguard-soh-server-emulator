# Vanguard: Saga of Heroes — Client/Server Protocol Notes

As of 2026-10-11.

## Overview

The original Vanguard: Saga of Heroes client logs in, lists, creates and deletes characters, and connects to a zone server, all against the Python stub in `server/`. It stops at the Unreal Engine 2 handshake inside the zone connection.

- **Client:** `VGClient.exe`, 32-bit x86, built 2014-02-05, version 1.324.1.139565. Unreal Engine 2.5 based, SOE `UdpLibrary` transport.
- **Method:** static analysis with REA and Ghidra 12.1.4, then each finding tested live against `server/login_stub.py` using the unmodified client.
- **Function addresses** (`FUN_xxxxxxxx`) are Ghidra names for this exact binary (SHA-256 `449334c6060749227a85ed03f93b3110c1a869b293b53803ca0f6a41e081a2ef`).
- **Not covered yet:** the in-world Unreal protocol (actor channels, replication) and most in-game events.

## Connection flow

```
VGClient.exe --sessionid=<id>          reads bin/loginserver.txt
        │  UdpLibrary connect
        ▼
Login server  (UDP 10101)              login, world list (0x25), character list (0x66)
        │  event 0x27: world address + session key
        ▼
World server  (UDP 10100)              world login, character records (0x19), create/delete/customize
        │  event 8 (reply to Play): zone host and port
        ▼
Zone server   (UDP 10102 in the stub)  zone login, ping echo (type 9)
        │  Browse <host>:<port>/Entry.vgr
        ▼
Unreal in-world session                NOT BUILT YET: client waits for the server's first Unreal packet
```

The client is started directly with `--sessionid`. The VGOEmulator launcher instead logs in over HTTP (`login.php`) first, then writes `loginserver.txt` and starts the client the same way. Every hop up to the zone server is verified live against the stub.

## Transport layer (UdpLibrary)

All three servers use the same SOE UdpLibrary framing: a leading `00`, a packet-type byte, then big-endian fields. With CRC and encryption switched off in the confirm, later packets are sent in the clear.

| Type | Name | Layout | Notes |
| --- | --- | --- | --- |
| `01` | Connect | `00 01` u32 protocol=3, u32 connectCode, u32 maxRawPacketSize, cstring `API_PROTOCOL_1.0` | 31 bytes; client resends every ~1 s. maxRaw seen = 512 |
| `02` | Confirm | `00 02` u32 connectCode, u32 encryptCode, u8 crcBytes, u8 encrypt1, u8 encrypt2, u32 maxRaw, u32 protocol=3 | 21 bytes; all-zero crypto fields = no CRC, no encryption |
| `03` | Multi | 1-byte length + sub-packet, repeated | client bundles ack + data |
| `05` | Terminate | `00 05` u32 connectCode, u16 reason | reason table in Reference |
| `06` | KeepAlive | `00 06` | server must answer, or the client drops with reason 2 after ~90 s |
| `09`–`0C` | Reliable 1–4 | `00 09` u16 seq + payload | payload = app message or a Group |
| `0D`–`10` | Fragment 1–4 | `00 0D` u16 seq, u32 total (first only), data | reassembled by `FUN_00c04480` |
| `15`–`18` | AckAll 1–4 | `00 15` u16 seq | acks everything up to seq |
| `19` | Group | 1-byte length (or `FF` + u16) + message, repeated | used inside reliable payloads |

Key functions: connect builder in `UdpConnection::GiveTime` `FUN_00c02830`; cooked-packet dispatcher `FUN_00c01e70`; reliable channel `FUN_00c05350`.

## Application layer

Inside a reliable payload every message starts with a little-endian u16 type. Most game traffic is type 2, an event envelope.

| u16 type | Message | Layout |
| --- | --- | --- |
| 2 | Event envelope | u32 eventId, u32 length, data (parsed by `FUN_006ebb60`) |
| 3 | PacketLoginRequest (client → server) | string field1, string field2; string = u32 length + bytes, no terminator |
| 4 | PacketLoginReply | u8 success; stored as the logged-in flag |
| 9 | Ping (zone only) | u64 client timestamp; server echoes it |
| 1 | Unreal packet (zone only) | raw UE2 bit-packed packet |

**Reflection-serialized messages.** Some events (`0x386`, `0x388`, `0x389`, `0x5dd`, `0x725`) hold an `SGOTemplateObject` read by `FUN_00cd9da0`. Fields are packed back to back in registration order, with no tags or lengths:

| Field type | Bytes |
| --- | --- |
| 0, 1, 8 | 4 |
| 2 | UTF-16LE string, NUL-terminated |
| 3, 0x0B | 16 |
| 4, 7 | 1 |
| 5, 6 | 8 |
| 9 | 2 |
| 10 | 8-bit string, NUL-terminated |

Fixed-layout events use `wchar[64]` (128-byte UTF-16LE) text fields. Sending 8-bit text there made the client log the address as `㈱⸷⸰⸰1`.

## Login server (UDP 10101)

After the login reply, the login server sends the world list, the account's characters and the world server address, all as type-2 events. The client sends events back the same way.

| Dir | Event | Purpose | Data layout |
| --- | --- | --- | --- |
| C→S | type 3 | Login request | `"SOE_LOGIN"`, session id (from `--sessionid`) |
| S→C | type 4 | Login reply | u8 1 = success |
| S→C | `0x25` | Server-select list entry | u8 status, 3 pad, i32 population (−2 = down), UTF-16 name + NUL |
| S→C | `0x66` | Account character list | 0x80 pad, u32 count, u32 slots, u32 extra (UI shows slots + extra), 20 × wchar[64] `"<name>=<world>"` |
| S→C | `0x27` | Connect to world server | 4 × wchar[64]: account, session key, world name, address (`host[:port]`) |
| C→S | `0x139` | Create character | UTF-16 first name, last name, world, then 81 bytes (below) |
| S→C | `0x386` | Create result (reflection) | u8 result, wstring, wstring name (selected on success) |
| C→S | `0x13a` | Delete character (`MsgClientCharacterDelete`) | wstring first name, empty wstring; sent after the Confirm Delete dialog |
| S→C | 1, 2 | Login-side text / failure | 2 = "Invalid LoginServer login, result = %d" |
| C→S | `0x6f` | Client log line | u16 0x0c, string file, string text |

**Create request bytes after the names:** 4 zero bytes; 5 bytes with race at +7 and class at +8; i32 (−26 seen); i32 (1 seen); 64 appearance slider bytes.

**Create result codes:** 0 success, 1 first name taken, 2/3/4 invalid class/race/gender, 5 no starting location, 7 already in game, 8–0x0e name errors, 0x0f bad race/class combo, 0x10 no free slot.

**Other results:** `0x388` = customization result (`FUN_0048cfe0`, u8 0 = success); `0x389` = rename result (`FUN_00519240`). The delete result ("Character deleted.", `FUN_0048d080`) uses an event number not found yet; resending `0x66` updates the list without it.

Event dispatcher: `FUN_00617b10`. Character list reader: `FUN_0051e960`. Create result handler: `FUN_00496c90`.

## World server (UDP 10100)

The world server confirms login, supplies per-character details for the select screen, and answers Play with a zone address. One event number, `0x19`, means two different requests depending on whether it carries data.

| Dir | Event | Purpose | Data layout |
| --- | --- | --- | --- |
| C→S | type 3 | World login | account, session key (from event `0x27`) |
| S→C | type 4 | World login reply | u8 1 = success |
| S→C | 1 | "Successfully logged into WorldServer." | empty; triggers the client's list request |
| C→S | `0x19`, empty | Character details request | none |
| S→C | `0x19` | One character record | see below |
| C→S | `0x19`, with data | **Play** | wchar[64] name + 12 bytes (`01 00 ff ff 01 00 ff ff 00 00 00 00`) |
| S→C | 8 | Connect to zone | u32 port, wchar[64] host, wchar[64] chunk name |
| C→S | `0x13b` | Customize | 2 wstring names, 10 bytes, 64 appearance bytes |

**Character record (event `0x19`, 0x1f7 bytes + appearance string):**

| Offset | Field |
| --- | --- |
| +0x000 / +0x080 / +0x100 | wchar[64] first name, last name, world name |
| +0x180 | u32 class |
| +0x184 | u32 level |
| +0x19c | u32 race |
| +0x1a4 / +0x1a8 | chunk coordinates (shown as `Chunk_0_0.vgr`) |
| +0x1b4–+0x1b6 | bytes (unknown) |
| +0x1b7 | 64 appearance slider bytes (copied for Play by `FUN_0051ca70`) |
| +0x1f7 | 8-bit string of 180 space-separated integers |

Race and class must be valid IDs, or the client crashed once the world name matched.

World event dispatcher: `FUN_0062aaf0`. Record reader: `FUN_005f0770`. Play: `FUN_0051ca70` (`/select "%s" %d %s`).

## Zone server (UDP 10102 in the stub)

The client logs into the zone, then asks Unreal to travel to `<host>:<port>/Entry.vgr` and waits. This is where the stub stops. The zone API has no default port, so the port in world event 8 is required.

| Dir | Type / event | Purpose | Handler |
| --- | --- | --- | --- |
| C→S | type 3 | Zone login (same account and session key) | — |
| S→C | type 4 | Zone login reply | client logs "Login successful to Zone Server" |
| C→S | type 9 | Ping, u64 timestamp, every 1 s | — |
| S→C | type 9 | Ping echo; client computes latency | `FUN_006edcd0` |
| S→C | type 1 | Raw UE2 packet into `UNetConnection::ReceivedRawPacket` | `FUN_0095fcb0` |
| S→C | type 2 | Zone events (rename, race/gender change, exp debt, camp, NPC list, `0x30` pending disconnect) | `FUN_00622350` |

When Play is pressed the client also drops the login-server connection (Terminate, reason 6 "Application"). That is normal.

**Open:** the client sent no Unreal packet on its own after `Browse: 127.0.0.1:10102/Entry.vgr`. The next step is finding the first Unreal packet the server must send, then the UE2 control-channel handshake and level load.

## Reference

**ID tables**

| Table | Values |
| --- | --- |
| World status (`FUN_00cda3b0`) | 2 Loading, 3 Locked, 4 Up, 5 Low, 6 Medium, 7 High, other Down |
| Race (`FUN_00d02540`) | 0 Cat Person, 1 Deep Dwarf, 2 Dwarf, 3 Dark Elf, 4 High Elf, 5 Wood Elf, 6 Gnome, 7 Goblin, 8 Half Elf, 9 Lesser Giant, 0x0a Halfling, 0x0c Kojani, 0x0d Qaliathari, 0x0e Thestran, 0x0f Mordebi, 0x11 Raki, 0x12 Vulmane, 0x13 Kojan Barbarian, 0x14 Varanthari, 0x15 Varanjar, 0x16 Kurashasa |
| Class (`FUN_00d07120`) | 2 Bard, 4 Paladin, 5 Cleric, 7 Druid, 0x0e Psionicist, 0x0f Monk, 0x13 Ranger, 0x14 Dread Knight, 0x15 Rogue, 0x16 Shaman, 0x19 Sorcerer, 0x1b Disciple, 0x1c Warrior, 0x2c Blood Mage, 0x2d Necromancer (plus crafting and diplomacy classes) |
| Disconnect reason | 0 None, 1 IcmpError, 2 Timeout, 3 OtherSideTerminated, 4 ManagerDeleted, 5 ConnectFail, 6 Application, 7 UnreachableConnection, 8 UnacknowledgedTimeout, 9 NewConnectionAttempt, 10 ConnectionRefused, 11 ConnectError, 12 ConnectingToSelf, 13 ReliableOverflow, 14 ApplicationReleased, 15 CorruptPacket, 16 ProtocolMismatch |

**Key functions**

| Function | Role |
| --- | --- |
| `FUN_0051c3f0` | Login UI; builds `/login` or `/lslogin`, reads `loginserver.txt` |
| `FUN_006ebe70` / `FUN_006ec190` / `FUN_006ec2f0` | Connect to login / world / zone |
| `FUN_00d9a1a0` / `FUN_00d9a300` / `FUN_00d9a640` | ClientLoginApi (port 10101) / ClientWorldApi (10100) / ClientZoneApi (no default) |
| `FUN_00d9a940` / `FUN_00d9aa60` / `FUN_00d9abc0` | Login / world / zone message-type dispatchers |
| `FUN_00630d10` | Builds the visible character list |
| `FUN_00cd9da0` | Reflection deserializer |

**Open questions**

- What the server must send first on the Unreal channel (zone type 1).
- Meaning of the `0x66` header's first 0x80 bytes and the extra slot field.
- Exact semantics of the 12 bytes after the name in Play and of the 180 appearance integers.
- Event numbers for the delete and customize results as the client expects them; remaining events `0x5dd`, `0x5df`, `0x5e1`, `0x725`.
