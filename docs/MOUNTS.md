# Mounts

> **Verified live (2026-10-13):** right-clicking a "Thestran Riding Horse" item in the bags (the client sends 0x98 {handle, u8}) prints "You summon your Thestran Riding Horse." and Ranger rides a grey horse: the server adds `(500, 1000, 39)` to the pawn's `m_AttachmentGroups` and sets `m_MountType = 1`. `/dismount` (0x57c, no payload) or right-clicking the item again removes the entry, sets `m_MountType = 0`, and sends 0x0e code 0xac ("Dismounting."). Other players see the mount through the same pawn properties (verified live with two clients: Justins sees Ranger riding). Dev command: `!mount [id] [fly]`, `!mount 0` dismounts.
>
> **Mounted speed (verified live):** after the attachment update the server sends `GroundSpeed` in its own bunch: 1.6 x the client's 337.889 (read from pawn +0x7f0). Holding W for 3 s: 1012 units on foot, 1588 mounted. Dismounting sends the base speed again.
>
> **Mount meshes (2026-10-13):** each MOUNT_<id> in MOUNT_ITEMS.uem names its creature skeleton in its "Item Template" property. Verified live as ground mounts: 1000 horse, 8000 dire wolf, 13000 camel, 5001 griffon, 6000 wyrm, 7000 wyvern (the camera may need zooming out for the big ones). Families: horseQuarter 1000-1300, horseShire 3000+, horseUndead 4000-4005, horseSkeleton 4008/4011/4017, griffon 5001+ (110 ids), wyrm 6000+ (55), wyvern 7000+ (101), wolfDire 8000, wolf 8001/8002, spiderWolf 8005, drake 9000, fox 9001, hellhound 9006/100200, pegasus 9011/55100/101000+, manticore 9012+, boar 9022, bear 9030-9036, pangolin 9040, elementalFire 9050, raptorEagle 9060, raptorPhoenix 9065/9066, camel 13000+, unicorn 55000+, turtleDragon 207000+, scorpion 212000+, rhinoceros 203000+ and more (full list: `server/` session notes in docs/MOUNTS.md history).
>
> **Flying (not working yet):** the client's jump handler (FUN_00baf7e0) turns a jump into flight only when the pawn has a mount actor (+0x780), m_MountType (+0x78c) is 3 and Physics is PHYS_Falling: you must press jump **a second time while in the air**. `!mount 5001 fly` (or the Griffon Whistle, sold by Orin) sets type 3 and AirSpeed, and the griffon renders, but scripted double presses never produced flight (only single jumps registered). Worth trying by hand: mount, jump, and press jump again at the top of the jump. Also not done: barding (slot 45) and real mount icons (1225 is a placeholder).

Server: `login_stub.set_mount`, `zone.gear_attachments` (MOUNT_PACKAGE 500, MOUNT_SLOT 39). Content: items.json `"mount": {"id": 1000, "type": 1}`; the camp merchant sells the horse for 500 copper.

The rest is the client analysis (static, by a research agent).


[O] = observed in client code or data. [I] = inferred. Offsets are real pawn offsets. pawn_layout.txt is off by +0x2d0 after m_AttachmentGroups because it sized that struct as 4 bytes instead of 60x12, so its iMount at 0x4b4 is really 0x784.

## 1. What puts a player on a mount

### The trigger is an attachment-group entry, not a property [O]
- A mount is an **m_AttachmentGroups element (PackageIndex 500, AttachmentIndex = mount id, VGInventorySlot 39)**.
- Pawn PostNetReceive `FUN_00bcc5a0` calls vtbl+0x3c8, which is `FUN_00bcbd20` (AddAttachment). There, `pkg == 500 || pkg == 501`:
  - slot 0x27 (39, MOUNT) → `FUN_00bc9a70(mountId, pkg)`, which is **MountUp** (string "Level is NULL in MountUp").
  - slot 0x2d (45, MOUNTBARDING) → `FUN_00bc46a0`, which adds mount armor/mane/tail to an existing modular mount.
  - other slots (40 flying, 44 aquatic) → MountUp, but only if `FUN_004a4eb0(pawn)` (an IsA check on the pawn class) passes.
  - This check runs before the usual render gate.
- Removing or replacing that element makes PostNetReceive call vtbl+0x3cc, which is `FUN_00bc6d10(oldPkg, oldAtt, oldSlot)`. For pkg 500/501 with slot != 0x2d it calls vtbl+0x2b8, which is **Dismount** (`FUN_00bca650`, "Level is NULL in Dismount").
- pkg 501 uses `IOD_MOUNT_ITEMS.*`, which only contains IOD_MOUNT_101041. **Use pkg 500**, which uses `MOUNT_ITEMS.uem` in Assets/Characters/Meshes.

### What MountUp (FUN_00bc9a70) does [O]
1. It returns without doing anything if the rider's m_iRaceId is a horse race (0xb3, 0xd2, 0xd3).
2. It picks a size class from the rider race:
   - 2 for Dwarf, Gnome, Goblin, Halfling (2, 6, 7, 10, ...).
   - 1 for elves, humans, Raki and similar (3, 4, 5, 8, 12-15, 17, ...).
   - 3 for Half-Giant, Orc, Vulmane, Barbarians, Kurashasa (9, 16, 18, 20, 21, 22, ...).
   - 0 (not modular) when the mount id is >= 4000.
3. **Modular mesh** (id < 4000 and size class != 0): it loads `MOUNT_ITEMS.MOD_MOUNT_BODY_<size><NN>`, `..._TAIL_<size><VV>` and `..._MANE_<size><VV>`.
   - NN = id % 100 as 2 digits. VV = (id % 1000) % 5 as 2 digits. This digit split is [I], taken from the names in the package: BODY_100..330, TAIL/MANE_100..305.
   - If any of the three is missing, it uses the full mesh below instead.
4. **Full mesh**: `MOUNT_ITEMS.MOUNT_<id>`. The package has about 1000 of these, for example MOUNT_1000-1007, 1100.., 2000.., 4000-4020, 5001.., 6000.., 7000.., 10000.., 20000.., 100000.., 200000...
5. It derives the mount race from the mesh (`FUN_00bb7ba0` / `bb7c30` / `bae410`) and **writes it into iMount (+0x784) itself**. It also sets fMountScale (+0x788) from the mesh template.
6. It spawns an `SGOAttachment` actor and stores it in m_Mount (+0x780). The actor's +0x388 is set to 0x27 and +0x38c to pkg. It attaches the actor to the "Body" bone and sets pawn+0xa99 = 1 when the mesh is modular.
7. It raises the pawn's Location.Z by the collision-height difference.
8. It calls `FUN_00bc8cb0` (collision = mount race collision x fMountScale) and `FUN_00bb5ae0(m_Posture)`. The second call resets GroundSpeed (see section 3).
- Rider animations `mountedIdle`, `mountedRun`, `mountedIdleBreak` and `mountedIdleLapBreak` come from the EMFX code at 0x94750f [O].

### Replicated pawn properties [O]
From the Engine.u script text, Pawn block `reliable if (bNetDirty && Role==ROLE_Authority)`:
- `var SGOAttachment m_Mount;`: not replicated. The client sets it.
- `var int iMount; // is this pawn mounted`: replicated, but MountUp overwrites it with the mount race id and Dismount sets it to 0.
- `var float fMountScale;`: replicated, but MountUp overwrites it.
- `var eVGMountType m_MountType;`: replicated, enum of 4 values sent with `SerializeInt(v, 4)`. **The client never sets it**; it only clears it on dismount or destroy (0xbca7bb, 0xbb332b, 0x7fe6eb). **The server must send it.**
  - VGMOUNT_TYPE_None = 0
  - VGMOUNT_TYPE_Ground = 1
  - VGMOUNT_TYPE_Aquatic = 2
  - VGMOUNT_TYPE_Flying = 3
- What reads m_MountType:
  - PlayerController script: `PlayerFlying.PlayerMove` blocks moving backwards when it is Flying, and `BeginState` pops Velocity.Z to 550.
  - Native code at 0xbaf832: if m_Mount != None, m_MountType == 3 and Physics == PHYS_Falling, it calls controller vtbl+0x170 ([I] goes into PlayerFlying, i.e. a jump turns into flight).
  - Native code at 0x9d9b3f and 0x9da267 handles flying physics and animation.
  - Item use at 0x5060f3 does the open-space check only when m_MountType == 0.
  - `/portrait` at 0x601f21.
- Equipment slot ids (slot-tag table at 0x50d6e5..0x50d975) [O]: MOUNT 39, MOUNTFLYING 40, HARVPACK 41, RANGED 42, AMMO 43, MOUNTAQUATIC 44, MOUNTBARDING 45, MOUNTSADDLEBAGS 46, MOUNTHORSESHOES 47.
- Zone message 0x3e7 MsgPlaceOnVehicle is for vehicles, not mounts. No zone message is needed to mount.

## 2. Client→server events and server replies

- **Summon or use:** `FUN_00505ff0` handles right-click "use" on an item and `/itemuse <name>` (0x604d30 → FUN_0050b590). It sends **0x98 {i32 item handle, u8 FUN_00c067a0()}** through FUN_004cfb00 [O].
  - Before sending, when the item's equip slot (+0x58) is 39, 40 or 44 and the pawn's m_MountType == 0, it checks for open space with `FUN_00bb48f0(CollisionRadius*2, CollisionHeight)`. If there isn't enough, it prints "You need more open space around you to do that." and sends nothing [O].
  - **Conflict:** server/INVENTORY.md currently treats 0x98 as unequip. For an equipped item in slot 39, 40 or 44, the server should treat 0x98 as a summon/dismount toggle [I].
- **Dismount:** `/dismount` (cmdtab 0x13f00fc → 0x5fd220) sends **0x57c with no payload** through FUN_004cfb50 [O].
- **Server→client:**
  - The mount itself is shown only by pawn replication (section 4).
  - The notice `0x0e` MsgSingleShort i16 **0xac** prints "Dismounting" (channel 0x2a) in FUN_0061d530 [O].
  - Item-use failures go through `0x1c5` u8 (FUN_00507970). Its string table contains WrongMountType and NotWhileFlying (0x508a12 / 0x508a2a); the code numbers were not mapped [O strings].
  - Abilities have `m_NeedMountType`, `m_bNeedDismount` and `m_bNeedDismountUnless3DSException` (SGOUnrealAbstractionLayer.u) and the same WrongMountType string at 0x43f6d6 (ability fail 0x241) [O].

## 3. Movement speed

- The client **does not speed up a mounted pawn** [O].
  - `FUN_00bb5ae0` (SetPosture) sets **GroundSpeed (+0x7f0) = rider race entry +0x50** (or +0x54 when posture == 2).
  - MountUp calls it at its end, so GroundSpeed is reset to the rider race default at that moment.
- GroundSpeed, WaterSpeed and AirSpeed are replicated `reliable if (bNetDirty && bNetOwner && Role==ROLE_Authority)` [O]. Our pawn has bNetOwner = True, so **the server sets mount speed by replicating GroundSpeed** (and AirSpeed for flying mounts).
  - Send it in a **later bunch** than the attachment change, because PostNetReceive → MountUp → SetPosture would overwrite a GroundSpeed sent in the same bunch.
  - Send it again after any m_Posture change.
- MsgScore field 29 is display only: fMovementSpeedSelfPct = field x 0.18018, so 555 shows 100% [O per MSGSCORE.md]. Raise it too, so the character sheet shows the mounted speed.
- The real race default (+0x50) was not read. [I] Start with GroundSpeed about 1.6x the normal run speed; if the normal speed is unknown, try 900.
- Collision while mounted comes from the mount race x fMountScale (FUN_00bc8cb0, iMount != 0 branch). The server does not need to send it.
- The console exec at 0xb789c0 ("Your new groundSpeed is: %f") is a local cheat. Ignore it.

## 4. Minimal recipe (try in this order)

1. **Mount up** (on 0x98 for a mount item, or a test command):
   - Replicate on the pawn channel: `m_AttachmentGroups[k] = (500, 1000, 39)`, using any free element k, and `m_MountType = 1`.
   - Use 1000 for a modular horse sized to the rider (BODY_x00, TAIL_x00, MANE_x00 exist), or 4000 / 5001 / 7000 for full meshes. Use 3 instead of 1 for a flying mount.
   - Keep the gear elements unchanged.
   - Other clients get the same pawn properties and run the same MountUp.
2. **Then, in a separate bunch:** `GroundSpeed = 900.0` (and `AirSpeed = 900.0` for flying). Optionally send MsgScore with field 29 = 900.
3. **Dismount** (on 0x57c, or 0x98 again while mounted):
   - Replicate `m_AttachmentGroups[k] = (-1, -1, -1)` and `m_MountType = 0`. Removing the element calls Dismount.
   - Then, in a separate bunch, `GroundSpeed = <normal>`.
   - Send `0x0e` i16 0xac ("Dismounting").
4. Do not send iMount, fMountScale or m_Mount. The client computes them.
5. If the horse does not appear:
   - Try `MOUNT_4000` (non-modular, which skips the size-class path).
   - Check that the rider race is a player race listed in section 1. Unknown races go through FUN_004d2250 and may abort.
   - Check that the attachment index is > 0 (PostNetReceive requires att > 0).
6. Mount equipment (optional): an element `(500, bardingIndex, 45)` adds `MOD_MOUNT_ARMOR_<size><%03d>` on top of a modular mount (id < 4000).

## Key addresses
| Address | Function |
|---|---|
| FUN_00bcc5a0 | Pawn PostNetReceive |
| FUN_00bcbd20 | AddAttachment (pkg 500/501 branch) |
| FUN_00bc6d10 | RemoveAttachment (calls Dismount) |
| FUN_00bc9a70 | MountUp |
| FUN_00bca650 | Dismount (vtbl+0x2b8) |
| FUN_00bc46a0 | Mount armor, mane and tail |
| FUN_00bc8cb0 | Collision and scale |
| FUN_00bb5ae0 | SetPosture / GroundSpeed |
| FUN_00505ff0 | Item use → 0x98 |
| 0x5fd220 | `/dismount` → 0x57c |
| FUN_0061d530 | Notice code 0xac |
| 0x804d8a / 0x804ddc | iMount / m_MountType in the pawn rep list |
| vtable 0x117a1ec | Pawn vtable (+0x2b8 Dismount, +0x3c8 Add, +0x3cc Remove) |

None of this has been tested live yet.

## Flying (verified live 2026-10-14)

**Take-off works.** With a breakpoint logger on the running client (`tools/winbreak.py`, breakpoints on Jump FUN_00baf7e0, the GameClient callback FUN_00b713d0 and the event sender FUN_006eb1b0), a standing Jump on the griffon calls the sender with event **0x5b**, and the server log shows `client event 0x5b`: it had arrived all along and was simply unhandled (the earlier tests never made a standing mounted jump, or missed the log line). A jump while falling sends **0x5a** the same way.

The server's answer is the UE2 PlayerController RPC **ClientAdjustPosition**(TimeStamp, NewState, newPhysics, NewLocX..Z, NewVelX..Z, NewBase) with newPhysics 4 (PHYS_Flying) and NewState `PlayerFlying` (`zone.client_adjust_position`). Two details matter: TimeStamp must be the newest ServerMove TimeStamp (the client ignores older corrections), and newPhysics is an EPhysics enum byte, sent in 5 bits (19 values) rather than 8 (`netcache.param_enum_size`); with 8 bits every later field was misread and the pawn jumped to the world origin. A replicated `Physics` property alone, or `ClientGotoState('PlayerFlying')` alone, did not make the client fly.

Seen live: after the standing jump the griffon held 659 units while the ground under it rose by 46 (a walking pawn follows the ground), flew where the view pointed, and climbed from 1000 to 8500 units with the view pitched up. Jump in the air sends nothing, so a flight ends by flying low (the server lands the pawn when it is under 80 units above the ground, `flight_check`, 3 s after take-off) or by dismounting, which drops the rider (an 8000-unit fall did 2254 damage and killed Ranger).

**Other players** simulate the flier as a SimulatedProxy, whose TickSimulated keeps a pawn on the ground (or falling) only while `bSimulateGravity` is set. So take-off also sends everyone else `bSimulateGravity = False`, Physics 4, the raised Location and zero Velocity, and landing sends them back; a flier that stops moving gets one zero-velocity update, or the watchers' copy keeps drifting along its last velocity. Seen with two clients: before, the watcher saw the griffon standing on the ground; after, it hovered in place above him. Flight follows the view pitch both ways: with the view slightly below level (ServerMove View pitch 65278) the griffon sank steadily (648 to 579 over 2800 units), and with it pitched up it climbed. Synthetic mouse-look from the test scripts changed the pitch only sometimes, so steering is best tried by hand; S sent no moves while flying. The server log shows the view pitch and yaw beside each position while a player flies.
