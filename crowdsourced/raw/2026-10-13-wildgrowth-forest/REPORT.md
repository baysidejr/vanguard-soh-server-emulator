# Wildgrowth Forest collection batch — 2026-10-13

12 records: 1 zone, 3 NPCs, 1 merchant role, 4 quests and 3 items. `gaps.jsonl` contains 6 unresolved searches. This is a follow-up research batch; it is not approved server content.

## Files

| File | Records |
|---|---:|
| zone.jsonl | 1 |
| npc.jsonl | 3 |
| merchant.jsonl | 1 |
| quest.jsonl | 4 |
| item.jsonl | 3 |
| gaps.jsonl | 6 gaps |

## Evidence

Inspected public pages individually on 2026-10-13. [Vanguard Archive](https://vgsoharchive.com/zones/wildgrowth-forest) supplies the zone map legend and links to the NPCs and quests. This is a 2026 compilation; embedded historic accounts and different pages on the same archive are not independent corroboration. Historical page dates are unknown. Original Fandom quest access failed; low-confidence quest records retain the archive's provisional readings and its conflict warnings. Source robots.txt was inaccessible; no bulk crawler was used.

The strongest item source is the direct [Gloves of Foreststalking detail](https://vgoplayers.com/items.php?itemId=1271087). It explicitly distinguishes required level 6 from item level 16 and gives stats different from the archive's principal reading. Direct values and exact capitalization are preferred. No site guide prose or long game-text excerpts were copied; summaries are original.

## Human checks before integration

- All four quests are low confidence because of level/giver conflicts. Default conversion must skip them. A previous/next link is not necessarily an enforced prerequisite.
- The Forest Walks documents twelve Foreststalkers but does not establish the exact singular entity name; target remains null.
- The Strange Flame lists three flames without explaining their update triggers. Step kinds remain null; even with `--include-low`, conversion must withhold this quest.
- Shared Tracker Camp map coordinates do not establish precise NPC spawn positions and disagree with quest coordinates. No movement, count, height or respawn values are inferred.
- NPC race/client models are unknown; no Thestran defaults should be assigned. The merchant's role is known, but its inventory is null rather than empty.
- Gloves have an explicit required level. Bind trigger, price, race restrictions and client icon still need review; unlabelled page numbers were not interpreted as money.
- The archive's NPC 'dropped by' label can describe a quest reward relation. Do not turn it into a combat loot table.
- Class restrictions and unmapped item stats require review in proposed item metadata. The converter's icon 443 is a fallback, not a historical icon.

## Validation and proposal workflow

```text
python -B crowdsourced/validate.py raw/2026-10-13-wildgrowth-forest
python -B crowdsourced/convert.py raw/2026-10-13-wildgrowth-forest
```

Expected candidates: 3 items, no quests, NPCs or merchant inventory. See generated `reviewed/2026-10-13-wildgrowth-forest/proposed/ISSUES.md` for withheld records and manual work. `PROVENANCE.json` preserves the accepted records' evidence. No files outside crowdsourced are changed.
