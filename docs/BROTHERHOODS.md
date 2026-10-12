# Brotherhoods

**Verified live (2026-10-12, two clients):**
- `/brotherhoodinvite Ranger` opens the client's "Brotherhood invite" popup ("Justins has invited you to join a brotherhood."). Accepting prints "Ranger has joined the brotherhood."
- `/brotherhoodleave` shows the client's "Leave the Brotherhood?" confirm. Accepting sends zone `0x4c0`; the server removes the member, and a brotherhood left with one member is dissolved.
- `/brotherhoodname Dust Riders`, `/brotherhoodmotd Meet at the camp` and `/brotherhoodnote bring arrows` are saved and sent to every member. The leader only can rename or set the MOTD.
- `/brotherhoodpromote Justins` makes Justins the leader; the client prints "Justins is now the leader of the brotherhood." itself.
- `/brotherhoodremove Justins` shows "Remove from Brotherhood?"; Accept sends `0x4c1 {i32 id}`, and the client prints "Justins has been kicked from the brotherhood." itself.

The code is in `server/brotherhood.py` and `login_stub.handle_brotherhood`. Brotherhoods are stored in `server/brotherhoods.json`, a local file that git ignores. The maximum is 6 members.

The client's dispatcher is `FUN_00470a20`. Requests are zone events.

| Direction | Id | Payload | Meaning |
|---|---|---|---|
| C→S | `0x4bd` | `wstr name` | `/brotherhoodinvite` |
| S→C | `0x4bd` | `wstr inviter` | invite popup |
| C→S | `0x4be` / `0x4bf` | none | accept / decline |
| C→S | `0x4c0` | none | leave (sent after the client's confirm popup) |
| C→S | `0x4c1` | `i32 member id` | remove (after "Remove from Brotherhood?") |
| C→S | `0x4c2` | `i32 member id` | promote to leader. The client looks the name up in its member list, so the id must match 0x6ea |
| C→S | `0x4c3` / `0x4c4` / `0x4c5` | `wstr` | MOTD / my note / rename |
| S→C | `0x6ef` | `i32` | status: 0 not active, 1 member, 2 leader |
| S→C | `0x6ed` | `wstr` | brotherhood name |
| S→C | `0x6ea` | `wstr name, i32 class, i32 level, i32 id, i32 ?, i32 exp contribution, i32 rank, wstr note` | member add/update, keyed by id (`FUN_00470420`). Rank: -1 leaving, 0 member, 1 leader. The fourth int (member +0x2c) is unknown; the server sends online 0/1 |
| S→C | `0x6e7` | `i32 id, bool8 kicked` | member left / kicked; the client prints "%s has left the brotherhood." / "%s has been kicked from the brotherhood." |
| S→C | `0x6eb` | `wstr motd, i32 set-by id` | MOTD (BrotherhoodMOTD gamevar; prints nothing, so the server adds a "Brotherhood MOTD:" line) |
| S→C | `0x6ec` | `wstr note, i32 id` | one member's note |
| S→C | `0x6e9` | `i32 id, i32 level` | one member's level |
| S→C | `0x6e8` | `i32 id` | new leader |
| S→C | `0x0e` | `i16` | 0x68 full, 0x69 not leader, 0x6e can't brotherhood with yourself |

Not done yet:
- the brotherhood XP bonus
- `/brotherhoodstats` sent nothing in the test (it may need the brotherhood window open)
- `0x6ee {i32 id, i32}` and the member record's fourth int
