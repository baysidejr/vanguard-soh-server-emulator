# Guilds

**Verified live (2026-10-12, two clients):**
- `!guildcreate` opens the client's own "Enter Guild Name" dialog (`0x4e7`). Accepting sends `0x4d3`, and the server prints "You have founded the guild Wastes Wardens."
- `/guildinvite Justins` opens the Guild Invite popup on the other client, and chat says "Ranger has invited you to join Wastes Wardens at the rank of Recruit."
- Accept prints "You have joined the guild.", and the leader sees "Justins has joined the guild."
- **Guild name over the head (verified live):** the player pawn's replicated `m_GuildId` (SGOPCPawn net field 122) is set at spawn and on create/join/leave. Every client also gets a `0x40` name tag for each guild, so Ranger shows "(Wastes Wardens)" under the name. After `/guildquit` the tag goes away and members see "Ranger has left the guild."
- Fields 123 `m_bIsAfk` and 124 `m_LfgStatus` are next to it, but replicating `m_bIsAfk` = 1 made the pawn vanish on every client, so AFK/LFG show only in /who.
- `/gu Hello guild!` shows as "[Guild][Justins]: Hello guild!" for the leader and "To [Guild]: Hello guild!" for the speaker.

The code is in `server/guild.py` and `login_stub.handle_guild_event` / `guild_login`. Guilds are stored in `server/guilds.json`, a local runtime file that is git-ignored.

The client's guild dispatcher is `FUN_004f1610`. Requests are zone events.

| Direction | Id | Payload | Meaning |
|---|---|---|---|
| S→C | `0x4e7` | none | opens the guild-name dialog (no slash command exists; the emulator uses `!guildcreate`) |
| C→S | `0x4d3` | `eid64, wstr name, ...` | create |
| S→C | `0x4dd` | `i32 guild id, i32 my rank` | membership (0 = none). Ranks are 1..10; 10 is leader, 9+ can invite/kick/promote |
| S→C | `0x4ea` | `wstr name, i32, bool8, bool8 recruiting, wstr notes, i32, i32, 10 × {wstr rank name, bool8 invite, bool8 remove, bool8 notes}, 20 × u8` | guild window header and rank names |
| S→C | `0x4eb`, `0x4ec` × n, `0x4ed` | member records | member list (clear, rows, end) |
| S→C | `0x4ee` | member record | one member changed. Rank 0 = removed; notify 1 joined, 2 removed, 3 quit; an online flag change prints online/offline |
| S→C | `0x40` | `u64 0, i32 id, wstr name` | guild id → name (overhead tags on pawns with that `m_GuildId`) |
| C→S | `0x4d5` | `wstr name` | `/guildinvite` |
| S→C | `0x4e9` | `eid64 inviter, wstr inviter, wstr guild, wstr rank, i32` | invite popup |
| C→S | `0x4d6` / `0x4d7` | none | accept / decline |
| C→S | `0x4dc` / `0x4db {wstr}` / `0x4da` | | quit / kick / delete |
| C→S | `0x4d8` / `0x4d9` | `wstr name` | promote / demote |
| S→C | `0x0e` | `i16` | 0xd8 joined, 0xd9 removed, 0xdc already in a guild, 0xde name too long, 0xe6 can't delete, 0x1a no guild |

**Member record:** `eid64 id, wstr name, i32 rank, i32 chunk x, i32 chunk y, i32 class, i32 level, bool8 online, bool8 recruiter, u32 last online, wstr personal note, wstr guild note, f32 points, wstr officer note, i32 notify`.

**Guild chat** goes over the world connection: type 6 command `"guildsay <text>"`. Members get `0x0f {text, speaker, 0x0b}`, and the speaker gets the echo `0x11 {text, 0x0b}`.

Not done yet:
- the MOTD (`0x4e2`/`0x4e1`), rank renaming (`0x4d2`) and notes
- the social-channel member-list request (`0x4ec`)
- brotherhoods (`0x4bd`–`0x4c5`, `0x6e7`–`0x6ef`)
