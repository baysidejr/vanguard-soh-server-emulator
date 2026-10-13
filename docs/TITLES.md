# Titles and the game clock

> **Verified live (2026-10-13):** at login the server sends 0x35f with the character's titles (starting titles "Wanderer" (prefix) and "of the Wastes" (suffix) from `server/content/titles.json`). `/titleset Wanderer` sends 0x185 {id} and the client prints "You will now be known as Wanderer Ranger."; `/titleset "of the Wastes"` (multi-word names need quotes) gives "...Wanderer Ranger of the Wastes.". The server saves the choice and replicates `m_PlayerDisplayTitlePre`/`m_PlayerDisplayTitlePost` to everyone in the chunk: a second client (Justins) sees "Wanderer Ranger of the Wastes" over Ranger. The title strings are also part of the pawn's spawn properties, because at login the Unreal channel is not open yet. WORLD event 0x1d sets the game clock: `/time` then prints "Game time: 07/01/1000 12:35:00." instead of 01/01/1000.

Server: `server/titles.py`, `login_stub.title_login/handle_title_event/grant_title`. Quests can grant a title (`reward.title`; "Wanderer Trouble" gives "Camp Defender"). Dev command `!title <id>`. The game day runs 72 real minutes (20x speed) from 2026-10-13 00:00 UTC = day 0, 12:00.

The rest is the client analysis (static, by a research agent).


[O] means read directly from the disassembly. [I] means inferred.

## 1. Titles

Client state is the object at `[0x1463a20]`. It holds two title lists, each sorted by name on insert (`FUN_005c8400`):
- `+0x04` prefix list. Gamevar `TitlesPrefix`.
- `+0x10` suffix list. Gamevar `TitlesPostfix`.
- `+0x20` index of the active prefix (`TitlesPrefixActiveIndex` / `TitlesPrefixActive`). `-1` means none.
- `+0x24` index of the active suffix (`TitlesPostfixActiveIndex` / `TitlesPostfixActive`).
- `+0x28` `bShowMyTitles`.
- `+0x29` `bShowOtherTitles`.

Each title entry is `{wstring name; +0x1c i32 id; +0x20 bool isSuffix}`. [O]

### Server to client (zone dispatcher FUN_005c88e0)

| id | layout | meaning |
|---|---|---|
| **0x35f** full title list | header `{i32 count, i32 activePrefixId, i32 activeSuffixId, bool8 bShowMyTitles}` (`FUN_00462e30`), then `count` × `{wstr name, i32 titleId, bool8 isSuffix}` (`FUN_005c53d0`, the same record as 0x360). | [O] `FUN_005c8600` reads the header, then loops `count` times. A record goes into the suffix list if `isSuffix` is true, otherwise into the prefix list. If a record's id equals `activePrefixId`, its index becomes the active prefix; if it equals `activeSuffixId`, it becomes the active suffix. The header bool is stored in `bShowMyTitles` (+0x28). Then it refreshes the gamevars and sets bit 0 of `[obj+0x51c]` (obj = `FUN_00b71a30()`). Send `-1` or another unused id for "no active title". The client adds to its lists and never clears them here, so send this once at login. [I] |
| **0x360** title granted | `MsgTitleInfo {wstr name, i32 titleId, bool8 isSuffix}` | [O] `FUN_005c87c0` adds the title to the matching list and prints `TitleNewTitle` with the name as `%s`. |
| **0x361** title revoked | `MsgSingleInt {i32 titleId}` | [O] `FUN_005c6e20` removes the id from the suffix list (or else the prefix list), fixes up the active index, and refreshes the gamevars. |
| **0x362** clear active | `MsgSingleBool {bool8 isSuffix}` | [O] `FUN_005c68e0`: `isSuffix=1` clears the active suffix and `0` clears the active prefix. **Side effect:** if the slot was set, the client also sends **c2s 0x186** `{bool8 isSuffix}` and prints `TitleSuffixRemoved` or `TitlePrefixRemoved`. |
| **0x363** force select | `MsgSingleInt {i32 titleId}` | [O] `FUN_005c80e0` looks up the id (`FUN_005c5fe0`). If it is unknown it prints `TitleNoSuchTitle`; if it is already active it prints `TitleAlreadySelected`. Otherwise it sets the prefix or suffix slot, **sends c2s 0x185 `{i32 titleId}`**, and prints `TitleChanged`/`TitleNowKnownAs` (`FUN_005c7990`). |

### Client to server (zone, via FUN_004cfb00/FUN_004cfb50 → FUN_00409210)

| id | layout | trigger |
|---|---|---|
| **0x185** select title | `MsgSingleInt {i32 titleId}` | [O] Sent by `/titleset <title name>`. Handler `0x608c20` calls `FUN_005c7d40`, which looks the title up **by name** (`FUN_005c7400`), not by number, so `/titleset 1` prints "You do not have that title." The client checks the title is owned and not already active, updates the slot locally, sends 0x185, and prints `TitleNowKnownAs`. It is also echoed after s2c 0x363. The UI `title_select` command most likely uses the same path. [I] |
| **0x186** remove title | `MsgSingleBool {bool8 isSuffix}` | [O] Sent by `FUN_005c68e0`: the UI remove action, and the echo after s2c 0x362. |
| **0x187** toggle my titles | no payload | [O] `/togglemytitle` (`0x5fc510` → `FUN_005c5410`) flips `bShowMyTitles` locally, prints `TitleMineDisplayOn`/`Off`, and sends 0x187. |
| none | none | [O] `/toggletitles` (`0x5fc520` → `FUN_005c5f50`) is **local only**. It flips `[0x18b9404]+0x11c`, sets `bShowOtherTitles` (+0x29), sets bit 0 of `[obj+0x51c]`, and prints `TitleOthersDisplayOn`/`Off`. |

### Over-head display

The client never writes the title into the pawn. `FUN_005c7990` (TitleChanged) and the name builder `FUN_00418280` only *read* these replicated pawn strings. [O for reads, I for "never writes"] The native offsets come from the pawn constructor `FUN_007fe610`. The replication indices come from `server/netcache.py` for `SGOPCPawn` (max 125):

| property | type | native offset | replication index |
|---|---|---|---|
| `m_PlayerDisplayName` | Str | +0x718 | 59 |
| `m_PlayerDisplayTitle` | Str | +0x724 | 83 (the second line under the name, e.g. "Guard" or a guild) |
| `m_PlayerDisplayTitlePre` | Str | +0x734 | **82** |
| `m_PlayerDisplayTitlePost` | Str | +0x740 | **81** |

The displayed name is built as Pre + " " + Name + " " + Post. [O, from the TitleChanged string build]

### Recommended server flow

1. **Login:** send 0x35f with all owned titles. Each record is `{name, id, isSuffix}`. The header carries the active prefix id, the active suffix id (or -1), and `bShowMyTitles`. Replicate `m_PlayerDisplayTitlePre`/`Post` on the player's pawn with the active strings. Leave them empty if `bShowMyTitles` is off.
2. **Grant a title:** store it, then send 0x360 `{name, id, isSuffix}`.
3. **Revoke a title:** send 0x361 `{id}`. If it was active, clear it and replicate an empty Pre/Post.
4. **0x185 `{id}` received:** validate ownership, set the active prefix or suffix (based on the title's `isSuffix`), persist it, and replicate the Pre/Post string to everyone, the owner included. Do **not** answer with 0x363, because the client would echo 0x185 again.
5. **0x186 `{isSuffix}` received:** clear that slot, persist it, and replicate an empty Pre/Post. Handle it idempotently, because it can also arrive as the echo of s2c 0x362.
6. **0x187 received:** flip the stored `bShowMyTitles` and replicate Pre/Post as empty or as the real strings. `bShowOtherTitles` is client-side only.
7. **GM or quest-forced changes:** use 0x363 (select) or 0x362 (clear). The client echoes 0x185/0x186, which the steps above handle idempotently.

## 2. /time (game clock)

- [O] `/time` (`0x600080`) is **entirely local** and sends nothing. It reads the client game clock at `[0x1475e0c]` and prints `GameTime` with the format `%02d/%02d/%04d %02d:%02d:%02d` = **day/month/year h:m:s**, then `LocalTime`.
  - year = `day/360 + 1000`
  - month = `(day%360)/30 + 1`
  - dom = `day%30 + 1`
  - hours, minutes and seconds come from `secondsOfDay` (`FUN_005fdbf0`).
- [O] **Zone event 0x10e is not sent by /time.** It is sent by `/location` (`0x5fec60`, at `0x5fede8`, no payload) after it prints the local "Loc" line.
- Clock struct (created in `FUN_0099c760`):
  - `+0` secondsOfDay. Initialised to 0xa8c0 = 12:00.
  - `+4` dayNumber. Initialised to 0.
  - `+8` / `+0xc` pending seconds / pending day, used while the clock is stopped.
  - `+0x10` speed: game seconds per real second, **20**. One game day is 72 real minutes.
  - `+0x18` time of the last tick.
  - `+0x20` tick period: 0.25 s. `0` means stopped (`/stoptime`, `/starttime`).
  - `+0x28` dirty flag.
- [O] The tick (`FUN_0098b2d0`) adds `round(elapsed*20)` seconds and wraps at 86400 into `day+1` (`FUN_00988c90`).
- **[O] Server sync is WORLD event 0x1d** in the world-server dispatcher `FUN_0062aaf0` (case at `0x62ad6f`). It is a raw payload, not a message class: `{i32 secondsOfDay (0..86399), i32 dayNumber}`. It calls `FUN_005184c0` (sets the seconds and stamps the tick time) and `FUN_00518490` (sets the day). Days count from 01/01/1000. A 360-day year has 12 months of 30 days.
- No zone message or replicated property sets the clock. [O for this dispatcher only; no other writer to the struct was found]
- [I] Two level-load paths reset or alter the clock depending on flags:
  - `0x99e14a` (when `[0x141cf64]==0`): seconds = 0 and period = 0.25.
  - `0x99dcd3` (when `[0x1485fec]==0`): sets 14:00 and stops time.
  - **Recommendation:** send world 0x1d after login and again after each zone entry, and periodically (for example every few minutes) to correct drift. Server time model: `secondsTotal += 20 * realSeconds`, giving `secondsOfDay = total % 86400` and `day = total // 86400`.

## 3. /played

- [O] `/played` (`0x5fc650`) sends **zone c2s 0x10f** with no payload (`FUN_00409210`).
- [O] The reply is **zone s2c 0x10f** `MsgSingleInt {i32 seconds}`. `FUN_005e7520` passes the value to `FUN_00552260(value, buf, 1, 1)`.
- [O] **The unit is seconds.** `FUN_00552260` divides by 86400, then 3600, then 60, and appends " day"/" days", " hour"/" hours", and so on. The `1` flag selects the long word forms; otherwise it uses ":".
- Server: track accumulated online seconds per character and reply with `int(total_seconds)`.
