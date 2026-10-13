# Housing: server -> client messages (VGClient.exe, static analysis)

[O] = read in code. [I] = inferred. Offsets are SGO message-object offsets (field order on the wire = registration order, which is NOT offset order).
Tools: `cfo.py <regfn>` prints type@offset per registration call; `hreg.py <handler>` finds ctor/registration; `codes0e.py` dumps the 0xe notice table.
Housing manager object = `this` in FUN_00483d60's handlers ("mgr"). Ids 0x830, 0x831, 0x835, 0x836 return 1 in FUN_00483d60 with no handler (accepted, ignored) [O].

## Plot / building / construction (sub-dispatcher FUN_00483d60)

### 0x454 MsgPlotInfoFull (handler FUN_0047f590, reg FUN_00473770) — store plot data, does NOT open the window
Wire order (type, msg offset -> mgr field -> meaning):
| # | type | off | mgr | meaning |
|---|---|---|---|---|
| 1 | i32 | 0x14 | +0x18 | unknown id (not displayed) [I: plot instance id] |
| 2 | i32 | 0x18 | +0x1c | plot id "PID" (Debug Info line) |
| 3 | wstr | 0x38 | - | not copied by client (send plot name/"") |
| 4 | wstr | 0x54 | +0x20 | owner name -> strPlotOwner |
| 5 | wstr | 0x70 | +0x3c | stored, not displayed [I] |
| 6 | i32 | 0x1c | +0x58 | plot cost (copper) -> strPlotCost (coin text) |
| 7 | bool8 | 0x21 | +0x5d | bPlotIsMine |
| 8 | bool8 | 0x20 | +0x5c | for sale: 1 -> bPlotForSale=1, strPlotOwner=""; 0 -> owned (owner/date/upkeep shown) |
| 9 | i32 | 0x98 | +0x60 | upkeep bank balance (copper) -> strUpkeepBankBalance (red if <0) |
| 10 | i32 | 0x9c | +0x64 | upkeep cost (copper) -> strUpkeepCost |
| 11 | i32 | 0xa0 | +0x68 | last upkeep deduction (time_t) -> strUpkeepLastDeduction |
| 12 | i32 | 0xa4 | +0x6c | next upkeep deduction (time_t) -> strUpkeepNextDeduction |
| 13 | u32 | 0xa8 | +0x70 | purchase date (time_t) -> strPlotPurchaseDate |
| 14-16 | f32 x3 | 0x8c/90/94 | +0x8c.. | plot location x,y,z (debug text only) |
| 17 | i32 | 0xac | +0x74 | missed upkeep payments -> strMissedPayments; >0 sets bPlotMissedUpkeepPayment |
| 18 | bool8 | 0x22 | +0x78 | bHasFullPerm |
| 19 | bool8 | 0x23 | +0x79 | bPlotHasConstruction |
| 20 | bool8 | 0x24 | +0x7b | bPlotCanViewPermissions |
| 21 | bool8 | 0x25 | +0x7a | bPlotCanEditPermissions |
| 22 | bool8 | 0x26 | +0x7c | bPlotCanViewUpkeepBank |
| 23 | bool8 | 0x27 | +0x7d | bPlotCanPayUpkeep |
| 24 | bool8 | 0x29 | +0x7e | may start construction: bPlotStartConstruction = this && !hasConstruction |
| 25 | bool8 | 0x28 | +0x7f | bBuildingGuildUsable |
| 26 | i32 | 0x2c | +0x84 | guild id of building (compared with player guild DAT_01463950+0x1ec for bCanChangeGuildUsable) |
| 27 | bool8 | 0x30 | +0x80 | bPlotIsHQ |
| 28 | bool8 | 0x31 | - | registered but never read; the client instead copies msg+0x34 (never deserialized) into mgr+0x88 (HQ guild id). Client bug; send 0 [O] |
| 29.. | 10 x {i32 a, i32 b, i32 c, i32 d, i32 e, wstr name} | a@0xb0+4i, b@0xd8, c@0x100, d@0x128, e@0x150, name@0x178+0x1c*i | +0xb8+0x34*i | **building options for this plot** (PlotOptionList). a = building type id (row id; also shown as strConstructionBuildingType); b = row data2 (unknown, stored in row +0x20); c = unused; d = strConstructionBuildingNumFixtures; e = strConstructionBuildingNumChests; name = strConstructionBuildingName and list text. Rows with empty name are skipped (FUN_0047b7d0, FUN_0047e030) |
Side effects: sets bPlotHasBuilding=0, bCanChangeGuildUsable, bCanChangeGuildHQStatus (owner && in a guild && !HQ, or HQ && same guild && guild rank==10), bPlotStartConstruction [O].

### 0x455 MsgBuildingInfoFull (FUN_0047fc00, reg FUN_00473b00) — send after 0x454 when the plot has a house
| # | type | off | mgr | meaning |
|---|---|---|---|---|
| 1 | i32 | 0x14 | +0x23dc | building id "BID" (debug) |
| 2 | wstr | 0x1c | - | not read [I: building name] |
| 3 | wstr | 0x38 | +0x23e0 | owner name -> "This house belongs to %s." |
| 4 | wstr | 0x54 | +0x2400 | stored, never read |
| 5 | bool8 | 0x18 | +0x23fc | is mine -> "This is your house." + BuildingTearDownButton=1 |
| 6 | bool8 | 0x1a | +0x23fd | bBuildingViewFixtureList |
| 7 | bool8 | 0x1b | +0x23fe | bCanSendTrophiesToOwner |
| 8 | bool8 | 0x19 | - | not read |
| 9 | u32 | 0x7c | +0x2424 | build date (time_t) -> "This house was built on %s" (BuildingBuildDate) |
| 10-12 | f32 x3 | 0x70/74/78 | +0x2428.. | location (debug) |
| 13 | i32 | 0x80 | +0x241c | max fixtures -> FixtureMaxText |
| 14 | i32 | 0x84 | +0x2420 | max chests -> ChestMaxText |
Sets bPlotHasBuilding=1, bPlotStartConstruction=0, clears the fixture list [O].

### 0x458 (no payload) FUN_00480c90 — **show the plot information window**
Sets bPlotInformation=1 and fills all str*/b* UI vars above from mgr, fills PlotOptionList, FixtureCount/ChestCount, BuildingOwnerText, BuildingDebugInfo, BuildingBuildDate. Window `_plot_information` (`_plot_upkeep_bank_balance` coloured) [O]. Order: 0x454 -> (0x455) -> 0x458.

### 0x483 MsgSingleInt {i32 copper} FUN_0047d4f0 — update strUpkeepBankBalance (red if negative) [O].
### 0x479 MsgSingleBool {hasConstruction} FUN_00475d80 — mgr+0x79, bPlotHasConstruction, recompute bPlotStartConstruction [O].
### 0x47a MsgSingleBool {guildUsable} FUN_0047b130 — bBuildingGuildUsable; mgr+0x84 = player guild if set [O].
### 0x47b MsgIntAndBool {i32 hqGuildId, bool8 isHQ} FUN_00475ec0 — mgr+0x88, bPlotIsHQ [O].
### 0x47c MsgBuildingGuildHeadquartersResponse (FUN_0047d110, reg FUN_004735b0): i32 a(0x14), i32 b(0x18), wstr ownerName(0x1c), bool8(0x38, unused)
Opens `_building_guild_leader_headquarters_confirm` (BuildingGuildLeaderHeadquartersConfirm=1), window data1=b, data2=a, strPlotOwnerNameForHeadQuaters=ownerName. [I] asks a guild leader to accept a member's plot as guild HQ; a/b are ids echoed back by the confirm button.
### 0x47d MsgBuildingGuildInfo {i32 unused, wstr guildHQName} FUN_0047f4a0 — strGuildHQName [O].

### Construction
0x453 MsgConstructionInfoFull (FUN_00482ad0, reg FUN_004736c0) and 0x474 (FUN_0047ed10, same class):
| # | type | off | meaning |
|---|---|---|---|
| 1 | i32 | 0x14 | construction/site id -> window data of `_building_construction_wnd` (mgr+0x2444) |
| 2 | i32 | 0x18 | mgr+0x2448, never read |
| 3 | wstr | 0x1c | project (building) name: "Current Project: %s" / SelectedConstructionProjectName |
| 4 | i32 | 0x38 | percent complete: "Project Status:  %d %% complete." |
| 5.. | 20 x {i32 resId@0x3c+4i, wstr resName@0x8c+0x1c*i, f32 qtyA@0x2bc+4i, f32 qtyB@0x30c+4i} | materials. Rows with resId<=0 skipped (0x453). 0x474 lists rows with (int)qtyA>0 as "%s ( %d )" |
- 0x453: stores into mgr+0x246c (20 x 0x2c), bPlotHasConstruction=1, shows BuildingConstruction window and BuildingMaterialItemList (row FUN_00672d20 keeps both floats) [O]. [I] qtyA = still needed, qtyB = required/total.
- 0x474: does not store; fills BuildingConstructionResourceList, BuildingConstructionResources=1, SelectedConstructionProjectName (preview of the resources a chosen building option needs) [O/I].
- 0x476, 0x477 (no payload): BuildingConstruction=0 (close construction window) [O]. [I] one is "completed", one "abandoned".

### Permissions (building: 10 slots at mgr+0x2bc, 0x350 each; chest: 3 slots at mgr+0x2818)
0x456 MsgBuildingPermission (FUN_0047fe60, reg FUN_00473a80) — add to first empty slot, no refresh; 0x470 same + refresh list (FUN_00479b60):
| # | type | off | slot | meaning |
|---|---|---|---|---|
| 1 | i32 | 0x14 | - | unused [I: building id] |
| 2 | i32 | 0x18 | +4 | permission id (0 = empty slot, so never send 0) |
| 3 | wstr | 0x28 | +8 | permission name (BuildingPermissionName) |
| 4 | i32 | 0x1c | +0x24 | guild rank id (selects row in `_guild_rank_select_list`; rank ids from mgr+0x27ec) |
| 5 | u32 | 0x20 | +0x28 | flag bits (below) |
| 6 | bool8 | 0x24 | +0x2c | bPermAllPlayers |
| 7 | bool8 | 0x25 | +0x2d | bPermAllGuildMembers |
Flag bits (FUN_0047a180, `_permission_edit_wnd`) [O]: bit0 OpenDoor, bit1 MoveFixture, bit2 PlaceFixture, bit3 PickupFixture, bit4 AllowModify, bit5 PayUpkeep, bit6 ManageConstruction, bit12 AllowView, bit13 ViewUpkeepBank, bit14 ViewFixtureList, bit15 SendTrophiesToOwner, bit31 NoAccess.
0x471 MsgSingleInt {permId}: delete building permission slot + refresh [O].
0x457 MsgBuildingPermissionFriend {i32 permId, i32 friendId, wstr name}: add friend (max 20 per permission, 0x28 each; friendId 0 = empty) to building permission, no refresh. 0x46f: same, searches building then chest permissions, refreshes. 0x46a: same for chest permissions only, no refresh. 0x46e {permId, friendId, (wstr unused)}: remove friend from building or chest permission [O].
0x469 MsgChestPermission (FUN_00480180, reg FUN_00473a00): i32 chestId(0x14 -> mgr+0x2814), i32 slotIndex 0..2 (0x18), i32 permId(0x1c), i32 guildRank(0x20), u32 flags(0x24, not shown in UI), bool8 allPlayers(0x28 -> bChestPermAllPlayers), bool8 allGuild(0x29 -> bChestPermAllGuildMembers), wstr name. Out-of-range slot is ignored [O].
0x468 (no payload) FUN_00480280: reset chest permissions (chestId=-1, clear 3 slots) [O].
0x46b MsgChestInfo (FUN_0047d330, reg FUN_0047c520): i32 chestId, wstr displayName (-> ChestDisplayName), wstr itemName (-> ChestItemName). Opens `_manage_chest` (ManageChest=1, ChangeChestPermission=0), window data = chestId [O].

### Fixtures
0x45a (no payload): clear BuildingFixtureList and free records. 0x45c MsgBuildingFixtureInfo {i32 fixtureId, bool8 f1, bool8 f2, wstr name} (reg FUN_00473630): add record silently; 0x45d: add + add row now; 0x45b (no payload): rebuild list + FixtureCountText/ChestCountText; 0x45e MsgSingleInt {fixtureId}: remove one and update counts [O]. f1/f2 are copied to the row (+0x20/+0x21); meaning not found [I: e.g. is-trophy / is-chest].
0x459 MsgStringAndFloat {wstr className, f32 v} FUN_0047d250 -> FUN_00b80900: **spawns the client-side placement preview actor**. It ray-traces from camera/cursor into the world (FUN_00b81c70) and spawns an actor of class `className` there (FUN_00b7ee00, f32 passed as last arg [I: scale]); keeps it at manager+0x14 and enters cursor mode "Floater1" [O/I].

### Building NPCs (FUN_004864e0)
0x5cc / 0x5cd MsgBuildingNPCInfo (reg FUN_00484190): i32 npcId(0x14), wstr name(0x18), wstr text2(0x34), wstr (0x50, unused), i32 ctl(0x6c). ctl -1 = clear list, -2 = end of batch -> fill list UI, else add entry (value kept at +0x44). 0x5cc = BuildingNPCList (NPCs you may spawn), 0x5cd = PlacedBuildingNPCList (`_building_npc_window`) [O].

## House chest (sub-dispatcher FUN_004733d0; generic chest manager)
| id | payload | handler | effect |
|---|---|---|---|
| 0x199 | MsgTwoInts {i32 chestId(+0x34), i32 capacity(+0x30)} | FUN_00472e60 | "You begin to use the Chest."; opens `_chest`, Chest=1, ChestDisplayName="House Chest" (hard-coded), ChestCapacity=capacity, builds slots [O] |
| 0x19a | none | FUN_004724c0 | "You stop using the Chest."; clears list; Chest=0 |
| 0x19b | MsgTwoInts {i32 itemHandle, i32 slot} | FUN_004721f0 | move existing chest item to slot |
| 0x19c | MsgSingleInt {itemHandle} | FUN_00472ac0 | remove item, "<name> was removed from your chest." |
| 0x19d | MsgTwoInts {itemHandle, qty} | FUN_00471e90 | update stack count |
| 0x19e | item record (MsgSingleItemInfo, FUN_00516610) | FUN_004732b0 | add item to chest and draw at its slot (item+0x1bc) |
| 0x19f | none | FUN_004722e0 | clear chest item list |
| 0x1a0 | none | FUN_00471a50 | refresh ChestInventoryList icons |
| 0x1a1 | item record | FUN_00473280 | add item silently |
| 0x1a2 | MsgFourInts {invItemHandle, container(+0x654), slot(+0x1bc), unused} | FUN_00473300 | move an inventory item into the chest |
| 0x1a3 | MsgFourInts {chestItemHandle, container, slot, unused} | FUN_00472560 | move a chest item back to inventory |

## 0x6f raw packet, subtype 10: HousingTeleportDataPacket (FUN_00622250 -> FUN_00622190/FUN_00622090/FUN_00621a00/FUN_00620880, UI FUN_005ef850)
Raw little-endian payload (not SGO): `i16 10, i32 count, count x { i32 id, i32 nChars, nChars x u16 (no terminator) }` [O]. Each entry becomes a row in `_housing_teleport_list` (inside `_housing_teleport_list_window`, only if that window exists): label = name, row data = id [O]. Subtype 4 is a different system (claim/promotional packets), not housing.

## 0xe MsgSingleShort notice codes (FUN_0061d530 jump table 0x61f510; text from bin\VGClient.int)
| code | key | text |
|---|---|---|
| 0x1b | GuildHeadquartersRemoved | Your guild no longer has a guild headquarters. |
| 0x1c | GuildHeadquartersAdded | Your guild has a new guild headquarters. |
| 0xe0 | GuildPlotPurchaseError | You must be a guild leader, have a full group of guild members, and have the continent specific guild commission to purchase a guild plot. |
| 0x15c | CantBePlacedInChest | That item cannot be placed in that chest. |
| 0x15d | ChestFull | That chest is full. |
| 0x15e | PermissionListAboveMax | Unable to add new permission list. Above the Max allowed. |
| 0x15f | SaveFailed | Save failed. |
| 0x160 | NoActorExists | No actor exists for this item. Please /bug this. |
| 0x161 | CantFindFixtureBldg | BUILDING ERROR: Failed to find fixture building. |
| 0x162 | CantFindFixtureActor | BUILDING ERROR: Failed to find fixture actor. |
| 0x163 | CantMoveFixture | Unable to move fixture to this location. |
| 0x164 | NoPermissionToMoveFixture | You do not have permission to move this fixture. |
| 0x165 | NoPermissionToPlaceFixture | You do not have permission to place a fixture here. |
| 0x166 | NoPermissionToSendFixture | You do not have permission to send trophies to their owner. |
| 0x167 | CantSendNotTrophy | Only trophies can be sent to their owner. |
| 0x168 | BldgCantHoldMoreFixtures | This building can not hold any more fixtures. |
| 0x169 | PlaceFixtureItemError | You cannot place No Rent, Soulbound, Quest, or No Drop items in your house. |
| 0x16a | InvPlotSelection | Invalid plot selection. |
| 0x16b | PlotNotForPurchase | This plot is currently not available for purchase. |
| 0x16c | PlotNotForSale | That plot is not for sale. |
| 0x16d | OnePlotPerAcct | You may not purchase an additional plot. Free Members can only own 1 plot, Gold Members can own 2 plots. |
| 0x16e | CantPurchasePlot | Unable to purchase plot. You don't have enough money. |
| 0x16f | PlotDBError | Unable to purchase plot. Database error. |
| 0x170 | PurchasedPlot | Successfully purchased targeted plot. |
| 0x171 | FailedPurchasePlot | Failed to purchase plot, plot not found. |
| 0x172 | FirstSellBldgs | You can not sell this plot at this time. You must first sell all of your buildings. |
| 0x173 | SoldPlot | Successfully sold targeted plot. |
| 0x174 | SellOwnPlots | You can only sell plots that you own. |
| 0x175 | CantFindPlot | Can't find selected plot on the server. |
| 0x176 | CantFindPlotWithBldg | Can't find plot associated with this building. |
| 0x177 | RemoveChestItems | You must remove all of your items from your chest before you can pick it up. |
| 0x178 | RemovedFixtureFromBldg | Successfully removed Fixture from building. |
| 0x179 | NoSpaceInInv | You don't have space in your inventory for that item. |
| 0x17a | NoPermissionToPickupFixture | You do not have permission to pickup that fixture. |
| 0x17b | CantDeletePermissions | You do not have permission to delete permissions. |
| 0x17c | DepositSuccess | Deposit successful. |
| 0x17d | CantChangePermissions | You do not have permission to change permissions. |
| 0x17e | NoLongerGuildUsable | This building is no longer flagged as guild usable. |
| 0x17f | NowGuildUsable | This building is now flagged as guild usable. ... |
| 0x180 | CantSetPublicAccess | You cannot set the public access level above Friend. |
| 0x181 | CantFindPermission | BUILDING ERROR: Unable to find permission specified. |
| 0x182 | CantFindBldgObj | BUILDING ERROR: Unable to find building object referenced in permission. |
| 0x183 | NoPermissionToAddPlayer | You do not have permission to add a player to this permission. |
| 0x184 | NoPermissionToAddFriend | You do not have permission to add a friend to this permission. |
| 0x185 | NoPermissionToRemoveFriend | You do not have permission to remove this friend. |
| 0x186 | CantRemoveFriend | BUILDING ERROR: Unable to remove selected friend from permission. |
| 0x187 | CantAddPermissionList | Unable to add new permission list. |
| 0x188 | CantAddPermissions | You do not have permission to add a permission. |
| 0x189 | MaxPermissions | You are at the max number of permissions allowed. |
| 0x18a | ConstObjNotFound | Construction object not found. |
| 0x18b | InvPlotInstance | Invalid plot instance for this construction instance. |
| 0x18c | InvBldgType | Invalid building type. |
| 0x18d | FailedFindPlotDef | Failed to find plot definition for this instance. |
| 0x18e | CantAbandonConstr | You do not have permission to abandon construction. |
| 0x18f | CantFindConstrSite | Unable to find construction site. |
| 0x190 | CantFindPlotWithSite | Unable to find plot associated with this construction site. |
| 0x191 | FailedCreateNewBldg | Failed to create new Building Instance. |
| 0x192 | ConstrCompleted | Construction completed successfully. |
| 0x193 | SiteMissingMaterials | This construction site is still missing materials. |
| 0x194 | InvResourceDef | Invalid resource definition. |
| 0x195 | MaterialIDNotFound | Construction material ID not found at that index. |
| 0x196 | MaterialNotInInv | Construction material not found in inventory. |
| 0x197 | MaterialNotSuitable | That material is not suitable for this construction project. ... higher grade. |
| 0x198-0x19a | FailedRemoveMaterialsFromInvOne/Two/Three | Failed to remove construction material from inventory, 1/2/3. |
| 0x19b | MaterialNotNeeded | This construction material is no longer needed. |
| 0x19c | CantFindPlotDef | Can't find selected plot definition on the server. |
| 0x19d | ConstProjInProgress | You currently have a construction project in progress. |
| 0x19e | BldgExistsForPlot | A building already exists for this Plot. |
| 0x19f | FailedBeginConst | Failed to begin building construction. |
| 0x1a0 | ConstStarted | Building construction successfully started. |
| 0x1a1 | NoPermissionToStartConst | You do not have permission to start construction. |
| 0x1a2 | RequestPlotInfo | Requesting plot information from server. |
| 0x1a3 | BldgInstanceNotFound | Building Instance not found. Can't sell it. |
| 0x1a4 | PlotInstanceNotFound | Plot Instance not found. Can't sell it. |
| 0x1a5 | PlotDefNotFound | Plot Definition not found. Can't sell it. |
| 0x1a6 | CantSellBldg | You can not sell this building. You must first retrieve all of your belongings in your house. |
| 0x1a7 | RemovedBldgFromPlot | Successfully removed Building from plot. |
| 0x1a8 | BldgPurchased | Building successfully purchased. |
| 0x1a9 | DontOwnPlot | You do not own this plot. |
| 0x1aa | InvFixtureType | This item is not a valid fixture type. |
| 0x1ab | NoPermissionToAccessBldg | You do not have permission to access this building. |
| 0x1ac | FailedOpenDoor | Failed to open door. BuildingInstance not found. Please report this error. |
| 0x1ad | NoPermissionToUseChest | You do not have permission to use this chest. |
| 0x1ae | NoPermissionToViewChest | You do not have permission to view this chest. |
| 0x1af | NoPermissionToDepositChestItem | You do not have permission to deposit items in this chest. |
| 0x1b0 | NoPermissionToTakeChestItem | You do not have permission to take items from this chest. |
| 0x1b1 | NotUsingChest | You are not using a Chest. |
| 0x1b2 | NotUsingThisChest | You are not using 'this' Chest. |
| 0x1b3 | CantAddChestItem | Unable to add item to chest. |
Full table: scratchpad codes0e.txt (code, chat channel, key).

## Minimal S->C sequences
- Inspect a plot: 0x454 (for sale: field8=1, cost, options list) -> 0x458. Owned with house: 0x454 -> 0x455 -> fixtures (0x45a, 0x45c x N, 0x45b) -> 0x458.
- Buy: 0xe 0x170 (PurchasedPlot), then 0x454 (owned, IsMine=1) + 0x458.
- Construction: 0xe 0x1a0 -> 0x453; progress 0x453 again; complete 0xe 0x192 + 0x477/0x476 + 0x479(false) + 0x455.
- Open house chest: 0x199 {chestId, capacity} -> 0x19e per item -> 0x1a0; close 0x19a.
