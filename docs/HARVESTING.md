# Harvesting in VGClient.exe: resource nodes, start/stop, progress UI, rewards

> **Verified live (2026-10-12):** a Copper Ore Vein (SGONPCPawn race 172, EntityTypes 0x800); /con gives the harvesting lines; U (or the client's 0x109) opens the Harvesting window "Mining - Copper Ore Vein" with a progress bar; four strikes later "You harvest 3 Copper Ore." and the ore is in the bag. Implemented in `server/harvest.py` and `login_stub.handle_harvest_event/harvest_tick`; nodes are mob templates with a `harvest` block. 

> **Tools and skills (verified live 2026-10-12):**
> - **Tool check.** Harvesting needs a tool in the equip slot `0x35` "Harvesting Tool" whose items.json `harvest` kind matches the node. A "Miner's Pick" has item type 16 and right-click equips it to slot `0x35`. Without the tool the server sends `0x252 {"Mining", 0x22}`, and the client prints "You failed to use Mining because you do not have a tool that harvests the right type of resource equipped."
> - **Skill check.** Mining is skill stat `0x0f` (subtype 0x15). If it is below the node's `skill`, the server sends `0x0e 0x7b`.
> - **/con.** The con value is 10–14, computed from the player's skill against the node's `difficulty`.
> - **Skill-ups.** A successful harvest may raise the skill by 1. The server sends `0x2d4` and the chat line "Your Mining skill has increased to N." Skill values are saved with the character. Use the static-prop races (e.g. 536 OreMedium) for visible nodes: race 172 (RockOre) showed only a name plate.


Static analysis only (Ghidra via REA, plus the client's .u/.aby packages read with `server/upackage.py`).
[O] means seen in code or data. [I] means inferred.
Zone events use the usual frame: `u16 2, u32 id, u32 len, payload` (little-endian).

---

## 0. TL;DR

- **A resource node is an ordinary `SGONPCPawn` whose replicated `EntityTypes` has bit `0x800`.** [O] The race only picks the model. Good ore models: race **172 RockOre** (skeletal, model variants 0..3), **176 RockMineral**, or the static-mesh props **536..550** (`OreMedium*`/`OreSmall*`).
- **Start harvesting:** when the target has `EntityTypes & 0x800` (and is not a corpse), interacting with it makes the client send **client event `0x109`, no payload**. The client sends no target id; the server uses the current target (the client selects it first). [O] It is **not** `ServerUse`, and it is **not** `0xd0`.
- **Stop:** `/endharvesting` sends **client `0x10a`, no payload**. [O]
- **Server → client harvesting UI:** dispatcher `FUN_004f54d0`, events `0x2dc`–`0x2e3`. [O]
  1. `0x2dc` opens the window.
  2. `0x2dd` "Harvesting has begun."
  3. `0x2df` updates progress.
  4. `0x2e1` sends the reward list, `0x2e2` the reward item records, `0x2e3` refreshes the window.
  5. `0x2de` "Harvesting has ended."
- **Errors:**
  - `0x0e` i16 codes: `0x77` AlreadyHarvesting, `0x7a` ResourceAlreadyHarvested, `0x7b` NeedSkillToHarvest, `0x7c` CannotHarvestResource, `0xeb` HarvestBeforeLooting, `0x159` CantAttackHarvestResource.
  - Tool failures: `0x252` {wstr, i32 `0x20..0x23`}, or the ability-fail code `0x16` on `0x241` or `0x1c5`.
- **Tool:** item type 16 (field 74). The equip slot is **`0x35` "Harvesting Tool"**; the harvesting pack slot is `0x29`. [O] The client does no tool check before sending `0x109`. All checks are server-side, and the client only prints the failure codes.

---

## 1. How a resource node appears in the world

### 1.1 Pawn class and the `EntityTypes` flag [O]

`SGOUnrealPawn` has a replicated `IntProperty EntityTypes`. It is net field 108 in the `SGONPCPawn` net cache: I dumped the class's net fields with `server/netcache.py`, and field 108 is EntityTypes.

- **Pawn offset `+0xaf8`.** SGOUnrealPawn properties are laid out in reverse export order after `m_Customization` (+0xaa8, 64 bytes): `m_GameplayLevel` +0xae8, `m_GameplayClass` +0xaec, `m_PointsValue` +0xaf0, `GravityPlane` +0xaf4, **`EntityTypes` +0xaf8**, `m_Rank` +0xafc, `m_ConsiderRating` +0xb00. [O/I]
- The hover code backs this up: it reads +0xae8 as the level and +0xaec as the class (`FUN_00d07120`).

Bits, from the hover/cursor code `FUN_00418060` and the interact code `FUN_00417da0` [O]:

| bit | meaning (hover gamevar / cursor) | interact action (`FUN_00417da0`) |
|---|---|---|
| 0x2 | corpse (CorpseHover; loot cursor if `+0x37c & 1`, or **bit 0x800**, or race 0x24b) | loot (`FUN_005203d0`) — checked first |
| 0x4 | crafting station | `FUN_005af860` |
| 0x8 / 0x0e000000 | merchant | — |
| 0x10 | NPC (NonPlayerHover) | — |
| 0x20 | player | context window |
| 0x40 | trainer; 0x80 recipe trainer; 0x200 task master; 0x100000 assembly trainer | |
| 0x100 | banker | |
| **0x800** | **resource: `Harvestable.cur`, "ResourceHover"** | **`FUN_004f1c10` → send `0x109`** |
| 0x8000 | interactable (`0x184 {u64 id}`) | |
| 0x20000 | mailbox | `FUN_00525140` |
| 0x800000 | — | `FUN_00450310` |
| 0x1000000 | altar | |
| 0x10000000 | attackable (sword cursor when faction < -7999) | otherwise `0x2b0` |

So for an ore vein, send `EntityTypes = 0x800`. Adding `0x10` for the NPC hover panel is optional and untested. [I]

A corpse with `0x2|0x800` (a skinnable corpse) shows the loot cursor, and interacting with it loots rather than harvests. The server answers with `HarvestBeforeLooting` (`0x0e` code `0xeb`). [O/I]

### 1.2 Race (model) ids [O]

The static-mesh "races" are filled by `FUN_00bd7650` (race id = (entry offset − 0xe4200)/4). Resource-looking entries:

| id | name | mesh |
|---|---|---|
| 530 / 531 / 532 / 569 / 570 | TreeMediumOne / TreeMediumTwo / TreeLargeOne / TreeBareOne / TreeSmallOne | Ra8500_P1_TreeBirch_* |
| 567 | StumpSmallOne | TreePine stump |
| 533 / 579 / 580 | GrassClump Two/One/Three | BushesGrasses |
| 534 / 535 | HerbBushOne / HerbSproutOne | BushesGrasses_Herb001 |
| **536–543** | **OreMedium Eight/Five/Four/One/Seven/Six/Three/Two** | **Ra8500_P1_Mines_MineRockOre001_Med0N** |
| **544–550** | **OreSmall Five/Four/One/Seven/Six/Three/Two** | MineRockOre001_Sml0N |
| 552–566 | StoneMedium*/StoneSmall* (quarrying) | MineRockStone001 |
| 573 | Bramble | C1_Trees |
| 574 | BushIrishYew | |
| 575–577 | GemSmall One/Three/Two | MineRockGem001 |
| 671–676 | Red/Yellow/Pink/Violet/Orange/BlueFlowerPod | Flowerpods |
| 677 / 682 / 683 | CorpseFlower / BlackLotusPatch / OrchidPatch | LargeFlowers |

Skeletal "creature" races that look like real harvest nodes (from the `docs/CREATURES.md` table):
- 172 **RockOre** [0..3], 176 RockMineral [0..3]
- 174 PlantAlchemical [0..7], 175 PlantTextile [0..4]
- 180–184 TreeAsh/Aspen/Beech/Cottonwood/Oak, 169 TreePine
- 295 MushroomAlchemical, 296 RootWood, 330 Crystal
- 229 RockCaveIn: the node-collapse effect (used with visual 20081 "NPC_PARTICLE_CAVEIN_DEATH")

I recommend **race 172 (RockOre), `m_iModelNum` 0..3** for ore. It is a skeletal mesh, so the per-strike reaction visuals (`REACTION_NPC_SPARK`, dirt whirl) can animate on it. [I]

The race only selects the mesh. Nothing in the race table marks a race as "harvestable". That comes only from `EntityTypes`. [O]

### 1.3 /con on a node [O] (`FUN_005e7670`, event `0x3da`)

Payload: `{i32 kind, i32 con, i32 difficulty, i32 level, wstr name, wstr tool}`. Harvesting uses **kind = 3**, and the con values are **10..14**, not 0..7:

| con | text |
|---|---|
| 10 | "%s is trivial for you to start harvesting." |
| 11 | "%s is easy for you to start harvesting." |
| 12 | "%s is just right for you to start harvesting." |
| 13 | "%s is too difficult for you to start harvesting." |
| 14 | "%s is much too difficult for you to start harvesting." |
| any other | "This is a harvesting NPC." |

After that line, unless con == −1, the client appends "  Harvesting this resource requires a %s tool." using the **tool wstr** (for example "Mining"). For kind 3, difficulty and level are ignored. Kinds other than 0 and 3 print "Consider what?".

---

## 2. Client → server

| id | payload | sent by | meaning |
|---|---|---|---|
| **0x109** | none | `FUN_004f1c10` (thunk: `push 0x109; call FUN_004cfb50`), called from interact `FUN_00417da0` when the target has `EntityTypes&0x800` and not `&2`; also from the UI command dispatcher `FUN_006a8060` (at 0x6a95b8) | **Begin harvesting the current target** [O]. Before it, `FUN_004d01d0(pawn,1,1)` selects the pawn as target, so the server gets the usual `0x5d {u64 id}` first [I] |
| **0x10a** | none | `/endharvesting` command (table entry at 0x13eecc0 → stub 0x5fcdb0: `push 0,0,0x10a; call FUN_00409210`) | Stop harvesting [O] |
| **0x10b** | `i32 count, count × i32 itemId` (each element is a serialized MsgSingleInt, `FUN_00422cd0`) | `FUN_004f2ae0` ← `FUN_004f4ef0` | Request item records for reward ids the client cannot resolve (`FUN_00517390` lookup failed). The server answers with `0x2e2` per item [O]. Handled (2026-10-14): the ids are bag items, answered with their records and 0x2e3. Unit-tested; the client never asked in live harvests, because the records are sent with the rewards |
| 0x3d9 | none | `/con` | Consider → reply with `0x3da` kind 3 [O] |
| 0xd0 | i32 ability handle | ability use | Only if you give harvesting abilities. Not needed to start harvesting [O] |

`/harveststats` (stub 0x5fcda0 → 0x4f1bd0) is client-only. It prints "You aren't harvesting." or "Quantity: Current=%d", reading object +0x18. [O]

The client-side harvesting state object is `DAT_0146397c`:
- +0x00 bHarvesting (u8)
- +0x04 / +0x08 target SI current / max (f32; 0x2dc sets both to 18.0)
- +0x0c skill id
- +0x10 / +0x14 node eid
- +0x18 quantity (f32)
- +0x1c "rare items present"
- +0x20 / +0x24 primary / secondary skill
- +0x2c / +0x30 reward vector, 0x14 bytes per entry: {i32 id, i32 qty, i32 rare, Item*, u8 shown, u8 removed}

---

## 3. Server → client (dispatcher `FUN_004f54d0`) [O]

| id | class / handler | payload (wire order) | effect |
|---|---|---|---|
| **0x2dc** | MsgDisplayHarvestingUI / `FUN_004f4850` (schema `FUN_004f1980`) | `u64 nodeEntityId, f32 unused, u8 quantity, u8 skillStatId` | Clears the reward list. Sets quantity (+0x18), skill (+0xc), SI cur = max = 18.0, node eid. Sets `HarvestingActionName` from the skill: **0x0f "Mining"**, 0x32 "Quarrying", 0x4b "Lumberjacking", 0x59 "Reaping", 0x76 "Skinning", 0x79 "Gathering", else "Harvesting". Updates the `bHarvesting` gamevar from +0 and the bars (`FUN_004f3f00`: HarvestingQuantity bar max 6.0, HarvestingTargetSI bar = cur/max) |
| **0x2dd** | none / `FUN_004f1c30` | — | +0 = 1. Chat "Harvesting has begun.". `bHarvesting = 1`, `IsHarvestingDone = 0`, rare flag cleared, HarvestingRewards and HarvestingRareItemList emptied |
| **0x2df** | MsgHarvestingInfoToClient / `FUN_004f47a0` | `f32 quantity, f32 siCurrent, f32 siMax` | Progress. siCurrent is clamped to ≥ 0. Redraws the bars |
| **0x2e0** | MsgTwoInts / `FUN_004f27e0` | `i32 primarySkillId, i32 secondarySkillId` | Character window `_harvesting_primary_skill` / `_secondary_skill` tooltips (`Har<Skill>Tooltip`). Optional |
| **0x2e1** | MsgHarvestingRewardItems / `FUN_004f52d0` → `FUN_004f4ca0` per record | `i32 count, count × {i32 itemId, i32 quantity, u8 rare}` | Adds or updates reward entries. rare ≠ 0 sets the "rare present" flag and puts the item on HarvestingRareItemList; rare 0 goes to HarvestingRewards. Entries missing from the list are marked removed. Then calls `FUN_004f4ef0` (refresh) |
| **0x2e2** | MsgSingleItemInfo / `FUN_004f2d30` | the standard item record (same as 0x197) | Parses the item (`FUN_00516610(...,1,-1)`) and attaches it to the reward entry whose id == **item field 1 (server item id)**. Sets the shown quantity. Does **not** redraw |
| **0x2e3** | none / `FUN_004f4ef0` | — | Refresh the reward lists. Ids without an item record → client sends `0x10b` |
| **0x2de** | none / `FUN_004f1de0` | — | +0 = 0, skill = −1. Chat "Harvesting has ended.". If rare items are present: `IsHarvestingDone = 1` (the window stays). Else: `bHarvesting = 0` and the lists are cleared |

Related events:

- **`0x3d1` / `0x3d3` MsgDisplayAbility** with HARVESTING_ABILITIES visual ids (`Assets/Abilities/HARVESTING_ABILITIES.aby`, display tags read from the exports) [O]:
  - 20000 ATTACK_DEFAULT, 20001–20003 ATTACK_SINGLE_TARGET_0..2
  - 20083 ATTACK_LUMBERING, **20084 ATTACK_MINING**, 20085 ATTACK_QUARRYING, 20086 ATTACK_REAPING, 20087 ATTACK_SKINNING, 20088 ATTACK_GATHERING
  - **20004 DEATH (node death)**, 20081 NPC_PARTICLE_CAVEIN_DEATH, 20082 MINING_1

  These are only visuals: the strike swing on the player plus the spark/chip reaction on the node (phase 2 = hit).
- **`0x0e` MsgSingleShort `i16 code`** (`FUN_0061d530`) [O]:
  - 0x77 AlreadyHarvesting, 0x78 NeedTarget, 0x79 InvalidTarget
  - 0x7a ResourceAlreadyHarvested, 0x7b NeedSkillToHarvest, 0x7c CannotHarvestResource
  - 0xeb HarvestBeforeLooting, 0x159 CantAttackHarvestResource (for auto-attack on a node)

  These are localized-string tags. The text comes from the client's string table.
- **`0x252` MsgStringAndInt `{wstr name, i32 reason}`** (`FUN_00465c70`) prints "You failed to use <name> because…" [O]:
  - 0x20 "…you do not have a high enough rank harvesting tool equipped."
  - 0x21 "…you do not have the right type of tool equipped."
  - 0x22 "…you do not have a tool that harvests the right type of resource equipped."
  - 0x23 "…you are not harvesting the right type of resource."
- **`0x241`** (ability fail, `FUN_0043e610`) and **`0x1c5`** (item/ability fail, `FUN_00507970`), u8 code **0x16** = "You need to wield a harvesting tool to use this ability." [O]
- **`0x197`** puts the harvested item into the bag. This works today (see `docs/INVENTORY.md`). Nothing in the harvesting module sends items to inventory itself: the 0x2e1/0x2e2 lists are display only. I found no client "take reward" event in the module, so granting the item with `0x197` is the safe assumption. [I]

---

## 4. Tool and skill requirements

- **Harvest tool:** item field 74 (type, +0x524) = **16**; a harvest pack is 17. Equip slot **0x35 "Harvesting Tool"** (`FUN_00d047b0`). Other harvesting slots: 0x29 Pack, 0x30 Head, 0x31 Chest, 0x32 Legs, 0x33 Hands, 0x34 Feet, 0x36 Waist. [O]
- **Tool tooltip `FUN_006aba00`:** only when type == 16 and +0x580 > 0. It shows field 80 (+0x53c, an int "power") divided by field 81 (+0x548 f32), the power multiplied by the summed effects with id 0x2d, and field 82 (+0x54c, speed). This is display only. [O]
- **Skills** are stats in subtype 0x15. The harvesting stat ids are 0x0f Mining, 0x32 Quarrying, 0x4b Lumberjacking, 0x59 Reaping, 0x76 Skinning, 0x79 Gathering, and 0xc4 Harvesting (`server/stat_names.py`). The u8 skill in `0x2dc` and the ints in `0x2e0` are these stat ids. [O]
- **The client does no tool or skill check before `0x109`** (`FUN_004f1c10` is a bare send). [O] The server decides and reports failures with `0x0e` codes 0x7b/0x7c, or `0x252` reasons 0x20–0x23.

---

## 5. Minimal recipe: spawn an ore node → player harvests → player gets ore

1. **Spawn the node.** Use `npc_bunch(..., cls_path="<pkg>.SGONPCPawn", name="Copper Ore Vein", race=172, ...)` with `extra_props={"EntityTypes": 0x800, "m_iModelNum": 0}`. Keep `Health` 100 and `m_bIsDead` 0. Static alternative: race 536–550.
   - The client then shows the Harvestable cursor ("ResourceHover"). [O for the flag; I that it works end to end]
2. **Consider.** On `0x3d9` with the node targeted, send `0x3da {3, 11, 0, 1, "Copper Ore Vein", "Mining"}`. The client prints "Copper Ore Vein is easy for you to start harvesting.  Harvesting this resource requires a Mining tool."
3. **Start.** The player right-clicks or uses the node: the client sends `0x5d {u64 nodeId}` [I], then **`0x109`**. The server checks:
   - already harvesting → `0x0e 0x77`
   - node depleted → `0x0e 0x7a`
   - no type-16 item in slot 0x35 → `0x252 {"Mining", 0x22}`, or `0x0e 0x7c`
   - skill too low → `0x0e 0x7b`

   If the checks pass, send:
   - `0x2e0 {0x0f, -1}` (optional)
   - `0x2dc {u64 nodeId, f32 0, u8 0, u8 0x0f}`
   - `0x2dd`
4. **Progress.** Run a timer, for example every 2 s, N strikes:
   - `0x3d1` {caster player, target node, ability **20084**, phase 2}: swing and sparks.
   - `0x2df {f32 quantity, f32 siCurrent, f32 siMax}`. For example siMax 18, siCurrent going down 18 → 0, quantity going up 0 → q (the client bar max is 6).
   - Optional chat through `0x0f`.
5. **Success** (siCurrent reaches 0). Pick a new unique item id X (the inventory item id), then send:
   - `0x2e1 {1, [X, qty, 0]}`
   - `0x2e2` = the same item record as 0x197 (field 1 = X, name "Copper Ore", quantity, icon; type 22 "crafting resource")
   - `0x2e3`: the rewards list shows the ore
   - **`0x197`** with the same item: it goes into the bag
   - `0x2de`: "Harvesting has ended.", and the window closes because there are no rare items
6. **Deplete the node.**
   - `0x3d1` with ability **20004** (DEATH) or 20081 (cave-in) on the node, then either replicate `bHidden=1` / close its actor channel, or set `Health=0, m_bIsDead=1`.
   - Mark it depleted on the server, so later `0x109` gets `0x0e 0x7a`. Respawn later by reopening the channel.
7. **Stop early.** On client `0x10a`, or when the player moves away, send `0x2de`.
8. **Auto-attack on a node** (`0x3d8` with an `EntityTypes&0x800` target): answer with `0x0e` code `0x159` (CantAttackHarvestResource) and do not start combat.

---

## 6. Open points / not verified

- None of this has been tested live. The send order 0x2dc → 0x2dd and 0x2e1 → 0x2e2 → 0x2e3 is inferred from the handlers: 0x2e2 only attaches to entries that already exist, and only 0x2e1/0x2e3 redraw.
- The harvesting window XML may need `SGOUI` toggling. The handlers only set gamevars (`bHarvesting`, `HarvestingActionName`, `HarvestingRewards`, `HarvestingTargetSI`, `HarvestingQuantity`).
- The f32 at `0x2dc` (+0x20) is read but never used by the handler.
- It is unclear whether harvesting abilities (0xd0) should drive the strikes, as in the real game, or a server timer. A timer is enough for the client.
- Which UI command in `FUN_006a8060` also sends `0x109` (at 0x6a95b8) was not mapped.
- The localized text for the `0x0e` tags lives in the client string table and was not dumped.

## Key addresses
- `FUN_00418060` hover/cursor (EntityTypes +0xaf8)
- `FUN_00417da0` interact
- `FUN_004f1c10` send 0x109
- `FUN_004f54d0` harvest dispatcher
- handlers: `FUN_004f4850` (0x2dc), `FUN_004f1c30` (0x2dd), `FUN_004f1de0` (0x2de), `FUN_004f47a0` (0x2df), `FUN_004f27e0` (0x2e0), `FUN_004f52d0`/`FUN_004f4ca0` (0x2e1), `FUN_004f2d30` (0x2e2), `FUN_004f4ef0` (0x2e3 / refresh)
- `FUN_004f2ae0` (sends 0x10b)
- `FUN_004f1980` (0x2dc schema)
- `FUN_005e7670` (0x3da)
- `FUN_0061d530` (0x0e codes)
- `FUN_00465c70` (0x252)
- `FUN_0043e610` (0x241)
- `FUN_00507970` (0x1c5)
- `FUN_00d047b0` (equip slot names)
- `FUN_006aba00` (tool tooltip)
- `FUN_00bd7650` (static-mesh races)
- `/endharvesting` 0x5fcdb0, `/harveststats` 0x5fcda0 → 0x4f1bd0
- harvest state object `DAT_0146397c`
