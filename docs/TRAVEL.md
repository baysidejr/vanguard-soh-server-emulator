# Travel journal (Adventure Journal "Locations" tab)

> **Verified live (2026-10-13):** at login the server fills the Quests window's Locations tab. Categories come from the chunk's spawns: Merchants, Trainers, Services, Crafting Stations, Riftways and Quest Givers. Only the categories that have entries are sent. The tab lists Orin the Trader, Veyla Brightsteel, Hollis Grent, Tamsin Vale, Garret Holm, Brenna Ashford, the Mailbox, the Altar of Binding, the Camp Forge, the Finishing Table, the Assembly Bench and the Riftway. The player's built house (plot name, e.g. "Wastes Homestead") goes under the client's built-in "Player Housing". Clicking an entry's round button tracks it (green check). That is client-only; nothing is sent. Implemented in `server/travel.py` and `login_stub.journal_login`.

Tags: [O] = read in decompiled code. [I] = inferred.

| Dir | Id | Payload | Meaning |
|---|---|---|---|
| S->C | **0x2ae** | `wstr name, i32 categoryId, i32 0` | Adds a category under "All Locations" (FUN_005d86d0) [O]. The first one also creates the built-in categories -3 All Locations, -2 Corpses and -4 Player Housing [O]. |
| S->C | **0x382** MsgSingleTravelJournalEntryToClient | `i32 id, i32 0, f32 x, f32 y, f32 z, wstr name, i32 chunkX, i32 chunkY, i32 0, u8 type, wstr description, i32 categoryId, bool8 track, i32 0` | Adds a location (FUN_005d83a0). It is dropped unless the category exists [O]. Types [O]: **1** is the tombstone icon (DEATH.md); **0** also prints "The locations section of your Adventure Journal has changed."; any other type is a plain point of interest. The server uses type 2 at login so the chat stays quiet. |
| S->C | 0x383 | `i32 id` | Removes a location [O]. |
| S->C | 0x2aa | same as 0x382 | Updates the position, name and description of an existing entry, looked up by id (FUN_005d60d0) [O]. |

## Tracking a location (verified live 2026-10-13)

Tracking is done by the client alone. `/traveldirections <entry id>` (FUN_00609100 -> FUN_005d7190 -> FUN_005d5c90) looks the entry up, prints "Orin the Trader Chunk = .. Location = -31250.0, -5450.0, 450.0", sets the gamevars TravelJournalIsTracking / TJTrackEntryChange, and puts a red marker on the compass. Every frame FUN_005d2410 works out the distance and heading from the entry's chunk and x, y, z (chunks are 204800 units). An unknown id prints "Invalid journal entry.". `/traveldirectionsoff` stops it. Entry ids are `travel.ENTRY_ID_BASE` + the spawn's index in the chunk (Orin = 120586244 in chunk_n19_12).

Optional server route, read in the client but not sent [O]:
- **0x384** `{i32 count, count x {f32 x, f32 y, f32 z}}`: waypoints stored at mgr+0x5c; sets mgr+0x48 (route active) (FUN_005d7b50).
- **0x385** `{u8}`: 0 "Route to location found.", 2 "You are in the wrong chunk to track that entry.", 3 clears the route (FUN_005d5680).
- **0x381** `{i32 count, count x entry}`: several journal entries in one message (FUN_005d8c60).

Not done: discovering locations by visiting them (all of a chunk's service locations are known at login) and server routes.
