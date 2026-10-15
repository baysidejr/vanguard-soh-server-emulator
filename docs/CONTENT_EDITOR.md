# Content editor: what the client doesn't have

Vanguard's world content lived in SOE's database, not in the client. This file tracks every piece of server-only data we find, so a hosted, crowdsourced **encounter editor** can be built at the end of the project. People will use it to place spawns, draw patrol routes, build encounters and write quests. Everything is saved as shared JSON that anyone can reuse.

Status: the editor is planned for the end of the project. Until then, the server is built data-driven so the editor can write the same files.

Content already loaded from JSON (`server/content.py`; run `python content.py` to validate): `content/mobs.json`, `content/loot.json` and `content/spawns/<chunk>.json`. A spawn's z is optional and comes from the terrain heightmap.

## What the client provides

Verified 2026-10-12 by scanning all 325 maps in `Assets/Maps`.

- **World geometry for every chunk:** terrain heightmaps (`server/terrain.py`), about 54,000 compound objects, 3,900 static meshes, water and lava volumes, lights, fog, weather.
- **Map markers:**
  - 431 `PlayerStart`s. These are not reliable spawns: in `chunk_n19_12` one hangs over a canyon and one is over the sea.
  - 12 `PathNode`s, which look like leftovers.
  - Effect markers that hint at inhabited places: bonfires, chimney smoke, crafting steam.
- **Models:** all character and creature models (332 race ids incl. creatures, with variant numbers: [CREATURES.md](CREATURES.md)), and item meshes (`Assets/Characters/Meshes/<TYPE>_ITEMS.uem`, see [GEAR.md](GEAR.md)).
- **Ability visuals:** for player classes and NPCs (`Assets/Abilities/*.aby`, including `NPC_ABILITIES` and `NPC_BASE_ABILITIES`, see [ABILITY_VISUALS.md](ABILITY_VISUALS.md)).
- **UI and messages:** item icons (`VGUIAssets/Global/Icons/iconsTK.xml`), UI text, and every message layout.

## What the client does not have

| Data | What it needs | Current placeholder in the server |
| --- | --- | --- |
| Mob spawns | chunk, position, facing, mob template, respawn time, spawn groups and camps | `server/content/spawns/<chunk>.json`: one placeholder camp in chunk_n19_12 |
| Patrol and wander paths | waypoints per mob or group, wander radius, speed | spawns can have `wander` (radius) or `path` (patrol waypoints, `pause` seconds at each); the Thestran Guard patrols (verified live) |
| Mob templates | name, race or creature model, level, health, damage, aggro radius, abilities, gear (`m_AttachmentGroups`), faction | `server/content/mobs.json`: 4 placeholder templates (no abilities, faction or creature models yet) |
| Loot tables | items, chances, quantities, coin per mob template | `server/content/loot.json`: one placeholder table |
| Items | stats, item type, icon, mesh number for the model, slot, flags, flags (No Trade, Bind On Equip, Quest, No Sell, Unique...) | a handful of starter items in `zone.py` |
| Abilities (gameplay) | costs, ranges, damage, cooldowns, effect kind (buff/DoT/heal), durations, stat bonuses, level per class, trainer prices and which trainer teaches what | names from `.aby` tags, placeholder numbers (`class_abilities.py`) |
| Recipes and resource nodes | recipes (inputs, stages, actions, output), node types, yields, respawn | `server/content/recipes.json` (one recipe), `harvest` (kind, item, quantity, tool, skill, difficulty) and `station` blocks in mobs.json; tools in items.json (`harvest_tool`) |
| Diplomacy | statement cards per class or level, NPC parley decks and strategy, parley rewards (faction, items, dialogue unlocks), presence requirements | `server/content/diplomacy.json`: 8 placeholder cards, a starting deck, bar size, one parley (Orin) whose first win awards a card; `parley` key in mobs.json. Which cards each class starts with, and which parleys award which cards, are unknown |
| Factions | every faction (name, id), starting standing per race or class, which mobs belong to which faction, standing changes per kill (and allied or enemy factions), faction rewards from quests, parleys and work orders, faction requirements on merchants, items and quests | `server/content/factions.json`: 3 placeholder factions; `faction` key in mobs.json; quest and parley rewards `faction {id: amount}`. Real faction ids and names are unknown (they lived in the server database) |
| Work orders | task masters (where, which crafts), order lists per craft and skill level, supplies, items to deliver, rewards (coin, crafting XP, faction), chained refining/finishing orders | `server/content/workorders.json`: one placeholder order at one task master (Garret Holm); work-order recipe `wo_copper_ingot` in recipes.json |
| Encounters | boss phases, triggers, adds, scripted events | none |
| Quests | givers, text, steps, objectives, rewards | `server/content/quests.json`: two placeholder quests (kill, collect and talk steps, prerequisites, item rewards); quest dialogue trees (0x2af responses) not yet used |
| NPC dialog and merchants | conversation trees, vendor inventories and prices, trainers | `server/content/merchants.json` (one placeholder vendor); `server/content/dialogs.json`: one placeholder conversation tree (the Thestran Guard) with goto nodes and faction/give actions; real NPC dialogue text is unknown |
| Starting areas and bind points | per race or class start location and bind spots | flat land found in the heightmap (`zone.default_ground_spawn`) |
| Dungeon membership | which chunks or areas are dungeons, entrances | unknown; most dungeons are inside overworld chunks |
| NPC services | which NPCs are bankers, trainers, repairers, crafting stations; bank sizes; repair prices; what each trainer teaches | `banker`, `trainer`, `repair`, `station` flags in mobs.json; 40 bank slots; repair 2 copper per point per item level; trainers teach the next 6 class abilities at 1 silver steps; recipe trainers sell the recipes listed in `recipe_trainer` at their `trainer_cost` (which recipes each real trainer taught is unknown) |
| Item durability | wear per death or per hit, which item types wear | 10 points per death on equipped non-misc items |
| Crafting tools and complications | tool per recipe step, complication tables per recipe or stage, counter actions | one tool (Crucible Tongs) and one complication (Slag Buildup) in recipes.json |
| Death penalty | debt per death and per level, debt recovery from tombstones and resurrection, corpse decay time, altar locations and meshes, summon cooldowns; the item that clears all debt (client template 1454022: its name, price and where it was sold) | 100 debt per death (cap 500), half back on recovery, no decay, no altars |
| Mounts | which items summon which mount ids (about 1000 meshes in MOUNT_ITEMS), mount speeds, flying/aquatic types, where mounts are sold and level requirements; barding items (which index each one shows, which mounts and levels can wear it) | placeholder mount items (horse 1000, dire wolf, camel, griffon) and two barding items (Green Caparison 105, Plate Barding 205) at the camp merchant |
| Riftways | world positions and chunks of the 39 riftway destinations, which ones a player has discovered, travel prices (the client hardcodes 50/500/2000/5000 copper by color) | `server/content/riftways.json`: all 39 names and colors from the client map; only Sundering Wastelands has a (placeholder) landing spot; two Riftseeker brazier stones in chunk_n19_12 |
| Housing | plot positions and prices, building types per plot, prefab names, fixtures and chests, upkeep, construction materials | `server/content/plots.json`: one placeholder plot with two building types (instant construction) Which NPCs a house can hold (Manage NPCs; plots.json building `"npcs"`): plot 101 offers the camp banker as a placeholder. |
| Titles | every title name and id, prefix or suffix, how each is earned (quests, levels, achievements, crafting, diplomacy) | `server/content/titles.json`: 3 placeholder titles |
| Player summoning | which abilities or items summon a player or the group (the client's Call Confirmation, 0x270 / 0x271), their range, cost and cooldown, where they work | only the dev command `!call <name>` |
| Pets | which abilities summon which pet (race, model, level), pet abilities, pet types per class | none yet |
| Fishing | fish species (name, fresh/salt water, zones, weight range, bait, 4-direction combo), fish and bait items, bite timing, minigame tuning, fishing spots with water | two placeholder fish, one pole, one bait; water comes from each chunk's WaterVolume actors in the .vgr level package (z below 0 on the beach south of the camp) |
| Crafting utilities and toolbelts | which steps need which utilities and tools, utility and tool items, toolbelt items and sizes | one utility (Mould Oil) on one step |
| Finishing stations and recipes | which stations are refining or finishing (and for which crafts), finishing recipes per craft with their categories, finishing skill ids | one Finishing Table and one finishing recipe (Copper Buckle, skill 0x46 Smithing) |
| Item rarity | rarity of every item (Mundane ... Legendary+), which decides what goes to group loot rolls | items.json `rarity` names (only Copper Ring is set, uncommon; default mundane) |
| Combat chains and reactions | which abilities chain into which (per class and rank), reaction windows, counters (which enemy casts they answer) and rescues | `server/content/chains.json`: one placeholder chain for Ranger and one for Warrior; `rescues.json` (Warrior Taunt I) |
| NPC spells and counters | which NPCs cast which spells (cast time, damage, icon, counterable or interruptible), which player abilities counter or interrupt them | mobs.json `spells` on the Canyon Widow (Venom Spit), `server/content/counters.json` (Riposte I, Parry I) |
| Experience | XP per kill or quest, level curve | 150 XP per kill, ±15% per level of difference, none from mobs 6+ levels below (`combat.KILL_XP`); level N needs 1000 × 1.12^(N−1) (`zone.xp_for_level`), cap 50 |
| Tutorial popups | when each tutorial shows (first death, first level, ...) and its title and text: MsgTutorialDisplayEvent carries two server strings (ctor FUN_005d9a00); the client only remembers "do not show again" (0x183 for the death penalty tutorial) | none |

## Planned editor (end of project)

1. **In-game builder mode.** GM chat commands on our server, with the real client as the 3D editor:
   - `!spawn <template>` places a mob at your feet.
   - `!path add`, `!wander <radius>` and `!respawn <seconds>` set movement and respawns.
   - `!camp`, `!delete`, `!undo` and `!save` manage what you've placed.
2. **Web forms** for mob templates, loot tables, items, quests and dialog, plus a chunk map drawn from the heightmap with spawns plotted on it.
3. **Shared JSON in a git repository.** For example `content/spawns/<chunk>.json`, `content/mobs/*.json` and `content/quests/*.json`.
   - Contributions arrive as pull requests, checked by a validation script (model ids exist, positions are on terrain, levels are sane).
   - The content gets a data license (for example CC-BY-SA), separate from the code's AGPL.
4. **Importers.** Scripts that turn old fan wiki and guide data (and VGOEmu data, if they share it) into draft JSON for builders to verify in game.
5. **Player feedback in game.** `/bug` opens the client's Bug Report window. Submit sends 0x4aa {wstr description, i32 category, i32 severity, i32 reproducibility}, and the server stores it in `server/bug_reports.json` (not committed) with the player, chunk, position and target (`server/bugs.py`). The editor can show these reports on the chunk map next to the spawns. The client also has a Quest Report window (0x4ad opens it; ratings for challenge, rewards, lore, confusion and fun). It is not wired up yet.

**Bard songs:** the song parts (melodies, verses, embellishments, bridges, lyrics, choruses, codas, rests), with each part's effect and energy cost, were server data. `server/content/songs.json` holds placeholders; see docs/SONGS.md.

**Finding spawns in game:** `!npclist [radius]` (dev commands) prints the NPCs near you with the client's GM NPC list (0x786): "Hollis Grent (Lvl 20) camp_banker EncounterDBId: 13 Loc: -31400.0, -5600.0, 450.0." The EncounterDBId is the entry's index in `content/spawns/<chunk>.json` and the tag is its mob key, so a builder can go from what they see in game to the line to edit.

**Quest feedback:** with `--quest-feedback`, the server opens the client's Quest Feedback window (`SGOUI toggle "Quest Feedback"`) after each completed quest. The window asks for challenge, reward, lore, confusion, friends needed, a fun grade and comments. Accept sends 0x4ab {i32 quest id (-1 here), wstr comments, 6 x i32}, and the server saves the answers with the quest key in `server/quest_feedback.json` (not committed). The client's own opener, 0x4ad {wstr, i32}, shows nothing (verified live).

**Combat forms and Psionicist mindsets:** which forms each class has, and what each one does, were server data. `server/content/forms.json` holds placeholders; see docs/FORMS.md.

**Brotherhood XP bonus:** the real bonus rate was server data; ours is 5% per grouped brotherhood member (`brotherhood.BONUS_PER_MEMBER`).

**Civic diplomacy:** the real civic stats per area, their ranges and their effects were server data; ours is one placeholder value ("Thestran Wastes Camp Prosperity", +5 per win against Orin).

**Deconstruction:** what each item broke down into (components, the level needed) was server data. Every item answers "can not be deconstructed" until that exists (docs/CLIENT_REQUESTS.md, Deconstruction).

**Alternate advancement:** the AA abilities (general, archetype, class and special lists), their costs, ranks and effects were server data, sent as MsgAlternateAdvancementAbilitiesAdd. `/aalist` (0x85c) and the AA window get no answer until that data exists.

**Summoned pets:** what each class summon (Awaken Abomination, Summon Attendant of Hayatet/Rakurr/Tuurgin, Ritual Animatus) creates, its race, model, level, health and abilities were server data; abilities.json has placeholders.

**Wildgrowth Forest outpost (chunk_n20_12):** Elara Thornwood (quests 5003-5004), Bram Oakhollow (forest_supplies), timber wolves, a thornback bear, webweavers, the Wildgrowth Wardens faction (1004) and the Wolf Pelt / Bear Claw / Spider Silk / Forester's Cloak items are all invented placeholders.

**Character formulas:** race and class attribute bonuses, attribute growth per level, health/endurance/energy per level and per attribute point, hit/dodge/parry/block/crit chances, armor mitigation, ability power scaling and the kill XP curve were server data. All of them are placeholders in `server/zone.py` and `server/combat.py` (constants at the top of each formula).

**Bags:** the real bags (names, slot counts, icons, where they drop or are sold) were server data. `server/content/items.json` has one placeholder, "Small Pouch" (8 slots, sold at camp_supplies); see docs/INVENTORY.md "Bags".

**Fishing leaderboards:** the real servers ranked catches across the whole server; ours ranks the characters in characters.json (docs/FISHING.md).
