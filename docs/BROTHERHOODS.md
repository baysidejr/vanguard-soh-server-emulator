# Brotherhoods

**Verified live (2026-10-12, two clients):**
- `/brotherhoodinvite Ranger` opens the client's "Brotherhood invite" popup ("Justins has invited you to join a brotherhood."). Accepting prints "Ranger has joined the brotherhood."
- `/brotherhoodleave` shows the client's "Leave the Brotherhood?" confirm. Accepting sends zone `0x4c0`; the server removes the member, and a brotherhood left with one member is dissolved.

The code is in `server/brotherhood.py` and `login_stub.handle_brotherhood`. Brotherhoods are stored in `server/brotherhoods.json`, a local file that git ignores. The maximum is 6 members.

The client's dispatcher is `FUN_00470a20`. Requests are zone events.

| Direction | Id | Payload | Meaning |
|---|---|---|---|
| C→S | `0x4bd` | `wstr name` | `/brotherhoodinvite` |
| S→C | `0x4bd` | `wstr inviter` | invite popup |
| C→S | `0x4be` / `0x4bf` | none | accept / decline |
| C→S | `0x4c0` | none | leave (sent after the client's confirm popup) |
| S→C | `0x6ef` | `i32` | status: 0 not active, 1 member, 2 leader |
| S→C | `0x6ed` | `wstr` | brotherhood name |
| S→C | `0x6ea` | `wstr name, 6 × i32, wstr` | member added. **The six ints are guessed** (id, level, class, online, leader, 0) |
| S→C | `0x6e7` | `i32 id, bool8 kicked` | member left / kicked. The client printed nothing, probably because it keys members by the guessed id, so the server prints "X has left the brotherhood." itself |
| S→C | `0x6e8` | `i32 id` | new leader |
| S→C | `0x0e` | `i16` | 0x68 full, 0x69 not leader, 0x6e can't brotherhood with yourself |

Not done yet:
- the brotherhood XP bonus
- remove (kick), promote, MOTD and notes (`0x4c1`–`0x4c5`)
- decoding the member record's ints
