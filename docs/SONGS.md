# Bard songs

> **Verified live (2026-10-13), with `!songs` on Ranger:**
> - The Song window opens (`SGOUI toggle "Song"`). Compose shows all seven part rows. The part lists (Melodies, Verses, …) list the song parts from `content/songs.json`.
> - Dragging a part onto its slot fills it, and the cost line updates ("Song Cost: 3 - 0 = 3 Energy / sec").
> - Save sends 0x578. The server replies 0x573, and "War Song" appears in the song list. Saved songs are stored per character (`songs`) and come back after a restart.
> - Play sends 0x576 {1}. The server answers with "Currently Playing: War Song" (0x57b), a buff that combines the parts' bonuses, an Effects Maintained entry and "You begin to sing War Song."
> - Stop (0x575) removes all of it.
> - Implemented in `server/songs.py` and `login_stub.handle_song_event`.
>
> The client's drag-and-drop needs a slow drag (scratchpad `dragslow.ps1`); the quick `drag.ps1` only highlights the slot.

Tags: [O] read in decompiled code (client song dispatcher FUN_005c5310, drop handler FUN_005c3f30). [I] inferred.

## Parts
Song parts are abilities (0x215 MsgAbilityInfo) [O]:
- wire **#31 = 10** (song kind)
- **#32 = part**: 0 Melody, 1 Verse, 2 Embellishment, 3 Bridge, 4 Lyric, 5 Chorus, 6 Coda, 7 Rest
- **#56 = energy per second** (shown in the cost line)

The client sorts them into the SongMelody/Verse/…/RestList game-vars. The drop handler accepts a part only into its own slot type. A Rest (7) goes into any slot except the Melody slot, and lowers the cost [O].

Songs reference parts by **ability id** (#20); -1 marks an empty slot. Every song message carries:
1. the melody,
2. then, for i = 0..5, one id each for Verse, Embellishment, Bridge, Lyric, Chorus and Coda [O].

## Messages
| Dir | Id | Payload | Meaning |
|---|---|---|---|
| S->C | 0x572 | 6 x u8 (Verse..Coda) | Unlocked slots per part; a row shows only when its count is above 0. The Melody slot is always 1 [O]. |
| S->C | 0x573 | i32 song id, wstr name, wstr description, i32 melody, 6 x 6 x i32 | Add or update a saved song, matched by name [O]. The server uses list position + 1 as the id. |
| S->C | 0x574 | none | Delete every song; slot counts drop to 0 [O]. Resend 0x572 afterwards. |
| S->C | 0x57b | wstr | Song now playing ("" = none) [O]. |
| C->S | 0x578 | same as 0x573 | Save. **The song id field is junk**; key songs by name [O]. |
| C->S | 0x577 | same as 0x573 | Play the composition without saving it [O]. |
| C->S | 0x576 | i32 song id | Play a saved song. Sent by the list's Play button, by `/playsong "name"`, and by a song dragged to the hotbar (which becomes a `/playsong` macro) [O]. |
| C->S | 0x575 | none | Stop: the Stop button or `/stopsong` [O]. |
| C->S | 0x579 | i32 song id | Delete. The server deletes the song and resends the list so ids stay positional. |
| C->S | 0x57a | i32 id a, i32 id b | Move up/down: swap two songs [O/I]. |

The server enforces the limits (the client has none): a name, a melody, name up to 32 characters, description up to 128, at most 20 songs.

**Energy (verified live):** a playing song costs its energy per second, once a second (`energy_tick`, 0x2d4 energy stat). The blue bar falls, and the song stops with "You do not have enough energy to keep singing." when it runs out. Without a song, energy regenerates 3 a second.

## Not done
- Group-wide song effects. The song's buff currently goes to the singer only.
- Interruption by fear or flying.
- Real song data (CONTENT_EDITOR.md).
