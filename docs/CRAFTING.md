# Crafting (refining) message flow in VGClient.exe

> **Verified live (2026-10-12):** U on the Camp Forge (EntityTypes 0x4) → Crafting Setup with "Copper Ingot" under Normal Recipes → select (0xfe) → Begin (0xfb, 0xfc) → crafting window (Grade, Action Pts 100/100, Stage 1: Smelting) → step → Smelt action (0xf6) → "You create Copper Ingot.", "You gain 120 crafting experience!", "Your crafting session ends."; 2 Copper Ore used, ingot in the bag. Implemented in `server/craft.py` and `login_stub.handle_craft_event`; recipes in `server/content/recipes.json`. The station is a robed NPC for now: race 572 (computed from the BlacksmithForge prop table offset) falls back to the client's placeholder figure, and the skeletal smelter races don't draw. **Forge model (verified live):** race 572 "BlacksmithForge" can never draw. The client's race table points it at the object `Ra8001_P1_CraftBlacksmith_furnace001` inside the package `Ra1_P1_craftBlacksmith_mesh`, which doesn't contain it, so the client falls back to a placeholder. No other race is a forge. The Camp Forge now uses race 600 **GenericBrazier**, an iron fire bowl.

Other static-mesh races that load (checked against the packages):
- crafting stations: 655 BlackCauldron, 578/1084 GemTable, 551 SawMill, 568 TailorSpinningWheel, 571 AlchemyFlask, 808 FabricRack, 750 Fireplace
- chests: 590, 607, 1072
- tents: 603, 604, 619, 654
- campfire: 1087
- banners: 631, 644
- barrels: 588, 740

Ore race 536 has a broken package name, so the vein now uses 537.

**Camp props (verified live):** mob templates with `"prop": true` are scenery that can't be attacked. The camp now has a campfire (race 1087 at `"scale": 0.1`, since the mesh is building-sized at 1.0), a supply chest (1072) and a banner (631). `scale` sets the pawn's replicated DrawScale. The tents (619, 654) are full-size pavilions that cover the camp, so none is placed.

> **Stages, quality and complications (verified live 2026-10-12):** Copper Ingot now has two stages, each with two steps.
> - **Stages.** "Stage 1: Preparation" has Sort Ore and Heat Crucible; "Stage 2: Smelting" has Smelt Ore and Pour Ingot. Each action costs action points (120 in total).
> - **Each action:** the server sends `0x2ed`, `0x2f6` (AP used), `0x30a {step, 100}`, `0x2f7 {stage, 0..252}`, `0x2f8` (quality 0–1000; the window shows grade D/C/B/A at 250/500/750) and `0x2fa` (a 2 s grade flash on the step).
> - **Next stage.** When a stage's steps are done, the server sends `0x30d`, then `0x2f7 {next stage, 0}`. **`0x2f5` is sent only once, at Begin.** It repaints the window as stage 1, so sending it later undoes a stage advance.
> - **Complication.** During stage 2, "Slag Buildup" may appear (60% chance). The server sends `0x308` (red "New Complication: Slag Buildup" screen text) and `0x2f9` (3 complication slots; the client prints "New complication: Slag Buildup!"). While it is active, each action loses 100 quality.
> - **Counter.** The correction entry lists the actions of the counter family (90). Using "Skim Slag" sends the normal `0xf6`. The server answers with an all-empty `0x2f9` ("Complication has been removed: Slag Buildup") and `0x2fa` with step -1 (white screen text "Complication resolved").
> - **Rejections.** Running out of AP sends `0x2ec {"", 6}`; an action that isn't allowed now sends `0x2ec {"", 7}`.
> - **Data.** Recipes in `recipes.json` now take `stages`, `max_ap`, a per-step `ap`, and `complications` (stage, chance, penalty, and the counter action).
> - **Tools (verified live).** A step may name a `tool`, an item that must be in the bags. Smelt Ore needs Crucible Tongs, which Orin sells. Without it the server sends `0x2ec {"Crucible Tongs", 3}`, and the client prints "Missing tool: Crucible Tongs".
> - **Missing-item steps (verified live 2026-10-14).** At Begin and at each new stage the server sends `0x30b {i32 step id}` for every step of that stage whose tool or utility item is not in the bags (`craft.missing_steps`). The client dims that step's icon (`FUN_005bcdd0` sets a flag on the step row; `0x30c` / `FUN_005bcfa0` clears it). It only finds steps of the current stage, so flags for later stages are sent when the stage starts. Seen live: with Crucible Tongs but no Mould Oil, Stage 2's Mould Oil step was dimmed and the tongs step was not; without the message neither was.
> - **Catalysts (verified live):** a recipe's `catalyst` `{item, quality}` is offered at Begin with `0x2fb {item handle}`, which prints "Add secondary ingredient" and shows "Add Catalyst". The client's catalyst window (`VGUICraftingCatalyst.xml`, shown by the `CraftingCatalystAvailable` gamevar; the entry is built by `FUN_005b8310`) did not appear, so the server also accepts right-clicking the catalyst in the bags during a craft. Right-clicking Smelting Flux printed "You add Smelting Flux to the mixture." and raised the grade from D to B (65%) before any step (`0x2fc`, `0x2f8`). Clicking the window entry would send `0xf7 {handle}`, which takes the same path. Smelting Flux sells at the camp merchant for 30 copper.
> - **Still open:** toolbelts and utilities (`0x300` usable items), and why the catalyst window stays hidden.


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
| 0xf9 / 0x108 | `{i32 recipeId}` | `FUN_005aa990` (journal recipe info) | Answered (see "Journal recipe page") |

The UI-event-name to handler mapping is [I], because the handler functions sit next to each other in the 0x68a1xx table. The function-to-event-id part is [O].

### Server -> client
- **0x2ea MsgCraftingInitToClient** `{i32 numCraftInvSlots, i32 stationId, bool8 autoFill}`. Handler `FUN_005b8ef0`, registration `FUN_005b0990` [O].
  - field0 → `FUN_004f67f0` = gamevar `InventoryNumCombatSlots`. The crafting inventory is the "combat inventory" [O].
  - field1 → refining+0x34. Reset to -1 on session end. Meaning (station id/type) is [I].
  - bool → `_crafting_auto_fill_selector` checkbox [O].
  - If state != 0 the client prints "Programmer error ... not idle." and ignores the message. On success it sets state = 4 and prints "Select the recipe you wish to use."
- **0x2e9** `{u8 code}`: errors. 0 "That is not a valid crafting target.", 1 "DEBUG - Crafting station missing data.", 2 TooFarAway, which the client prints as "You're too far away to do that." (sent when the station is more than 800 units away; verified live 2026-10-14).
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
- **0x2e5** adds and prints "<color=yellow>New action acquired: %s". The server uses it for actions learned during play (a recipe bought from a trainer, a work order's recipe) that no recipe in the book already had; seen live 2026-10-15 ("New action acquired: Heat Ingot" ... for Copper Wire). Login uses 0x2e8.
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

## Utilities and toolbelts (verified live 2026-10-13)

- **Utilities:** a recipe step can need a consumable (`"utility": {"item", "qty"}`; Copper Ingot's "Pour Ingot" step needs Mould Oil, sold at the camp merchant for 5 copper). The client never checks tools or utilities; the server does on the action (0xf6): without the oil it answers 0x2ec {"Mould Oil", 1} ("Missing item: Mould Oil"), with it "You use Mould Oil." and one is taken from the bags. Tools and utilities in the bags are listed under their steps on the Table Setup screen with 0x300 {n, (item handle, step id, selected)} sent before the 0x2eb recipe OK (the catalyst under step -2).
- **Toolbelts:** crafting equip slots are now known (66 tool, 67-69 the three toolbelts; vgmsg.EQUIP_SLOTS). `/craftingchangeactivetoolbelt 2` sends 0xa4 {68}; the server saves the active belt and answers 0xa5 {68} (the Toolbelts window checkmarks) and 0x30e (closes it). 0xf8 {belt handle} (clicking a belt in the Toolbelts window) does the same; it is not "use tool". Tools are still found anywhere in the bags; belt contents are not enforced yet. The saved belt is sent again (0xa5) at every zone-in, so the checkmark survives a relog.

The rest is the client analysis (static, by a research agent).


[O] = read in code or XML; [I] = inferred. Frame: zone event `u16 2, u32 id, u32 len, payload`.

### 0. Short answers
- **The client never decides whether a tool is available.** Recipe steps (0x2ee/0x2ef) and actions (0x2e8) have no tool or utility field. `FUN_005b3980` (0xf6) checks only state 3. The active toolbelt index at inventory+0x6b4 is read only by the 0xa5 handler that sets the checkmarks [O]. No client code walks the toolbelt contents [I: no other reader found]. The server checks tools and utilities when it gets 0xf6. To reject, send `0x2ec {wstr name, u8 code}`: 3 "Missing tool: X", 4 "Missing tool of type: X", 1 "Missing item: X", 2/8 "Missing item of type: X". `server/craft.py` already does this.
- **Making a tool show as "available"** needs nothing: an action is clickable whenever its family matches the step. To display tools or utilities under a step, list them in **0x300** (below).
- **Utilities** are placed into the *crafting inventory* (the client's "combat inventory") during Table Setup. The server consumes them when an action that needs one is used. There is no separate "use utility" event: the action itself is the plain `0xf6`. The reply is the normal action reply plus `0x1b3 {handle, newCount}` (stack shrinks) or `0x1b2 {handle}` (gone).
- **Toolbelt** = a *container* item (field 74 item type 11/12/18, field 14 capacity > 0, field 71 its container id) equipped in slot **CRA_WAIST1/2/3 = 67/68/69 (0x43/0x44/0x45)**. Tools are items of **type 2 "Crafting Tool"** stored inside the belt. Field 97 (+0x580) is the tool tier; with tier > 0 the tooltip says "Crafting Tool".

### 1. Equip slots (FUN_0050cc10 tag table, values 0x50db9f..0x50dfc8) [O]
HAR_TACKLEBOX 54, CRA_HEAD 55, CRA_APRON 56, CRA_CHEST 57, CRA_LEGS 58, CRA_HANDS 59, CRA_FEET 60, CRA_LEFTFINGER 61, CRA_RIGHTFINGER 62, CRA_LEFTEAR 63, CRA_RIGHTEAR 64, CRA_CONTAINER 65, **CRA_TOOL 66**, **CRA_WAIST1 67, CRA_WAIST2 68, CRA_WAIST3 69**.
(HEAD=0 and EYES=1 confirm the mapping.) Add these to `vgmsg.EQUIP_SLOTS`.
- The paper doll (VGUICharacter.xml ~4490) and the "Toolbelts" window (VGUICraftingToolbelts.xml) both show slots CRA_WAIST1..3. A green check appears on the one whose gamevar `bToolbelt<N>Active` is set.
- Localised text in bin\VGClient.int: "Toolbelt 1/2/3", "Change Toolbelts", and the 0x0e codes **0x11c** DontChangeToolbelt, **0x11d** CantChangeToolbelts ("Unable to change toolbelts at this time."), **0x11e** CantEquipNonToolbelt, **0x141** NeedToolbeltToCraft ("You must be wearing a toolbelt to craft.").
- Tooltip (FUN_006b2920): a container whose default slot (field 8) is a waist slot reads "<slot name> (N Slots)". Type 2 with tier > 0 reads "Crafting Tool" [O].

### 2. Active toolbelt
- C **0xa4** `{i32 slot}` (`FUN_004fa090`; it sends only for 0x43..0x45) [O]. It is sent from:
  - `/craftingchangeactivetoolbelt 1|2|3` (`FUN_00607a30`). Any other number prints "Invalid toolbelt number...".
  - Using (`equipment_use`, UI case 0x79 → `FUN_0068de60`) an equipped container whose equip slot is 0x43..0x45.
- C **0xf8** `{i32 itemHandle(+0x650)}` (`FUN_005b3330`) is sent by UI event 0x169 `crafting_change_toolbelt_by_icon` (`FUN_0068b840`): left-clicking a belt in the Toolbelts window [O]. **This corrects CRAFTING.md**, which calls 0xf8 "use tool" / `mo_refining_use_tool`. `mo_refining_use_tool` (0x15f) belongs to the old RefiningStatus window and has no case in the UI dispatcher `FUN_006a8060`, so it is dead.
- S **0xa5** `{i32 slot}` (`FUN_004f9f30`): stores inventory+0x6b4 and sets bToolbelt1/2/3Active = (slot == 0x43/0x44/0x45) [O]. At init bToolbelt1Active = 1 (`FUN_005113b0`). Send 0xa5 at login and as the reply to 0xa4/0xf8.
- `/craftingchangetoolbelt` (`FUN_005fc360`) only toggles the gamevar `CraftingChangingToolbelt`, which shows the Toolbelts window under the crafting window. There is also a "Toolbelt" button in VGUICrafting.xml. Nothing is sent. S **0x30e** (no payload, `FUN_005b0280`) clears it (closes the window) [O]. Send 0x30e after the switch.

### 3. Table Setup screen (state 1; "Crafting Table Setup" in VGUICraftingInventory.xml, visible on gamevar CraftingIsSetupOrCrafting)
Layout: on the left, a "Steps" list (gamevar `CraftingRecipeStepsRequiringItems`). Below it, "Select a step above and choose an item below:" with the item list (`CraftingRecipeUsableItemList`, each entry shows icon, name, a charges/qty number and a green check when selected). Then an auto-fill checkbox, a "slots" label (CombatInvSlotsTaken / InventoryNumCombatSlots), and the buttons Begin / Back / Cancel.

**S 0x300 MsgCraftingUsableItemsToClient** `{i32 n, n × {i32 itemHandle, i32 stepId, bool8 selected}}` (`FUN_005baae0` → `FUN_005b9e80`) [O]:
- Each call replaces the list at refining+0x1c8.
- Each record gets the item's name and icon from the bag (`FUN_004fa970`) or from the crafting inventory (`FUN_004faa70`). "Unknown Item" means neither has it. Count = charges (field 33) if nonzero, else quantity if > 1.
- Step list (`FUN_005b9fd0`) = the distinct stepIds in 0x300, in order. A real stepId uses the recipe step's name (`FUN_005bba10`, matching step+0x40 = the step's family id). **-1** = "Other Items / Items that might be useful"; **-2** = "Catalysts / Items that combine well with the primary ingredient".
- The list is rebuilt by the **0x2eb OK handler** (`FUN_005ba6c0` → `FUN_005b9fd0(recipe,1)`, auto-selecting the first step) and by the tick (`FUN_005ba5d0`) when the selected step changes. **So send 0x300 before 0x2eb {0xff}** [O].

Client events during setup:
| UI event | handler | sends |
|---|---|---|
| 0x168 `crafting_select_step_needing_item` | `FUN_0068b810`→`FUN_005b3cf0` | sets R+0x1d4 = stepId, lists items with that stepId, **C 0x103** (no payload). In state 3 it only lists the *selected* items (`FUN_005b2f50`) and sends nothing |
| 0x0e `_scroll_window_select_crafting_item` | `FUN_00686f20`→`FUN_005b2ea0(handle)` | not selected → **C 0x100 {i32 handle}** (`FUN_005b2840`, "add to crafting inventory"); selected → **C 0x101 {i32 handle}** (`FUN_005b29e0`). Both are allowed in state 1 only; otherwise the client prints "You may only manipulate your crafting inventory during the crafting setup process." |
| drag from bag to the crafting inventory (`FUN_0068a300`) | `FUN_005b2910` | C 0xff {handle, slot} |
| 0x10e `crafting_auto_fill_inventory_toggle` | `FUN_0068a2c0`→`FUN_005b0400` | **C 0x106** (no payload) [O] |
| 0x10f `refining_setup_back` | `FUN_0068a2e0`→`FUN_005b05e0` | **C 0x107** (no payload) [O] |
| 0x103 `refining_setup_finish` (Begin) | `FUN_0068a130` | C 0xfc |
| 0x105 `refining_cancel` | `FUN_0068a170` | C 0xfd |

(These correct CRAFTING.md: 0x106 = auto-fill toggle and 0x107 = Back, not submit/finish.)

Server replies:
- **0x100 accepted** → S **0x1b0 {i32 handle, i32 craftSlot}** (`FUN_0050ebf0`). It moves the bag item into the crafting inventory and toggles the item's `selected` flag (`FUN_005b49b0`): green check [O]. Then S **0x305 {i32 slots, i32 slotsTaken}** (`FUN_005b33b0`; InventoryNumCombatSlots / CombatInvSlotsTaken) [O].
- **0x101** → S **0x1b1 {i32 handle, i32 container(-1), i32 slot}** (`FUN_00512e30`). It moves the item back to the bag and toggles the flag off (`FUN_005b49b0`) [O]. Then 0x305.
- **0x106** → S **0x30f {bool8}** checkbox (`FUN_005b3640`) [O]. If on, the server may auto-place everything (one 0x1b0 per item) [I].
- **0x107** → S **0x310** (back to recipe select, state 4) after returning the placed items with 0x1b1 [I].
- **Implemented (verified live 2026-10-14 at the Camp Forge).** "Auto Setup Table" (0x106) is answered with 0x30f {1}, and the checkbox shows the tick. This server always places the recipe's utilities and tools itself, so the box stays on. Back (0x107) is answered with 0x310: the window returns to "No recipe selected" and the client prints "Select the recipe you wish to use.". No items need returning, because this server never moves them into a crafting inventory. Selecting the recipe again and crafting works as before.
- **0x103** needs no reply [I].
- Optional per-step highlight: S **0x30b {i32 stepId}** sets and **0x30c {i32 stepId}** clears a flag on that step's entry in the crafting window (current stage only; `FUN_005bcdd0`/`FUN_005bcfa0`). Probably "this step still needs an item/tool" [I].

### 4. During crafting (state 3)
- The same list, filtered to the **selected (placed)** items of the clicked step, stays visible (`FUN_005b2f50`). Clicking an item does nothing useful (0x100/0x101 are refused locally).
- Utilities are used through actions: C `0xf6 {actionId, -1}`. The server checks that the step's utility is in the crafting inventory and consumes one:
  - S **0x1b3 {i32 handle, i32 newCount}** (`FUN_00506740`, "stack changed") updates the bag and the usable-item count (`FUN_005b3220(h,count,1,0)`).
  - At zero, S **0x1b2 {i32 handle}** (`FUN_00506540`, "deleted") clears the item's `selected` flag [O].
  - If the utility is missing: `0x2ec {"<utility name>", 1|2}`.
- Tools are not consumed. Check that the **active** toolbelt (the 0xa5 slot) contains the tool item: otherwise `0x2ec {"<tool>", 3}`, or `{"<tool type>", 4}`. Optionally lower durability (field 106) with a normal item update [I].
- At the end, unused crafting-inventory items go back with 0x1b1, or are deleted with 0x1b2 if consumed.

### 5. Recommended server flow
1. **Login:** inventory with the toolbelt equipped (0x197: equip slot 67, field 74 = 11, field 14 = capacity, field 71 = belt handle, field 8 = 67, allowed-slot mask 67..69). Tools sit inside the belt (field 15 = belt handle, field 16 = slot, type 2, field 97 = tier ≥ 1). Then **S 0xa5 {67}**.
2. **C 0xa4 {slot} / C 0xf8 {beltHandle}:** if the slot holds a belt, set it active, then S 0xa5 {slot} and S 0x30e. During an action (state 2) reply 0x0e 0x11d. If the belt isn't one, reply 0x0e 0x11c.
3. **C 0xfa (station):** with no belt equipped in 67..69, send 0x0e **0x141** NeedToolbeltToCraft and stop (optional, retail behaviour [I]). Otherwise send 0x2ea as now.
4. **C 0xfe (recipe):** build the 0x300 list from the bags. For each step that needs a utility, list the matching bag stacks `{handle, stepId(step family), 0}`. Put the catalyst item under -2 and other useful items under -1. Tools can be listed too (handles inside the belt) so the player sees them [I]. **Send 0x300, then 0x2eb {0xff,…}**, then 0x305 {slots, 0}.
5. **C 0xfb** → 0x303 (state 1, Table Setup visible).
6. **Setup:** on 0x100 {h}, move the stack into the crafting inventory: S 0x1b0 {h, slot}, 0x305. On 0x101 {h}: S 0x1b1 {h, -1, bagSlot}, 0x305. On 0x106: toggle and send 0x30f, auto-placing if on. On 0x107: return items, then 0x310. Ignore 0x103.
7. **C 0xfc (Begin)** → as now (0x2f6/0x2f8/0x2f7/0x2f5). Optionally send 0x30b {stepId} for steps whose tool or utility is missing.
8. **C 0xf6 per action:** look up the step's `tool` (in the active belt) and `utility` (in the crafting inventory).
   - Missing → 0x2ec {name, 3|4|1|2} (the client re-enables the lists only on code 0, so also send 0x2f5 [I], or keep the current behaviour that already works live).
   - OK → current reply set, plus 0x1b3/0x1b2 for the consumed utility. Utilities can add quality or remove complications, the same way the catalyst does.
9. **End (success/cancel 0xfd/0x102):** 0x1b1 the leftover crafting-inventory items back to the bags, then 0x2fd.

Recipe data suggestion: per step `"tool": "Crucible Tongs"` (already supported) and `"utility": {"item": "Smelting Flux", "qty": 1}`. Items need `"type": "crafting_tool"` (2), `"toolbelt"` (container 11 with `"slots"`), `"utility"` (type 7, crafting component, or 22).

### 6. Open points
- What retail listed in 0x300 for tools, and the exact meaning of 0x30b/0x30c.
- Whether retail required the station's step utility to be placed in setup, or also accepted it from the bags.
- The toolbelt's own item type (11, 12 or 18) — any container type works for the client.

## Refining and finishing stations (verified live 2026-10-13)

When a station is used (client 0xfa) the server sends **0x304 `{i32 n, n × i32 recipe id}`** (handler FUN_005bac40) before opening the window. The Crafting Setup window lists exactly these recipes and shows the refining page or the finishing page by the `kind` of the **first** one (`nRecipeSelectRefineOrFinish`, FUN_005aa0c0). The finishing page groups recipes under Work Order Recipes, Primary Components, Secondary Components, Miscellaneous Recipes and Special Recipes (category 1, 2-3, 4-5, 6). The journal's crafting page shows both trees (FUN_005a8f50).

In `mobs.json`, `station: true` is a refining station and `station: "finishing"` a finishing station; the server sends the book recipes of that kind (`zone.book_recipes`) and refuses a recipe that isn't in the player's book. Test: the Finishing Table at the Ranger camp (`!tp -30750 -5300 g 0`, `!give Copper Ingot`) makes a Copper Buckle (Miscellaneous Recipes).

The recipe window's "Recipe Skill" is the recipe's `skill` stat id (`stat_names.py`): the buckle uses 0x46 Smithing. Which skill each real finishing recipe used is server data (the client's per-craft lists are `PCCraft<Craft>FinishingSkillList`).

## Journal recipe page (verified live 2026-10-15)

The crafting journal's recipe page (Abilities window, Crafting tab: Refining / Finishing) stayed blank. Selecting a recipe sends **0x108** `{i32 recipe id}` and shows nothing until the server answers (FUN_005aa990 only sends while the recipe's "details pending" byte, +4, is set). The answer is **0x2f2**, the full recipe in the same layout as the 0x2ee add (FUN_005ac180 updates the recipe and redraws the page). The client then shows the name, icon, "Recipe Skill" and description. **0x309** `{i32 count, count x i32 step id}` adds the red "Steps missing items: <step>, ..." line for steps whose tool or utility the player doesn't carry (`craft.missing_steps`). Seen: Copper Ingot "Steps missing items: Pour Ingot", and Copper Buckle (finishing) with nothing missing. Only recipes in the player's book are answered.
