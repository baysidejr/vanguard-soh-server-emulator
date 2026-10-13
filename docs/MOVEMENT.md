# Player movement (in progress)

> **Status (2026-10-13):** WASD does not move the player's own character yet. Investigation below.

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
