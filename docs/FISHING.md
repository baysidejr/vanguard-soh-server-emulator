# Fishing

> **Partly verified live (2026-10-13):** with a Fishing Pole (item type 26, primary hand) and Wastes Grub bait (type 26, secondary hand) equipped, `/fishing` sends 0x59d; the server answers 0x59d, the client passes its gear checks (sends 0x111 {2} and 0x59a {2}) and casts ("You cast your line."). In the Sundering Wastelands camp there is no water, so the bobber never lands; after 15 s the server ends it ("Your line needs to land in water."). Simulating the landing (`!fishbite`) is not enough: the client ignores "Fish on!" (0x59a {4}) unless its own bobber is in a water volume (state 3).
>
> **Coded, not yet verified:** the bite after 4-10 s, the pull minigame (0x59c event 9 with a direction, the player's 0x59b answer, 3 "Good" / 4 "Oops", 4 good answers land the fish, 2 misses lose it), the catch (event 5, a Sand Carp or Mud Eel, the bait is used up, a Fishing skill-up on stat 0x5b). Needs a chunk with water to test.

Server: `server/fishing.py`, `login_stub.handle_fishing_event/fishing_tick/fishing_finish`. The camp merchant sells the pole (150 copper) and bait (2 copper).

The rest is the client analysis (static, by a research agent).


[O] = read in code, [I] = inferred. All zone sends go through `FUN_00409210` (zone, the same path as `FUN_004cfb00`/`FUN_004cfb50`). MsgSingleInt = `{i32}`.

## Client object
- Fishing manager is global `DAT_014639d8`, ctor `FUN_004cdad0` (0x20 bytes). Fields: +0 state, +4 time in state, +8 reel-anim timer, +0xc timer for the 0x599 send, +0x10/+0x11 flags, +0x14 combo counter, +0x18..+0x1b key-held latches, +0x1c "reeling bobber in" flag [O].
- Per-frame tick is `FUN_004cf880` (called from 0x4152bf). Key input goes to `FUN_004ceab0(key, msg)` (called from 0x418da1). The S->C dispatcher is `FUN_004cf940` (called from the zone dispatcher at 0x62286d) [O].
- Client states: **0** idle, **1** casting (wind-up), **2** bobber in flight, **3** bobber in water (waiting), **4** fish on (minigame), **5** reeling [O].

## Equipment, item type, location checks (all client-side, in `FUN_004cdf20`)
- **Fishing pole:** the item in slot **0x1c PRIMARYHAND** must have item type (field 74, item+0x524) == **26 (0x1a)**. If not, the client shows "You need a fishing pole equipped in your primary hand to fish." [O]
- **Bait:** the item in slot **0x1d SECONDARYHAND** must also be type **26**. If not: "You need bait equipped in your secondary hand to fish." [O] The type-name table `FUN_00d057a0` names type 26 "Fishing" [O]. Pole and bait use the same type, so the server should tell them apart by item id/template [I].
- **Not sailing:** `FUN_00830050` checks whether the pawn is on a ship. If so: "You can not fish while sailing." [O]
- Equip slot **0x58 (88) "Fishing Tackle Box"** exists (slot-name table `FUN_00d047b0`, case index 0x59 = slot+1) [O]. Nothing in the fishing code uses it; it is probably a container slot like the harvesting pack [I].
- **Water check:** handled by client physics. In state 2, `FUN_004ce180` waits until the bobber actor's PhysicsVolume (`actor+0x1c8`) has flag `+0x400 & 0x20` (bWaterVolume [I]). Only then does it switch to state 3, play the splash FX and send 0x599. There is no client range or "must stand near water" check before casting. The player can fish anywhere the bobber lands in a water volume [O]. If the bobber lands on ground, it sits in state 2 until /fishing is used again (`FUN_004cf6a0` stops fishing once the bobber is at rest, physics 0) [O].
- Account flag: string "TrialFeatureFishing = Fishing is only available to Gold Members." (0x5e66e9). The fishing code never checks it, so enforcing it is up to the server [O/I].
- Skill stat id **0x5b "Fishing"** (`server/stat_names.py`, tooltip `AdvFishingTooltip`) [O].

## Client -> server
| id | payload | when | addr |
|---|---|---|---|
| **0x59d** | none (`FUN_004cfb50`) | `/fishing` (table 0x13eea4c, stub 0x5fcfd0 -> `FUN_004cf9c0`) in state 0, 3, 4 or 5. State 1 does nothing; state 2 runs `FUN_004cf6a0` (shortens the throw: velocity x0.5, cap 800; or stops if the bobber is at rest) | [O] |
| **0x111** | MsgSingleInt `{2}` | sent while starting the cast, after the S->C 0x59d checks pass | 0x4ce041 [O] |
| **0x59a** | MsgSingleInt `{2}` | same moment as 0x111: "I am casting" | 0x4ce08e [O] |
| **0x59a** | MsgSingleInt `{0}` | client cancels: Esc key-up in state 3/4, /fishing on a bobber at rest, reeling the bobber to within 500 units of the pawn, and the per-tick abort (`[DAT_01463a58+0x330] != -1`, meaning unknown) (`FUN_004ce7f0(1)`) | [O] |
| **0x599** | MsgSGOVector `{f32 x,y,z}` (ctor `FUN_004cd8d0`) | bobber position: once when it lands in water (`FUN_004ce180`), then every 2.0 s in state 3 (`FUN_004cf780`) | [O] |
| **0x59b** | MsgSingleInt `{dir}` | state 4 only. One send per key press (the latch resets on key-up). MoveForward=**0**, TurnRight=**1**, MoveBackward=**2**, TurnLeft=**3** (`FUN_004cdb10`) | [O] |
| **0x5a4** | `{i32 type, i32 fishId, bool8 today}` (`FUN_00446210`), sent on the **world social channel** (`FUN_00409220`, type 5) | Fishing tab: picking a fish or changing the dropdown ("Biggest Catches For Today" -> 1, "All Time Biggest Catches" -> 0) (`FUN_004467c0`) | [O] |

Also in state 3, holding **MoveBackward** (`FUN_004ce900`) pulls the bobber toward the pawn at 600 u/s, and the reel animation plays. Bobber positions keep going out through 0x599 [O].

## Server -> client (dispatcher `FUN_004cf940`)
| id | payload | handler | effect |
|---|---|---|---|
| **0x59d** | none | `FUN_004cdf20` | **Begin cast.** Runs the pole/bait/sailing checks, sends 0x111{2} and 0x59a{2}, plays the `fishingCast` animation, state=1. After 1.0 s it plays the sound `Fishing.Cast`. After 1.4 s it plays the `fishingIdle` animation and spawns the bobber `FX_Meshes002.FX_meshes_FishingBobber001` (actor tag "FishingBobber") as a thrown projectile (`FUN_004ce370`), state=2 [O] |
| **0x59a** | MsgSingleInt `{state}` | `FUN_004cedc0` -> `FUN_004cde10` | Sets the client state. **0** = stop locally (no echo). **4** = "Fish on!" text, `GlobalFalls.Swim` sound, `fishingReel` animation + `Fishing.ReelIn` sound (`FUN_004cd6a0`, 1.2 s timer). **5** = reel animation. Other values only set the state (e.g. 3) [O] |
| **0x599** | MsgSGOVector `{x,y,z}` | `FUN_004cdd10` | Moves the bobber (FarMoveActor), e.g. when a fish drags it [O/I] |
| **0x59c** | MsgEntityIDAndTwoInts `{eid64, i32 event, i32 dir}` (ctor `FUN_004cd780`) | `FUN_004cee50` | Minigame events, table below. `eid` = the entity whose Head gets the event-0 FX (send the fisher's id) [O] |

0x59c events (jump table 0x4cf638) [O]. dir: 0 Up/Forward, 1 Right, 2 Down/Backward, 3 Left.
| ev | client effect |
|---|---|
| 0 | combo counter +1; sound `Spells.ImpactBSmoke3`; direction FX `FXmystical_FishingDirection{Up,Right,Down,Left}001fx` on eid's Head (size 2.0); text "Combo part %d/4" |
| 1 | "Combo failed" + `UISounds.Error`; counter = 0 |
| 2 | "Combo complete!" + `Spells.Rune`; counter = 0 |
| 3 | "Good" + `UISounds.DuelCount`; local pawn plays `fishingForward/Right/Backward/Left` (by dir) |
| 4 | "Oops" + `UISounds.Error` |
| 5 | popup "Fish caught!" + `UISounds.DuelWin`; stops fishing (no send) |
| 6 | popup "The fish got away!" + `UISounds.DuelLose`; stops |
| 7 | sound `GlobalFalls.Swim` (0.75); counter = 0 |
| 8 | sound `Fishing.ReelOut`; `FUN_00bae940` on eid |
| 9 | sound `Spells.ImpactBDivine`; small direction FX (size 0.5) on the local pawn's Head = **the fish's pull/telegraph direction** |
| 10 | "Fish completed a combo!" + `Spells.ImpactBDivine3` |
| 11 | "You scared the fish!"; stops |

### Fishing achievements ("Fishing" tab in the Quests window, `VGUIFishingAchievements.xml`; dispatcher `FUN_00449300`, manager `DAT_014639dc`)
- **0x5a1** (add) / **0x5a2** (update by fishId), message `FUN_004476f0`, schema `FUN_004459e0` [O]:
  `wstr fishName, wstr biggestCatchLocation, i32 type(must be 0), i32 fishId (-2 = clear list, -3 = refresh UI), i32 totalCaught, f32 totalWeight, f32 highestWeight, bool8 freshWater (0 = salt), wstr onlyBait, wstr favoriteBait ("unknown" or empty = any), u8 combo[4]` (0 Up, 1 Right, 2 Down, 3 Left; first byte 0xFF = "Unknown."). Display: `FUN_006703f0`/`006707c0`/`00670c60`. Text: "You've caught %d %s!", total weight, "The biggest %s ... weighed %0.2f ... in %s", "%s can be found in fresh/salt water", bait hints, "Combo: Up, Left, ..." [O]
- **0x5a3** best-catches rows (message `FUN_00448180`, schema `FUN_00445aa0`): `i32 ?, i32 rowId (-2 clear / -3 refresh), i32 (must be 0), wstr, wstr, i32, f32`. The UI columns are Rank, Name, highestweight, Location, so it is probably wstr name, wstr location, i32 rank, f32 weight [I]. This is the reply to 0x5a4.

## Animations / FX / sounds
- Pawn animations (anim name table at 0xbd2eda): `fishingCast, fishingIdle, fishingIdleBreak, fishingReel, fishingForward/Backward/Left/Right, fishingCatch, jogFishing`. Emote `FISHING_CAST` (social 400060) [O].
- Replicated pawn bool **`m_bFishingIdleActive`**: pawn+0xa9c bit 0x20 (rep list at 0xbf2f02). The server should set it while fishing so other players see the fishing idle [O for the property, I for its use].
- Unused here: `fishingCatch` (the server could play it on catch, e.g. via event 0x2e) [I].

## Recommended server flow
1. C 0x59d -> check that the pole (slot 0x1c, type 26) and bait (slot 0x1d, type 26) are equipped, plus any account flag -> reply S **0x59d** (empty). The client re-checks and sends 0x111{2} + 0x59a{2}. Set the pawn's `m_bFishingIdleActive`.
2. Wait for C **0x599** {x,y,z} (bobber in water). Optionally validate that the point is water and within cast range (about 1000 u). Pick a fish from a zone/water-type table (fresh/salt, bait preference). Keep accepting 0x599 updates; if the player reels in (position moves toward them) before the bite, you may send 0x59c ev 11 "scared".
3. After a random wait (e.g. 5-20 s), send **0x59a{4}** ("Fish on!"). Optionally send 0x59c ev 7/8 for splash and line-out sounds and 0x599 to drag the bobber.
4. Minigame loop: send **0x59c ev 9 {dir}** (pull direction). The player answers with **0x59b {dir}**. If it matches, send ev 3 "Good" (same dir); otherwise ev 4 "Oops". Track tension or progress. Combo variant: the fish has a 4-direction combo (achievement `combo[4]`). Each correct input in sequence gets ev 0 (dir, eid = player) "part n/4", a mistake gets ev 1, completing it gets ev 2 (bonus progress). Ev 10 = the fish does its combo (penalty) [I for the scoring rules; no client logic].
5. End: on success, send **0x59c ev 5**, give the fish item (inventory add), consume the bait (update or remove the slot 0x1d item), and roll the Fishing skill-up (stat 0x5b via the stats update, same as harvesting). Then send 0x5a2 (or 0x5a1 the first time) with updated totals for the achievements tab. On failure, send ev 6 (got away) or ev 11 (scared). Clear `m_bFishingIdleActive`. If the client sends 0x59a{0}, end the session silently. The server can also force a stop with S 0x59a{0}.
6. Handle 0x5a4 (world/social channel) by replying 0x5a3 rows: -2 clear, then rows, then -3.

## Server-only data gaps (for docs/CONTENT_EDITOR.md; that file was not edited)
Fish species table (name, fresh/salt, zones, weight range, preferred/required bait, 4-direction combo), fish and bait item templates, bite-timer and minigame tuning, skill-up curve, best-catch leaderboards.
