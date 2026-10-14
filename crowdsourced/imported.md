# Import log

One line per import into `server/content/`: date, batch folder, records imported, target files.

| Date | Batch | Records | Into |
|---|---|---|---|
| 2026-10-14 | all raw batches, ability.jsonl (medium confidence) | 271 ability names (re-spacing only; a name is used only when it equals the tag name ignoring spaces, punctuation and case) | server/content/ability_names.json via tools/ability_names.py; 5 abilities.json keys renamed to match |
