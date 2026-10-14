# Ability extraction review — parser version 4

The new immutable cache-only batch `raw/2026-10-13-221434-123320-archive-enriched-v4/` contains 3,315 research records from 712 downloaded pages. It made no network requests and passed structural validation with zero issues.

Among its 3,009 ability records, 285 now have explicit resource costs, 263 have short exact current tooltips, and 121 have numeric effect observations. These counts describe populated fields, not fully verified abilities or finished combat implementations.

## Evidence preserved

- Brutal Strike I records 20 endurance and an Instant cast. Its current damage bonus is 6, while alternate and historical descriptions state 7. The versions remain separate.
- Energy Rift I's archive labels contain endurance costs of both 171 and 30. The operative cost remains null and confidence is low. The current damage range is recorded separately from the historical range; energy restoration numbers remain separate as well.
- Holy Strike II retains the current additional damage range and flat bonus, with historical figures under their own scope. No character scaling or target-condition behavior is guessed.

The archive reports some values as read from VGO Emulator tooltips and others as spellbook existence without tooltip verification. Those claims are marked as reported by the archive; this collector has not independently authenticated screenshots or selected a historical live-game patch. Long tooltip text and guide prose are not copied.

## Validation and remaining work

83 tests pass. New cases cover named costs, contradictory cost labels, equal repeated costs, current versus historical values, long-tooltip handling, percentage-versus-flat damage, explicit restoration durations and weakness tags. Review still needs complete damage/healing formulas, scaling, conditional effects, ability IDs, missing units and source-version reconciliation.

The live downloader continues with the new parser. Background checkpoints and previously delivered batches remain intact. All changes are confined to `crowdsourced/`; no server import or commit was performed.
