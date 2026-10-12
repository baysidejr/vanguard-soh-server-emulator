# Crafting (refining) message flow in VGClient.exe

> **Verified live (2026-10-12):** U on the Camp Forge (EntityTypes 0x4) → Crafting Setup with "Copper Ingot" under Normal Recipes → select (0xfe) → Begin (0xfb, 0xfc) → crafting window (Grade, Action Pts 100/100, Stage 1: Smelting) → step → Smelt action (0xf6) → "You create Copper Ingot.", "You gain 120 crafting experience!", "Your crafting session ends."; 2 Copper Ore used, ingot in the bag. Implemented in `server/craft.py` and `login_stub.handle_craft_event`; recipes in `server/content/recipes.json`. The station is a robed NPC for now: race 572 (computed from the BlacksmithForge prop table offset) falls back to the client's placeholder figure, and the skeletal smelter races don't draw. A real forge model is open.

> **Stages, quality and complications (verified live 2026-10-12):** Copper Ingot now has two stages, each with two steps.
> - **Stages.** "Stage 1: Preparation" has Sort Ore and Heat Crucible; "Stage 2: Smelting" has Smelt Ore and Pour Ingot. Each action costs action points (120 in total).
> - **Each action:** the server sends `0x2ed`, `0x2f6` (AP used), `0x30a {step, 100}`, `0x2f7 {stage, 0..252}`, `0x2f8` (quality 0–1000; the window shows grade D/C/B/A at 250/500/750) and `0x2fa` (a 2 s grade flash on the step).
> - **Next stage.** When a stage's steps are done, the server sends `0x30d`, then `0x2f7 {next stage, 0}`. **`0x2f5` is sent only once, at Begin.** It repaints the window as stage 1, so sending it later undoes a stage advance.
> - **Complication.** During stage 2, "Slag Buildup" may appear (60% chance). The server sends `0x308` (red "New Complication: Slag Buildup" screen text) and `0x2f9` (3 complication slots; the client prints "New complication: Slag Buildup!"). While it is active, each action loses 100 quality.
> - **Counter.** The correction entry lists the actions of the counter family (90). Using "Skim Slag" sends the normal `0xf6`. The server answers with an all-empty `0x2f9` ("Complication has been removed: Slag Buildup") and `0x2fa` with step -1 (white screen text "Complication resolved").
> - **Rejections.** Running out of AP sends `0x2ec {"", 6}`; an action that isn't allowed now sends `0x2ec {"", 7}`.
> - **Data.** Recipes in `recipes.json` now take `stages`, `max_ap`, a per-step `ap`, and `complications` (stage, chance, penalty, and the counter action).
> - **Still open:** tools and utilities (`0x2ec` codes 3/4 "Missing tool", `0x300` usable items, `0x2fb` catalysts).


This comes from static analysis only (Ghidra via REA) and has not been tested live. [O] means I read it in code; [I] means I inferred it.
Frame: zone event `u16 2, u32 id, u32 len, payload`. Payloads are packed little-endian, and each wstr is UTF-16LE including its NUL terminator.
The client-side object is `VGClientRefining` (global `DAT_01463980`). Its session state is at `+0x38` [O]:

| state | meaning | set by |
|---|---|---|
| 0 | idle | `FUN_005b9380` (reset, on 0x2fd / cancel) |
| 4 | choosing a recipe | 0x2ea, 0x310 |
| 1 | setting up the workbench (recipe chosen) | 0x303 |
| 3 | crafting: actions allowed | 0x2f5 |
| 2 | an action is running (2 s timer at +0x30) | 0x2ed (only from state 3) |

Server -> client dispatchers: `FUN_005bad40` handles session/window events 0x2e9-0x312. `FUN_005ac760` handles the recipe book (0x2ee-0x2f4, 0x309, 0x11c). `FUN_004b7550` handles the known crafting actions (0x2e4-0x2e8).

---

## 1. Starting a session

### Client -> server [O]
| id | payload | sender | when |
|---|---|---|---|
| **0xfa** | none | `FUN_005af860` ← interact `FUN_00417da0` when the target has `EntityTypes & 0x4` (crafting station). If state != 0 the client prints "You are already crafting." | Use a crafting station. No target id is sent, so use the current target (client `0x5d` first) |
| **0xfe** | MsgIntAndBool `{i32 recipeId, bool8 flag}` (flag = recipe+4 byte) | `FUN_005b2ab0` ← UI `FUN_0068a200` (list type 0x23 selection = `refining_select_recipe`), `/refinesetrecipe` (`FUN_005b51d0`) | Select a recipe in the list |
| **0xfb** | none | `FUN_005b0300` ← UI `FUN_0068a150` (`refining_recipe_select_finish`, the Start button in the recipe picker). Prints "You may not craft at this time." if state != 4 but sends anyway | Confirm the recipe and go to setup |
| **0xfc** | none | `FUN_005af890` ← UI `FUN_0068a130` (`refining_setup_finish`). Needs state 1 and a selected recipe (+4 != -1), otherwise prints "You need to finish setting up..." | Begin crafting |
| 0xff | MsgTwoInts `{i32 itemHandle(+0x650), i32 dropSlot}` | `FUN_005b2910` ← `FUN_0068a300` (drag into the crafting inventory), `/refineadditem`. Only in state 1 | Optional: add an ingredient |
| 0x100 / 0x101 | `{i32 handle}` | `FUN_005b2840` / `FUN_005b29e0` (state 1) | Optional: add or remove an ingredient |
| 0xf9 / 0x108 | `{i32 recipeId}` | `FUN_005aa990` (journal recipe info) | Not needed |

The UI-event-name to handler mapping is [I], because the handler functions sit next to each other in the 0x68a1xx table. The function-to-event-id part is [O].

### Server -> client
- **0x2ea MsgCraftingInitToClient** `{i32 numCraftInvSlots, i32 stationId, bool8 autoFill}`. Handler `FUN_005b8ef0`, registration `FUN_005b0990` [O].
  - field0 → `FUN_004f67f0` = gamevar `InventoryNumCombatSlots`. The crafting inventory is the "combat inventory" [O].
  - field1 → refining+0x34. Reset to -1 on session end. Meaning (station id/type) is [I].
  - bool → `_crafting_auto_fill_selector` checkbox [O].
  - If state != 0 the client prints "Programmer error ... not idle." and ignores the message. On success it sets state = 4 and prints "Select the recipe you wish to use."
- **0x2e9** `{u8 code}`: errors. 0 "That is not a valid crafting target.", 1 "DEBUG - Crafting station missing data.", 2 TooFarAway [O].
- **0x2eb MsgCraftingRecipeSelectResult** `{u8 result, i32 recipeId, wstr, wstr}`. Handler `FUN_005ba6c0`, registration `FUN_005af630` [O].
  - result: **0xff = OK**, 0 "Invalid crafting recipe.", 1 "You can't use that recipe at this station.", 2 "You don't have all the materials..." (still fills the missing-items UI). Anything else → "Setting the recipe failed for unknown reasons." [O]
  - recipeId must already be in the recipe book (`FUN_005a7900`), otherwise "Programmer error ... bad recipe ID" [O].
  - On OK the client prints "Crafting recipe selected: <name>", stores current recipe = id (+4), stores max AP = recipe+0xd4 into +0xc, and resets the stage to 0 [O].
  - The two wstrs feed missing-item text; send them empty [I].
- **0x303** (no payload): state 4 → 1, "You may now set up your workbench." [O]
- **0x2f5** (no payload) "BeginTurnConfig": state → 3, so actions are allowed. If the client is idle it prints "Programmer error" [O].
- Optional: 0x300 MsgCraftingUsableItemsToClient `{i32 count, count × {i32 itemHandle, i32 stepId(-1 "Other Items", -2 "Catalysts"), bool8 }}` (`FUN_005baae0`/`FUN_005b9e80`); 0x305 `{i32 slots, i32 slotsTaken}`; 0x1b0 `{i32 handle, i32 slot}` moves a bag item into the crafting inventory; 0x1b1 `{handle, container, slot}` moves it back; 0x1b2 `{handle}` deletes it from the crafting inventory [O].
- 0x310 (no payload) puts the client back into recipe select (state 4) [O].

### Recipe book (must be filled before 0x2ea)
- **0x2ee** adds a recipe and prints "Refining recipe added: <name>". **0x2ef** is the same parser with the chat line suppressed. ZONE_MESSAGES.md labels 0x2ef as MsgLearnedCraftingRecipe, which is wrong: dispatcher `FUN_005ac760` clears the print flag and then runs the 0x2ee path [O].
- 0x2f2/0x2f3 add or replace a recipe and also refresh the journal; 0x2f4 `{i32 id}` deletes one [O].

**MsgAddCraftingRecipe** (registration `FUN_005bb100`, parsed by `FUN_005bece0`) [O]:
```
wstr  name                       (recipe name)
wstr  description                ("Recipe Skill: %s\r\n\r\n%s")
i32   icon                       -> +0x44
i32   recipeId                   -> +0x08   (the key everywhere)
i32   stepCount N                -> +0x50   (N trailing step records)
i32   maxActionPoints            -> +0xd4
i32   catalystIcon               -> +0x48   (icon of the "Catalysts" pseudo-step) [I]
i32   otherItemsIcon             -> +0x4c   (icon of "Other Items") [I]
i32   kind                       -> +0xe0   0 = refining (RefiningRecipeTree), 1 = finishing
i32   category                   -> +0xe4   refining: 1 General, 2 Unique, else WorkOrder (clamped 1..3); finishing 1 Primary, 2-3 Secondary, 4-5 Misc, 6 Unique (1..7)
i32   usesLeft                   -> +0xe8   <1 = unlimited
bool8 mastered                   -> +0xec
bool8 mastered2                  -> +0xed
i32   skillId                    -> FUN_00d03670 name for "Recipe Skill: %s"
4 x wstr stage names             -> +0x64.. ("Stage %i: %s", FUN_005be0d0)
N x MsgCraftingRecipeAction (a recipe *step*, registration FUN_005bb080):
   wstr name
   i32  icon                     -> step+0x3c
   i32  stepIndex 0..N-1         -> step+0x00 (hotkey / lookup index, FUN_005bb990)
   i32  stepId (= action family) -> step+0x40 (actions whose family == this are offered for the step; 0x2fa/0x300 refer to it)
   i32  unused                   (not stored by this parser)
   i32  stage (0-based, byte)    -> step+0x44 (which CraftingRecipeStepSection<stage> it lists under)
   wstr description
```

### Known crafting actions (the "abilities" the player clicks)
**MsgCraftingActionAdd** (registration `FUN_004b5560`) `{i32 actionId, wstr name, wstr description, i32 icon, i32 family, i32 apCost}` [O].
- **0x2e8** adds silently.
- **0x2e5** adds and prints "<color=yellow>New action acquired: %s".
- 0x2e7 bulk-adds `{i32 count, count × record}`.
- 0x2e6 `{i32 id}` removes one; 0x2e4 clears all.

The window lists, for the selected step, every known action whose `family == step.stepId` (`FUN_004b7070` → `FUN_005b78f0`, tooltip "%s\r\nBase Action Point Cost: %d") [O]. Action ids can be the CRAFTING_ABILITIES range (30000+) [I].

---

## 2. In-session state, actions, updates

### Client -> server [O]
| id | payload | sender | when |
|---|---|---|---|
| **0xf6** | MsgTwoInts `{i32 actionId, i32 -1}` | `FUN_005b3980` ← `FUN_0068b720` (`crafting_activate_action_by_icon` on `_crafting_action_family_entry`), hotkeys `FUN_005b3a60`/`FUN_005b3b20`. Only in state 3, else "You may not choose a crafting action at this time." The slash-command path `FUN_005b52b0`→`FUN_005b2b50` sends `{actionId, i32 arg}` | **Use a crafting action** |
| 0xf7 | `{i32 catalystItem}` (from 0x2fb) | `FUN_005b2bf0` (state 3) | Add catalyst |
| 0xf8 | `{i32 itemHandle}` | `FUN_005b3330` ← `FUN_0068b840` (`mo_refining_use_tool`) | Use a tool item |
| 0x104 | none | sent every time the action-family list is shown (`FUN_005b78f0`/`FUN_005b7e00`) | Ignore [I] |
| 0x103 | none | `FUN_005b3cf0` (step needing item selected) | Ignore |
| 0x105 | none | `FUN_005b0330` (type filter "type1".."type7") | Ignore |
| 0x106 / 0x107 | none | `FUN_0068a2c0` / `FUN_0068a2e0` (UI buttons, most likely `refining_submit_turn` / `refining_finish`) [I] | Treat as "finish now" if desired |

### Server -> client [O]
| id | payload | handler | effect |
|---|---|---|---|
| **0x2ed** | none | `FUN_005b9da0` | Action accepted: +0x30 = 2.0 s "CraftingTimeRemaining" bar, state 3→2, closes the action lists |
| **0x2f5** | none | `FUN_005b9020` | Ready for the next action (state 3) |
| **0x2f6** | `{i32 apUsed}` | `FUN_005b2d50` | +8 = used. Gamevars `RefiningActionPointsUsed` = max−used and `RefiningActionPointBar` (max = recipe maxActionPoints) |
| **0x2f7** | MsgIntAndByte `{i32 stage, u8 progress}` | `FUN_005b2de0` | Progress bar `CraftingStatusBarSection<stage>`, value 0..**252 (0xfc)** full. If `stage` != the current stage, the old one is first filled to 252 |
| **0x2f8** | `{i32 quality}` | `FUN_005b6ae0` | 0..1000 `CraftingQuality` bar; label thresholds 250/500/750 |
| 0x30d | none | `FUN_005b0430`→`FUN_005be530` | Stage++ (shows "Stage %i: %s") |
| **0x2fa** | MsgTwoStringsAndInt `{wstr grade, wstr text2, i32 stepId}` | `FUN_005b9220` | Marks step `stepId` done with grade text ("Excellent!", "Great!", "Good", "Moderate", "Fair", "Poor", "Awful" pick the colour). stepId −1 instead shows `grade` as a floating screen message |
| 0x2f9 | 3 × `[wstr name, i32, wstr, i32, wstr, wstr, i32, i32, i32]` | `FUN_005b5fc0` | Complications/corrections, "New complication: " / "Complication has been removed: " (empty name = slot empty) |
| 0x307 / 0x308 | `{wstr, wstr, i32}` | | Orange/red ("New Complication:") screen text |
| 0x2fb | `{i32 item}` | | "Add secondary ingredient", catalyst available; 0x2fc clears it |
| 0x2ec | `{wstr, u8}` | | "Missing item: / Missing item of type: / Missing tool: " |
| 0x301 | none | | "You do not have enough items selected..." |
| 0x30a-0x30c, 0x30e, 0x30f | | | Step-item state, toolbelt, auto-fill. Not needed |

---

## 3. Completion / close
- No dedicated "item crafted" message was found. Deliver the result with the normal inventory messages [I]:
  - Consume the ingredients: **0x1a5** `{i32 handle, bool8 0}` removes a bag item, or **0x1ae** `{i32 handle, i32 remaining}` reduces a stack (MERCHANTS.md); 0x1b2 `{handle}` if the items are in the crafting inventory.
  - The new item: **0x197** MsgSingleItemInfo (container −1, free slot, new handle, field 74 = 7 crafting component or 22 resource, field 91 = quality grade).
- XP: **0x3d5** `{i32 amount, i32 rest, u8 kind=1, u8 group=0, bool8 0, u64 sourceEid, bool8 0, bool8 0}` → "You gain %i crafting experience!", then **0x3de** MsgScore with fields 12/13/37 (craft level/XP/frac).
- Optional: 0x306 "You have mastered this recipe."
- **0x2fd** (no payload, `FUN_005b9de0`): if not idle, prints "Your crafting session ends." and runs `FUN_005b9380` (state 0, clears recipe/AP/quality/complications, closes windows) [O]. Use it for every server-side end (success, failure, abort).
- Client cancel: `refining_cancel` → `FUN_0068a170`→`FUN_005b99e0`. Confirm = 1 resets the client locally and sends **0xfd** (no payload). The server should return the crafting-inventory items (0x1b1) and may echo 0x2fd (harmless when idle) [O/I].
- `FUN_005b8e20` (no direct caller; a slash-command entry) prints "You stop crafting." and sends **0x102** (no payload). Treat it like 0xfd [O].
- Errors: `0x0e` codes `CantRefine` / `CantRefineNow` exist in the string table [I].

---

## 4. Minimal recipe: "Copper Ingot" from 2 Copper Ore, one action

Constants: recipe 5001, step id/family 1, action 30001 "Smelt", ore handle H (already in the bag from harvesting).

**At login (after the inventory):**
1. S `0x2ef` (silent add): name "Copper Ingot", desc "Smelt two copper ore into an ingot.", icon <any>, id 5001, N=1, maxAP 100, 0, 0, kind 0, category 1, uses 0, 0, 0, skill 0, stage names ["Smelting","","",""], then step: `wstr "Smelt Ore", i32 icon, i32 0 (index), i32 1 (stepId), i32 0, i32 0 (stage), wstr "Melt the ore down."`
2. S `0x2e8` action: `{30001, "Smelt", "Smelt the ore.", icon, family 1, apCost 10}`

**The station:** an NPC pawn whose replicated `EntityTypes` = 0x4 (optionally |0x10).

**Flow:**
3. C `0x5d {u64 station}` (target), C **0xfa**.
4. S **0x2ea** `{i32 8, i32 1, bool8 0}`: recipe picker opens, state 4.
5. C **0xfe** `{i32 5001, bool8 x}` → S **0x2eb** `{u8 0xff, i32 5001, wstr "", wstr ""}`. Optional: S 0x300 `{1, [H, 1, 1]}`.
6. C **0xfb** → S **0x303** (state 1, workbench). You can skip the ingredient placement (0xff/0x1b0) and check the 2 ore server-side.
7. C **0xfc** → S `0x2f6 {0}`, `0x2f8 {500}`, `0x2f7 {0, 0}`, **0x2f5** (state 3).
8. The player clicks step "Smelt Ore" (client sends 0x104, ignore) and then "Smelt" → C **0xf6** `{30001, -1}`.
9. S **0x2ed**. Optionally `0x3d1` visual (e.g. 30203 ANIMATION_PC_HAMMER1 or 30127 smelter, from CRAFTING_ABILITIES.aby). Then `0x2f6 {10}`, `0x2f7 {0, 252}`, `0x2f8 {750}`, `0x2fa {"Great!", "", 1}`.
10. Finish: `0x1ae {H, qty-2}` (or `0x1a5 {H,0}` if exactly 2), `0x197` Copper Ingot (new handle, free slot, type 7), `0x3d5 {25,0,1,0,0,playerEid,0,0}`, `0x3de` MsgScore, **0x2fd**.
11. On C 0xfd / 0x102 at any point: return items, and S 0x2fd.

Open points:
- Exact UI-name ↔ 0x106/0x107 mapping.
- Meaning of 0x2ea field1 and of the 0x2eb strings.
- The unused step i32.
- Whether retail sent 0x30d between stages (0x2f7 alone is enough for the client).
- Whether 0x2f5 must follow 0x2ed before 0x2fd (not needed for the client).
