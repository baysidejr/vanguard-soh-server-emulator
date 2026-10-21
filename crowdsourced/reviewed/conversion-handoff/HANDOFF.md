# Conversion handoff

3400 conversion candidates from 34474 selected source records (60268 raw rows examined). Nothing imported.

- items.json: 3384
- mobs.json: 0
- quests.json: 16
- loot.json: 0
- merchants.json: 0

Review `proposed/` alongside `DISPOSITION.json`, `ISSUES.json`, `UNRESOLVED_REFERENCES.json` and the exact raw file/line pointers in `SELECTIONS.json`. `INPUTS.json` hashes the snapshot inputs. Withheld records retain their source pointers and reasons.

Do not overwrite live content with these files. Merge reviewed entries individually. Resolve references, identity conflicts, unsupported mechanics, icon fallback and schema changes first; then run the receiving server validation and integration tests. No candidate is certified historically complete or import-ready merely because conversion succeeded.

Rebuild from the repository root: `python -B crowdsourced/build_handoff.py`. No network access; only closed raw batches are read. Source replay selection never merges fields; distinct source sets remain separate and ambiguous identities are withheld.
