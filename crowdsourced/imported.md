# Import log

One line per import into `server/content/`: date, batch folder, records imported, target files.

| Date | Batch | Records | Into |
|---|---|---|---|
| 2026-10-14 | all raw batches, ability.jsonl (medium confidence) | 271 ability names (re-spacing only; a name is used only when it equals the tag name ignoring spaces, punctuation and case) | server/content/ability_names.json via tools/ability_names.py; 5 abilities.json keys renamed to match |
| 2026-10-15 | all raw batches, ability.jsonl (newest record per name, low confidence) | 355 class abilities: 200 icons (archive IconNNN = client icon NNN, checked by eye on a sample), 276 tooltips as descriptions, 217 refresh times, cast times where recorded; only fields an entry lacked; each entry keeps `_source` | server/content/abilities.json via the content editor's Fill all from the archive (tools/editor.py ability_fill) |
| 2026-10-15 | all raw batches, npc.jsonl (Khal) | 27 NPCs at their recorded positions (placeholder race and health) | server/content/mobs.json, spawns/chunk_n13_n9.json via tools/import_zone.py |
| 2026-10-15 | all raw batches, npc.jsonl (Khal) | 32 NPCs at their recorded positions (placeholder race and health) | server/content/mobs.json, spawns/chunk_n13_n9.json via tools/import_zone.py |
| 2026-10-15 | all raw batches, quest.jsonl (Khal) | 32 quest givers at their quests' start locations (race from the zone's continent) | server/content/mobs.json, spawns/chunk_n13_n9.json via tools/import_zone.py |
