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

**World social (type 5) guild requests (verified live 2026-10-12):**

| Direction | Id | Payload | Meaning |
|---|---|---|---|
| C→S | `0x4e2` | raw wstr | `/guildmotdset text` (officers and up). The server broadcasts `0x4e1` to the guild |
| S→C | `0x4e1` | `wstr motd, wstr set by, i32 time` | "Guild Motd: %s". Also sent at zone login |
| C→S | `0x4e3` | none | the MOTD view request. `/guildmotd` with no text was not seen on the wire; the client shows its cached copy |
| C→S | `0x4d2` | `i32 name byte length, i32 rank, wstr name` | `/guildrenamerank 1 Pup` (leader only). The leading length int was seen live |
| S→C | `0x4de` | `i32 rank, wstr name` | "Guild rank %s has been renamed to %s." The client renames before formatting, so both names print as the new one; the server sends its own text plus a fresh `0x4ea` instead |
| C→S | `0x4df` | `wstr name` | `/guildstatus name` |
| S→C | `0x4df` | `wstr name, wstr guild name, i32 rank` | "%s is a %s in %s." The rank name comes from the viewer's own rank table; rank 0 prints "That player is not in a Guild." (`FUN_004eb5e0`) |
| C→S | `0x4ec` | none | member-list request; the server replies with `0x4eb`/`0x4ec`/`0x4ed` |

Custom rank names and the MOTD are stored per guild in `guilds.json` (`ranks`, `motd`, `motd_by`, `motd_time`).

Not done yet:
- recruiting (0x4ca-0x4ce: recruiting flag, notes, property tags, rank flags; recruiting list 0x4c6-0x4c9)
- recruiting and guild properties (`0x4ca`–`0x4ce`, `0x4d1`)

## Notes, points and recruiter flag (verified live 2026-10-13)

`/guildsetnote Out fishing` (world type-5 **0x4e3** {wstr}, the sender's personal note; 0x4e3 is not a MOTD request, `/guildmotd` sends nothing), `/guildsetpoints Ranger 42` (**0x4e5** {wstr name, f32}), `/guildsetofficernote Ranger Trusted scout` (**0x4e6** {wstr name, wstr}); **0x4e4** {wstr name, wstr} sets the guild note and **0x4d1** {i32 member id low bits} toggles the recruiter flag. The server stores them per member (`member_info` in guilds.json; officers and up for the others' notes) and resends that member's record (0x4ee) to the guild. The Member Info tab then shows Personal "Out fishing", Points 42.0, Officer "Trusted scout". The record's last-online field is the character's `last_logout`.
