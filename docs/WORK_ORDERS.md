# Crafting work orders (task masters)

> **Verified live (2026-10-13):** hailing Garret Holm (Task Master) shows "I'm looking for work. (Work orders)". Clicking it opens the Available Work Orders window with "Copper Ingots for the Camp" (Difficulty: Moderate, Skill: Smelting, Requested items: 2 Requisitioned Copper Ingot). Select gives 4 Requisition Copper Ore and puts "Requisitioned Copper Ingot" under **Work Order Recipes** at the forge. Complete without the ingots prints "You need more items to complete that work order."; after crafting two it prints "Work order accepted.", "Requisitioned Copper Ingot was removed from your recipe book", the coin, "You gain 200 crafting experience!" and a faction gain.

Server: `server/workorder.py`, `login_stub.handle_workorder_event`. Content: `server/content/workorders.json` (orders), work-order recipes in `recipes.json` (`work_order: true`, `category: 3`), task masters in `mobs.json` (`task_master: true`).

## Server behaviour

- Task master NPCs get `EntityTypes 0x200` (task master cursor) and a dialogue option of type 4.
- 0x171 (request work): checks the target and range (1500 units), then sends 0x4a1 and 0x4a2 with that task master's orders, minus the one the player is on. With no orders left it adds 0x4a4 code 2, which keeps the window open on the Current tab so the player can turn in.
- 0x173 (select): one order at a time (code 4 otherwise). Sends 0x4a3 code 0, 0x4a7, 0x4a9 (the needed-items text, which 0x4a7 drops), teaches the work-order recipe (0x2ef with its actions), and gives the supplies.
- 0x174 (complete): must be the issuing task master (code 4) and have the delivered items (code 3). Takes the items, forgets the recipe (0x2f4), pays coin, crafting XP (experience message kind 1) and faction.
- 0x175 (abandon): takes back the leftover supplies and forgets the recipe.
- 0x172 (Done or close): 0x4a4 code 5.
- At login the active order is sent with 0x4a7 and 0x4a9, and its recipe is in the book. Work-order recipes are not sent to players without that order.
- The active order is saved per character (`work_order` in characters.json). Orders can be repeated.

Static analysis of VGClient.exe only (Ghidra via REA plus capstone). **[O]** = read directly in code. **[I]** = inferred.
Framing is the same as craft.py `_event`: `struct.pack("<HII", 2, id, len(payload)) + payload`. wstr = UTF-16LE text plus 00 00.

Client manager: `VGClientWorkOrder` list object, global `DAT_014639d0`. Its fields [O]:
- +0x00 bool: requisitioning (the work order window is open)
- +0x04 vector: **available** list (TaskMasterWorkOrderList)
- +0x14 vector: **current/active** list (CurrentWorkOrderList and JournalWorkOrderList)
- +0x3c: id selected in the journal
- +0x40: id selected in the Available tab
- +0x44: id selected in the Current tab

Each work order is a `VGClientWorkOrder` object (0xb0 bytes, ctor FUN_004b9920).

## MsgTaskMasterWorkOrder record (13 fields, in wire order) [O]
Field-to-object mapping comes from FUN_004bd450 and FUN_004bd690. The UI use comes from FUN_004bbce0 (Available details), FUN_004bb360 (Current details), FUN_004bad10 (Journal details) and FUN_004bcbb0 / FUN_004ba990 (list rows).

| # | type | obj off | meaning | evidence |
|---|---|---|---|---|
| 1 | wstr | +0x04 | **name** | `*WorkOrderName`. The list row text is this name, colored by field 5 (FUN_004ba7f0) [O] |
| 2 | wstr | +0x20 | **description** | `*WorkOrderDescription` [O] |
| 3 | i32 | +0x58 | **work order id** (key everywhere; -1 = ignore in 0x4a7) | list-row data, lookups, all C->S ids [O] |
| 4 | i32 | +0x5c | **icon id** | itoa → first string of the list entry. The crafting recipe list does the same with recipe icon +0x44 (0x5a9c7c) [I, strong] |
| 5 | i32 | +0x60 | **difficulty "con"** (player skill minus order level) [I formula] | ≥8 "Trivial" (dkgray); 5..7 "Very Easy" (cyan); 2..4 "Easy" (blue); -1..1 "Moderate" (white); -4..-2 "Difficult" (yellow); -7..-5 "Very Difficult" (red); ≤-8 "Downright Impossible" (purple). Used for `*WorkOrderDifficulty` and the name color [O] |
| 6 | i32 | +0x64 | parent slot used when #8=1: 0, 1 or 3 index manager slots +0x2c/+0x24/+0x34 (FUN_004b79a0) | Slots appear never filled (only freed in FUN_004b9c10), so the client shows "This work order provides the needed items for another." Send 0 [O/I] |
| 7 | wstr | +0x3c | **issued by** (task master name) | "Issued by: %s " → `*WorkOrderIssuedBy` [O] |
| 8 | bool8 | +0x8c | **is a sub-order** (this order supplies items for another order) | `*WorkOrderSteps` text [O] |
| 9 | i32 | +0x68 | number of **other work orders needed** for the required items (used when #8=0) | 1 → "There is another work order needed…"; n → "There are %d other work orders needed…"; 0 → empty [O] |
| 10 | i32 | +0x6c | number of **recipes in your recipe book** for this order | 1 → "There is a recipe in your recipe book for this work order."; n → "There are %d recipes…"; 0 → empty (`*WorkOrderRecipes`) [O] |
| 11 | wstr | +0x70 | **requested/needed items text** | "Requested items: %s" (`*WorkOrderNeededItems`). If empty, the client sends **0x178 {id}** to ask for it [O] |
| 12 | wstr | +0x90 | unknown; stored but never read by the UI | only ctor/dtor/copy touch +0x90 [O]. Send "" |
| 13 | i32 | +0xac | **crafting skill id** | FUN_00d03670(skill) → "Skill: %s " (`*WorkOrderSkill`); -1 = blank. Same skill-name lookup as the recipe skillId [O] |

There are no reward, coin or XP fields. The client never displays rewards for work orders [O].

## Server → client

| id | handler | payload | meaning |
|---|---|---|---|
| **0x4a1** | FUN_004bcff0 | none | **Open the requisition window.** Sets flag=1, prints "You requisition work.", closes the NPC dialogue (FUN_004c8680(1,0,0) if open), refreshes the current/journal lists, sets `nWorkOrderWindowState`=0 (Available tab) and `SelectingWorkOrder`=1 (window visible). Does not clear the available list [O] |
| **0x4a2** | FUN_004bd450 | **`i32 count` + count × MsgTaskMasterWorkOrder** | **Replace the available list.** Clears the old list (FUN_004b9b30), then adds a row per record. ZONE_MESSAGES.md omits the count prefix [O]. Always fill field 11 here: the 0x4a9 reply only updates the current list |
| **0x4a3** | FUN_004bcab0 | MsgIntAndByte `{i32 id (unused), u8 code}` | Result of select (0x173). 0 "Work order selected." Clears the available list and Available details; the server must then send 0x4a7 (and optionally a new 0x4a2). 1 "You are not requisitioning work."; 2 "That work order is not available."; 3 "You have already completed that work order."; 4 "You are currently on a work order.  Abandon it to select another."; 0xff "You failed to solicit that work order."; other values: silent [O] |
| **0x4a4** | FUN_004ba3d0 | MsgSingleByte `{u8 code}` | Requisition end or refusal. Clears the available list. 0 "Your target is not a task master."; 1 "You are too far away to request work."; **2 "Your target has no work for you right now."** (the only code that keeps the window open: flag=1, Current tab, SelectingWorkOrder=1, so turn-ins still work); 3 "Your task master has disappeared."; 4 "Please target a task master."; 5/7/0xff "Requisition ended."; 6 and any other value close the window with no message. Every code except 2 sets flag=0 and hides the window [O] |
| **0x4a5** | FUN_004bd0e0 | MsgIntAndByte `{i32 id, u8 code}` | Result of complete/turn-in (0x174). 0 "Work order accepted." Clears the available list, resets Current details, removes `id` from the current/journal list. 1 "You are not requisitioning work."; 2 "You are not working on that work order."; 3 "You need more items to complete that work order."; 4 "You must return a work order to the task master who issued it."; 5 "That work order requires you complete others first."; 6 "You may not complete work orders while trading, please finish your trade first."; 0xff "You failed to complete that work order." [O] |
| **0x4a6** | FUN_004bd200 | MsgIntAndByte `{i32 id, u8 code}` | Result of abandon (0x175). 0 "Work order abandoned." Resets Current details and removes `id`. 1 "You need to talk to a task master."; 2 "You are not working on that work order."; 0xff "You failed to abandon that work order." [O] |
| **0x4a7** | FUN_004bd690 | one MsgTaskMasterWorkOrder (no count) | **Add an active work order** to the current and journal lists (refreshes both via FUN_004bcda0). Ignored if id == -1. If the id already exists, the client does not update it (to change one, send 0x4a8 then 0x4a7). **Field 11 is discarded (set to "")**, so the client later asks for it with 0x178. Send at login for each active order and after a successful select [O] |
| **0x4a8** | FUN_004bd350 | MsgTwoInts `{i32 id, i32 unused}` | Remove work order `id` from the current/journal lists without a message (expired or cancelled by the server). The second int is not read [O] |
| **0x4a9** | FUN_004bc600 | MsgStringAndInt `{wstr neededItems, i32 id}` | Fills field 11 (+0x70) of active order `id`. If it is the order selected in the journal and the text is not empty, sets `JournalWorkOrderNeededItems` = "Needed items: %s" [O]. The Current-tab details refresh only when the order is selected again [O] |

## Client → server

All of these go through FUN_004cfb00 (MsgSingleInt `{i32}`, ctor FUN_00422cd0) or FUN_004cfb50 (no payload).

| id | payload | sender | trigger |
|---|---|---|---|
| **0x171** | none | FUN_004b76c0 (only if flag==0; otherwise prints "You are already requisitioning a work order.") | **Request work.** Sent from (a) NPC dialogue option **type 4** in 0x2bf (FUN_004c4640 case 4), and (b) the NPC mouse-over menu `mo_task_master_npc_work_order_select` (UI cmd 0x158 → FUN_0068b5b0). The server uses the player's current target. Reply: 0x4a1 + 0x4a2, or 0x4a4 code 2 (no work), or 0x4a4 code 0/1/4 (bad target) [O] |
| **0x172** | none | FUN_004b76f0 (only if flag==1; otherwise "You are not requisitioning a work order.") | **End requisition.** Sent by the Done buttons `task_master_work_order_done` (0xca) and `current_work_order_done` (0xcd), and by closing the window (its CLOSE action fires task_master_work_order_done). The client keeps flag=1 until the server answers, so reply **0x4a4 code 5** ("Requisition ended.") or code 6 (silent) [O] |
| **0x173** | `i32 workOrderId` (Available selection mgr+0x40) | FUN_004b9150 → FUN_004b8c00 | Select button `task_master_work_order_select` (UI 0xc9). Reply: 0x4a3, then 0x4a7 [O] |
| **0x174** | `i32 workOrderId` (Current selection mgr+0x44) | FUN_004b9170 → FUN_004b8d00 | **Complete / turn in**: `current_work_order_complete` (0xcb) and NPC menu `mo_task_master_npc_work_order_complete` (0x159). Client bug: `mo_task_master_npc_work_order_abandon` (0x15a) also calls FUN_004b9170 and so sends 0x174, not 0x175. Reply: 0x4a5 [O] |
| **0x175** | `i32 workOrderId` (mgr+0x44) | FUN_004b9190 → FUN_004b8c80 | **Abandon**: `current_work_order_abandon` (0xcc). Reply: 0x4a6 [O] |
| **0x178** | `i32 workOrderId` | inside FUN_004bbce0, FUN_004bb360, FUN_004bad10 | Sent when the selected order's needed-items text is empty, from any of the details panels. Reply: 0x4a9 [O] |

Other UI commands are client-only [O]:
- 0xce / 0xcf: `available_/current_work_order_list_show` set `nWorkOrderWindowState` to 0 or 1 (FUN_004b79e0).
- 0xd0 / 0xd1: select a row in the list.
- 0xf9: `journal_select_work_order` → FUN_004bad10.

Dead code with no static callers: FUN_004b9f40 (select by name → 0x173), FUN_004ba140, FUN_004ba340 (hide the window and send 0x172), and FUN_004ba750 (sends **0x81f** with one wstr).

There are no slash commands, and no UnrealScript (.u) package mentions work orders. Window XML: VGUIAssets/Shells/Default/Windows/VGUITaskMasterWorkOrders.xml (Available/Current tabs) and VGUICurrentWorkOrders.xml.

## Setup the server needs
- Task master NPC: set the **EntityTypes bit 0x200** (CraftingTaskMaster cursor, "TaskMasterHover", FUN_00418060 at 0x4188cf) [O]. Also offer a 0x2bf dialogue option of **type 4** (e.g. "Request work") [O per QUESTS.md / FUN_004c4640].
- Work-order recipes: send them through the normal recipe book (0x2ee/0x2ef MsgAddCraftingRecipe) with category **3 for refining** (→ RefiningWorkOrderRecipes) or **7 / any value outside 1..6 for finishing** (→ FinishingWorkOrderRecipes, 0x5a99f9) [O]. Field 10 is just a count the server reports; the client does not link recipes to orders.
- At login, send 0x4a7 for each active order so the journal fills.

