# Riftways

> **Verified live (2026-10-13):** two Riftseeker braziers (race 767) stand in chunk_n19_12, one at the camp and one by the canyon. Standing at the canyon one, `/rift ThreeRivers` prints "The riftway to Three Rivers is not open on this server yet." and `/rift SunderingWastelands` prints "You lose 50 copper." and "The riftway carries you to Sundering Wastelands.", moving the player to the camp. The Map window's Riftway button opens the client's "Vanguard Riftway System" map (Thestra, Kojan and Qalia tabs); its destination buttons run the same `/rift <Name>`.

Server: `login_stub.handle_rift`. Content: `server/content/riftways.json` (all 39 destinations from the client's map, keyed by the uppercased name the client sends; only SUNDERINGWASTELANDS has a position), riftway stones are mob templates with `"riftway"`.

- 0x597 {wstr NAME}: the server looks the name up, requires a riftway stone within 800 units, charges the color price (green 50, blue 500, yellow 2000, red 5000 copper; purple hubs free) and teleports with 0x3e5. Destinations in other chunks are refused for now.

The rest is the client analysis (static, by a research agent).


[O] = observed in code/data, [I] = inferred.

## TL;DR
- The riftway map is a **purely client-side window**. The server does not open it, sends it no data, and keeps no "discovered" list in the client. The player opens it from the **Map window's "Riftway" button**.
- Clicking a destination runs the **client slash command `/rift <Name>`**. The client sends **zone event `0x597` with one `wstr` = the name in UPPERCASE** (for example `THREERIVERS`).
- The four colors are **cost tiers** (green/blue/yellow/red), plus purple for hubs. The prices are hardcoded in the client and shown only in the map legend. Gold Members get 20% off.
- The client has **no riftway-specific server→client message** (no discovered, result or error message). The server does all validation, charging and teleporting, and reports results as normal chat/system text.

## 1. Opening the window [O]
- `VGUIAssets/Shells/Default/Windows/VGUIMap.xml`: the button `_riftway_map_button` ("Riftway", tooltip `MapRiftwayButton` = "Riftway System Map — Click to open or close the Riftway System Map." in `bin/VGClient.int:913`) fires the UI event `_riftway_map_button_press`.
- `0x6a6673` registers the UI event name `_riftway_map_button_press` as **UI id 0x20a**. The UI-event switch `FUN_006a8060` (jump table `0x6aa19c`, index 0x209 → `0x6a9c98`) calls **`FUN_0068bca0`**. That function finds the window with searchKey `_riftway_map` (string ref `0x68bcae`) and toggles it: show and bring to front if hidden, otherwise hide.
- This is the only code reference to `_riftway_map`. No zone message, NPC dialogue option or EntityTypes bit opens it:
  - The built-in NPC options in `FUN_004c7a00` are teach, recipes, banking, work, wares, assembly, summon remains, escrow, market and repair. None of them is riftway.
  - The EntityTypes interact code has no riftway path.
- Window: `RiftMaps.xml`, `VGUIWindow "Vanguard Riftway System"`, searchKey `_riftway_map`, with three tabs: Thestra (`t-rift`), Kojan (`k-rift`), Qalia (`q-rift`). All buttons are static XML. Nothing is greyed out or hidden by game state.
- Data the window needs: only the four gamevars `strGreen/Blue/Yellow/RedRiftwayCost` for the legend. The client sets them itself (see §2).

## 2. Picking a destination [O]
- Each destination button has `<Command>/rift Name</Command>` and an `Action hide_window _riftway_map` that closes the window. The player can also type `/rift X` by hand from anywhere, so **the server must validate everything**.
- `/rift` is in the client command table (`0x13eea64` → handler **`FUN_006123c0`**):
  1. It pops the first token with `FUN_00ce3d70` (space-delimited, quote-aware: `/rift "Dead bog"` gives one token [O for the `"` handling, I that the quotes are stripped]).
  2. It uppercases a–z (`FUN_00cdacc0`).
  3. It calls `FUN_005ebe50(name)`.
  4. `FUN_005ebe50` builds `MsgSendSingleSGOString` (ctor `FUN_004277e0`, vtable `0x1062d70`, one field `wstr` at +0x14) and calls **`FUN_004cfb00(0x597, msg)`**.
  - It does nothing if no argument is given. The client does no proximity, coin or level check.
- **C→S `0x597`: `wstr destination`** (UTF-16LE, NUL-terminated, uppercase). `0x597` has no server→client handler in the zone dispatcher tables.
- **Colors = price tiers** (`FUN_005ee1a0`, called from the membership handler `FUN_005ef460`). Values are copper; `[DAT_01463a58+0x378]==2` (Gold Member) selects the second value:

  | Color | Normal | Gold Member | Notes |
  |---|---|---|---|
  | Green | 50 c | 40 c | levels ~10–22 |
  | Blue | 500 c (5 s) | 400 c | ~20–30 |
  | Yellow | 2000 c (20 s) | 1600 c | ~30–46 |
  | Red | 5000 c (50 s) | 4000 c | 40+ |
  | Purple | — (no legend entry) | — | hubs; cost unknown [I: free or hub-specific] |

  The `+0x378` membership value comes from S→C **`0x725`** (`eid64, i32 membership, bool8`), handled at `0x617cd7` and in the world dispatcher at `0x62b127`. 2 = Gold ("Congratulations! You are now a Gold Member"). Mail postage uses the same flag.
- [I] The color most likely shows the **destination's** tier, so the price is set by where the player goes. This follows from the legend design; the client never computes a charge.

## 3. Server→client messages
- [O] The client has no riftway discovered, result or error message, and no riftway text strings other than the gamevars and window names.
- Use existing tools:
  - chat/system text for errors such as "You must be at a riftway", "You cannot afford", or "You have not discovered that riftway";
  - the coin update the server already uses for money;
  - `0x3e5` MsgForceLocationSet or chunk travel (`docs/CHUNK_TRAVEL.md`) for the move.
- Optional visual [O asset / I use]: `SOR_ABILITIES.aby` contains `RIFTWAY_SUMMON_CAST_I/II/III` = ability ids **660165 / 660167 / 660170** and `RIFTWAY_SUMMON_RESOLVE_I/II/III` = **660166 / 660168 / 660169**, with `FX_GROUND_RIFTWAY*` and `FX_HAND*_RIFTWAY*`. They can be played with `0x3d1` MsgDisplayAbility (caster = player) as a travel cast and arrive effect.
- Discovery: the client has no state for it. If the server wants discovery, it must track it itself and reject undiscovered targets with chat text. The map still shows every button.

## 4. Recommended server flow
1. Spawn a riftway stone per location as an ordinary pawn/prop at the coordinates of your choice. These must come from VGOEmu or wiki data; they are not in the client.
   - [I] Add EntityTypes `0x8000` (interactable → `0x184 {u64 id}`) if you want clicking the stone to do something, for example a chat hint "Open your map (M) and press Riftway". The client cannot open the window from the server (`0x598` runs client console commands, but nothing maps to the riftway window).
   - Optionally mark the stone as discovered when the player comes near or uses it.
2. On C→S `0x597 wstr NAME`:
   1. Look up NAME in a table (case-insensitive).
   2. Require the player to be within N meters of any riftway stone (the same continent's network).
   3. Optionally require that NAME is discovered.
   4. Look up the price by destination color, with 20% off for Gold.
   5. Check and deduct the coin.
   6. Optionally play 660165, then after about 3 s 660166.
   7. Teleport: `0x3e5` within the chunk, or chunk travel for another chunk.
   8. Send a chat line ("You travel through the riftway to X.").
   - On failure, send a chat error and nothing else.
3. The client never needs prices from the server. They are derived locally after `0x725`.

## Destination table (from RiftMaps.xml) [O]
The token is the uppercased value the server receives. The tab is the continent.

| Tab | Display name | `/rift` arg (server receives) | Color |
|---|---|---|---|
| Thestra | New Targonor [Hub] | NewTargonor (NEWTARGONOR) | Purple |
| Thestra | Three Rivers [10-20] | ThreeRivers | Green |
| Thestra | Renton Keep [15-22] | RentonKeep | Green |
| Thestra | Silverlake [20-25] | Silverlake | Blue |
| Thestra | Veskal's Exchange [22-27] | VeskalsExchange | Blue |
| Thestra | Misthaven Crossing [22-27] | MisthavenCrossing | Blue |
| Thestra | Shrine of the Flame [22-25] | ShrineOfTheFlame | Blue |
| Thestra | Trengal Keep [23-25] | TrengalKeep | Blue |
| Thestra | Kaon's Rush [26-30] | KaonsRush | Blue |
| Thestra | Wardship of the Sleeping Moon [30-40] | WardshipOfTheSleepingMoon | Yellow |
| Thestra | Northern Highlands [30-35] | NorthernHighlands | Yellow |
| Thestra | Beranid Hills [38-46] | BeranidHills | Yellow |
| Thestra | Kamelott Landing [40+] | **ShoresofDarkness** (name differs from the label) | Red |
| Thestra | Plains of Anguish [40-43] | PlainsOfAnguish | Red |
| Thestra | Lost Canyon [40-44] | LostCanyon | Red |
| Thestra | Deadbog [45-50] | `"Dead bog"` → **DEAD BOG** (contains a space) | Red |
| Qalia | Khal [Hub] | Khal | Purple |
| Qalia | Ahgram [Hub] | Ahgram | Purple |
| Qalia | Qa Riverbank [10-15] | QaRiverbank | Green |
| Qalia | Lomshir [10-15] | Lomshir | Green |
| Qalia | Ksaravi Gulch [16-20] | KsaraviGulch | Green |
| Qalia | Tauthien Delta [16-20] | TauthienDelta | Green |
| Qalia | Skrilien Point [18-26] | SkrilienPoint | Green |
| Qalia | Temple of Dailuk [20-26] | TempleOfDailuk | Blue |
| Qalia | Hathor Zhi [25-30] | HathorZhi | Blue |
| Qalia | Coterie Infinium Sanctuary [20-35] | CoterieInfiniumSanctuary | Blue |
| Qalia | Zossyr Hakrel [30-40] | ZossyrHakrel | Yellow |
| Qalia | Tar Janashir [34-40] | TarJanashir | Yellow |
| Qalia | Cragwind Ridge [30-35] | CragwindRidge | Yellow |
| Qalia | Seawatch Coast [35-45] | SeawatchCoast | Yellow |
| Qalia | Razad [41-45] | Razad | Red |
| Qalia | Afrit [45-50] | Afrit | Red |
| Qalia | Tehatamani [45-50] | Tehatamani | Red |
| Kojan | Tanvu [Hub] | Tanvu | Purple |
| Kojan | Wildgrowth Forest [10-16] | WildgrowthForest | Green |
| Kojan | Jalen's Crossing [10-12] | JalensCrossing | Green |
| Kojan | Sundering Wastelands [13-18] | SunderingWastelands | Green |
| Kojan | Tomb of Lord Tsang [12-14] | TombOfLordTsang | Green |
| Kojan | Blighted Lands [15-22] | BlightedLands | Green |

The client has no world coordinates or chunk ids for any of these. Those are server-only data and should be logged in `docs/CONTENT_EDITOR.md`.
