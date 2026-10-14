# Sundering Wastelands collection batch — 2026-10-13

20 records: 1 zone, 3 NPCs, 3 creatures, 5 quests and 8 items. `gaps.jsonl` contains 7 unresolved searches. These are research records and conversion candidates, not approved imports.

## Files

| File | Records |
|---|---:|
| zone.jsonl | 1 |
| npc.jsonl | 3 |
| creature.jsonl | 3 |
| quest.jsonl | 5 |
| item.jsonl | 8 |
| gaps.jsonl | 7 gaps |

## Evidence

Public pages were inspected individually on 2026-10-13. No accounts, private pages, client assets or bulk crawler were used. Source dates are null when a page does not show its historical record date; a site's footer year is not a game-data timestamp.

The strongest item evidence is the direct VGOPlayers detail pages for [Attacker](https://vgoplayers.com/items.php?itemId=624001), [Defender](https://vgoplayers.com/items.php?itemId=624045) and [Spellbinder](https://vgoplayers.com/items.php?itemId=624036). These establish exact name capitalization and current recorded stats. They do not establish which live-game patch the values came from.

[Gulgrethor Fortress on Fandom](https://vanguard.fandom.com/wiki/Gulgrethor_Fortress) corroborates the agents' quest relationships and says Missing Agents is not required for the fortress quests. [Vanguard Archive's zone page](https://vgsoharchive.com/zones/sundering-wastelands) and individual quest/NPC pages supplied additional facts. The latter is a 2026 compilation of older material: its embedded source accounts are not independent confirmations. Original Telon Project and some direct quest pages were inaccessible; the inspected MMODB archive URL returned 401. No authentication or access-control bypass was attempted. Archive robots.txt could not be inspected (direct request returned 403); no automated scraping was undertaken. VGOPlayers robots.txt returned 404.

Summaries and notes are original. No guide prose or long dialogue passages were copied. Exact quest dialogue and tracker strings remain unknown rather than replaced with summaries.

## Human checks before integration

- NPC races/models are unknown; converter should withhold all three agents. Their levels do not establish race or combat statistics.
- Agent Nuraga's coordinates disagree in sign. All coordinate strings retain their source format; do not silently treat them as verified XYZ spawn positions.
- Direct pendant records differ from the newer archive in rarity and, for Defender and Spellbinder, stats. Direct records are preferred, with alternatives in notes. Required level is not inferred from item level 23.
- Quest title capitalization and item names need client/tooltips where noted. Do not create duplicate quests from Headless Heralds spelling variants.
- Strong is Weak requires four interactions and has inconsistent orb names. It is withheld by conversion, not reduced to a quest with fewer requirements.
- Unknown coin units, loot rates, respawn times, quest-conditioned drops and merchant stock remain unknown. No numerical rates were assigned to qualitative drop descriptions.
- Pendant of the Mender and Knowledge From The Grave are external references not collected in this batch. The proposal reference report must identify them.
- Remnants requires soul spawning after an undead death; collecting an item alone does not reproduce that behavior.
- Class restrictions and unsupported item properties require manual mapping even where item proposals exist. Icon 443 is only the existing converter fallback.

## Validation and proposal workflow

```text
python -B crowdsourced/validate.py raw/2026-10-13-sundering-wastelands
python -B crowdsourced/convert.py raw/2026-10-13-sundering-wastelands
```

The expected candidates are 8 items and 4 quests; Strong is Weak, NPCs and creatures are withheld. Generated `reviewed/2026-10-13-sundering-wastelands/proposed/ISSUES.md` is the authoritative conversion warning list. `PROVENANCE.json` preserves all accepted records' sources, confidence and notes, including records not converted. No server files are imported or changed.
