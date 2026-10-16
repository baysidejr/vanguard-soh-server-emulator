# Import log

One line per import into `server/content/`: date, batch folder, records imported, target files.

| Date | Batch | Records | Into |
|---|---|---|---|
| 2026-10-14 | all raw batches, ability.jsonl (medium confidence) | 271 ability names (re-spacing only; a name is used only when it equals the tag name ignoring spaces, punctuation and case) | server/content/ability_names.json via tools/ability_names.py; 5 abilities.json keys renamed to match |
| 2026-10-15 | all raw batches, ability.jsonl (newest record per name, low confidence) | 355 class abilities: 200 icons (archive IconNNN = client icon NNN, checked by eye on a sample), 276 tooltips as descriptions, 217 refresh times, cast times where recorded; only fields an entry lacked; each entry keeps `_source` | server/content/abilities.json via the content editor's Fill all from the archive (tools/editor.py ability_fill) |
| 2026-10-15 | all raw batches, npc.jsonl (Khal) | 27 NPCs at their recorded positions (placeholder race and health) | server/content/mobs.json, spawns/chunk_n13_n9.json via tools/import_zone.py |
| 2026-10-15 | all raw batches, npc.jsonl (Khal) | 32 NPCs at their recorded positions (placeholder race and health) | server/content/mobs.json, spawns/chunk_n13_n9.json via tools/import_zone.py |
| 2026-10-15 | all raw batches, quest.jsonl (Khal) | 32 quest givers at their quests' start locations (race from the zone's continent) | server/content/mobs.json, spawns/chunk_n13_n9.json via tools/import_zone.py |
| 2026-10-15 | all raw batches, npc.jsonl (Ahgram) | 33 NPCs at their recorded positions (placeholder race and health) | server/content/mobs.json, spawns/chunk_n14_n11.json via tools/import_zone.py |
| 2026-10-15 | all raw batches, npc.jsonl (New Targonor) | 52 NPCs at their recorded positions (placeholder race and health) | server/content/mobs.json, spawns/chunk_n27_24.json via tools/import_zone.py |
| 2026-10-15 | all raw batches, npc.jsonl (Tanvu) | 49 NPCs at their recorded positions (placeholder race and health) | server/content/mobs.json, spawns/chunk_n19_6.json via tools/import_zone.py |
| 2026-10-15 | all raw batches, npc.jsonl + quest.jsonl (71 zones: every zone in ChunkNames.txt with positioned NPCs except Sundering Wastelands and Wildgrowth Forest, which hold the placeholder camps) | 959 NPCs at their recorded positions (941 templates; placeholder race and health) | server/content/mobs.json, spawns/<chunk>.json via tools/import_zone.py |
| 2026-10-15 | raw batches of the crowdsourced/archive-collection branch (commit 0c411dc, read from a git archive, not merged), npc.jsonl + quest.jsonl | 112 more NPCs in 32 zones, plus model variants, role titles and parley types for all imported NPCs | server/content via tools/import_zone.py --raw |
| 2026-10-15 | collection branch raw batches (0c411dc), creature.jsonl | 179 located creatures as hostile mobs (placeholder health and damage) | server/content via tools/import_zone.py --raw |
| 2026-10-15 | archive item.jsonl | 37 items that imported creatures drop (crowdsourced/convert.py mapping via the editor's item draft; placeholder icon 443 where none) | server/content/items.json |
| 2026-10-15 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 5 spawns, 5 templates | server/content via tools/import_zone.py --all |
| 2026-10-15 | raw batches + branch origin/crowdsourced/archive-collection, quest.jsonl | 17 quests whose giver and objectives are all placed, 4 quest items | server/content/quests.json, items.json via tools/quest_readiness.py --apply |
| 2026-10-15 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 72 spawns, 24 templates | server/content via tools/import_zone.py --all |
| 2026-10-15 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 734 spawns, 732 templates | server/content via tools/import_zone.py --all |
| 2026-10-15 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 39 spawns, 0 templates | server/content via tools/import_zone.py --all |
| 2026-10-15 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 3 spawns, 3 templates | server/content via tools/import_zone.py --all |
| 2026-10-15 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 186 spawns, 181 templates | server/content via tools/import_zone.py --all |
| 2026-10-16 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 12 spawns, 12 templates | server/content via tools/import_zone.py --all |
| 2026-10-16 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 8 spawns, 7 templates | server/content via tools/import_zone.py --all |
| 2026-10-16 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 12 spawns, 12 templates | server/content via tools/import_zone.py --all |
| 2026-10-16 | raw batches + branch origin/crowdsourced/archive-collection (all zones, skipping Sundering Wastelands, Wildgrowth Forest) | 43 spawns, 35 templates | server/content via tools/import_zone.py --all |
