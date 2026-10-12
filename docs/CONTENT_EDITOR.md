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
| Patrol and wander paths | waypoints per mob or group, wander radius, speed | NPCs only chase their attacker (`combat.chase_step`) |
| Mob templates | name, race or creature model, level, health, damage, aggro radius, abilities, gear (`m_AttachmentGroups`), faction | `server/content/mobs.json`: 4 placeholder templates (no abilities, faction or creature models yet) |
| Loot tables | items, chances, quantities, coin per mob template | `server/content/loot.json`: one placeholder table |
| Items | stats, item type, icon, mesh number for the model, slot, flags | a handful of starter items in `zone.py` |
| Abilities (gameplay) | costs, ranges, damage, cooldowns, level per class, trainer prices and which trainer teaches what | names from `.aby` tags, placeholder numbers (`class_abilities.py`) |
| Recipes and resource nodes | recipes (inputs, stages, actions, output), node types, yields, respawn | `server/content/recipes.json` (one recipe), `harvest` (kind, item, quantity, tool, skill, difficulty) and `station` blocks in mobs.json; tools in items.json (`harvest_tool`) |
| Diplomacy | statement cards per class or level, NPC parley decks and strategy, parley rewards (faction, items, dialogue unlocks), presence requirements | `server/content/diplomacy.json`: 7 placeholder cards, one player deck, one parley (Orin); `parley` key in mobs.json |
| Encounters | boss phases, triggers, adds, scripted events | none |
| Quests | givers, text, steps, objectives, rewards | `server/content/quests.json`: two placeholder quests (kill, collect and talk steps, prerequisites, item rewards); quest dialogue trees (0x2af responses) not yet used |
| NPC dialog and merchants | conversation trees, vendor inventories and prices, trainers | `server/content/merchants.json` (one placeholder vendor); dialog is only "Show me your wares." |
| Starting areas and bind points | per race or class start location and bind spots | flat land found in the heightmap (`zone.default_ground_spawn`) |
| Dungeon membership | which chunks or areas are dungeons, entrances | unknown; most dungeons are inside overworld chunks |
| NPC services | which NPCs are bankers, trainers, repairers, crafting stations; bank sizes; repair prices; what each trainer teaches | `banker`, `trainer`, `repair`, `station` flags in mobs.json; 40 bank slots; repair 2 copper per point per item level; trainers teach the next 6 class abilities at 1 silver steps |
| Item durability | wear per death or per hit, which item types wear | 10 points per death on equipped non-misc items |
| Crafting tools and complications | tool per recipe step, complication tables per recipe or stage, counter actions | one tool (Crucible Tongs) and one complication (Slag Buildup) in recipes.json |
| Experience | XP per kill or quest, level curve | 150 XP per kill, 1000 per level (`combat.KILL_XP`, `zone.XP_PER_LEVEL`) |

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
