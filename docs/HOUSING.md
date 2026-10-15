# Player housing

> **Verified live (2026-10-13):** the server can place a house. `!house` opens an actor channel for `Engine.PlayerPlacedObject` with `m_PrefabNameTag = "Ra6001_P1_C1_Grid_PHcity01_Home001root001_lvl10_ver1"`, and the client builds a full Thestran house (stone base, timber frame, chimney, roof) at that spot. The open bunch needs an initial **rotation** after the location (bNetInitialRotation); without it the client misreads the properties ("NetSerializeItem failed for Owner"). Props 53-58 (m_PrefabNameTag, m_ParentUniqueID, m_ObjectUniqueId, m_MouseOverDisplay, m_BuildingType, m_BuildingUniqueId) all arrive.
>
> **Plots (verified live):** plot 101 "Wastes Homestead" (`server/content/plots.json`) shows a For Sale sign (`Ra1_P1_C1_Markers_ForSaleSign`, m_BuildingType 1). Inspect (0x460 {type, id}; dev `!plot`) opens the client's "Player Housing Information" window: "Plot Purchase Price: 10 silver", "This plot is for sale.". Admin tab > Purchase Plot > the client's "Confirm Plot Purchase" > Accept sends 0x481 {plot id}: "You lose 10 silver.", "Successfully purchased targeted plot." (0x0e 0x170). The Construction tab lists the plot's buildings from the 0x454 options (Thestran Cottage, Thestran Home, with type, max fixtures and max chests); Construct Building sends 0x479 {plot id, type} and the server builds it at once: "Construction completed successfully." (0x0e 0x192), the sign is replaced by the cottage for everyone in the chunk (a second client, Justins, sees the house). Ownership and buildings are saved in `server/housing.json` (not committed). Tear down (0x480) and sell (0x47f, half the price back) are coded but untested.
>
> **Interior and furniture (partly verified):** teleporting into the cottage shows its interior (plastered walls, leaded window, doorway), so the prefab brings its rooms. Furniture items (items.json `"fixture": prefab`; the camp merchant sells an Oak Table and an Ale Keg) are placed by right-clicking them in the bags while standing in your own built house (within 900 units of the plot): "You place the Oak Table." and a PlayerPlacedObject of type 3 is opened for everyone in the chunk and saved with the plot. The table prefab renders (checked in open ground with `!house Ra0005_P0001_C0001_Tables_Table01 3`); inside the house the script-driven camera could not be turned to frame it. Pick Up (0x462 {fixture object id}) returns the item ("Successfully removed Fixture from building." = 0x0e 0x178; tested with the `!pickup` dev command, which uses the same handler). Move nudges (0x464, ±10 units / ±256 yaw) re-open the object at the new spot (untested). The server also answers the client's own placement flow (0x461 -> 0x459 ghost preview -> 0x46d with the clicked pose; unit-tested), but the client never sent 0x461 in a live test on 2026-10-14: dragging the Oak Table from the bags onto the cottage floor (Ranger standing inside, interior visible) opened "Delete: Oak Table" instead, which means the client's "inside a house" check (FUN_0047b7b0 -> FUN_004771d0) found no house-interior zone at the drop point. See "Inside a house" test below.
>
> **Chests (verified live):** a "Storage Chest" item (`"fixture"` + `"chest": 20`) placed in the house becomes a PlayerPlacedObject of type 4. Opening it (0x151 {chest object id}; tested with the `!chest <n>` dev command, which uses the same handler as the object's Open menu) shows the client's "Chest" window ("You begin to use the Chest."): 0x199 {id, capacity}, 0x19f, 0x1a1 per item, 0x1a0. Dragging the Rusty Sword from the bags onto the chest sends 0x155 {chest, item handle, count, slot}; the server removes it from the bags (0x1a5) and adds it to the chest (0x19e). Dragging it back sends 0x157 {chest, item, count, container, slot}: "You receive Rusty Sword.", "Rusty Sword was removed from your chest." (0x19c). Chest contents are saved with the plot. A chest with items can't be picked up (0x0e 0x177 RemoveChestItems).
>
> **Upkeep deposits (verified live):** 0x47e {plot id, copper} from the Admin tab (tested with `!upkeep 25`): "You lose 25 copper.", "Deposit successful." (0x0e 0x17c) and 0x483 {balance}; the balance is saved with the plot and shown in 0x454. Upkeep is charged weekly from that balance when the plot window is opened (verified live: with the last payment 8 days ago the Admin tab shows "Upkeep Balance: (- 25)" in red, "Your last deduction was Mon Oct 12 ...", "The next deduction will be Mon Oct 19 ...", "Missed Payments: 1"). Nothing happens to a plot with missed payments yet.
>
> **Construction materials (verified live 2026-10-13):** a building option with plots.json `materials` {item: count} (the Thestran Home needs 2 Rough Stone and 2 Tattered Cloth) is not built at once. Construct (0x479) starts a project ("Construction of a Thestran Home has begun.") and opens the client's Building Construction window with 0x453 `{i32 site (plot id), i32 0, wstr project, i32 percent, 20 x (i32 resource id, wstr name, f32 needed, f32 added)}`, drawn as "Rough Stone 2.00 of 2". The resource id must be the item's template id (item field 1, `zone.template_id`): the client's Construction Material Select popup (the row's "+") lists the bag items with that id. Accept sends 0x475 `{i32 construction id = plot id, i32 bag item handle, i32 template id, i32 row}`; the server takes the items and resends 0x453 ("Project Status: 50 % complete."). Complete Construction asks for confirmation ("…consume all building resources") and sends 0x478 `{plot id}`: with every material in, the house goes up ("Construction completed successfully.", 0x477 closes the window). Abandon (0x476) gives the materials back. 0x473 `{plot id}` reopens the window. `!cev <event> <i32...>` injects a client event for testing (e.g. `!cev 0x479 101 2`).

> **Permissions (window verified live 2026-10-13):** the owner's permission entries are saved per plot (`housing.json` "permissions": {id, name, rank, flags, all_players, all_guild, friends}). Create/edit 0x470/0x472 `{i32 plot, i32 perm id, wstr name, i32 guild rank, u32 flags, bool8 all players, bool8 all guild}`, delete 0x471 `{plot, perm id}`, add a friend 0x46f `{wstr player, i32 perm id, i32 0}`, remove 0x46e `{perm id, friend id}`. With the plot window the server sends 0x456 per entry (the Permissions tab lists "Friends"; Edit Permission ticks the flag boxes) and 0x46f `{perm id, friend id, wstr name}` per friend (the friend id must not be 0: row + 1; 0x457 does not fill the Edit Permission name list). `housing.allowed` (unit-tested) checks the flags for moving/picking up furniture (0x2/0x8), placing it (0x4), paying upkeep (0x20) and adding construction materials (0x40); NoAccess (0x80000000) wins. Entries cover all players, the owner's guild or their friend list.

> **Repossession (unit-tested):** once a minute the server charges due upkeep on every plot (`housing_tick`); after `REPOSSESS_AFTER` (4) missed weekly payments the plot is taken back: the owner gets a "Repossessed" letter from the Housing Office plus one letter per furniture item and chest item, and the For Sale sign returns for players in the chunk.

> **Chest permissions (verified live with two clients 2026-10-13):** Manage Chest (0x466 {chest id}; dev `!chest <n> manage`) shows the client's "Manage Chest" window with Edit View / Deposit / Withdrawal Permission (slots 0/1/2). Each slot is its own permission (All Players, All Guild Members + rank, a name list), not a plot permission. Accept sends 0x467 {chest id, slot, permission id, rank, u32 junk, bool8 all players, bool8 all guild, wstr ""}; the chest id is -1 until the slot exists, so the server uses the chest being managed. The server answers 0x468 + 0x469 {chest, slot, permission id 1001+slot, rank, 0, all players, all guild, wstr name} + one 0x46f {permission id, row + 1, wstr name} per name (0x46a does not redraw the list). Add Player only works once the slot exists and sends 0x46f {wstr name, i32 1001+slot, 0}. Before: Justins got "You do not have permission to use this chest." (0x0e 0x1ad); after Ranger added Justins to View: "You begin to use the Chest." Deposit and withdraw also need the View slot.

> **Doors (static analysis only, not done):**
> - A left click on a Mover sends zone message **0x24 {u32 m_MoverID}** (mover+0x6ec). It is a raw struct sent through the same path as zone message 0x9, and only within 1500 units [O].
> - Code: FUN_00b81660 -> AMover::Activate FUN_007efbc0 -> FUN_00bcf7a0/FUN_00b714f0. `PlayerController.TryActivateMover` uses the same path.
> - Online, the client does not move the door itself. No server->client event touches Movers, so the server has to open it by replicating the Mover actor (SimInterpolate, KeyPos/KeyRot, bClosed, TargetKeyframe, …; replication list at 0x805470) [I].
> - 0x0e code 0x1ac is FailedOpenDoor ("BuildingInstance not found"). There is no locked or no-permission door text, so the server enforces the OpenDoor permission (0x1) by not opening the door.
> - Only three chunks have map Movers (chunk_n16_6, chunk_n18_6, chunk_n23_26). Building doors are spawned by the client from the prefab (ACompoundObject AttachMovers / ShouldSpawnMoversAndTriggers). The camp cottage prefab has an open doorway and no door.
> - Full notes are in the research report (door_report.md).
> - **Checked 2026-10-13:** none of the map Movers is a door. chunk_n16_6 Mover0 is a TexPropCube far outside the map; chunk_n18_6 Mover189/Mover133 are rotating sun decorations (InitialState ConstantLoop, MoveTime 4); chunk_n23_26 Mover10 is a small ship (Ra0001_P0001_Ships_Small001) that sails 12432 units and back (LoopOpenTimed, MoveTime 20, StayOpenTime 10). The PHcity01 Home001 cottage was viewed from all four sides: it has a doorway, no door. The prefab table names door parts (e.g. Ra6060_P1_C4_Grid_PHcity01_do003_lvl10_ver1) for other buildings, so door support waits for a building that uses one.
> - How the client replays a replicated Mover (FUN_007f99f0, PostNetReceive): when SimInterpolate (+0x6b4) changes it copies SimOldPos/SimOldRot into OldPos/OldRot, sets PhysAlpha = X x 0.01, PhysRate = Y x 0.01, KeyNum = Z & 0xff, PrevKeyNum = Z >> 8, and switches to PHYS_MovingBrush (8). So a server opens a door by sending SimInterpolate = (0, 100 / MoveTime, 256 x 0 + 1) on the Mover's channel (a map Mover is referenced by its export index in the level package, which is package-map entry 0).

Server: `zone.open_placed_object`. Dev command: `!house [prefab] [type]` (800 units +x of the player). 37 root prefabs (whole buildings) are listed in `bin/compoundobjectMD.tab` (`...PHcity01_Home001root001...`, `HomeShop`, `Inn`, `Temple`, `GuardTower`, `CraftingBarn`; Ra6001 Thestra, Ra6021 Qalia, Ra6060 Kojan).

The rest is the client analysis (static, by a research agent).


[O] = read in code, [I] = inferred. Nothing was run. Detailed tables: `housing_s2c.md` (S->C layouts, every 0xe code), `housing_c2s.md` (C->S, UI command ids), `housing_world.md` (actors, prefabs, preview). All SGO messages use normal zone framing. Fields go on the wire in registration order, which is not their offset order.

Key client objects:
- Housing manager `DAT_014639d4`:
  - +0 / +4: id and type of the last placed object the player clicked (copied from actor +0x3f0 / +0x3f4 by FUN_00483c90; the call is at 0x418031).
  - +0x1c plotId, +0x23dc buildingId, +0x2444 constructionId, +8 handle of the fixture item being placed.
- Chest manager `DAT_014639b8` (+0x34 is the open chest id). Building NPC manager `DAT_014639e0`.
- S->C sub-dispatchers: FUN_00483d60 (plot, building, permissions, fixtures), FUN_004733d0 (chest 0x199-0x1a3), FUN_004864e0 (0x5cc/0x5cd).

UI (VGUIAssets/Shells/Default/Windows):
- VGUIBuildingInformationWnd.xml:
  - "Player Housing Information" window `_plot_information`, shown by `bPlotInformation`. Tabs: General, Buildings, Construction, Permissions, Admin, Building Inventory.
  - Confirm popups: PlotPurchaseConfirm, PlotRelinquishConfirm, BuildingDeconstructionConfirm, construction complete/abandon, and the guild HQ confirms.
  - Also: `_fixture_movement_popup`, Manage Chest `_manage_chest`, Edit Chest Permission, Create/Edit Permission.
- VGUIBuildingConstruction.xml: `_building_construction_wnd`, the resources window and the material-select popup.
- VGUIBuildingInventory.xml: Chest window `_chest`.
- VGUIBuildingNPCs.xml: `_building_npc_window`.

## 1. Server -> client

### Plot and building info
**0x454 MsgPlotInfoFull** (handler FUN_0047f590, registration FUN_00473770) [O]
- It only stores the data. **0x458** (no payload, FUN_00480c90) then sets bPlotInformation=1 and opens `_plot_information`.
- Fields in wire order:
  1. i32, not shown
  2. i32 **plotId**
  3. wstr, ignored
  4. wstr **ownerName**
  5. wstr, not shown
  6. i32 **cost in copper** (strPlotCost)
  7. bool8 **bPlotIsMine**
  8. bool8 **forSale** (1 = bPlotForSale and the owner is blanked)
  9. i32 upkeep bank balance (shown red if negative)
  10. i32 upkeep cost
  11. i32 last upkeep deduction (time_t)
  12. i32 next upkeep deduction (time_t)
  13. u32 purchase date (time_t)
  14-16. f32 x, y, z
  17. i32 missed payments
  18. bool8 full permission
  19. bool8 bPlotHasConstruction
  20. bool8 canViewPerms
  21. bool8 canEditPerms
  22. bool8 canViewUpkeepBank
  23. bool8 canPayUpkeep
  24. bool8 canStartConstruction
  25. bool8 bBuildingGuildUsable
  26. i32 guildId
  27. bool8 bPlotIsHQ
  28. bool8, never read. Client bug: the HQ guild id is copied from msg+0x34, which is never filled. Send 0.
  29. **10 x {i32 buildingTypeId, i32 b, i32 c, i32 maxFixtures, i32 maxChests, wstr name}**. This is the list of buildings that can be built on the plot (PlotOptionList). Empty names are skipped. b is kept as row data; c is unused.

**0x455 MsgBuildingInfoFull** (FUN_0047fc00) [O]
- Send it after 0x454, because 0x454 clears bPlotHasBuilding.
- Fields in wire order:
  1. i32 **buildingId**
  2. wstr, unused
  3. wstr ownerName ("This house belongs to %s.")
  4. wstr, unused
  5. bool8 isMine ("This is your house."; also enables tear-down)
  6. bool8 viewFixtureList
  7. bool8 canSendTrophiesToOwner
  8. bool8, unused
  9. u32 build date
  10-12. f32 x, y, z
  13. i32 maxFixtures
  14. i32 maxChests

**Small plot updates** [O]

| id | payload | meaning |
|---|---|---|
| 0x483 | {i32} | upkeep balance |
| 0x479 | {bool8} | hasConstruction |
| 0x47a | {bool8} | guildUsable |
| 0x47b | {i32 hqGuildId, bool8 isHQ} | HQ state |
| 0x47c | {i32 a, i32 b, wstr owner, bool8} | opens the guild leader HQ confirm |
| 0x47d | {i32, wstr} | strGuildHQName |

### Construction [O]
- **0x453 MsgConstructionInfoFull** (FUN_00482ad0) opens BuildingConstruction. Payload:
  - i32 siteId
  - i32, unused
  - wstr projectName
  - i32 percentComplete
  - **20 x {i32 resourceId, wstr resourceName, f32 qtyA, f32 qtyB}**. Which float is "needed" and which is "total" is [I].
- **0x474**: same class, but it only fills the resources list as "%s ( %d )". It works as a cost preview [I].
- **0x476 / 0x477** (no payload): close the construction window.

### Permissions [O]
Flags are a u32 bitmask (FUN_0047a180 / FUN_004753a0):

| mask | permission |
|---|---|
| 0x1 | OpenDoor |
| 0x2 | MoveFixture |
| 0x4 | PlaceFixture |
| 0x8 | PickupFixture |
| 0x10 | AllowModify |
| 0x20 | PayUpkeep |
| 0x40 | ManageConstruction |
| 0x1000 | View |
| 0x2000 | ViewUpkeepBank |
| 0x4000 | ViewFixtureList |
| 0x8000 | SendTrophiesToOwner |
| 0x80000000 | NoAccess |

Building permissions have 10 slots; chest permissions have 3.

| id | class | payload / effect |
|---|---|---|
| 0x456 / 0x470 | MsgBuildingPermission | {i32 unused, i32 permId (not 0), wstr name, i32 guildRank, u32 flags, bool8 allPlayers, bool8 allGuild}. 0x470 also refreshes the list. |
| 0x471 | | {permId}: delete a permission |
| 0x457 / 0x46f / 0x46a | MsgBuildingPermissionFriend | {permId, friendId, wstr name}: add a friend, up to 20. 0x457 = building only; 0x46f = building or chest, with refresh; 0x46a = chest only. |
| 0x46e | | {permId, friendId}: remove a friend |
| 0x469 | MsgChestPermission | {i32 chestId, i32 slot 0..2, i32 permId, i32 guildRank, u32 flags, bool8 allPlayers, bool8 allGuild, wstr name} |
| 0x468 | | no payload: reset chest permissions |
| 0x46b | MsgChestInfo | {i32 chestId, wstr displayName, wstr itemName}: opens `_manage_chest` |

### Fixtures [O]
| id | payload | effect |
|---|---|---|
| 0x45a | none | clear the fixture list |
| 0x45c | {i32 fixtureId, bool8 chest, bool8, wstr name} | add a fixture silently. The first bool marks a chest: the client counts those for "Chests: (n of m)" (FUN_00479e00 counts records with byte +8 set). The second bool's meaning is unknown. |
| 0x45d | same as 0x45c | add a fixture and show it immediately |
| 0x45b | none | rebuild the list and the fixture/chest counts |
| 0x45e | {fixtureId} | remove one fixture |
| **0x459** | **{wstr prefabName, f32}** | **start the placement preview** (see section 3). The f32 is probably the draw scale [I]. |

### Chest (FUN_004733d0) [O]
| id | payload | effect |
|---|---|---|
| **0x199** | {i32 chestId, i32 capacity} | opens `_chest` with the title "House Chest" |
| 0x19a | none | close |
| 0x19e | item record | add an item and draw it |
| 0x1a1 | item record | add an item silently |
| 0x19f | none | clear |
| 0x1a0 | none | refresh icons |
| 0x19b | {handle, slot} | move an item |
| 0x19c | {handle} | remove an item |
| 0x19d | {handle, qty} | change a stack count |
| 0x1a2 | {invHandle, container, slot, 0} | inventory to chest |
| 0x1a3 | {chestHandle, container, slot, 0} | chest to inventory |

The item record is the same MsgSingleItemInfo used elsewhere.

### Other [O]
- **0x5cc / 0x5cd MsgBuildingNPCInfo** {i32 npcId, wstr name, wstr text2, wstr unused, i32}. An npcId of -1 clears the list and -2 ends the batch (fills the window); any other id adds a row (FUN_00486340 tests the first field, msg+0x14). The last i32 is kept at record +0x44. 0x5cc = available NPCs, 0x5cd = placed NPCs. (Corrected 2026-10-14: this used to say the last field was the control value, and a list sent that way stayed empty.)
- **0x6f** raw packet, subtype 10, HousingTeleportDataPacket: `i16 10, i32 count, count x {i32 id, i32 nChars, nChars x UTF-16 (no terminator)}`. It fills `_housing_teleport_list` (FUN_005ef850). Subtype 4 is the claim/promotion system, not housing.
- **0x726** {i32 2}: trial-account "Housing" block popup. Do not send it.
- **0xe notice codes** (FUN_0061d530): the housing block is 0x15c-0x1b3, plus 0x1b/0x1c (guild HQ removed/added) and 0xe0. Key codes:

| code | name |
|---|---|
| 0x170 | PurchasedPlot |
| 0x16e | CantPurchasePlot (no money) |
| 0x16d | OnePlotPerAcct |
| 0x173 | SoldPlot |
| 0x1a0 | ConstStarted |
| 0x192 | ConstrCompleted |
| 0x1a8 | BldgPurchased |
| 0x168 | BldgCantHoldMoreFixtures |
| 0x169 | PlaceFixtureItemError |
| 0x178 | RemovedFixtureFromBldg |

  The full list is in `codes0e.txt`.

## 2. Client -> server
All of these go through FUN_004cfb00 / FUN_004cfb50. UI command ids come from FUN_006a0062 and jump table 0x6aa19c (`uicmds3.txt`).

### Plot
| id | payload | sent by |
|---|---|---|
| **0x460** | {i32 objType, i32 objId} | **Inspect** (mouse-over 0x1a0) on a building/plot object; the values are actor +0x3f4 / +0x3f0. 0x82f has the same layout and is sent by Avatar Inspect (0x19f). |
| **0x481** | {plotId} | **buy**. `plot_info_buy_plot` (0x1a8) only shows PlotPurchaseConfirm; `plot_purchase_cost_accept` (0x1a7) sends. |
| 0x47f | {plotId} | sell / relinquish (`plot_relinquish_accept`) |
| 0x5c6 | {wstr targetName} | `/transferplot <name>` then `/transferplotconfirm accept`. Done: the plot (building, fixtures, chests) goes to that player if they are online and own no plot; both get a chat line (verified live 2026-10-14: "Ranger has transferred Wastes Homestead to you.") |

### Construction
| id | payload | sent by |
|---|---|---|
| 0x474 | {buildingOptionId} | building details. Reply: S->C 0x474 preview [I]. |
| **0x479** | {plotId, buildingOptionId} | **start construction** (`plot_construct_selected_building`) |
| 0x473 | {plotId} | view the current construction |
| 0x475 | {constructionId, invItemHandle, resourceRowData, resourceRowIndex} | add material |
| 0x478 | {constructionId} | complete |
| 0x476 | {constructionId} | abandon |
| 0x480 | {buildingId} | tear down (`building_deconstruction_accept`) |

### Upkeep and guild
| id | payload | meaning |
|---|---|---|
| 0x47e | {plotId, copper} | deposit (platinum x1,000,000) |
| 0x47a | {plotId} | toggle guild usable |
| 0x47b | {plotId} | set / relinquish guild HQ |
| 0x47c | {i32, i32, wstr "", bool8 accept} | guild leader's answer |

**Guild headquarters (verified live 2026-10-14, one client: Ranger owns plot 101 and leads Night Watch).** The rules come from the client's own tooltips (VGClient.int `BuildingGuildHeadQuarters`, `BuildingGuildHeadQuartersRemove`). The owner must be in a guild (else notice 26 "You're not in a guild."). The guild leader must be at the plot to confirm (the server's range is 2000 units in the same chunk, a choice). There is one HQ per guild. Once confirmed, the plot's permissions are replaced by one guild permission (all guild members may open the door), and the leader becomes co-owner. Only the leader can clear it, which deletes the permissions again.
1. Admin tab > Make Guild Headquarters > Accept sends 0x47b {plot}.
2. The leader gets S->C 0x47c {i32 plot, i32 guild id, wstr owner, bool8 0}: "Ranger would like to designate their plot as the guild headquarters...".
3. The leader's Accept echoes 0x47c {101, 2, "", 1}.
4. Every online member gets notice 28 "Your guild has a new guild headquarters." and 0x47b {guild id, 1}. The Admin button turns into "Relinquish Guild Headquarters".
5. Relinquish > Accept sends 0x47b again. Members get notice 27 "Your guild no longer has a guild headquarters." and 0x47b {0, 0}.

The plot window also sends 0x47d {0, wstr guild name} for an HQ. Plot info (0x454) fields 25-27 carry the guild-usable flag, the HQ guild id and the HQ flag.

**Guild usable** (0x47a {plot}, owner only) flips a saved flag, answers 0x47a {bool8} and shows notice 383 "This building is now flagged as guild usable. To allow guild members access to this building, you must create a permission with guild options selected." or 382. Unit-tested. The flag grants nothing by itself: access comes from permissions, as the notice says. The toggle button was not found in the plot window during the live test.

**Building Inventory (verified live 2026-10-14).** With the house built, the plot window sends the fixture list (0x45a, 0x45c per fixture with its object id, 0x45b) to anyone with the ViewFixtureList permission (bit 14), and again after a placement or pickup. Seen: "Id 84934658: Storage Chest", "Fixtures: ( 1 of 30 )", "Chests: ( 1 of 3 )". "Move Fixture to me" sends 0x465 {object id}; the server moves the fixture to the player's feet (needs MoveFixture and the player inside that house) and reopens it for the chunk. Verified live. "Pickup Fixture" sends 0x462, already handled. The fixture menu's "Send To Owner" (0x463 {object id}) answers notice 359 "Only trophies can be sent to their owner." (no item here is a trophy), or 358 without the SendTrophiesToOwner permission. Unit-tested.

**Building NPCs (lists verified live 2026-10-14).** Manage NPCs (Building Inventory tab) opens "Building NPCS" and sends 0x5d1 and 0x5d2. The server answers with the NPCs the house may hold (0x5cc; plots.json building `"npcs"`, mobs.json keys; plot 101 lists the camp banker as a placeholder) and the placed ones (0x5cd). Seen: the Avail tab lists "Hollis Grent", and selecting him shows "Banker". **The shipped client cannot send Spawn, Goto or Remove.** In VGUIBuildingNPCs.xml the three buttons' `<Settings name="_spawn_building_npc_button">` (and `_goto_...`, `_remove_...`) lines are commented out, so the actions bound to those sender names never fire. Memory showed the selection was set (manager+0x28 = 1), and FUN_00484a30 would send 0x5ce. The server still handles 0x5ce (an NPC placed where the owner stands inside the house, saved in housing.json `npcs` and loaded with the world), 0x5cf and 0x5d0. Unit-tested only.

**Building preview** (0x474 {building type} from the Buildings tab when the plot is empty) is answered with 0x474 in the 0x453 layout, listing the building's materials from plots.json. Unit-tested. It was not seen live because plot 101 already has a house.

### Fixtures
| id | payload | sent by |
|---|---|---|
| **0x461** | {itemHandle} | FUN_00480b30, called from the bag drag-and-drop handler (around 0x69693f) when an item from `_inventory` or `_character_window` is dropped on the 3D world and FUN_0047b7b0 says the point under the cursor is in a house; otherwise the drop asks to delete the item. The UI command `mo_inventory_place_fixture` (0x149) also calls it, but no menu builder adds that option. |
| **0x46d** | MsgSpawnFixture (ctor FUN_00475c50, registration 0x473be0): {i32 itemHandle, i32 buildingId, f32 x, f32 y, f32 z, i32 yaw, i32 pitch, i32 roll} | a world click while the preview is active (0x41944d -> FUN_0047da50). The pose is read from the ghost actor. |
| **0x464** | same class, as a change: {fixtureId, 0, dx, dy, dz, dYaw, dPitch, dRoll} | the 12 `fixture_move_*` buttons (all UI 0x1c5). Each press is +-10.0 units or +-256 rotator units. |
| 0x462 | {id} | pick up (mouse-over menu or the fixture-list button) |
| 0x463 | {id} | send to owner |
| 0x465 | {fixtureId} | move tome/fixture to me |

The mouse-over "Move" option only opens `_fixture_movement_popup`.

### Chest
| id | payload | meaning |
|---|---|---|
| **0x151** | {chestId} | **open** (only for object type 4) |
| 0x152 | {chestId} | close |
| 0x155 | {chestId, invItemHandle, count, destRow} | deposit (drag-drop) |
| 0x153 | {chestId, chestItemHandle, count, destRow} | move within the chest: done (move, swap with the item there, or split `count` off onto a free slot); the server redraws the chest with 0x19f + 0x1a1 items + 0x1a0. Verified live 2026-10-14 (`!chest <n> move <handle> <count> <slot>`) |
| 0x157 | {chestId, chestItemHandle, count, destContainer, destSlot} | withdraw |
| 0x466 | {chestId} | Manage Chest |
| 0x467 | {chestId, permType 0..2, permEntryId, guildRank, u32 0, bool allPlayers, bool allGuild, wstr ""} | save a chest permission |

### Permissions
| id | payload | meaning |
|---|---|---|
| 0x470 | MsgBuildingPermission {plotId, permId, wstr name, guildRank, u32 flags, bool allPlayers, bool allGuild} | create (field fill partly [I]) |
| 0x472 | same | edit |
| 0x471 | {plotId, permId} | delete |
| 0x46f | {wstr playerName, permId, 0} | add a friend |
| 0x46e | {permId, friendRow} | remove a friend |

### Building NPCs and teleport
- Building NPCs:
  - 0x5d1 / 0x5d2 (no payload): window opened.
  - 0x5ce {i32 npcTemplate, f32 heading, f32 x, y, z}: spawn at the player's position.
  - 0x5cf {placedId}: remove. 0x5d0 {placedId}: go to.
- Teleport: `housing_teleport_list_accept` (0x26b, FUN_006a7e20) sends raw zone msg **0x6f** with the body `{i16 11, i32 teleportId}` (HousingTeleportDataResponsePacket).

### Dead or client-only
- Never sent: 0x45f (MsgBuildingMoverClicked), 0x7ec, 0x7ed.
- No-ops: `select_housing_plot`, "Construction...", "Change Permission".
- `/beatchest` is a local animation test.

## 3. World representation and placement preview
- **Plots, houses, fixtures and chests are Unreal actors, not pawns.** No EntityTypes bit is involved [O].
- When a click hits no pawn, FUN_00417da0 calls FUN_00483c90(actor, 1). That picks the mouse-over menu from **m_BuildingType** (FUN_004839b0, option table 0x13e5f38) [O]:

| m_BuildingType | menu |
|---|---|
| 1, 2, 8 | Inspect (building or plot) |
| 3 | fixture: Pick Up / Move / Send To Owner |
| 4 | chest: Pick Up / Move / Open / Manage Chest |
| 7 | hover text only (sign) |
| 0 | ignored |

- Classes: `Engine.CompoundObject : Actor` and `Engine.PlayerPlacedObject : CompoundObject` (IsA checks FUN_00475980 / FUN_004759e0). Doors are Engine.Mover.
- Replicated properties after Actor's 0..52 (FUN_00806580 / FUN_00806700) [O]:

| index | field | offset |
|---|---|---|
| 53 | m_PrefabNameTag (str) | +0x3d4 |
| 54 | m_ParentUniqueID (int) | +0x3d0 |
| 55 | m_ObjectUniqueId (int) | +0x404 |
| 56 | m_MouseOverDisplay (str) | +0x3f8 |
| 57 | m_BuildingType (int) | +0x3f4 |
| 58 | m_BuildingUniqueId (int) | +0x3f0 |

- When the actor arrives (FUN_00816ff0), the client builds the prefab named in m_PrefabNameTag. If m_ParentUniqueID != 0 it links the object under that parent [O].
- Server plan [I, strong]: open an actor channel (ue2net.actor_open_bunch) with class Engine.PlayerPlacedObject, a location and rotation, and fields 53..58. Close the channel to remove the object. This is untested: class defaults (bStatic, bNoDelete, RemoteRole) could block it.
- **Plot-for-sale markers** are presumably the same: a PlayerPlacedObject with type 1, the plot id in m_BuildingUniqueId and a "For Sale" m_MouseOverDisplay [I]. There is no plot or deed merchant UI: you buy by inspecting the plot object.
- **In-house check** (FUN_004771d0): the zone at the player's location must have +0xa8 = a PlayerPlacedObject and zone byte +0x388 == 3. It returns that object's m_BuildingUniqueId. The interior zone therefore has to come from the loaded house prefab [I].
- **Prefabs**: `bin/compoundobjectMD.tab` (type 6 rows are prefab roots) and `Assets/Archives/binaryprefabs.sgo`. Housing-city sets:
  - `Ra6001_P1_C1_Grid_PHcity01_Home001/004`, `HomeShop002/003`, `CraftingBarn001`, `Inn001`, `Temple001`, ... named `*root001_lvl10_ver1`, each with a `mi001` interior.
  - `Ra6021_..._Home001-005`.
  - `Ra6060_..._Home001-004`.

  Candidate small house: `Ra6001_P1_C1_Grid_PHcity01_Home001root001_lvl10_ver1` with type 2 [I]. Which prefabs are fixtures and chests was not identified.
- **Placement preview** [O]:
  1. The client sends 0x461.
  2. The server replies 0x459 {prefabName, f32}.
  3. FUN_0047d250 / FUN_00b80900 trace from the camera through the cursor (FUN_00b81c70) and spawn a **local ghost CompoundObject** of that prefab at the hit point (attached to the house zone if the zone type is 3). The cursor mode becomes "Floater1".
  4. A left click reads the ghost's Location (+0x1cc) and Rotation (+0x1d8), destroys it and sends 0x46d. With no item pending, the click just cancels.
  5. The server then spawns the real type 3/4 actor [I].

  Whether the ghost follows the mouse every frame is unconfirmed. Later nudges (0x464) have no ghost: the server moves the actor and replicates the new Location/Rotation.
- **Travel journal**: category -4 "Player Housing" is built in (0x5d88b4). Send 0x382 entries with category -4 for the house.

## 4. Minimal sequences
Message order is [O]. Which replies the server sends is [I].

**A. Buy a plot**
1. The server has spawned a PlayerPlacedObject (type 1, m_BuildingUniqueId = plotId) at the spot.
2. The player clicks it and picks Inspect. C->S **0x460 {1, plotId}**.
3. S->C **0x454** {plotId, cost, IsMine=0, forSale=1, options[0] = {typeId 1, b, c, maxFix 20, maxChest 2, "Small House"}, canStartConstruction=0, ...}, then **0x458**. The info window opens.
4. Buy, then Accept. C->S **0x481 {plotId}**.
5. Server: check the coin (else 0xe 0x16e) and one plot per account (else 0x16d). Send S->C **0xe {0x170}**, then 0x454 again with IsMine=1, forSale=0, ownerName, canStartConstruction=1, then 0x458.

**B. Place a small house.** The client has no instant-placement path; houses go through construction.
1. On the Buildings tab the player selects the option. C->S **0x474 {typeId}**. S->C 0x474 (materials preview) [I].
2. Construct. C->S **0x479 {plotId, typeId}**.
3. S->C **0xe {0x1a0}**, **0x479 {true}**, **0x453** {siteId, 0, "Small House", pct, materials...}.
4. A first version can skip materials: the client sends 0x478 {siteId} on Complete. Or, server-side, immediately send:
   - **0xe {0x192}**
   - **0x477** (closes the construction window)
   - **0x479 {false}**
   - Open an actor channel: PlayerPlacedObject, m_PrefabNameTag = the house prefab, m_BuildingType = 2, m_BuildingUniqueId = buildingId, m_MouseOverDisplay = owner's house. Optionally remove or re-flag the plot marker.
   - **0x455** {buildingId, ..., isMine=1, maxFixtures, maxChests}.
5. (Material path: C->S 0x475 per material, answered with 0x453 updates, then 0x478.)

**C. Open its storage**
1. The chest exists as a PlayerPlacedObject with m_BuildingType = 4, m_BuildingUniqueId = chestId, and m_ParentUniqueID = the house (spawned with the house, or placed through 0x461 -> 0x459 -> 0x46d).
2. The player clicks it and picks Open. C->S **0x151 {chestId}**.
3. S->C **0x199 {chestId, capacity}**, **0x19f** (clear), one **0x1a1/0x19e** per item, then **0x1a0**.
4. Deposit: C->S 0x155, answered with 0x1a2 or 0x19e [I].
5. Withdraw: C->S 0x157, answered with 0x1a3 or 0x19c [I].
6. Close: C->S 0x152, answered with S->C 0x19a.
7. Errors are 0xe codes 0x1ad-0x1b3 (NoPermissionToUseChest, ChestFull, ...).

## Open questions
- Whether the client actually spawns a replicated PlayerPlacedObject from an actor channel. This is the biggest risk: test it first with one actor and a known prefab.
- Which prefab names are fixtures and chests, and how items map to fixture prefabs. This is server data; log it in docs/CONTENT_EDITOR.md.
- Plot positions, costs, upkeep and building-type tables are all server-only data.
- The two bools in 0x45c/0x45d; field b of the plot options; qtyA vs qtyB in 0x453.

## World representation (detail)

[O] = read in code/data, [I] = inferred. Addresses are VGClient.exe VAs.

### 1. Houses, fixtures and chests are replicated Unreal actors, not pawns

- There is no EntityTypes bit for plots, buildings, fixtures or chests. The pawn interact code FUN_00417da0 only tests pawn bits (+0xaf8). When the click hits no pawn, it falls through to `FUN_00b81620(0)` (a non-pawn trace hit) and then `FUN_00483c90(actor, 1)` on the housing manager `DAT_014639d4` (call at 0x418031) [O].
- Class hierarchy (from the StaticClass name strings) [O]:
  - `Engine.CompoundObject : Actor` (IsA helper FUN_00475980, class global DAT_01469c5c)
  - `Engine.PlayerPlacedObject : CompoundObject` (IsA helper FUN_004759e0, DAT_01469c98)
  - `Engine.Mover` (IsA FUN_00475920) is used for doors.
- Replicated NetFields (computed with server/netcache.py over Core/Engine/SGOUnrealAbstractionLayer; RepIndex shown) [O]:

| RepIdx | class | property | obj offset | meaning |
|---|---|---|---|---|
| 0..52 | Actor | Location, Rotation, ... DrawScale(34), StaticMesh(36), ... | | standard |
| 53 | CompoundObject | StrProperty `m_PrefabNameTag` | +0x3d4 (FString) | prefab to build (binaryprefabs.sgo / compoundobjectMD.tab name) |
| 54 | CompoundObject | IntProperty `m_ParentUniqueID` | +0x3d0 | 0 = standalone; otherwise link into a parent compound object [I: fixture → its building] |
| 55 | PlayerPlacedObject | IntProperty `m_ObjectUniqueId` | +0x404 (copied to +0x3cc) | this object's id |
| 56 | PlayerPlacedObject | StrProperty `m_MouseOverDisplay` | +0x3f8 | hover text |
| 57 | PlayerPlacedObject | IntProperty `m_BuildingType` | +0x3f4 | drives the click menu (below) |
| 58 | PlayerPlacedObject | IntProperty `m_BuildingUniqueId` | +0x3f0 | building/plot id; this is the id the housing UI and C->S messages carry |

  Offsets are confirmed by GetOptimizedRepList: ACompoundObject FUN_00806580 and APlayerPlacedObject FUN_00806700 (0x8067a7 m_BuildingUniqueId@+0x3f0, 0x8067fb m_BuildingType@+0x3f4, +0x3f8 m_MouseOverDisplay, +0x404 m_ObjectUniqueId). Getters: FUN_00816c90 returns +0x3f0, FUN_00816ca0 returns +0x3f4 [O].
- Client setup after spawn (FUN_00816ff0, a PlayerPlacedObject post-net/begin-play routine) [O]:
  - Tag = FName(m_PrefabNameTag)
  - +0x3cc = m_ObjectUniqueId
  - the object is added to a level list (+0x1148)
  - if m_ParentUniqueID == 0 it builds itself (FUN_008e6e80); otherwise it links to its parent (FUN_00811be0, else FUN_00816f90)
  - then it applies its position and rotation (FUN_00814150 = AdjustPositionAndRotation)

  ACompoundObject PostNetReceive FUN_00811110 reloads the prefab when m_PrefabNameTag changes [O].
- So the server spawns houses, fixtures and chests through an actor channel: `ue2net.actor_open_bunch` with class index `Engine.PlayerPlacedObject`, location and rotation, plus props 53..58 [I, strong; same mechanism as remote pawns]. Removing one = close the actor channel. Untested risks: class defaults (bStatic/bNoDelete/RemoteRole) and whether bNetInitialRotation applies.

### 2. m_BuildingType → click menu (FUN_004839b0, menu `_building_options_menu`) [O]

On interact (FUN_00483c90): the clicked actor's Owner (+0x78) must be a CompoundObject. FUN_00477170 resolves it to the PlayerPlacedObject (itself, or its +0xa8 parent). Types 0 and 7 are ignored. The manager stores {+0x3f0 id, +0x3f4 type} and then builds the menu. Each entry is added by FUN_00483800(optionId, clearFirst) from the table at 0x13e5f38 ({optionId, uiCmd, label, event}):

| m_BuildingType | menu entries (UI cmd) | meaning [I] |
|---|---|---|
| 1, 2, 8 | Inspect `mo_building_options_inspect` (0x1a0) | plot / building / (8 = other building kind, e.g. a construction site) |
| 3 | Pick Up `mo_fixture_option_pickup` (0x1a1), Move `mo_fixture_option_move` (0x1a2), Send To Owner `mo_fixture_option_send_to_owner` (0x1a5) | fixture (furniture) |
| 4 | Pick Up, Move, Open `mo_chest_open` (0x155), Manage Chest `mo_chest_manage` (0x1a4) | house chest |
| 7 | no menu. Hover only: FUN_008f4530 returns 7 and shows m_MouseOverDisplay | sign / label object |
| 0 | ignored | plain |

Other table entries that no type uses: Construction... `mo_building_construction_open` (0x156), Avatar Inspect (0x19f) and Change Permission (0x1a3).

Hover (FUN_008f45c0, every 0.1 s): it traces 5000 units from the camera through the cursor. If the hit actor's Owner is a PlayerPlacedObject of type 7 or 3, it highlights it (ambient 0x32,0x32,0x32) and uses m_MouseOverDisplay as the hover text (FUN_0040c340) [O]. Type 4 is not highlighted.

A dead path: FUN_0047e600 sends **0x45f** {id +0x3f0, type +0x3f4, bool mover+0x6e0} ("MsgBuildingMoverClicked"). It runs only when FUN_00483c90 gets param 0, and the only caller passes 1 [O].

### 3. "Inside a house" test [O/I]

FUN_004771d0(loc) and FUN_00b7e750 use FUN_00b75d40(loc) → zone (FUN_007f08d0, which walks up the zone's outer chain until it finds one whose byte +0x388 is 3, stopping at type 6). The zone's +0xa8 must be a PlayerPlacedObject; the test returns its m_BuildingUniqueId (0 = not in a house). The house interior zone comes from the building prefab (zones and portals inside the compound object). So fixture placement only works if the building actor loaded a prefab with an interior zone, and that zone's +0xa8 links back to the PlayerPlacedObject [I]. FUN_00b80900 also treats zone byte +0x388 == 3 as a house-interior zone [O].

**Runtime check (2026-10-14, `tools/winbreak.py`).** Dragging the Oak Table onto the cottage floor with Ranger inside: FUN_004771d0 ran once; FUN_00b75d40 returned a zone whose type byte +0x388 is **1** and whose +0xa8 is 0, and FUN_007f08d0 (the walk up to a type-3 zone) returned 0, so the client took the drop as "delete". The zone under the cottage is the level's own zone: the cottage prefab brings walls but no house-interior zone. Zone types are set by FUN_00810f30: a table lookup by the zone's name (+0x38c; table entry byte +0x10 = type) when that data is loaded, else FUN_00810660, which makes a zone type 3 when its count at +0x3ac is above 0 (a parent of a type-3 zone becomes 5, others 2). FUN_00810660 did not run at all when the house was loaded again after /camp. So drag placement needs a house prefab whose compound object carries an interior zone (a zone name the table knows as type 3, or one with +0x3ac entries); which prefab or zone data the original houses used is still unknown. Right-click placement (server-side) keeps working. The name-keyed table is probably `bin/compoundobjectMD.tab` (columns Name, FileTime, FileSize, HashIndex, Radius, **Type**, AG_Type): its Type column uses exactly the zone types (2 exterior pieces, 3 rooms such as `Ra21_P1_C2_Grid_Home02_room004_ver01`, 5 a part holding rooms such as `..._PHcity01_Home004mi001_lvl10_ver1`, 6 a root such as `..._Home004root001_lvl10_ver1`). The cottage's own parts are in it (root 6, mi 5), while the zone found under the dropped table was type 1, a type the table never uses: the point lookup (FUN_00b75d40) does not see the house's compound-object zones at all, so they are probably not registered for location queries when a PlayerPlacedObject spawns the prefab. Next step: break in FUN_00b75d40 near a house that the level itself contains, if one exists, to compare.

### 4. Fixture placement preview (client-side ghost) [O]

1. Inventory item menu `mo_inventory_place_fixture` (UI 0x149) → FUN_0068cc..., then **FUN_00480b30(itemHandle)**:
   - It requires the player's location to be inside a house; otherwise it prints "You can only place items when in your house."
   - It stores the handle at mgr+8 and sends **0x461 MsgSingleInt {itemHandle}**.
2. Server → **0x459 MsgStringAndFloat {wstr prefabName, f32 f}** → FUN_0047d250:
   - FUN_00b81c70 traces from the camera through the mouse cursor (2000/20000/100000/500000 units) to a world point.
   - **FUN_00b80900(prefab, point, f)** spawns a *local* CompoundObject ghost (world-singleton+0x14, DAT_018bde2c=1). It attaches to the house zone through FUN_00b80730 when zone type is 3, otherwise FUN_00b7ee00. `f` is passed through to the spawn as its last argument [I: draw scale].
3. Left click while a ghost exists (FUN_00419423: FUN_00b70840 checks +0x14 != 0). When connected (FUN_004093c0), it jumps to **FUN_0047da50**:
   - FUN_00b7e750 reads the ghost location (+0x1cc), rotation (+0x1d8), prefab name and the buildingId of the zone it is in. The ghost is destroyed (FUN_00b78290).
   - It sends **0x46d MsgSpawnFixture {i32 itemHandle, i32 buildingId, f32 x, f32 y, f32 z, i32 pitch, i32 yaw, i32 roll}** and resets mgr+8 = -1.
   - Offline (or mgr+8 == -1), FUN_00b80a60 makes a permanent local copy instead.
   - I did not confirm a per-frame "follow the mouse" update for the ghost.
4. The server then spawns the real PlayerPlacedObject (type 3 or 4, m_ParentUniqueID/m_BuildingUniqueId = house) at that location [I].

MsgSpawnFixture: RTTI 0x13e5ff8, vtable 0x1073fb0, ctor FUN_00475c50, fields FUN_00473be0 = i32, i32, f32, f32, f32, i32, i32, i32 [O].

### 5. Moving a placed fixture (no ghost; server-authoritative nudges) [O]

- `mo_fixture_option_move` opens `_fixture_movement_popup` (0x473e80).
- Its buttons `fixture_move_{pos,neg}_{x,y,z,yaw,pitch,roll}` (UI 0x1f6..0x201, handler around 0x47b2d0; FUN_00476220 is the same thing by index 0..11) each send **0x464 MsgSpawnFixture {i32 fixtureId (mgr+0), i32 0, f32 dx, f32 dy, f32 dz, i32 r0, i32 r1, i32 r2}** as a *delta*:
  - translation steps are ±10.0 (constants 0x1074038/0x107403c)
  - rotation steps are ±0x100 Unreal rotation units
- The client does not move anything locally. The server must apply the delta and re-replicate Location/Rotation on the fixture's actor channel [I].

### 6. Assets: player-housing prefabs (m_PrefabNameTag candidates) [O names, I usage]

bin/compoundobjectMD.tab (Name, ..., Type) lists prefab roots. Type 6 = prefab roots. Player-housing city sets (lvl10 builds):
- Ra6001_P1_C1_Grid_PHcity01_* (Thestra / human style):
  - Home001root001_lvl10_ver1, Home004root001_lvl10_ver1
  - HomeShop002root001..., HomeShop003root001...
  - CraftingBarn001root001..., GuardTower001root001..., Inn001root001..., Temple001root001...
  - SmallGuild001_*, LargeGuild001_Root01
  - each one has a matching `...mi001_lvl10_ver1` (master interior)
- Ra6021_P1_C2_Grid_PHcity01_Home001..005root001_lvl10_ver1, HomeShop003, Small/LargeGuild001 (Kojan)
- Ra6060_P1_C4_Grid_PHcity01_Home001..004root001_lvl10_ver1(_ver2), HomeShop003, SmGH001/LgGH001 (Qalia)
- Older per-style sets: Ra6001_P1_C1_Grid_House01_Root00N_lvl10, HouseShop02/03, CraftingBarn01, GuardTower01, Inn01, Monastery01; Ra6060 TanvuHouse01..03, TanvuHouseShop02/03, TanvuInn01, ...
- Prefab data is in Assets/Archives/binaryprefabs.sgo. Meshes are in Assets/Meshes/Ra6001_P1_C1_Grid_House01_mesh.usx, Ra6001_P1_C1_Grid_HouseShop02/03_mesh.usx and Ra6060_P1_C4_Grid_TanvuHouse0N_mesh.usx.
- Chest meshes live in Ra*_Chests_* packages; which prefab names are housing fixtures was not determined.

A small house = PlayerPlacedObject with m_PrefabNameTag "Ra6001_P1_C1_Grid_PHcity01_Home001root001_lvl10_ver1", m_BuildingType 2 [I], m_BuildingUniqueId = plot/building id, at the plot location.

### 7. Misc

- 0x726 {i32 feature}: feature 2 = Housing shows "Free Members are unable to access this game feature." (FUN_005e6580). Never send it for full accounts [O].
- Travel journal category **-4 "Player Housing"** is built in (created at 0x5d88b4). Send 0x382 travel-journal entries with categoryId -4 for the house location (see DEATH.md) [O/I].
- 0x6f subtype 10 = HousingTeleportDataPacket (list window `_housing_teleport_list_window`, TeleportData 0x14 bytes: +0 i32 id, +8 string). The reply is HousingTeleportDataResponsePacket (type 11, ctor 0x685cc0, sent from FUN_006a7e20 via `housing_teleport_list_accept` 0x275 / `select_housing_plot` 0x269). Subtype 4 of 0x6f is the claim/promotional packet family, not housing [O].
