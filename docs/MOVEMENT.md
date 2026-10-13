# Player movement (in progress)

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
