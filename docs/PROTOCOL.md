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

The client logs into the zone, then asks Unreal to travel to `<host>:<port>/<level>.vgr`. The zone API has no default port, so the port in world event 8 is required.

| Dir | Type / event | Purpose | Handler |
| --- | --- | --- | --- |
| C→S | type 3 | Zone login (same account and session key) | — |
| S→C | type 4 | Zone login reply | client logs "Login successful to Zone Server" |
| C→S | type 9 | Ping, u64 timestamp, every 1 s | — |
| S→C | type 9 | Ping echo; client computes latency | `FUN_006edcd0` |
| S→C | type 1 | Raw UE2 packet into `UNetConnection::ReceivedRawPacket` | `FUN_0095fcb0` |
| S→C | type 2 | Zone events (rename, race/gender change, exp debt, camp, NPC list, `0x30` pending disconnect) | `FUN_00622350` |

When Play is pressed the client also drops the login-server connection (Terminate, reason 6 "Application"). That is normal.

### Unreal Engine 2 channel (zone type 1)

Zone message type 1 = `u16 1, u32 length, packet`: one UE2 `UNetConnection` packet, carried by the client's `UdpUnrealConnection` (`FUN_00bd1310`). Field widths come from `UNetConnection::ReceivedPacket` (`FUN_0095f230`); `server/ue2net.py` re-encodes the captured client HELLO byte for byte.

| Field | Encoding |
| --- | --- |
| PacketId | SerializeInt(32768), 15 bits |
| per item: IsAck | 1 bit; ack → AckPacketId SerializeInt(32768) |
| bunch header | bControl, [bOpen, bClose], bReliable, ChIndex SerializeInt(1024) 10 bits, ChSequence SerializeInt(4096) 12 bits (reliable), ChType SerializeInt(8) 3 bits (reliable or open), DataBits SerializeInt(4096) 12 bits |
| terminator | one 1 bit, then zero padding; bits are LSB-first |
| control text | FString: compact-index length incl. NUL, 8-bit chars, NUL |

**Login handshake and world entry (verified live 2026-10-11):**

```
client → HELLO REVISION=0 MINVER=3151 VER=3186
server → CHALLENGE VER=3186 CHALLENGE=12345 STATS=0
client → LOGIN
server → USES GUID=... PKG=chunk_n19_12 ... FNAME=chunk_n19_12.vgr   (level package first)
server → USES ... Core / Engine / SGOUnrealAbstractionLayer
server → WELCOME LEVEL=chunk_n19_12 LONE=0
client → JOIN                      (log: "INITIAL LEVEL LOAD COMPLETE", "Sending join.")
client → zone event 0x71 BECOME_PC (20 bytes: ff×8, then zeros)
server → actor channel 1 open: Engine.PlayerController at a PlayerStart, bNetOwner=1
         (client: loading screen closes, the world is rendered)
```

The client never sends UE2 acks: the UE2 stream rides on UdpLibrary's reliable channel.

**Package map.** `UNetPendingLevel::NotifyReceivedText` (`FUN_009677e0`) builds the client's package map only from `USES GUID=<4×u32 hex> PKG=<name> FLAGS=<flags> SIZE=<bytes> GEN=<generations> FNAME=<file>` lines received before WELCOME. WELCOME checks that each package exists locally with that GUID. The level is loaded from entry 0, so the level package must come first (with Core first the client quit with "Version mismatch … Level Core.MyLevel"). `server/upackage.py` reads GUIDs, generations and export tables from the player's own files (version 129, licensee 35; `UObject` is 0x30 bytes in this build).

**Object references** (`UPackageMapLevel::SerializeObject`, `FUN_00953ad0`): 1 bit (1 = actor, by channel index SerializeInt(1024)); otherwise SerializeInt(index, MaxObjectIndex), where index = sum of earlier packages' export counts + the export index.

**Actor channel open bunch** (`UActorChannel::ReceivedBunch`, `FUN_00964ab0`), with bControl and bOpen set and ChType 2:

| Field | Encoding |
| --- | --- |
| class | object reference (above) |
| location | `FVector::SerializeCompressed` (`FUN_00962170`): SerializeInt(bits, 20), then 3 × SerializeInt(v + bias, 2^(bits+2)) |
| rotation | only if the class default has bNetInitialRotation (`+0x4c` bit 20): per component 1 flag bit + byte |
| Pawn extra | Pawn subclasses only (`FUN_00962350`): byte, u32, u32 |
| properties | repeated: SerializeInt(RepIndex, MaxIndex), element byte if ArrayDim > 1, value (`NetSerializeItem`; bool = 1 bit) |

**Replication indices** (`GetClassNetCache`, `FUN_00b18180`): a class's NetFields (CPF_Net properties and replicated functions that don't override a superclass function) in export-table order, numbered after the superclass's. Actor has 53 (DrawType = 11, bNetOwner = 14), Controller 6, PlayerController 35 (MaxIndex 94). See `server/netcache.py`.

**Becoming the local player.** In this build `Actor.bNetOwner` (actor `+0x54` bit 0) is a *replicated* property. When a bunch leaves it set on a PlayerController while the connection is pending, the client calls `UNetConnection::HandleClientPlayer` (`FUN_0095df60`), which attaches the viewport and opens the connection.

**Levels.** World chunks are `Assets/Maps/chunk_<x>_<y>.vgr` (negative as `n<abs>`, for example `chunk_n19_12`); the client streams in neighbouring chunks itself. The character record's `+0x1a4/+0x1a8` hold the chunk coordinates. A spawn point comes from a `PlayerStart` actor's tagged `Location` property.

**Debugging tip:** comment out `Suppress=DevNetTraffic` in `bin/paths.ini` to get "Spawn …" and "<property> for …" lines in `bin/Logs/VGClient.log`.

**HUD.** Zone event `0x485` (no payload) sent after the spawn sets the client's world-loaded flags; the HUD appears (vitals, chat, minimap, XP bar). A map of about 790 server→client zone event ids, their VGMessages classes and field layouts is in [ZONE_MESSAGES.md](ZONE_MESSAGES.md) (layouts mostly observed, purposes mostly inferred).

**Movement.** After the spawn the server calls the RPC `PlayerController.ClientRestart()` (no parameters in this build; an actor bunch whose payload is just its RepIndex 67). The client then moves the pawn and sends unreliable `ServerMove` (#60) / `ShortServerMove` (#82) RPCs. RPC payload: RepIndex, then per parameter a present bit + value (bools: one bit), see `server/rpc.py`.

**Pawn properties** sent at spawn: `bNetOwner`, `EntityIDLowInt/HighInt` (= character id), `m_iRaceId`, `Health`, `m_PlayerDisplayName` (FString). With these the character model is visible.

**Chat.** Zone event `0x70` (wstr) = message of the day. Client Say = zone event `0x74` (wstr); the client echoes it locally. Zone event `0x0f` (wstr text, wstr speaker, i32 channel) posts a chat line ("[channel][speaker]: text").

**Position persistence.** The server saves the last `ClientLoc` per character and spawns there next time (same chunk).

**Chunk travel.** Zone events `0x1` / `0x9` (raw: eid64-like pair = chunk x, y; bool; wstr) call `VGPlanet::MoveViewActorToChunk(x, y)` (`FUN_0099eda0`) — not yet used.

**Character sheet.** Zone event `0x3de` MsgScore (111 fields, registrar `FUN_005db5d0`, handler `FUN_005e8260`) drives the level shown on the HUD portrait, the XP bar and the character window title ("Level 10 - Thestran Warrior"). Inferred fields (wire index): 0–2 position, 3–4 chunk, 5 race, 6 gender, 7 class, 8 adventure level, 9 adventure XP, 10 class, 12 crafting level, 14 harvesting level, 16 diplomacy level, 21 XP for next level, 29 movement speed. See `server/vgmsg.py`. The character window's name is SetNameID's string at `+0x1b0`.

**Stats.** Dispatcher `FUN_00577bc0`: `0x2d3` creates one stat (MsgSingleStatInfo, `FUN_00577790`), `0x2d5` is an i32 count followed by creates, and `0x2d4` MsgStatUpdate (`FUN_00576c90`) changes a stat that already exists, found by instance id + category. Creating HP (`0xd2`), Endurance (`0xe0`) and Energy (`0xee`) fills the HUD bars and the character window (`PCAdvHitpointsMax`...). The attribute values (`PCAdvStrength`...) are only set on the **update** path (`FUN_00573070`), so the server creates the stats and then sends an update for each attribute. Stat ids (wire field 0): Strength 3, Constitution `0x6f`, Dexterity `0x73`, Vitality `0x9a`, Intelligence `0x9e`, Wisdom `0xaa`; resists Fire `0x37`, Physical `0x72`, Mental `0x89`, Arcane `0xa3`, Cold `0xba`, Spiritual `0xbd`, Shadow `0x100`, Holy `0x101`, Planar `0x102`. Skills are stats with kind (field 10) 2 and a list subtype (field 12): 0 weapon types, 2 wield types, 3 armor, 4 combat, 7 perception and concealment, 8 resistance, 9 spell schools, 0x15 harvesting, 0x1e general (kind 4 + subtype 1 = weapon specialization); field 8 is the cap the bar fills toward. The full stat id → name table (260 ids, `FUN_00d03670`) is `server/stat_names.py`. Field layouts are in `server/vgmsg.py`. MsgScore field 35 = XP bar fraction and field 42 = Armor Class. Verified live: the character window shows the server's values.

**MsgScore** field map (all 111 fields, `FUN_005e8260`): [MSGSCORE.md](MSGSCORE.md). Fields 0–4 are the bind point; Attack/Ranged display −field 45/52; Defense = 100·(10·field 63)^0.7.

**Inventory** (verified live): `0x195` resets the inventory UI and creates the 50-slot main grid, then one `0x197` MsgSingleItemInfo per item (field 7 equip slot = −1, field 15 container = −1, field 16 slot, field 6 quantity, field 13 icon number from `VGUIAssets/Global/Icons/iconsTK.xml`), then `0x1bb` coins in copper (no chat line; `0x1aa` prints one). Details: [INVENTORY.md](INVENTORY.md).

**Chat channels:** zone event `0x0f` channel 3 = Say ("X says, ..."), 5 = Emote; other values print "[???]".

**Standing on the ground** (verified live). The client runs the player's pawn as a simulated proxy, and `APawn::TickSimulated` (`FUN_00a03070`) forces `PHYS_Flying` unless the pawn has `bSimulateGravity` set, so the character hovered. Replicating `bSimulateGravity = True` on the pawn makes it fall and land (Physics 1, Base set). Replicating `Role`/`RemoteRole` does not help: the client zeroes Role 3, and Role 4 broke the location. The stub spawns 90 units below the saved z (`SPAWN_Z_LIFT`) and ignores near-origin positions when saving.

**Equipment** (verified live): each worn item is first sent as a `0x197` item (the stub uses bag slot 49 − n), then `0x1a7` {i32 item handle, u8 0, u8 equip slot} moves it onto the paper doll. Slots include HEAD 0, CHEST 6, PRIMARYHAND 28, SECONDARYHAND 29, TWOHANDS 36, RANGED 42 (`vgmsg.EQUIP_SLOTS`).

**Abilities** (verified live): `0x21b` resets the ability book, one `0x215` MsgAbilityInfo (68 fields: name, description, handle, command, type text, level, id, icon, cast/recovery/refresh times, ranges, costs...) per ability, then `0x21d` ends the list. Using an ability sends client event `0xd0` {i32 handle}. Details: [ABILITIES.md](ABILITIES.md).

**Hotbar and HUD windows** (verified live): `0x54e` is a hotkey list (i32 count, then per entry `wiiiwwi`: bank name such as `m_wb`, slot, ability id or −1, item instance or −1, two strings, i32) that fills the bars; the client reports changes with `0x54b` (set) and `0x54c` (clear). After character select the hotbar, compass, menu bar, bag bar and lag meter are loaded but hidden; zone event `0x598` (wstr console command) runs a client console command, and `SGOUI toggle "<window>"` shows each one. It toggles, so send it once per session.

**System text.** Zone event `0x192` (wstr text, i32 colour) prints a line into the chat window without a speaker: 3 white, 4 red, 5 orange (combat), 6 blue, 7 tan.

**Targeting and combat** (verified live 2026-10-12, `server/combat.py`). Clicking a pawn sends client event `0x5d` {u64 entity id}; the client draws the selection ring. The server confirms with zone event `0x3e0` MsgPlayerCharacterUpdate {offensive target u64 + u8 health, defensive target u64 + u8, third u64 + u8} (handler `FUN_005e7df0`; without it the target window stays at 0%). `0x3e1` {u64 entity id, u8 health 0–255} updates the target window's health bar (`FUN_005ea760`, shown as byte·100/255) and is ignored unless the id is the confirmed offensive target. On death the server replicates `Health = 0` and `m_bIsDead = 1` (pawn `+0x3e8`; the name plate turns grey) and sends zone event `0x2e` {u64 entity id, i32 animation, i32 arg} with animation 1, which plays the death animation (`FUN_0061fd10` → `FUN_00bbb490`; ids 1–3 are death animations, resolved by `FUN_00bb33e0`). Damage numbers are placeholders. The player's health bar follows a `0x2d4` update of the Health stat (id `0xd2`: value = current, field 7 = maximum). Clearing `m_bIsDead` (with `Health` back up) makes a dead pawn stand again.

**Open:**
- (Solved) Non-owned pawns: SGOPCPawn and SGONPCPawn render, with name plates and minimap entries, once they also carry `bSimulateGravity = True` (verified live 2026-10-12; `python login_stub.py --test-npc`). Without it they hover, and earlier tests did not show them.
- Skill group header values; armor skills (subtype 3) don't show yet.
- Gender, face sliders and gear (`m_AttachmentGroups` = SGOAttachmentGroupInfoPair {slot, attachment, package}).

## Reference

**ID tables**

| Table | Values |
| --- | --- |
| World status (`FUN_00cda3b0`) | 2 Loading, 3 Locked, 4 Up, 5 Low, 6 Medium, 7 High, other Down |
| Race (`FUN_00d02540`) | 0 Cat Person, 1 Deep Dwarf, 2 Dwarf, 3 Dark Elf, 4 High Elf, 5 Wood Elf, 6 Gnome, 7 Goblin, 8 Half Elf, 9 Lesser Giant, 0x0a Halfling, 0x0b Orc (also 0x10), 0x0c Kojani, 0x0d Qaliathari, 0x0e Thestran, 0x0f Mordebi, 0x11 Raki, 0x12 Vulmane, 0x13 Kojan Barbarian, 0x14 Varanthari, 0x15 Varanjar, 0x16 Kurashasa |
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

- What the server must send after `BECOME_PC` (zone event 0x71) to spawn the player.
- Meaning of the `0x66` header's first 0x80 bytes and the extra slot field.
- Exact semantics of the 12 bytes after the name in Play and of the 180 appearance integers.
- Event numbers for the delete and customize results as the client expects them; remaining events `0x5dd`, `0x5df`, `0x5e1`, `0x725`.
