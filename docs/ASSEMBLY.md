# Assembly crafting

> **Partly verified live (2026-10-13):** Brenna Ashford (`assembly_trainer` in mobs.json) shows the client's option "Do you have any assembly recipes?" (0x2b8). Clicking it (0x16e) opens "Assembly Recipe Training" with Copper Ring (1 silver, 0x49c + count-prefixed 0x49d). Train (0x170 {recipe}) prints "You lose 1 silver." and "Assembly recipe added: Copper Ring" (0x34d MsgAddAssemblyRecipe), then Done (0x16f) "Training ended." (0x49f 5). Right-clicking the Assembly Bench (EntityTypes 0x800000|0x10) opens Abilities > Crafting > Assembly without any message to the server.
>
> **Not working yet:** the Assembly page's category dropdown and recipe tree stay empty ("None"); the client never asks for the tree (0x121), and an unprompted 0x350 is not shown. The assemble step (0x11f, timer 0x34b, success 0x349) is coded but untested. All items now carry a template id in field 1 (`zone.template_id`, stable per item name), which the client uses to match ingredients; handles (field 71) stay unique.

Server: `server/assembly.py`, `login_stub.handle_assembly_event/assembly_tick`. Content: `server/content/assembly.json` (Copper Ring = Copper Wire + Copper Ingot).

The rest is the client analysis (static, by a research agent).


Tags: [O] read in decompiled code or disassembly. [I] inferred. Payloads are packed little-endian in field-registration order. wstr = UTF-16LE text ending in 0x0000.

## Client objects
- **A = `DAT_01463988`, the assembly session** (ingredient slots and timer). +0 dirty flag. +4 f32 seconds left, +8 f32 total seconds, +0xc bool8 assembling. **+0x10..+0x20 = 5 item handles** (item +0x650, wire field 71; -1 = empty). **+0x24..+0x34 = 5 quantities.** [O]
- **B = `DAT_014639a8`, the assembly recipe book and window.** +0 bCanAssemble. +1 "print the learned message" flag. +2 assemble-all flag. +8 selected recipe id. +0x40 last opened tree node. +0x54 recipe that the candidate lists belong to. **+0x58 + 0x10·i = 5 candidate-item vectors**, one per ingredient (begin pointer at +0x5c + 0x10·i). +0xac tree nodes, **+0xbc learned-recipe list** (0x4c entries), **+0xc8 recipe map** (0x100 records, looked up by `FUN_004556a0`). [O]
- **T = the assembly-trainer object** (the `FUN_00462d90` ECX). +0 training flag. +8 list of trainable recipes. +0x18 second list. [O]
- **Recipe record** (0x100 bytes, `FUN_0045e3a0`): +0 id, +4 wstr name, +0x20 wstr (second string), +0x3c i32, +0x44 **reward item template id**, +0x48 i32, **+0x4c..+0x5c ingredient template ids** (-1 = none), **+0x60..+0x70 required quantities**, +0x74 + 0x1c·i ingredient names. [O]
- **Learned-list entry** (0x4c bytes): +0 id, +4 name, **+0x24 + 4i ingredient ids**, **+0x38 + 4i "discovered" flags**. [O]

## Opening the window
- **The assembly station has EntityTypes `0x800000`.** Interact `FUN_00417da0` (at 0x417ed7) calls `FUN_00450310`, which opens `_abilities_window` → page "Crafting" → page "Assembly" (`cft_assembly_recipes` in VGUIAbilities.xml). **This is client-only. Nothing is sent to the server.** [O] (A refining station is bit 0x4.)
- The same page is reachable from the Abilities window at any time. The server enforces the station rule through 0x34a codes 8 and 9 ("You must be at the correct assembly station…", "too far away…"). [O]
- **The assembly trainer has EntityTypes `0x100000`.** It gives the "AssemblyTrainerHover" cursor (`FUN_00418060` at 0x418974). The interact chain has no branch for this bit, so clicking it sends the normal hail/dialogue event (0x2b0). [O]
- Other windows: the timer bar `VGUIAssemblyTimer.xml` is visible while `bAssembling` = 1 (gamevars `AssemblyTimeStatus` and `strAssemblingRecipeInfo`). The "Ingredients" slot window `VGUIAssembly.xml` (`_assembly_ingredients`, list `AssemblyItemList`, 5 slots, buttons /assemble and /assemblycancel) is opened only by `FUN_004502d0`. Nothing in the client calls that function. [O]

## Recipe window (`FUN_0045c8f0`, `FUN_00459fa0`) [O]
- `AsmRecipeName` = the recipe name. `AsmRecipeRewardItem` = the icon of the reward template (+0x44), looked up in the client template cache (`FUN_00517390`).
- For each ingredient slot i:
  - `AsmRecipeIngredientItem<i>` / `AsmRecipeIngredientName<i>` come from the ingredient's template.
  - `AsmRecipeIngredientHave<i>` = the sum of stack quantities (item +0x70c, field 6) in candidate vector i.
  - `AsmRecipeIngredientRequired<i>` = the required quantity.
  - `AsmRecipeIngredientStatus<i>` = "%i / %i". `AsmRecipeIngredientFulfilled<i>` = have ≥ required.
- `bCanAssemble` = every slot is fulfilled. It enables the Assemble button.
- **The candidate vectors are filled only by server message 0x354.** If the server does not send 0x354, the button stays disabled.

## Client → server events
All are sent with FUN_004cfb00 (payload) or FUN_004cfb50 (no payload).

| id | payload | sender / trigger |
|---|---|---|
| **0x11f** | **15 × i32: 5 × {i32 recipeId, i32 itemHandle, i32 quantity}**. recipeId = B+8, repeated in each triple. handle = -1 and qty = 0 for an empty slot. Message ctor `FUN_0044ef00`, registration `FUN_0044eae0` (60 bytes). [O] | `FUN_0044f360`. Sent by **/assemble**, by UI 0xc6 `assembly_assemble_selected` (`FUN_004559b0`), and by the assemble-all loop. Not sent if B+8 == -1. `FUN_004559b0` first fills A's slots from candidate vector i, up to the required quantity of each, through `FUN_0044f460(handle, n)`. [O] |
| 0x120 | `{i32 itemHandle, i32 B+4}` (MsgTwoInts) | `FUN_00451f70` ← UI 0x8a (`FUN_00693980`, drop of a cursor-held item, cursor mode 1). Afterwards B+4 = -1. Purpose unclear. Possibly "try this item as an ingredient" (discovery) [I]; it can be ignored. |
| **0x121** | `{i32 treeNodeId}` | `FUN_00452000`. Sent when a tree node opens (UI 0xc8 `assembly_tree_open` → `FUN_00456590` → `FUN_00456570`), and after every 0x34c/0x34d to refresh the last opened node. Reply: **0x350**. [O] |
| **0x122** | `{i32 recipeId}` | `FUN_0045db20` (UI 0xc5 `assembly_recipe_select`; sets B+8 = node id) and `FUN_0045d720` (select by name). Sent only if the recipe is **not** in the map yet. Reply: 0x351, then 0x352 [I]. |
| **0x123** | `{i32 recipeId}` | `FUN_0045ca40`, when an ingredient template or the reward template is missing from the client template cache. Reply: 0x353 for each template, then 0x352 [I]. |
| **0x124** | `{i32 recipeId}` | `FUN_0045a980` (called from `FUN_0045ca40` once all templates are cached). It clears the 5 candidate vectors. Reply: **0x354**. [O] |
| 0x16e | none | Begin assembly training: dialogue option type 2 (`FUN_004c4640` → `FUN_00460010`). If T+0 == 1 it prints "You are already training." instead. [O] |
| 0x16f | none | Done (UI 0xc1 `assembly_trainer_done`, `FUN_00460040`). Only sent if T+0 == 1. [O] |
| 0x170 | `{i32 recipeId}` | Buy (UI 0xc0 `assembly_trainer_buy` → `FUN_00688cb0` → `FUN_00460a80`). The id is the selected row in `_assembly_trainer_recipe_list`. [O] |

Client-only commands [O]:
- **/assemblybegin** (`FUN_0044eb50`) prints three help lines.
- **/assemblyaddingredient \<keyword\> [n]** (`FUN_0044f8f0` → `FUN_0044f460`) and **/assemblyremoveingredient** (`FUN_0044fa50` → `FUN_0044f510`) only edit A's slots. Messages: "already in your assembly ingredients", "already filled your ingredient list", "That ingredient isn't in your list.".
- **/assemblydisplay** (`FUN_0044fd60`) lists the slots.
- **/assemblycancel** (`FUN_0044f610`) prints "Cancelling the assembly." and clears the slots. **Nothing is sent.**
- **/assemblydisplayrecipes** (`FUN_00457cf0`) lists learned recipe names.
- UI 0x113 `assembly_drag_drop` (`FUN_0068a460`) adds a dropped item to a slot. UI 0xc3 is category filters. UI 0xc7 toggles `bAssemblyAssembleAll` (B+2): while it is set and nothing is assembling, a tick (0x45626b) calls `FUN_004559b0` again. UI 0xc4 does nothing.

## Server → client: assembly session (dispatcher `FUN_0044fce0`) [O]

| id | payload | effect |
|---|---|---|
| **0x34b** | MsgStringAndFloat `{wstr info, f32 seconds}` (ctor `FUN_0044f770`) | `FUN_0044fb60`: A+4 = A+8 = seconds, A+0xc = 1. Sets `strAssemblingRecipeInfo` = info and `bAssembling` = 1, which shows the timer bar. The tick `FUN_0044f020` counts down and clears `bAssembling` at 0. |
| **0x349** | none | Prints "You have successfully assembled a new item!" and clears A's slots (`FUN_0044f580`). |
| **0x34a** | `{u8 code}` | Prints a failure line and clears the slots. 1 "Your assembly attempt failed.", 2 "That combination … doesn't appear to make anything.", 3 "must be in the crafting sphere", 4 "do not have the skill", 5 "lack the knowledge", 6 "ingredients are not of high enough quality", 7 "already assembling", 8 "must be at the correct assembly station", 9 "too far away from the station", 10 "may not assemble while trading". Other codes clear the slots silently. |

## Server → client: recipe book and tree (dispatcher `FUN_0045fda0`) [O]
**MsgAddAssemblyRecipe** (registration `FUN_0044ff70`):

`wstr name, wstr text2, i32 f3 (→rec+0x3c), i32 recipeId, i32 rewardTemplateId, i32 f6 (→rec+0x48), 5 × {i32 ingredientTemplateId (-1 none), i32 quantity, bool8 discovered, wstr ingredientName}`

f3 and f6 are probably skill level and category or station type [I].

| id | payload | effect |
|---|---|---|
| **0x34c** | MsgAddAssemblyRecipe | **Learn a recipe silently** (use at login). Adds it to the learned list and the map, then re-sends 0x121 for the last opened tree node. |
| **0x34d** | MsgAddAssemblyRecipe | The same, and also prints "Assembly recipe added: X" and the gold "New assembly recipe: X". (ZONE_MESSAGES.md says MsgSingleInt here; that is wrong.) |
| 0x34e | `{i32 recipeId}` | Removes the recipe: "X was removed from your assembly book". |
| 0x34f | `{i32 recipeId, i32 ingredientTemplateId}` | Marks that ingredient as discovered. Prints "You have discovered an assembly recipe ingredient!", or "…a new assembly recipe: X" once all are discovered. |
| **0x350** | `i32 n` + n × `{wstr name, i32 nodeId, i32 parentId}` | Fills the tree `FilteredAssemblyRecipeTree` (`FUN_0045e820` → `FUN_004534f0`). It also adds a "Retrieving recipes..." placeholder (`FUN_00450220`). Leaf nodeId = recipeId, because selecting a node sets B+8 = nodeId. Give category ids that don't collide with recipe ids [I]. |
| 0x351 | MsgAddAssemblyRecipe | Puts the recipe in the map without learning it (detail view). It is displayed if it is B+8. |
| 0x352 | `{i32 recipeId}` | Runs the template check (`FUN_0045ca40`): sends 0x123 if templates are missing, otherwise 0x124, and refreshes the view. |
| 0x353 | MsgSingleItemInfo (the 0x197 item layout) | `FUN_00516610(...,1,-1)` caches it as an item **template** (name, icon +0x6ec), then refreshes. Field 1 = the template id that recipes use [I]. |
| **0x354** | `i32 n` + n × `{i32 itemHandle (field 71), i32 recipeId}` | Candidate bag items (`FUN_0045e980`). Each item whose **item+0 (wire field 1)** equals ingredient id i goes into vector i. Then refreshes Have/Required/bCanAssemble. |

**Important [O]:** ingredients are matched on **item field 1** (`item+0`), not on the handle. Items that should count as ingredients need field 1 = the item template id. Keep field 71 as the unique handle. Today `vgmsg.inventory_item` puts the same instance id in both fields, so these items must send the template id in field 1. Check that nothing else in the client treats field 1 as unique [I].

## Server → client: assembly trainer (dispatcher `FUN_00462d90`) [O]
**MsgAssemblyTrainerRecipe** = `{wstr name, i32 recipeId, i32 icon, f32 costCopper, wstr description}`. Record (0x4c bytes): +4 name, +0x20 description, +0x3c id, +0x40 icon, +0x44 cost cast to int.

| id | payload | effect |
|---|---|---|
| 0x2b8 | none | Adds the dialogue option "Do you have any assembly recipes?" (type 2) (`FUN_004c7a00`). |
| 0x49c | none | T+0 = 1. Prints "You begin to train." and sets gamevar `AssemblyTraining` = 1, which opens VGUIAssemblyTrainer.xml. |
| **0x49d** | **`i32 n` + n × MsgAssemblyTrainerRecipe** | Appends to the trainable list (+8). The UI shows `AssemblyTrainerRecipeList`; selecting a row fills `AssemblyTrainerCurrRecipeName/Icon/Description/Cost`. **Unlike the recipe trainer's 0x498, this has a count prefix.** |
| 0x4a0 | same as 0x49d | Second list (+0x18), shown after the first (probably "not yet available") [I]. |
| 0x49e | `{i32 recipeId, u8 result}` | 0 = ok (the row is removed). 1 "You are not training.", 2 "That recipe is not available.", 3 "You can't afford that.", 5 inventory locked, 6 "That recipe is too difficult for you.", 0xff "You failed to learn that recipe." |
| 0x49f | `{u8 reason}` | Ends training and frees both lists. 0 not a trainer, 1 out of range, 2 nothing to teach, 3 trainer disappeared, 4 please target a trainer, 6 finish your trade, **5 (default) "Training ended."**. |

## Recommended server flow
1. **Spawn.** A trainer NPC with EntityTypes 0x100000 (|0x10 nameplate). An assembly station pawn with EntityTypes 0x800000 (|0x10).
2. **Login.**
   - Send 0x34c for each learned recipe.
   - Send 0x353 for every ingredient and reward template, so the names and icons resolve.
   - Send inventory items with field 1 = template id and field 71 = handle.
3. **Learn from the trainer.**
   - Hail (0x2b0) → send 0x2b8 with the other dialogue options.
   - Client sends 0x16e → reply 0x49c, then 0x49d {n, records}, or 0x49f 2 if there is nothing to teach.
   - Client sends 0x170 {id} → check coins and requirements. Send 0x1aa (coins) and 0x49e {id, 0}, then **0x34d** with the full recipe (ingredients flagged discovered = 1). Persist the recipe.
   - Client sends 0x16f → reply 0x49f 5.
4. **Open the window.** The player uses the station (client-only), or opens Abilities → Crafting → Assembly.
   - Client sends 0x121 {rootId} on tree open → reply 0x350 with categories and learned recipes. Use leaf ids = recipe ids.
5. **Select a recipe.** If the recipe is known, the client goes straight to 0x123 or 0x124.
   - 0x123 → send 0x353 for the missing templates, then 0x352 {id}.
   - 0x124 {id} → send **0x354**: every bag item whose template matches an ingredient, as {handle, id}. The window now shows "have / required" and enables Assemble.
6. **Assemble.** The button, or /assemble after the /assemblyaddingredient commands, sends **0x11f** (5 × {recipeId, handle, qty}).
   - Validate:
     - the recipe is learned (else 0x34a 5);
     - the target or nearest station has 0x800000 and is in range (8 or 9);
     - not already busy (7);
     - not trading (10);
     - the ingredients match by template and quantity (2).
   - Send **0x34b** {"Assembling <name>", seconds}.
7. **Finish.** After the delay:
   - consume the ingredients (0x1a5 removes an item, 0x1ae reduces a stack);
   - add the product (0x197, or 0x353 + 0x197);
   - send **0x349**;
   - re-send 0x354 so the counts refresh.
   - On failure, send 0x34a {code}.
   - If the client ignores 0x34b (or seconds = 0), still send 0x349.

## Open questions [I]
- The meaning of 0x120 and of recipe fields f3 / f6.
- The root tree node id, and the purpose of the -3 parent special case in `FUN_0045e820`.
- Whether the item template cache is keyed by field 1. Test this live.
