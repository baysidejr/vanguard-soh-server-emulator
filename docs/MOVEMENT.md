# Player movement

> **Fixed (2026-10-13, verified live with two clients):** WASD moves the player. Holding W moved Ranger from x -30900 to -29891 in about 3 s, walking (Physics 1) up and down slopes, with the client sending ServerMove RPCs; a second client (Justins) sees him walk up. The fix has three parts, below under "The fix".

## How the client should move its own character (Unreal Engine 2)

The client moves its own pawn locally (client-side prediction) and reports positions to the server with the PlayerController RPCs `ServerMove` / `ShortServerMove`; the server only corrects it (`ClientAdjustPosition`). For that, the client's copy of the pawn must be `ROLE_AutonomousProxy` (3) and be possessed by the local PlayerController.

## What the server does today

- The pawn (SGOPCPawn) and the PlayerController are opened on actor channels with `bNetOwner = True`; `PlayerController.Pawn` points at the pawn's channel; then the RPC `ClientRestart()` (no parameters in this build) puts the controller in the `PlayerWalking` state (seen in client memory).
- With the default roles the client pawn is `ROLE_SimulatedProxy` (2). `APawn::TickSimulated` (FUN_00a03070) then drives it from replicated velocity only, so keyboard input has no effect. `bSimulateGravity = True` was added earlier only so it doesn't hover.
- The client still sends `ShortServerMove` now and then (its controller ticks), but the reported position never changes with WASD.

## Findings so far

1. **Enum byte properties were encoded wrongly.** UE2 `UByteProperty::NetSerializeItem` writes an enum byte with `SerializeBits(ceil(log2(enum count)))`. The server used `SerializeInt(value, count)`, which is the same bit pattern only for some values (e.g. counts that are powers of two). `Role`/`RemoteRole` (`ENetRole`, 5 values) arrived as 0 whenever the value was 3. Fixed in `netcache.py` (verified with client memory: wire Role 3 now arrives as 3).
2. **Role order.** Sending wire `Role = 3, RemoteRole = 4` for the owner's pawn gives the client pawn Role 3 (AutonomousProxy), RemoteRole 4 (offsets: RemoteRole +0x42, Role +0x43). Enabled for testing with the environment variable `PAWN_ROLE=3,4`.
3. With Role 3 the pawn still does not move: it stays in `Physics = 2` (falling) at its spawn height with zero velocity, and the client sends only one `ShortServerMove`.
4. On the client the PlayerController (Role 3) is in state `PlayerWalking` and references the pawn, but the pawn's `Controller` (+0x3c4) is null. `Controller` is not a replicated property of SGOPCPawn in this build, so the server cannot send it directly; sending it anyway broke login.

## Tools used

- `scratchpad/vgmem.py`, `pawnstate.py`: read the running client's memory (actor role, physics, location, state frame).
- `!gotostate <state>`: dev command that sends the RPC `ClientGotoState(NewState)` (`zone.client_goto_state`).

## The fix

1. Enum byte properties are sent as fixed-width bits (`netcache.py`), so `Role`/`RemoteRole` arrive intact.
2. The owner's pawn is opened with wire `Role = 3`, `RemoteRole = 4`: on the client it becomes `ROLE_AutonomousProxy`.
3. The PlayerController is opened **without** its `Pawn` property, and the server sends the RPC **`GivePawn(Pawn)`** (PlayerController function 77) instead of `ClientRestart()`. `GivePawn` sets `Pawn`, sets `NewPawn.Controller = self` and calls `ClientRestart()` (Engine.u). It returns early if `Pawn` already equals `NewPawn`, so replicating `Pawn` first left `Pawn.Controller` empty and the character frozen.

`PAWN_ROLE=off` in the environment restores the old simulated pawn for comparison.

## Notes for later (from the client analysis)

- The server should acknowledge moves with `ClientAckGoodMove(TimeStamp)` and correct positions with `VeryShortClientAdjustPosition(TimeStamp, X, Y, Z, Base)`; unacknowledged moves pile up in the client's SavedMoves (it flushes at 100, harmless).
- The client also sends `DualServerMove` and Vanguard's `OnVehicleServerMove`; all carry the position.
- Never replicate `m_bIsDead = 1` on a living player: pawn physics zeroes acceleration while it is set.
- Enum parameters in client RPCs need the same fixed-width decoding (`rpc.py` reads bytes as 8 bits).

## Checked after the fix (2026-10-13)

- Teleports (`!tp`, 0x3e5), death, release and respawn: the character still walks afterwards.
- Mounts: riding is 1.6x faster (see MOUNTS.md).
- Walking across a chunk border hands the player to the next zone (verified walking along the seabed from chunk_n20_12 into chunk_n21_12, Port Aughos).
- `!tp x y g [yaw]` puts the player on the terrain at x, y (the `~` form keeps the old height, which can drop the player under the map near chunk edges).

## Fall damage (2026-10-13, verified live)

The server watches the height in every movement report (`zone.log_client_rpc` calls `args.on_move` for each report, including ones where the position did not change, so the landing is seen). `login_stub.check_fall` remembers the highest point of a fall; on landing, a drop of more than `SAFE_FALL` (500 units) costs `(drop - 500) * FALL_DAMAGE` (0.3) health. One-step jumps (z more than 1200 up or down, or more than 2000 sideways, in one report) are treated as teleports. Falls only count once the player has stood on the ground since logging in or teleporting (`fall_drop`, unit-tested in `test_login_hooks.py`): the first version also hurt players dropping from their saved spawn height at login and killed Ranger. Landing inside a WaterVolume (`water.water_boxes`) is safe. Reaching 0 health kills the player through the normal death path. The damage itself was verified live (a 1425-unit drop did 277 damage); falls straight after a `!tp` into the air no longer count.

## Movement sanity checks (log only, 2026-10-13)

The client moves its own character, so the server checks the reports (`login_stub.movement_warning`, unit-tested): over each 2 s window the horizontal speed must stay under the riding speed × 1.3 (`speed_limit()`), and one report must not move more than 2000 units. The client echoes every server teleport (zone event 0x3e5) back once it has moved; jumps and speed for 5 s after that echo are excused. Problems are only printed (`MOVEMENT WARNING <name>: ...`) and counted on the player (`move_warnings`); nothing is corrected yet (the correction RPC, `VeryShortClientAdjustPosition`, risks rubber-banding). Verified live: walking, riding and `!tp` give no warnings.

## Swimming, breath and drowning (verified live 2026-10-13)

Swimming is client-side: inside a WaterVolume the client switches its own pawn to `Physics = 3` (PHYS_Swimming). Breath is stat **0x50** (`vgmsg.STAT_IDS["breath"]`), created at login with value = max = 60 (`zone.BREATH_MAX`, kind 5). The client shows the HUD's **Breath** bar (`StatusBreathSelf`) while a 0x2d4 update has current < max (FUN_005763b0 sets `bIsDrowning = current != max`) and hides it when full. The server (`login_stub.breath_tick`, once a second) loses 1 breath while the head (location + 60) is inside a WaterVolume and regains 10 above it; at 0 the player takes 10% of max health a second ("You are drowning!") and dies through the normal death path. Test: `!tp -43000 -52900 g 49152` (the seabed off the fishing beach).

## Unstuck (verified live 2026-10-13)

`/petition` (client event 0xeb) opens the client's Help window. Its **Unstuck** button sends **0x44c** (no payload): the server teleports the player to their bind spot (altar) if it is in the same chunk, else to where they entered the chunk ("You have been moved to safety."), at most once every 5 minutes (`login_stub.unstuck`). The Help window's **Petition** button does not reach the server: it opens the client's built-in web browser on a URL from the launcher configuration (vgoemulator.net in this install), so don't use it while testing.
