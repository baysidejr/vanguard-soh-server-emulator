# Gear on character models: m_AttachmentGroups

> **Verified live (2026-10-12):** replicating `m_AttachmentGroups` = (9, 111000, 6), (16, 111000, 32), (12, 111000, 26), (33, 1, 28), (23, 1, 42) dresses the player in a robe with a bow; NPCs with (9/16/12, 111001) wear dark robes. Their SWORD_1000/SHIELD_1000 did not show yet. Implemented in `server/zone.py` (`gear_attachments`, `NPC_GEAR`) and `server/netcache.py`.


[O] = observed in client code or data. [I] = inferred.

## 1. Layout and wire format

- [O] Engine.u ScriptText (Pawn):
  ```
  struct native SGOAttachmentGroupInfoPair {
      var() int m_PackageIndex;      // +0
      var() int m_AttachmentIndex;   // +4
      var() int m_VGInventorySlot;   // +8
  };
  var SGOAttachmentGroupInfoPair m_AttachmentGroups[60];   // pawn +0x444, 12 bytes each
  var int m_AttachGroupVersion;                            // NOT replicated
  ```
  m_AttachmentGroups is in the Pawn `reliable if (bNetDirty && Role==ROLE_Authority)` list, together with m_Gender, m_iModelNum, m_iRaceId and the others.
- [O] Engine.u export 2518 (the struct): Children = m_PackageIndex (3017), then Next = m_AttachmentIndex (3016), then Next = m_VGInventorySlot (3015), then 0. Iteration order is the declaration order.
- [O] UStructProperty::NetSerializeItem = FUN_00b08440 (UStructProperty vtable 0x110cb7c, slot +0x9c). Struct names 0x57, 0x58, 0x5b, 0x5d and 0x5f get special handling. Any other struct walks its Children through the `Next` (+0x34) chain. For each member with `Map->vtbl+0x7c(prop) != -1`, it calls member->NetSerializeItem once per ArrayDim element. UIntProperty::NetSerializeItem = FUN_00b01c90, which serializes the raw 4 bytes.
- So each element on the wire is: element-index byte (ArrayDim 60 > 1), then **3 × 32-bit ints: PackageIndex, AttachmentIndex, VGInventorySlot**. No compression.
- [O] Fix needed in netcache.py: `NetField.writer` treats any 3-int tuple as a **Rotator**. You need a branch keyed on the struct name (the StructProperty's struct is in `extra`). For SGOAttachmentGroupInfoPair, write `w.bits(v & 0xFFFFFFFF, 32)` for each of the 3 ints.
- [I] Fill unused elements with (-1,-1,-1), or skip them. FUN_00bc5eb0 and FUN_00bcbd20 treat PackageIndex == -1 as a free slot.

## 2. Client handling (PostNetReceive FUN_00bcc5a0)

- [O] PreNetReceive saves the old array at DAT_01923ff0. For every element whose triple changed:
  - it first calls `vtbl+0x3cc(old.pkg, old.att, old.slot, 0, 0)` to remove the old attachment (FUN_00bc6d10);
  - then, if `pkg >= 0` and `att > (pkg==100 ? -1 : 0)`, it calls `vtbl+0x3c8(pkg, att, slot, 0, 0)` = **FUN_00bcbd20 AddAttachment**.
  - The vtable is 0x117a1ec (PostNetReceive is at +0xd4).
- [O] **AttachmentIndex must be > 0.**
- FUN_00bcbd20 (pawn `this`, race = m_iRaceId at +0x43c, race info = `DAT_01924754+0xe4200+race*4`):
  - pkg 500/501 is mount/special (slot 0x27/0x2d).
  - [O] Gate: it returns early unless `DAT_018bde28 != 0 || (*(DAT_01924c8c)+0x38) != 0`. [I] This is a "render models" flag that is normally set in game. The same gate applies to m_Customization (FUN_00bcaab0), so if face sliders already change the model, the gate passes.
  - [O] Weapons (pkg 0x15..0x2b) are skipped if raceinfo+0xf1 == 0. If raceinfo+200 != 0 and pkg < 0x15, pkg becomes 100 (creature/NPC race item set).
  - Bone: FUN_00bb0000(slot):
    - slot 0x1c (28 PRIMARYHAND) or 0x24 (36 TWOHANDS) → "RightWield"
    - slot 0x1d (29 SECONDARYHAND) or 0x2a (42 RANGED) → "LeftWield"
    - anything else → "Body"
    - slot 4/0x13 is left side (-1); slot 5/0x14 is right side (1).
    - pkg 0x22 (SHIELD) always uses "Shield"; slot 0x24 with HAMMER/AXE/CLUB/FLAIL/MACE/BARD uses "LeftWield".
    - If slot < 0, FUN_00bb00d0 picks the bone and sets slot 0x1c or 0x1d.
  - Mesh name: FUN_00bc4210(pkg, att, side) → loads an EMFXMesh. Gender comes from `vtbl+0x2b4` (m_Gender): 0 → "M", 1 → "F".

## 3. PackageIndex = item mesh type (FUN_00bb0200) [O]

| pkg | type | name format |
|---|---|---|
| 1-6 | HAIR_BANGS/TOP/BACK/SIDES/PONYTAIL/FACE | race-specific |
| 7 | ARM | |
| 8 | BACK | |
| 9 | CHEST | `CHEST_ITEMS.M_CHEST_<att>` |
| 0xa (10) | ? (sided) | |
| 0xb (11) | FACE | |
| 0xc (12) | FEET | `FEET_ITEMS.M_FEET_<att>` |
| 0xd (13) | FINGER (sided) | |
| 0xe (14) | HAND | `HAND_ITEMS.M_HAND_<att>` |
| 0xf (15) | HEAD | race "HUMAN": `HEAD_ITEMS.HUMAN_M_HEAD_<att>` |
| 0x10 (16) | LEG | `LEG_ITEMS.M_LEG_<att>` |
| 0x11 (17) | NECK | |
| 0x12 (18) | SHOULDER | |
| 0x13 (19) | WAIST | |
| 0x14 (20) | WRIST | |
| 0x15 (21) | TOOL | not gendered: `<T>_ITEMS.<T>_<att>` (applies to 0x15..0x2b) |
| 0x16 (22) | AXE | |
| 0x17 (23) | BOW | |
| 0x18 (24) | CLUB | |
| 0x19 (25) | CROSSBOW | |
| 0x1a (26) | DAGGER | |
| 0x1b (27) | FLAIL | |
| 0x1c (28) | HAMMER | |
| 0x1d (29) | MACE | |
| 0x1e (30) | POLEARM | |
| 0x1f (31) | STAFF | |
| 0x20 (32) | THROWN | |
| 0x21 (33) | SWORD | `SWORD_ITEMS.SWORD_<att>` |
| 0x22 (34) | SHIELD | |
| 0x23 (35) | SPEAR | |
| 0x24 (36) | FIST | |
| 0x25 (37) | SPADE | |
| 0x26 (38) | KNIFE | |
| 0x27 (39) | MARTIALFIST | |
| 0x28 (40) | MARTIALSWORD | |
| 0x29 (41) | MARTIALSTAFF | |
| 0x2a (42) | FOCUS | |
| 0x2b (43) | BARD | |
| 100 | race item set | `<RACE>_ITEMS.<RACE>_<att>` |
| 600 | TEST | |
| 601 | FULLSUIT | |

- The packages are Assets/Characters/Meshes/<TYPE>_ITEMS.uem (EMFXMesh exports, grouped by tier; for example CHEST_ITEMS.BaseClothing.M_CHEST_1).
- [I] Lookup is "Pkg.Name" without the group. The shipped game relies on this, so the loader finds objects anywhere in the package.
- AttachmentIndex = the numeric suffix of the mesh = the item's appearance id.
- **Note:** Assets/AttachmentGroups/*.sag and FUN_00bd3960 ("Shirts", "Pants", …, format "%s.%s_%d") are an older or editor-only path (FUN_00bc5eb0 and FUN_00bc3ce0). They are not used by replication. Ignore them.

## 4. VGInventorySlot = the same equip slot ids as vgmsg.EQUIP_SLOTS [O]

28 PRIMARYHAND, 29 SECONDARYHAND, 36 TWOHANDS, 42 RANGED, 6 CHEST, 32 LEGS, 26 FEET, 33 HANDS, 0 HEAD, 35 SHOULDERS, 21 WAIST, 34 WRISTS.

## 5. Test recipe (human male, m_Gender=0)

Real mesh ids from the .uem packages:

| idx | (pkg, att, slot) | mesh |
|---|---|---|
| 0 | (9, 1, 6) | CHEST_ITEMS.M_CHEST_1 (BaseClothing) |
| 1 | (16, 1, 32) | LEG_ITEMS.M_LEG_1 (BaseClothing) |
| 2 | (12, 1, 26) | FEET_ITEMS.M_FEET_1 (BaseClothing) |
| 3 | (33, 1000, 28) | SWORD_ITEMS.SWORD_1000 (Thestra_Tier01), RightWield |
| 4 | (34, 1000, 29) | SHIELD_ITEMS.SHIELD_1000 (Thestra_Tier01), Shield bone |

- Alternatives: chest 111000 (Thestra_Light_Tier01) or 161000 (Thestra_Clothing_Tier01); hands (14, 111000, 33); sword 1..7 (World_Generic).
- Values: `values["m_AttachmentGroups"] = [(9,1,6),(16,1,32),(12,1,26),(33,1000,28),(34,1000,29)] + [(-1,-1,-1)]*55`
- Wire: SerializeInt(RepIndex of m_AttachmentGroups, Max), then byte elementIndex, then int32 pkg, int32 att, int32 slot. This repeats per element. Send it in the actor open bunch, and again whenever gear changes (send only the changed elements).
- No extra zone event is needed. m_iModelNum is not needed for gear (it is used for the model build, FUN_00bcb8e0). m_Gender must be correct, because it selects M_ or F_ meshes.

## Key addresses

- FUN_00bcc5a0 PostNetReceive (attachment diff loops 0xbcc833-0xbcc8ff)
- FUN_00bcbd20 AddAttachment (vtbl+0x3c8)
- FUN_00bc6d10 RemoveAttachment (vtbl+0x3cc)
- FUN_00bc4210 mesh name builder
- FUN_00bb0200 type names
- FUN_00bb0000 slot → bone
- FUN_00b08440 UStructProperty::NetSerializeItem
- FUN_00b01c90 UIntProperty::NetSerializeItem
