# Chunk travel (crossing chunk_n19_12 into chunk_n20_12)

Static analysis of VGClient.exe (Ghidra/REA plus capstone).
- **[O]** = observed in code or data.
- **[I]** = inferred.

## TL;DR

Client zone event 0x9 is not a notification that needs an ack. It is the client asking the RegionServer to hand it over to the server that runs the new chunk. The retail answer is a full UE2 re-connect: **world event 8** ("connect to zone host:port, chunk_n20_12"), sent on the world connection.

The client then:
1. drops its zone connection and opens a new one;
2. runs HELLO…WELCOME LEVEL=chunk_n20_12 again;
3. because a seamless chunk move is pending, swaps GLevel to the already-streamed chunk_n20_12 instead of loading a map (`ChangeChunkMap` `FUN_0098ca30`);
4. destroys the old pawn and waits for a new PlayerController.Pawn on the new connection;
5. finally positions that pawn (`FixupViewActor` `FUN_00991800`).

Until a travel arrives, the client stays half-switched:
- VgPlanet's "current chunk" is (-20, 12).
- GLevel, the pawn's XLevel and its coordinate frame are still chunk_n19_12.
- The traverse checker is suspended.

Every trace the pawn makes in this state is resolved against the wrong level or frame. That is the endless 90-unit climb.

## 1. Client-side flow [O]

### 1a. Detection: `VgPlanet::CheckPlayerTraverseChunk` = `FUN_0099f550` (per tick)

**When `planet+0x300` is not 0** (a move is pending):
- State 1 returns at once, so nothing else happens.
- State ≥ 2:
  - it waits until all of these hold:
    - `PC.Level` (+0xf8) is set;
    - `LevelInfo+0x3f1 == 0`;
    - `PC.Pawn` (+0x390) is not null;
    - `Pawn != planet+0x2b0`;
  - it then counts `+0x300` up to 4 (3 ticks);
  - it calls `FixupViewActor` `FUN_00991800`;
  - it clears `+0x2b0` and `+0x300`;
  - it calls `FUN_0098ce40(1)`.

**When idle:**
- If the pawn is past ±(102400−40):
  - it stores a fallback position at `+0x310`: the position clamped 5 units inside the edge (x = −102355 here);
  - it stores the travel location `+0x304` = position shifted by ±204800;
  - it calls `MoveViewActorToChunk(newX, newY, 0, 0, 0)`.
- If that fails, it FarMoves the pawn back to `+0x310`, calls `FindBase` and zeroes the velocity.
- "That area is currently down or locked." is printed if `FUN_0098f470` rejects the chunk.

**Chunk index versus coordinates** (`FUN_009897c0`, LevelForPoint):

| Pawn coordinate | Chunk change | Coordinate change |
|---|---|---|
| x < −102400 | cx − 1 | x + 204800 |
| x > 102400 | cx + 1 | x − 204800 |
| y > 102400 | cy − 1 | y − 204800 |
| y < −102400 | cy + 1 | y + 204800 |

The Y axis is inverted relative to the chunk index.

### 1b. `VgPlanet::MoveViewActorToChunk(x, y, bCmd, bMsg, name)` = `FUN_0099eda0`

1. Guard: at most once per second ("Not enough time has passed.") unless `+0x1b4` is set.
2. Saves into the planet:
   - travel state;
   - TravLoc `+0x304..0x30c`. If `bCmd` is true it is −99999, which means "Putting player at start location due to chunk command use";
   - pawn rotation `+0x31c`;
   - controller rotation `+0x328`;
   - destination name FString `+0x2f0`, copied from `name` / `PC+0x718`.
3. Finds or loads the new level (`vt+0x8c` / `+0xb0` / `+0xc8`) and logs "* * * Moving to chunk…".
4. **Sets VgPlanet current level and chunk:** `FUN_0099d0e0` sets `+0x2ac` = chunk_n20_12 ULevel and `+0x2dc` = (−20, 12). This part only adds weather; it does not touch GLevel or the actors.
5. Sets **`+0x300 = 1`** and calls `Pawn->vt+0x350(0)`.
6. Chooses the path through `engine->vt+0x15c` (IsConnected, `FUN_00bcf250` → interface `+0x10`):
   - **Offline:** `FUN_0099c930` (PostTravelFixupTwo). It destroys the pawn, spawns a play actor in the new level (engine `+0x1bc`), runs FixupViewActor and re-homes the actors' Level/XLevel.
   - **Online:** `ConnectToChunk` `FUN_0099e770` → `engine vt+0x190` = `FUN_00bcf8a0` → `SGOEngineCore::Engine` vt+0x58 = **`FUN_00b71570`**. This builds the 0x9 message and sends it. Nothing else happens.
7. Afterwards: neighbour streaming (`FUN_0099adc0`, which logs "up for play") and sky/weather (`FUN_00995520`).

### 1c. Client→server zone event 0x9 payload [O]

Sent by `FUN_00b71570`, at 0xb715ab–0xb715c3:
- call: `sender->vt[0](5, 0, 9, &buf, 0x8c)`;
- the buffer is a 140-byte stack buffer;
- only 3 fields are written; the rest is uninitialised stack.
- The observed 150 bytes = 10-byte zone header + 140.

| Offset | Type | Meaning |
|---|---|---|
| +0 | i32 | target chunk X (−20) |
| +4 | i32 | target chunk Y (12) |
| +8 | u8 | bCmd: `MoveViewActorToChunk` param_3. 0 = walked or teleported across (TravLoc valid); 1 = chunk command (put at start) |
| +9 | u8 | padding (garbage) |
| +10 | wchar[65] | destination or start name. **Not filled** by the client (garbage) |

The server→client direction uses the same struct (`FUN_00620750`: `FUN_00b70ae0(x, y, +8 != 0, 0, wstr@+10)` → `FUN_0099eda0`). So **server→client 0x1/0x9 means "begin a chunk move"**, the same thing the client already did. Online, it just sends 0x9 again, which matches the live result. It completes nothing.

### 1d. What completes the move

**World event 8 handler** (`FUN_0062aaf0` case 8):
- Payload: u32 port, wchar[64] host, wchar[64] chunk name.
- Logs "Connecting to %s:%d (%s)".
- Calls `engine->vt+0xf0(viewport, "host:port", 0, 0)` (SetClientTravel, absolute).
- Calls `FUN_006ed160`. It closes the current zone connection (`+0x138`→vt+0x20) and the UE2 connection (`+0x13c`), then `FUN_006ec2f0` reconnects to the new address. It logs "Attemping to connect to chunk. Chunk Address…" in `#ClientZoneConnections.log`.

**`UGameEngine::Tick`** `FUN_008f7430`, when the pending level is ready (0x8f7ab0…):
- It first calls **engine vt+0x130 = `FUN_00bcf400`**.
- If `engine+0x244 & 1` (the Seamless bit) and `planet+0x300 != 0`, it clears bNeedLoadMap and calls **`ChangeChunkMap` `FUN_0098ca30(PendingLevel->URL, PendingLevel, 0, Error)`** instead of `LoadMap` (vt+0x1c0).
- If the load reports an error and `planet+0x300 != 0`, it calls `CancelMoveToChunk`.

**The Seamless bit:**
- Engine vt+0x1b8 = `FUN_00bcfb40` parses the URL options `Seamless=` (bit 0) and `SingleChunk=` (bit 1).
- `bin/User.ini` `[DefaultPlayer]` has `Seamless=1` and `SingleChunk=0`. These are default URL options, so the client's travel URL carries `?Seamless=1` (you can see it in LOGIN).

**`ChangeChunkMap` `FUN_0098ca30`:**
1. destroys the current pawn: `XLevel->vt+0xb8` (DestroyActor, bNetForce=1);
2. runs the engine's LoadMap stages (vt+0x198/0x19c/0x1dc/0x1a0);
3. **sets GLevel (engine+0x190) = `planet+0x2ac`**, the already-streamed chunk_n20_12;
4. runs vt+0x1a8/0x1ac/0x1b4/0x1bc;
5. destroys the new view pawn if one exists;
6. sets `planet+0x2b0 = 0` and **`planet+0x300 = 2`**.

**Then** the PC and pawn arrive on the new connection. CheckPlayerTraverseChunk state ≥ 2 calls **`FixupViewActor` `FUN_00991800`**, which:
- logs "* * * Setting player loc to TravLOC…";
- restores the controller and pawn rotation;
- if the `+0x2f0` name is empty: `FUN_00989a10(TravLoc)`, which is FarMoveActor(pawn, TravLoc.xy, TravLoc.z + CollisionHeight) in the new level;
- otherwise: `FUN_009912c0(name…)`, which places at a named spot;
- copies flags, calls GotoState and calls `Pawn->vt+0x350(0)`.

**Cancel paths:**
- **`CancelMoveToChunk` `FUN_0099e580`:**
  - clears `+0x300`;
  - finds the chunk from `planet+0x2ac+0x78` (a level URL/name FString);
  - re-selects it with `FUN_0099d0e0`;
  - FarMoves the pawn to `+0x310` and zeroes its velocity.
- **Triggers:**
  - world event **0x15** ("That chunk is not yet ready to be entered.", no payload);
  - world 0x33 / 0x60 (MsgInvalidChunkInfo → `FUN_0099b0f0`);
  - zone-connection failure (`FUN_00b70de0` ← `FUN_006ea950`);
  - a travel error in `FUN_008f7430`.

There is no zone event that "commits" a chunk change, and nothing re-parents the existing pawn online. Retail always destroys the pawn and gets a new one over a new net connection.

## 2. Why z climbs by 90 [O]/[I]

After step 1b the client has this state:

| Item | Value |
|---|---|
| `planet+0x2ac` / `+0x2dc` | chunk_n20_12 / (−20, 12) |
| GLevel, `Pawn.XLevel` (+0xfc), `Pawn.Level` (+0xf8) | chunk_n19_12 |
| `planet+0x300` | 1 (CheckPlayerTraverseChunk frozen, so there is no edge clamp and no further crossings) |

Every pawn trace converts coordinates relative to the **planet's** chunk:
- **[O]** `FUN_009897c0`: inside ±102400 it returns `planet+0x2ac`; outside, it returns the neighbour of (−20, 12) and shifts the point.
- **[O]** The actor trace wrapper `FUN_007e9fb0` traces XLevel (n19_12) first, then that level.
- **[O]** The ground-stick `FUN_00bb81f0` traces only in the returned level and converts the hit back with `FUN_00989690` / `FUN_00a046c0`.

The pawn's numbers, however, are still in chunk_n19_12's frame. Terrain under the points involved (`terrain_height.py`, y = 30000):

| Level | x = 101600 | x = −103200 |
|---|---|---|
| chunk_n19_12 (XLevel / GLevel) | **−9380** (sea floor at its east edge) | off terrain |
| chunk_n20_12 (planet current) | **2730** (the real ground) | off terrain |
| chunk_n21_12 (LevelForPoint for x = −103200 once the planet is at −20) | −5570 | off terrain |

- At x = −103200 the stick traces chunk_n21_12 at x = 101600 (terrain −5570) from z ≈ 5400. The 3600-unit probe misses.
- At x = 101600 the floor finder (FindBase) traces chunk_n19_12 first and finds its sea floor at −9380.

So the floor is never where the pawn is.

Two code paths turn such a miss into exactly +90:
- **[O]** **Ground-stick `FUN_00bb81f0`:**
  - with gravity direction `+0xaf4 = 5`, `FUN_00bb08a0` makes the probe −40·CollisionHeight and the offset +CollisionHeight;
  - on a miss, or a hit at time 0, the new Z is `LastValidServerPosition.Z + CollisionHeight` (= +90);
  - it then writes `LastStickToMeshZ`;
  - **[I]** it becomes cumulative whenever `LastValidServerPosition` is re-seeded from `Location`: 0xbb826c, taken when `LastStickToMeshTime == 0`, or a new PawnPosition.
- **[O]** **SGOPCPawn FindBase** (vt+0x17c = `FUN_00bce2c0`, called from FarMoveActor 0xa09dc0, TickSimulated 0xa038d0 and PostNetReceive 0x7f95b4):
  - it probes 50000 down;
  - on a miss while Physics = 2 it raises the start by a hard-coded **90.0** and retries (10× +90, then +1400);
  - when a retry hits, it **FarMoves the pawn to the raised start**;
  - it then discards the base because |z − hit.z| > 16, which leaves **Base = None**.

**[I]** Which of the two drives the observed climb needs one memory snapshot to decide. Read pawn `+0x8d0`, `+0x8d4`, `+0x8e4..0x8ec`, `+0x39` and `+0x7c` (Base) across two ServerMoves. Either way the root cause is the half-finished chunk switch, not terrain data. Teleporting inside n19_12's frame cannot fix it, because the planet's chunk origin stays at (−20, 12) until a travel or a cancel.

## 3. Testable server recipe

### Recipe A: retail-style seamless travel (recommended)

1. **Receive C→S zone 0x9** `{i32 cx, i32 cy, u8 bCmd, …}` = (−20, 12, 0).
   - Ignore bytes +9 and up.
   - Compute the new frame position with the table in 1a. Here x' = −103200 + 204800 = 101600 and y' = 30000.
   - Compute z' = terrain(chunk_n20_12, x', y') + 90 = 2820.
   - Set `player.level = "chunk_n20_12"` and the position to (x', y', z').
   - Mark the session as "chunk handoff pending", so the coming zone disconnect is not a logout or leave_world.
   - Stop saving ClientLoc until the new pawn is spawned.
2. **Send S→C WORLD event 8** on the world connection: `u32 zone_port, wchar[64] host, wchar[64] "chunk_n20_12"`. Use the existing `build_zone_connect_event(args.world_address, args.zone_port, "chunk_n20_12")`.
   - Client log: "Connecting to host:port (chunk_n20_12)".
3. **The client closes its zone SOE connection** and opens a new one with zone login type 3 (same account and session key). Reply type 4.
   - `ClientZoneConnections.log`: "Attemping to connect to chunk…".
4. **Run the UE2 handshake on the new connection exactly like the first login:**
   - HELLO → CHALLENGE → LOGIN (URL should contain `Seamless=1`);
   - **USES with chunk_n20_12 first**, then Core, Engine, SGOUnrealAbstractionLayer;
   - **WELCOME LEVEL=chunk_n20_12**.
   - Build the package map and net cache for chunk_n20_12. Object indices shift with the level's export count.
5. **The client runs `FUN_00bcf400` → `ChangeChunkMap`** (no disk load). It destroys the old pawn, sets GLevel = n20_12 and `planet+0x300` = 2.
   - Then expect JOIN. Expect zone 0x71 BECOME_PC too [I: same path as the first login].
6. **Open the PlayerController channel** (bNetOwner = 1), then **the SGOPCPawn channel**:
   - spawn location as in `spawn_location` (z' − SPAWN_Z_LIFT for the spawn bunch);
   - **PawnPosition** = (x', y', z');
   - bSimulateGravity;
   - make sure **PC.Pawn** points at the new pawn.
7. **The client runs FixupViewActor** after 3 planet ticks:
   - log: "* * * Setting player loc to TravLOC  PLocXYZ=… TRAVLocXYZ = 101600, 30000, …";
   - it FarMoves the pawn to TravLoc + CollisionHeight in n20_12.

   About 0.5 s later, re-send PawnPosition (x', y', z'), with or without 0x3e5. FixupViewActor's FarMoveActor does not refresh the stick cache.
8. **Check:**
   - the pawn stands at about z 2820 in chunk_n20_12;
   - ServerMove ClientLoc is now in n20_12's frame (|x| ≤ 102400);
   - walking back east triggers the mirror case: 0x9 (−19, 12), x' = x − 204800.

**Optional: chunk command or named arrival.** Set bCmd = 1 and give a name at +10 of a server→client 0x9 to start a teleport-style move: TravLoc = −99999, so the server's spawn position wins; with a name, `FUN_009912c0` places the pawn. The same world-event-8 handoff must follow.

### Recipe B: refuse the crossing (cheap interim)

- Reply to client 0x9 with **world event 0x15** (empty payload).
- The client runs `CancelMoveToChunk` and prints "That chunk is not yet ready to be entered.".
- `+0x300` is cleared, the pawn is FarMoved back to `+0x310` (x ≈ −102355) and its velocity zeroed. The edge then acts as a wall.

**[I]** Caveat: the revert looks the chunk up from `planet+0x2ac+0x78`. If that name is chunk_n20_12's own, the planet stays at (−20, 12) and you will need to test it. Re-send PawnPosition and 0x3e5 at (−102355, y, terrain + 90) afterwards.

### Do not

- Do not send server→client 0x9. It only restarts the client's request, which re-sends 0x9 and is rate-limited to once per second.
- Do not try to re-home the existing pawn with 0x3e5 or PawnPosition into the new frame. GLevel and XLevel stay chunk_n19_12 while the planet origin is (−20, 12).

## Key addresses

| Address | Role |
|---|---|
| `FUN_0099f550` | CheckPlayerTraverseChunk (planet state machine `+0x300`) |
| `FUN_0099eda0` | MoveViewActorToChunk |
| `FUN_0099e770` | ConnectToChunk → `FUN_00bcf8a0` → `FUN_00b71570` (sends 0x9, 0x8c bytes) |
| `FUN_0099c930` | Offline PostTravelFixupTwo |
| `FUN_0099d0e0` | Set planet current level / chunk |
| `FUN_009897c0` | LevelForPoint (±102400, Y inverted) |
| `FUN_0099e580` | CancelMoveToChunk |
| `FUN_00991800` | FixupViewActor |
| `FUN_00989a10` | FarMove view pawn (z + CollisionHeight) |
| `FUN_0098ca30` | ChangeChunkMap (seamless LoadMap replacement; `+0x300 = 2`) |
| `FUN_00bcf400` | Engine vt+0x130 hook |
| `FUN_00bcfb40` | Engine vt+0x1b8, `Seamless=` / `SingleChunk=` → engine `+0x244` |
| `FUN_008f7430` | UGameEngine::Tick pending-level completion |
| `FUN_0062aaf0` | World dispatcher: case 8 travel, 0x15 cancel, 0x33/0x60 invalid chunk |
| `FUN_006ed160` / `FUN_006ec2f0` | Zone reconnect |
| `FUN_00620750` / `FUN_00b70ae0` | Zone 0x1/0x9 S→C |
| `FUN_00bb81f0` | Ground-stick |
| `FUN_00bb08a0` | Gravity-direction probe and offset |
| `FUN_00bce2c0` | SGOPCPawn FindBase (vt+0x17c, 90-unit step-up) |
| `FUN_007e9fb0` | Actor trace wrapper (XLevel, then LevelForPoint level) |

**VgPlanet fields:**

| Offset | Field |
|---|---|
| +0x2a8 | engine |
| +0x2ac | current chunk ULevel |
| +0x2b0 | old pawn |
| +0x2dc | short cx, cy |
| +0x2f0 | destination name FString |
| +0x300 | travel state |
| +0x304 | TravLoc |
| +0x310 | fallback location |
| +0x31c | pawn rotation |
| +0x328 | controller rotation |
