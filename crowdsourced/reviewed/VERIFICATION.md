# Collection and converter verification — 2026-10-13

All writes were confined to `crowdsourced/`, including test scratch directories and generated proposals. No server content was imported. Git changes remain uncommitted.

## Checks run

- `python -B -W error::ResourceWarning -m unittest discover -s crowdsourced/tests -v`: **35 tests passed**. Covers percentage interpretation, precision and invalid probabilities, duplicate records and slug collisions, malformed nested data, absent source/confidence fields, unknown-value handling, quest IDs, partial objectives/inventories/loot, unresolved references, zero values, provenance, reruns, and delivery-file validation.
- `python -B crowdsourced/validate.py raw/2026-10-13-sundering-wastelands`: **20 records; zero structural validation issues**.
- `python -B crowdsourced/validate.py raw/2026-10-13-wildgrowth-forest`: **12 records; zero structural validation issues**.
- Both converter CLI runs completed successfully. All generated JSON files were read back and counts compared with the collected records.
- `git diff --check`: passed. Git status contains only changes inside `crowdsourced/`.

No extra packages were installed; Python's standard library was sufficient. Bytecode writing was disabled with `-B`. Tests use synthetic fixtures and clean up their temporary files.

## Delivered batches

| Batch | Raw records | Research gaps | Item candidates | Quest candidates | Conversion issues |
|---|---:|---:|---:|---:|---:|
| [Sundering Wastelands](../raw/2026-10-13-sundering-wastelands/REPORT.md) | 20 | 7 | 8 | 4 | 33 |
| [Wildgrowth Forest](../raw/2026-10-13-wildgrowth-forest/REPORT.md) | 12 | 6 | 3 | 0 | 15 |

Conversion issues are reported review work, not failed structural tests. Their number includes one entry per unsupported interaction and per unsupported item property; it is not a count of bad records.

## Import readiness

These proposals are **not ready to merge**. Sundering Wastelands quest candidates have unresolved giver/turn-in NPC references, and one reward choice lacks an item definition. Unsupported item stats and restrictions remain preserved in metadata for manual mapping. Unknown NPC/creature race or health prevents complete templates. The four Wildgrowth Forest quests are low confidence and skipped by default. Strong is Weak is withheld because the converter cannot express its interactions.

The reports retain contradictory names, coordinates, levels and item stats for review. Direct VGOPlayers item facts were preferred over conflicting later archive transcriptions. No source establishes complete live-game patch provenance. Passing tests verifies converter behavior; it does not authenticate the historical data or validate an integrated server.

## Next collection targets

1. Resolve the three Gulgrethor agents' client models and health using historical screenshots or public packet-derived records; reconcile Nuraga's coordinates.
2. Find the direct Pendant of the Mender record and the original Tracker Camp quest pages, including the archive's alternate readings.
3. Collect explicit item race restrictions and verify the remaining item-property mappings against the server formats.
4. Recover merchant stock, prices and quest-conditioned loot. Keep rates and quantities unknown until evidence establishes them.
5. After these gaps, expand to the racial starting areas and class trainers/ranks I–III using the same batch workflow.
