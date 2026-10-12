# Why replicated (non-owned) SGO pawns are never animated or drawn

> **Resolved (2026-10-12).** Remote pawns (SGOPCPawn and SGONPCPawn) render, with name plates and minimap entries. Their instances look the same as the local player's: `+0x74` and `+0x80` stay 0 on the player too, so those are not "rendered" markers. What changed is that the pawns now replicate `bSimulateGravity = True` like the player's pawn, and the camera was zoomed out (the default camera sat against a wall). The analysis below is kept as background on the EMotionFX mesh path.

All findings come from static analysis of VGClient.exe in Ghidra through REA. I also scanned the PE bytes read-only for vtable-call patterns. Nothing was launched and nothing was modified.

- **[O]** means observed in the decompiled or disassembled code.
- **[I]** means inferred.

## TL;DR

- **[O]** Characters do not use UE2 `USkeletalMeshInstance`. They use `UEMFXMesh` / `UEMFXMeshInstance`, which is the EMotionFX middleware. The RTTI string `.?AVUEMFXMeshInstance@@` and many `UEMFXMeshInstance::*` guard strings confirm this.
  - The instance at `actor+0x134` (vtable `0x112b874`) is a `UEMFXMeshInstance`.
  - Its vfunc `+0x114` (`0x9410f0`) is `MOV EAX,ECX; RET`, so it is the "as EMFX instance" cast.
- **[O]** Everything (animation channels, controllers, skinning, bounds, render) depends on one pointer: **`instance+0x5c`, the EMotionFX ActorInstance**.
- **[O]** That pointer is created only by `FUN_00944800`, which is `UEMFXMeshInstance::InstantiateInstance` (the string at `0x112bca0` is referenced inside it).
- **[O]** In the game client, `GIsEditor` (`DAT_018bde28`) is 0. In that case the render path (`FUN_0094bf20`), PlayAnim (`FUN_009470f0`), the update path (`FUN_00946330`) and the per-tick animation update (`FUN_00bb4080`) all **return immediately when `+0x5c == 0`**. They never create it themselves.
  - Your NPC fingerprint (+0x74=0, +0x80=0, +0x200=0.0, +0x220/224=0, +0x238=0, default bounds) is exactly "Render bailed out because +0x5c==0". See the field table below.
- **[O]** For a non-local pawn, the ActorInstance is created lazily in the SGO pawn's tick hook `FUN_00bcb380`. That is SGO pawn vtable slot `+0x120` (TickSpecial-like), called every tick from `APawn::Tick` (`FUN_00a04f80`).
  - **Local pawn:** `FUN_00944800` is called unconditionally.
  - **Any other pawn:** `FUN_00944800` is called only if the distance cull test `FUN_00bb77a0` passes:
    - `dist(localPlayer.Pawn.Location, npc.Location) <= npc.CullDistance` (pawn `+0x314`).
    - `+0x314` is set by `FUN_00bc8cb0` to `6000 * max(1, max(CollisionHeight, CollisionRadius)/90)`. It is doubled for race 0x83/0x84, and +60000 is added when Physics==4.
  - If the test fails it sets `instance+0x2c4 = 1` (culled) and returns without creating anything.
- So the "local vs remote" difference is **not** Role, RemoteRole, Controller or bNetOwner. It is `pawn == LocalPC.Pawn ? always instantiate : instantiate only if within CullDistance of the local pawn`. A second remote path exists through the customization code; see Q2.

## Q1 – What creates the animation state, and who writes the fields you observed

### Object layout (UEMFXMeshInstance)

| offset | meaning | evidence |
|---|---|---|
| +0x5c | EMFX ActorInstance (the thing that is missing) | **[O]** `FUN_00944800` @0x944892: `FUN_00e4cc10(mesh->+0x60, 0x110)` → `[EBX+0x5c]` |
| +0x60 | UEMFXMesh | **[O]** 944800 checks it, then calls `FUN_00942ff0` (mesh load) with ECX=[+0x60] |
| mesh+0x60 | loaded EMFX Actor template | **[O]** `FUN_00942ff0` loads it via `FUN_00e3ffd0(mesh+0x80, mesh+0x84, ...)`; 944800 aborts if still 0 |
| +0x64 | owner Actor | **[O]** 944800 aborts if 0 or if owner `+0x48 & 0x400000` (deleted/pending-kill-type flag) |
| +0x94 | "attached to / parent instance" | **[O]** bcb380 and bb4080 only act when it is 0 (top-level pawn) |
| +0xf0/+0xf4 | motion slot array (stride 0x50, 9 slots) used by PlayAnim | **[O]** `FUN_009470f0`, `FUN_00946330` |
| +0x204 | owning pawn | **[O]** used throughout PlayAnim |
| +0x220/+0x224/+0x228 | TArray (Data/Num/Max) of EMFX node controllers (look-at style) | **[O]** `FUN_00945050`: `FUN_00e4fb70(instance+0x5c, node, 0)` then appends to [+0x220], Num++ at +0x224, grows Max +0x228. Caller chain 945050 ← 945320 ← 9454a0. Needs +0x5c. |
| +0x74 | render frame stamp | **[O]** `FUN_0094bf20` (Render): `if (+0x74 != view->frame(+0x98)) { +0x80=0; changed=1; +0x74 = frame }` |
| +0x80 (byte) | "rendered this frame" | **[O]** Render sets it to 1 |
| +0x200 | **distance from owner Location to the view origin, not a time** | **[O]** Render: `+0x200 = FUN_005defb0(owner+0x1cc, view+0x194)` (also in `FUN_0094d470`) |
| +0x238 dword (= byte +0x23a) | "skin dirty this frame" | **[O]** Render, on frame change: `+0x80=1; +0x1dc=1; +0x23a=1`. 0x00010000 at +0x238 means byte +0x23a = 1. |
| +0x2c4 | distance-culled flag | **[O]** `FUN_00bb77a0` sets 1 before the test and 0 on pass. `FUN_00bb4080` requires 0. |
| +0x78 | not traced | **[I]** cache key / LOD id, written in render/skin code. Not needed for the diagnosis. |

### Functions in the chain

- **InstantiateInstance – `FUN_00944800`** [O]. Preconditions: `+0x60 != 0`, `+0x64 != 0`, `owner+0x48 & 0x400000 == 0`, and mesh+0x60 loaded after `FUN_00942ff0`. It then:
  - creates the ActorInstance at `+0x5c`;
  - resets the motion and buffer arrays;
  - calls `ActorInstance->vfunc+0x24(0,1,1,0)` (initial update);
  - calls `pawn->vfunc+0x2c0` (`FUN_00bcb180`, which applies the 64 customization slots through `FUN_00bcaab0`);
  - looks up eyelid nodes.
- **PlayAnim – `FUN_009470f0`** (`UEMFXMeshInstance::PlayAnim`). Bail-outs are listed under Q3.
- **Per-frame animation advance – `FUN_00bb4080`** (SGO pawn vtable `+0x278`). It is reached through `APawn::Tick` → `vfunc+0x138` (`FUN_00a04cd0`) when `pawn+0x3c0 & 0x200` and `!(pawn+0x50 & 0x20000000)`. It does the following:
  - requires `FUN_00bcf730()+0x38 != 0`, `DAT_018b9404+0x230 && +0x228`, Mesh, instance, **`+0x5c != 0`**, `+0x2c4 == 0` and `+0x94 == 0`;
  - writes `+0x138` (delta time), `pawn+0x118` (time of last animation update) and `instance+0x1d4`;
  - updates attachments at `+0x22c/+0x230` through `FUN_0094a450`;
  - calls `FUN_00946330` (`UpdateMotions`);
  - steps EMFX through `ActorInstance+0x260 → vfunc+0x14`.
- **Render – `FUN_0094bf20`** [O]:

  ```c
  if (*(instance+0x5c)==0 && (GIsEditor==0 || (FUN_00944800(), *(instance+0x5c)==0))) return;
  ```

  So in the game, Render never instantiates. It is also where `+0x74`, `+0x80`, `+0x200`, `+0x23a` and `+0x239` are written, and where `FUN_0094b4a0` / `FUN_009419d0` (skin and draw) run. Attachments are rendered from here (`FUN_00946150`, `FUN_009459d0`), which explains why your attachments never get LastRenderTime.
- **UE2 analogues** [I]:
  - `InstantiateInstance` ≈ `LinkSkelAnim` / `MeshGetInstance` setup;
  - `PlayAnim` (`FUN_009470f0`) ≈ `PlayAnim`;
  - `FUN_00946330` ≈ `UpdateAnimation`.

## Q2 – Why the local pawn gets it and a SimulatedProxy pawn does not

### The tick path is the same for both

**[O]** `APawn::Tick` = `FUN_00a04f80`. It is the SGO pawn vtable caller of slot `+0x120`, found by scanning for `mov reg,[reg+0x120]; call reg`.

- The stasis early-out does not apply to pawns, because of the `bIsPawn`-style bit `0x40` at `+0x48`.
- It always calls `vfunc+0x120` = **`FUN_00bcb380`** for every non-deleted pawn, whatever its Role.
- It then calls `vfunc+0x138` → `FUN_00bb4080`.

### `FUN_00bcb380`, after its unrelated parts

```
if (FUN_00bcf730()+0x38 == 0) return;                // DAT_01924c8c+0x38 (world/session ready)
inst = pawn+0x134 ->AsEMFX();  if !inst return;
pc   = DAT_01924c8c->vfunc+0x88();  if !pc return;    // local PlayerController
localPawn = pc+0x390; if !localPawn return;
if (inst+0x94 != 0) return;
if (localPawn == this) { ...; if (inst+0x5c==0) FUN_00944800(); ... }       // LOCAL: unconditional
else {
   if (DAT_01438a60 != 0 && FUN_00bb77a0(this, localPawn, this)) return;    // DAT_01438a60 is statically 1
   if (inst+0x5c != 0) return;
   FUN_00944800();                                   // REMOTE: only if not culled
   if (pawn+0x3e8) { play death pose via PlayAnim ... }
}
```

### The cull test `FUN_00bb77a0(localPawn, npc)`, ECX = npc

```
if (!npc.Mesh(+0x114) || !Mesh->vfunc+0x9c()) return 1;     // UEMFXMesh: 0x942700 returns self [I: MOV EAX,ECX like 0x9410f0]
inst->+0x2c4 = 1;
if (dist(localPawn+0x1cc, npc+0x1cc) <= npc->vfunc+0x9c()) { inst->+0x2c4 = 0; return 0; }   // vfunc+0x9c = FUN_00bafc10
return 1;
```

- `FUN_00bafc10` returns `*(float*)(pawn+0x314)`, plus 60000 if Physics (+0x39) == 4.
- `+0x314` is `Actor.CullDistance` [O]. The engine function `FUN_0080ff20` (ACompoundObject::UpdateCullDistances) writes 5000/40000 to the same slot.
- For SGO pawns it is written at the end of **`FUN_00bc8cb0`** [O]:

  ```
  +0x314 = 6000 * max(1, max(+0x330, +0x32c) * (1/90))    // x2 for race 0x83/0x84
  ```

  `+0x330` and `+0x32c` are the collision height and radius.
- `FUN_00bc8cb0` is called by the model builder: `FUN_00bcb8e0` → `FUN_00bc95a0` → `FUN_00bc8cb0(1.0,1)`. So CullDistance should be ≥ 6000 after the model is built. One exception: `bcb8e0` exits before `bc95a0` if `FUN_00bc2e90` / `FUN_00bc35b0` (load model + animations) return false while `DAT_018bde40 != 0`. In that case CullDistance stays at the class default, probably 0, and the remote pawn is culled forever.

### Second remote path, without a distance test (PostNetReceive)

**[O]** In `FUN_00bcc5a0` (PostNetReceive):

- **Trigger:** the race (`m_iRaceId`, `+0x43c`) is a playable race (2..0x16, `FUN_00d07d00`) or in 0xBA..0xCE, 0x15C..0x170, or 0xE4, **and** `m_Customization` (`+0xaa8`, 64 bytes) differs from the pre-receive snapshot `DAT_019246c0`.
- **If `GIsEditor == 0` and `FUN_00bcf730()+0x38 == 0`:** it only sets the dirty bit `+0x4c |= 0x1000`.
- **Otherwise:** it calls `FUN_00bcaab0(slot, value)` for the 64 slots. For slot ≥ 0xC that are within `DAT_0192479c`, and when `inst+0x60 != 0`, this calls `FUN_00944800` directly.

### Flags that do not gate this

**[O]** `DAT_018bde40` and `DAT_018bde28` (GIsEditor) are not Role or ownership gates for this.

- `DAT_018bde28` is GIsEditor [O]: in `FUN_00753e40`, the D3D SetRes code uses the editor's HWND/GetDC path only when it is non-zero.
- No check on Role, RemoteRole, bNetOwner or Controller was found on this path.

## Q3 – Does PlayAnim (`FUN_009470f0`) bail for the NPC?

Yes, at the very first statement [O]:

```c
if (*(ECX+0x5c) == 0) { if (DAT_018bde28 /*GIsEditor*/ == 0) return 0; FUN_00944800(); }
```

The other early-outs, after that point:

- `DAT_018b9404+0x230 == 0`;
- pawn `+0x3e8 && (+0x774 & 4)` (dead and already posed);
- `pawn->vfunc+0x324() & 0x400` with `param_14 == 0`;
- animation-name resolution failure (`FUN_00938120` / `FUN_00927c60` return 0);
- slot conflicts.

The same `+0x5c` gate applies to:

- `FUN_00bbb490` (your zone event 0x2e path), which also checks `inst+0x5c != 0` before calling PlayAnim;
- `FUN_00bbc450` / `FUN_008368d0` (idle);
- `FUN_00946330`.

That explains why AnimAction, fishing idle and event 0x2e had no effect. **PlayAnim succeeds as soon as `+0x5c` exists.** There is no separate "link anim set" step: animations are resolved by name against the EMFX motion library (`FUN_00942900` = `UEMFXMesh::LoadAnimations`, `FUN_00927c60`).

## Q4 – What the server should do

No zone event is required for instantiation. I found no network or zone handler on the creation path. Creation happens entirely client-side in the pawn tick.

1. **Put the remote pawn close to the local player's pawn.** In UE units, `dist(localPawn.Location, npc.Location)` must be ≤ the NPC's CullDistance (≈6000 uu for normal-size races) [O]. Check that the NPC's replicated Location uses the same frame and scale as the local pawn's Location (`+0x1cc`). If they differ (chunk offsets, cm vs uu), the pawn will never be instantiated.
   - **[I] Workaround / test only:** Physics=4 adds 60000 to the radius.
2. **Make sure the model build fully succeeds,** so that CullDistance gets set and the Mesh/EMFX data load. To do that, send a valid `m_iRaceId` (and the gender or `+0x110` value it uses) for which `FUN_00bc2e90` / `FUN_00bc35b0` return true. Otherwise `bc95a0` / `bc8cb0` are skipped and CullDistance stays at the class default.
3. **Alternative trigger without the distance test** (playable races 2..22 and the other listed ranges): replicate `m_Customization` with at least one byte that differs from the previous value. Do it after the client session object is "ready" (`DAT_01924c8c+0x38 != 0`). PostNetReceive then calls `FUN_00bcaab0` → `FUN_00944800`.
4. **The local client also needs a PlayerController whose Pawn (`+0x390`) is non-null** [O]. This is always true once you are in the world, because your own pawn renders.

## Live checks that settle it (read-only memory)

Read these on the NPC pawn P and its instance I = `*(P+0x134)`:

- `I+0x5c`: expect 0 now.
- `I+0x2c4`: 1 means distance-culled. 0 with `+0x5c == 0` points to an InstantiateInstance precondition failure.
- `P+0x314`: CullDistance. If it is 0, the model build did not reach `FUN_00bc8cb0`.
- `|P+0x1cc − localPawn+0x1cc|`: the distance.
- `I+0x60`, `*(I+0x60)+0x60`: mesh and EMFX template, must both be non-zero.
- `I+0x64`: must equal P.
- `I+0x94`: must be 0.
- `*(DAT_01924c8c)+0x38`: must be non-zero.

**[I] Test that should confirm the cause:** set `P+0x314` to 1e6, or move the NPC to the player's position. `I+0x5c` should then appear on the next tick, followed by +0x220 Num=4, +0x74, +0x200 and drawing.

## Function index

- `0x944800` UEMFXMeshInstance::InstantiateInstance (creates +0x5c)
- `0x942ff0` UEMFXMesh load EMFX actor (mesh+0x60); `0x942900` LoadAnimations
- `0x9470f0` UEMFXMeshInstance::PlayAnim
- `0x946330` UpdateMotions
- `0x94bf20` Render (writes +0x74/+0x80/+0x200/+0x23a); `0x94d470` other render path (same gate)
- `0x945050` creates node controllers into TArray +0x220
- `0xa04f80` APawn::Tick → vfunc+0x120 (`0xbcb380`), vfunc+0x138 (`0xa04cd0` → vfunc+0x278 = `0xbb4080`)
- `0xbcb380` SGO pawn tick hook: local → instantiate; remote → `0xbb77a0` distance cull, then instantiate
- `0xbb77a0` cull test; `0xbafc10` CullDistance getter (pawn+0x314, +60000 if Physics==4)
- `0xbc8cb0` sets collision and CullDistance; called from `0xbc95a0` ← `0xbcb8e0` (model builder), `0xbcc5a0`, `0xbcb1e0/0xbcb230`, `0xb73700`, `0x693f40`
- `0xbcc5a0` PostNetReceive; `0xbcaab0` customization slot → `0x944800`
- `0xbb4080` per-tick animation update (needs +0x5c, +0x2c4==0)
- SGO pawn vtable base `0x117a1ec` (also `0x117b534`, `0x117b99c` for the other two SGO classes, same slot layout [I]); UEMFXMeshInstance vtable `0x112b874`; UEMFXMesh vtable `0x112baac`

## Live check (2026-10-11, after this report)

Against a running client with test NPCs about 100 units from the player: the NPC mesh instances **do** have `+0x5c` (EMotionFX ActorInstance) set, `+0x2c4` = 0, CullDistance 6000, `+0x64` = owner, `+0x94` = 0. So distance culling and instance creation are not the blocker. The mesh Render `FUN_0094bf20` is still never reached (instance `+0x74` frame stamp stays 0) although the NPC actor's LastRenderTime updates. One caller, `FUN_009a84f0` at `0x9a8c1d`, only calls it when `FUN_007e8db0()` (a check over the actor's skins/materials, vfunc `+0x8c`, recursing into `+0x780`) returns nonzero and `FUN_007ec880(actor) == 0`. The other callers (`0x8cfb69`, `0x9a8c44`) are not yet examined. Still open.
