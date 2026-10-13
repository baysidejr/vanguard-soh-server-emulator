# Social: /who, friends, ignore, flags, /random, /inspect

**Verified live (2026-10-12, two clients):**
- `/who all` lists both players ("Justins: Level 12 Warrior, 1 Diplomat - Sundering Wastelands", then "2 player(s) found.").
- `/friend Ranger` prints "You have added Ranger to your friends list."
- `/random` rolls a Magic Die that everyone in the chunk sees.
- `/inspect Ranger` opens the Inspect window with Ranger's equipped gear.
- When Ranger's client disappears, Justins gets "Ranger has gone offline." (`0x4f6`).
- After `/afk` and `/anon`, Ranger shows in /who as "Ranger (AFK) [Anonymous]".

The code is in `server/social.py` and `login_stub.handle_social_world` / `handle_social_zone`. Friend and ignore lists are saved per character (`friends`, `ignores`).

## World connection, packet type 5 (social)

The world server's type-5 packets use the same frame as types 2 and 6: `u16 5, u32 id, u32 len, payload`. The client handler is `FUN_00625350`.

| Direction | Id | Payload | Meaning |
|---|---|---|---|
| C→S | `0x44` | raw 0x160-byte struct (offsets below) | `/who [all] [level] [level] [class...] [lfg] [name]` |
| S→C | `0x501` | none | clear the who list |
| S→C | `0x500` | MsgWhoInfo (fields below) | one player |
| S→C | `0x502` | `i32 count, i32 mode, i32 trial count, bool8 cut short` | print the list and "N player(s) found." |
| C→S | `0x4f7` | `wstr name, bool8` | `/friend name`. The server toggles: add, or remove if already listed |
| S→C | `0x4f2` / `0x4f3` | MsgFriendInfo | friend added / removed |
| S→C | `0x4f6` | MsgFriendInfo | status change: "X is now online." / "X has gone offline." |
| S→C | `0x4f9` | `i32 n`, n × MsgFriendInfo | the full friend list (sent at zone login) |
| C→S | `0x4f8` | `wstr name, bool8` | `/ignore name` (toggle) |
| S→C | `0x4f4` / `0x4f5` / `0x4fa` | MsgFriendInfo / list | ignore added / removed / full list |

**The /who request struct:**
- 4/8: chunk x/y filter (-999999 with `all`).
- 0xc/0x10: minimum/maximum level.
- 0x14: 32 class ids (-1 = none).
- 0x94: crafting class.
- 0x98: LFG mode.
- 0x99–0x9c: lfm/count/guild/friend flags.
- 0x9e: name filter (UTF-16).

**MsgWhoInfo, in wire order:**
1. `i32 id, wstr name, wstr guild`
2. `i32 level, i32 class`
3. `i32 0, i32 0`
4. `i32 craft level, i32 craft class` (0xff = none)
5. `i32 diplomacy level, i32 chunk x, i32 chunk y, i32 0`
6. `u8 lfg, bool8 lfm (Find list: shows "Request to Join"), bool8 afk, bool8 anonymous`
7. 23 × `wstr ""`, then 96 × `i32 0`

**MsgFriendInfo:** `i32 id, wstr name, i32 level, bool8 online, i32 class, i32 craft level, i32 craft class, i32 chunk x, i32 chunk y, u32, bool8 anonymous`. Offline friends use -1 for level, class and chunk.

## Zone events

| Direction | Id | Payload | Meaning |
|---|---|---|---|
| C→S | `0x505` | `bool8` | `/afk` |
| C→S | `0x5a6` | `i32, bool8` | `/anon` (the client always sends 1, so the server toggles) |
| C→S | `0x503` | `bool8` | `/lfg` |
| C→S | `0x15a` | `i32 min, i32 max` | `/random` (default 1..100). The client prints nothing; the server sends the result line |
| C→S | `0x48c` | `wstr name` | `/inspect [name]` |
| S→C | `0x48d`, `0x490 {wstr name, wstr class, i32 level}`, `0x48f` (an item record per equipped item), `0x48e` | | the Inspect window, in this order (`0x48f`/`0x490` are dropped without `0x48d` first) |

Not done yet: server-side ignore filtering (the client already hides ignored speakers). The Find window, LFG/LFM and Request to Join are in GROUPS.md; guilds in GUILDS.md.

## /played (verified live 2026-10-13)

The client sends zone 0x10f (no payload); the reply is zone 0x10f {i32 seconds} (handler FUN_005e7520, formatted by FUN_00552260 into days/hours/minutes/seconds): "You have played for: 16 seconds". The server saves `played` per character when the zone connection ends (not on chunk handoffs).

## Find window (verified live with two clients, 2026-10-13)

The Social window's Find tab sends world type-5 **0x503** (LFG page) or **0x504** (LFM page) {u8 search, u8 flag, 32 x (i32 class, i32 dungeon, i32 quest)}; search = 1 comes from the Search button (or opening the page), 0 from the /lfg or /lfm toggle. The reply is the /who sequence with a page mode: 0x501, one 0x500 per player, 0x502 {count, mode 1 = LFG page / 2 = LFM page, 0, 0}. The LFG page lists group leaders and players flagged LFM; the LFM page lists ungrouped players flagged LFG. Verified: after Justins types /lfg, Ranger's "Find members for my group (LFM)" page lists "Justins 20 Warrior Sundering Wastelands" (1 result). Dungeon, quest and class preferences are ignored for now. **Request to Join (verified live 2026-10-13):** the second byte after `u8 lfg` in MsgWhoInfo becomes find-list entry +0x62; when it is set (we set it for players flagged LFM and for group leaders) the entry shows a leader star and selecting it swaps "Invite to Group" for "Request to Join" (FUN_0057fba0 -> gamevar bShowInviteToGroupBtn). That button sends world 0x58b {wstr leader}; see GROUPS.md. `!lfm` flags you as LFM without being a leader (testing).
