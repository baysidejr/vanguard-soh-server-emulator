# Housing: client -> server events (VGClient.exe, static)

[O] = read in code; [I] = inferred. All sends use FUN_004cfb00(id, msg) (serialize -> FUN_00409210(id, bytes, len)) or FUN_004cfb50(id) (no payload). Wire order = field registration order in the message ctor.

## Client-side state the payloads come from
- Housing manager `DAT_014639d4` (class at 0x47xxxx):
  - +0x00 / +0x04: **object id / object type** of the placed object under the cursor. Copied from actor+0x3f0 / actor+0x3f4 by FUN_00483c90 (called from interact FUN_00417da0 at 0x418031 with the actor from FUN_00b81620). +0x0c = actor ptr. Type values (FUN_00816ca0) [O]: **1, 2, 8 = building** (menu: Inspect); **3 = fixture** (Pick Up, Move, Send To Owner); **4 = chest** (Pick Up, Move, Open, Manage Chest); 7 = ignored. FUN_00474560 returns +0 only if +4 == 4 (chest).
  - +0x08: item handle of the fixture being placed (-1 = none).
  - +0x1c: **plot id** (the inspected plot; set from S->C plot info).
  - +0x80: bPlotIsHQ. +0x23dc: building id. +0x2444: construction id. +0x2814: chest id for chest permissions; +0x281c + i*0x350: permission entry ids; +0x27ec[10]: guild rank values.
- Chest manager `DAT_014639b8`: +0x34 = open chest id. Building-NPC manager `DAT_014639e0`: +0x28 selected NPC template, +0x2c selected placed NPC.
- Mouse-over menu `_building_options_menu` (FUN_004839b0) item table at 0x13e5f38 {itemId, uiCmd, label, cmd} [O]: 7->0x1a0 "Inspect"; 0xa->0x1a1 "Pick Up"; 0xb->0x1a2 "Move"; 0xc->0x155 "Open"; 0xd->0x156 "Construction..."; 0xe->0x19f "Avatar Inspect"; 0xf->0x1a3 "Change Permission"; 0x10->0x1a4 "Manage Chest"; 0x11->0x1a5 "Send To Owner".

## UI command -> handler -> message
UI ids from the string table in FUN_006a0062 (with register tracking); handlers from jump table 0x6aa19c [O].

| UI cmd (id) | handler | C->S id | payload (wire order) | notes |
|---|---|---|---|---|
| mo_building_options_inspect (0x1a0) | FUN_00476430 | **0x460** | MsgTwoInts {i32 objType(mgr+4), i32 objId(mgr+0)} | Inspect a building/plot object. Sent only if mgr+0xc != 0 [O]. Server answers with plot/building info (0x454/0x455) [I] |
| mo_avatar_building_options_inspect (0x19f) | FUN_004763b0 | **0x82f** | MsgTwoInts {objType, objId} | same shape as 0x460 [O] |
| mo_fixture_option_pickup (0x1a1) | FUN_004760a0 | **0x462** | MsgSingleInt {objId(mgr+0)} | pick up fixture/chest [O] |
| pickup_fixture_button (0x1c3) | FUN_0068c140 -> FUN_00475fa0 | **0x462** | {fixtureId = selected row data in `_building_fixture_list`} | from the fixture-list window [O] |
| mo_fixture_option_send_to_owner (0x1a5) | FUN_00476120 | **0x463** | {objId} | [O] |
| mo_fixture_option_move (0x1a2) | FUN_00473e70 | none | - | opens `_fixture_movement_popup` with objId as data (local) [O] |
| fixture_move_{pos,neg}_{x,y,z,yaw,pitch,roll} (all share 0x1c5) | FUN_00698f80 -> FUN_0047b2b0 (matches button name) | **0x464** | MsgFixturePosition (ctor FUN_00475c50/0x473be0): {i32 fixtureId(mgr+0), i32 unused(0), f32 dX, f32 dY, f32 dZ, i32 dYaw, i32 dPitch, i32 dRoll} | **Step = ±10.0 units** (0x41200000) on one axis, or **±256 rotator units** (0x100 = ~1.4 deg) on one angle; all others 0. Struct offsets: +0x28 Pitch, +0x2c Yaw, +0x30 Roll, registered Yaw, Pitch, Roll [O] |
| fixture_movement_close (0x1c6) | FUN_0068f490 | none | - | closes popup [O] |
| move_tome_fixture_button (0x1c4) | FUN_0068c1c0 -> FUN_00476020 | **0x465** | {fixtureId (selected fixture-list row)} | "move to me" [I name] |
| mo_chest_manage (0x1a4) | FUN_0068c480 -> FUN_004761a0 | **0x466** | {chestId(mgr+0)} | request chest permission data (server answers 0x469/0x46b) [I] |
| mo_chest_open (0x155) | FUN_004715b0 (chest mgr) | **0x151** | {chestId} (only if obj type == 4) | refused locally if already interacting ("You are already interacting with a Chest.") [O] |
| chest_close (0xd5) | FUN_00471660 | **0x152** | {chestId or 0} | clears chest flag first [O] |
| chest drag/drop: inventory -> chest list | FUN_00687a50 -> FUN_004716f0 | **0x155** | MsgFourInts {chestId, invItemHandle, count(-1 => whole stack), destRowData} | deposit [O] |
| chest drag/drop: chest -> chest list | FUN_00687a50 -> FUN_00471d00 | **0x153** | MsgFourInts {chestId, chestItemHandle, count, destRowData} | rearrange inside chest [O] |
| chest item dropped on inventory | FUN_006963e0 (UI 0x6a86a6) -> FUN_00471bf0 | **0x157** | 5 x i32 (ctor 0x4712d0): {chestId, chestItemHandle, count, destContainer(-1 default), destSlot} | withdraw [O] |
| mo_inventory_place_fixture (0x149) | FUN_0068cc30 -> FUN_00480b30 | **0x461** | {itemHandle} | Only if FUN_004771d0(player location) > 0, else "You can only place items when in your house."; stores handle in mgr+8 [O] |
| (world click while placement preview active) | input handler 0x41944d -> FUN_0047da50 | **0x46d** | same class as 0x464: {i32 itemHandle(mgr+8), i32 buildingId (FUN_00816c90 of the building the point lies in, 0 if none), f32 X, f32 Y, f32 Z, i32 Yaw, i32 Pitch, i32 Roll} | Values from preview actor via FUN_00b7e750 (Location at actor+0x1cc, Rotation at +0x1d8). Then ends preview (FUN_00b78290), mgr+8 = -1. If mgr+8 == -1 the click just cancels the preview (FUN_00b80a60) [O] |
| plot_info_buy_plot (0x1a8) | FUN_00473f40 | none | - | shows `PlotPurchaseConfirm` [O] |
| plot_purchase_cost_accept (0x1a7) | FUN_004764b0 | **0x481** | {plotId(mgr+0x1c)} | **buy plot** [O] |
| plot_purchase_cost_cancel (0x1a6) | FUN_00473ed0 | none | hides confirm [O] |
| plot_info_sell_plot (0x1ab) | FUN_00474020 | none | shows `PlotRelinquishConfirm` [O] |
| plot_relinquish_accept (0x1aa) | FUN_00476560 | **0x47f** | {plotId} | sell/relinquish plot [O] |
| plot_info_done_inspect (0x1ac) | thunk FUN_004750e0 | none | hides `bPlotInformation` [O] |
| _scroll_window_select_building_option_item (0x1b0) | FUN_0047e030 | none | fills name/type/#fixtures/#chests from cached options (10 x 0x34 at mgr+0xb8) [O] |
| plot_selected_building_details (0x1af) | FUN_00476ce0 | **0x474** | {buildingOptionId (selected row of `_plot_option_select_list`)} | server replies 0x474 construction resources [I] |
| plot_construct_selected_building (0x1ad) | FUN_004766a0 | **0x479** | MsgTwoInts {plotId, buildingOptionId} | **start construction of a house type on the plot** [O] |
| plot_view_current_construction (0x1ae) | FUN_00476c60 | **0x473** | {plotId} | [O] |
| building_add_material_button (0x1d5) | FUN_0068c680 -> FUN_00483630 | none | opens `_material_select_popup` listing inventory items matching the resource [O] |
| material_select_add_ok (0x1d6) | FUN_00476d60 | **0x475** | MsgFourInts {constructionId(mgr+0x2444), invItemHandle, resourceRowData, resourceRowIndex} | "First select a material..." if none [O] |
| building_construction_abandon_button (0x1d9) | FUN_0068c6e0 -> FUN_00476eb0(btn+0x50) | **0x476** when arg==1 | {constructionId} | arg 2 = hide confirm, other = show confirm [O] |
| building_construction_complete_button (0x1da) | FUN_0068c700 -> FUN_00477010(arg) | **0x478** when arg==1 | {constructionId} | [O] |
| house_tear_down_house (0x1b3) | FUN_00474100 | none | shows `BuildingDeconstructionConfirm` [O] |
| building_deconstruction_accept (0x1b2) | FUN_00476720 | **0x480** | {buildingId(mgr+0x23dc)} | [O] |
| house_close_house_info (0x1b4) | thunk FUN_00475150 | none | hides bHouseInformation(+Basic) [O] |
| upkeep_deposit (0x1bc) | FUN_00482c50 | **0x47e** | MsgTwoInts {plotId, copper} | copper from `_upkeep_coin_platinum/gold/silver/copper` (plat x 1,000,000 seen; others x10000/x100/x1 [I]); only if > 0 [O] |
| toggle_building_guild_usable (0x1c7) | FUN_00476a00 | **0x47a** | {plotId} | [O] |
| make_guild_headquarters_button (0x1c8) | FUN_004741e0 | none | shows HQ or HQ-relinquish confirm by mgr+0x80 [O] |
| building_headquarters_accept (0x1c9) / relinquish_accept (0x1d3) | FUN_00476a80 / FUN_00476b30 | **0x47b** | {plotId} | same id both ways (toggle) [O] |
| building_headquarters_leader_accept (0x1cc) / _decline (0x1cb) | FUN_0047d830 / FUN_0047d940 | **0x47c** | MsgBuildingGuildHeadquartersResponse {i32 a, i32 b, wstr "", bool8 accept} | a/b = data values of `_building_guild_leader_headquarters_confirm` (echo of S->C 0x47c) [O/I] |
| create_permission_accept (0x1b6) | FUN_00480870 | **0x470** | MsgBuildingPermission {i32 plotId, i32 permId, wstr name, i32 guildRank, u32 flags, bool8 allPlayers, bool8 allGuildMembers} | name from `_permission_name_edit` (required) [O class; exact field assignment I] |
| permission_edit_save_button (0x1bb) | FUN_0068c3a0 -> FUN_00480570 | **0x472** | same class: {plotId, permId, name, guildRank, flags, allPlayers, allGuild} | [O] |
| delete_permission_button (0x1b8) | FUN_0068c3c0 -> FUN_00476be0 | **0x471** | MsgTwoInts {plotId, selectedPermId} | [O] |
| permission_playername_add_ok (0x1c1) | FUN_00699050 -> FUN_00480490 | **0x46f** | {wstr playerName, i32 permId, i32 0} (ctor 0x455260) | used for building and chest permissions [O] |
| permission_remove_player_button (0x1c0) / chest_permission_remove_player (0x1d1) | FUN_00476820 / FUN_00476910 | **0x46e** | MsgTwoInts {permId, friendRowData} | [O] |
| chest_permission_accept (0x1cd) | FUN_0068c4e0 -> FUN_0047d650 | **0x467** | MsgChestPermission {i32 chestId(mgr+0x2814), i32 permType 0..2, i32 permEntryId, i32 guildRank, u32 0, bool8 allPlayers, bool8 allGuild, wstr ""} | [O] |
| manage_chest_edit_perm (0x1cf), chest_permission_add_player (0x1d0), create/view/close permission buttons, add_player_button | - | none | local UI only [O] |
| mo_chest_change_permission (0x1a3), mo_building_construction_open (0x156), select_housing_plot (0x269), _scroll_window_select_permission_name_item (0x1be) | jump-table default 0x6a8372 | none | unimplemented no-ops [O] |
| manage_building_npcs_button (0x25f) | FUN_0068c1a0 -> FUN_00484320 | **0x5d1**, **0x5d2** | none | open `_building_npc_window`, request NPC lists [O] |
| spawn_building_npc (0x21b) | FUN_00484a30 | **0x5ce** | {i32 npcTemplateId(+0x28), f32 heading(float of pawn yaw int +0x1dc), f32 X, f32 Y, f32 Z (pawn location)} (ctor 0x484130) | [O] |
| remove_building_npc (0x21e) / goto_building_npc (0x21f) | FUN_00484af0 / FUN_00484b70 | **0x5cf** / **0x5d0** | {placedNpcId(+0x2c)} | [O] |
| housing_teleport_list_accept (0x26b) | FUN_006a7e20 | **0x6f (raw)** | HousingTeleportDataResponsePacket: {i16 subtype = 11, i32 teleportId} | id = selected row's data = TeleportData.+0 from S->C 0x6f/10. Serialized by FUN_0069a650, sent via FUN_00409210(0x6f,...) [O] |
| housing_teleport_list_decline (0x26a) | FUN_00685dd0 | none | closes the list [O] |

## Slash commands [O]
- `/transferplot <name>` (FUN_006017f0): the target must be a known pawn and not yourself; shows the "Transfer Plot?" popup (FUN_005ee500), whose buttons run `/transferplotconfirm accept|decline`.
- `/transferplotconfirm accept` (FUN_005ee7f0 -> 0x5c6): sends **0x5c6** MsgSendSingleSGOString {wstr targetName}.
- `/beatchest`: a local animation test (FUN_00bbdf80 on the pawn). It is not housing.

## Dead code (no callers or pointers anywhere) [O]
- FUN_00479d60 -> 0x7ec {plotId}
- FUN_004822a0 -> 0x7ed {wstr name, i32 plotId} ("You must first inspect a plot befor attempting to transfer ownership.")
- FUN_00476220 is a duplicate of the 0x464 builder that takes a case index.
- FUN_0047e600 -> 0x45f {i32 objId, i32 objType, wstr 1-char bool}: reached only from FUN_00483c90 with flag 0. Its only caller passes 1, so this path is not used.
