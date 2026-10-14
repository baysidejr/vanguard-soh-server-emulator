# Import readiness (2026-10-14)

All 121 raw batches were converted in memory with `crowdsourced/convert.py` (nothing written; script
kept outside the repo). About 10,000 records across the batches; many batches are successive versions
of the same pages (archive-bulk, then enriched v2 to v7).

**Result: almost nothing is ready to import.** Unique entries that convert cleanly across all batches:
16 items and 13 quests. Nothing has been merged into `server/content/`.

## Why records are withheld

| Count (all batches) | Issue | What it means |
|---|---|---|
| 4,475 | quest: unknown giver, level or objectives | Quests carry a giver and level, but objectives are only `candidate_steps` / `archive_objective_counters`, often without a target ("Yukionna Slain (15)"). Rewards are mostly null. |
| 4,438 | low confidence, skipped | The collector marks single-source or partial records `low`; conversion skips them unless `--include-low`. |
| 995 | npc: unknown client race, level or required health | The archived pages list services and locations, not the NPC's race, model or health. |
| 39 | merchant: unknown NPC, inventory or price | Inventories without prices are withheld whole. |
| 30 | creature: no client race | `creature_kind` missing. |
| 28 / 18 / 13 | item: class restrictions, weapon delay, item type | Need manual mapping to the server's item fields. |
| 16 batches | ability records not converted yet | `ability` is collected but the converter has no ability output yet. |

Sample (enriched v7, `quest.jsonl`, 75 quests): level 75/75, giver 74, zone 73, candidate steps 27,
real `steps` 1, rewards all null. `npc.jsonl` (228): services 228, location 195, level 114, race 0,
health 0; confidence 132 low, 96 medium.

## What would make more of it usable

1. **Quests:** a person (or the content editor) completes objective targets and rewards from the
   candidate steps; the converter could offer `candidate_steps` with a target and count as
   reviewable proposals instead of withholding the quest.
2. **NPCs:** race and model can't come from these pages. Pick from the client's race list per NPC in
   the content editor, or take them from VGOEmu captures once allowed. Health could fall back to a
   documented per-level placeholder only if the project decides to allow that.
3. **Abilities:** write the ability converter (100 records per batch are waiting).
4. **Deduplicate batches:** convert only the newest version of each page set (enriched v7 and the
   later bulk batches) to avoid reviewing the same records six times.
