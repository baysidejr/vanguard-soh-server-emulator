# Extraction review — parser version 3

This review records the extraction upgrade during autonomous collection. It does not approve any server import.

## Changes

- Item class restrictions can be read from labels on filtered links already present in a downloaded page. Those query URLs are never requested.
- Explicit hand-in NPCs, quest tracker counters, required-item rows, XP, coin denominations and reward choices are extracted. Missing objective triggers and targets still prevent a complete quest proposal.
- Explicit merchant roles produce NPC and merchant research records. Unknown inventory is null, never guessed or changed to an empty stock list.
- Class/profession index pages supply labelled ability rows and starting-attribute metadata. Low-level ability detail pages are promoted in the download queue. Unlabelled cost resources and numeric timing/range units remain unknown.
- Source-stat normalization uses the existing protocol enums for hit points, energy, focus and other supported stats. Contradictory aliases and unencodable fractional values are preserved for review.
- Page caches publish atomically, so concurrent cache enrichment cannot read a partly written response.
- Version 3 gives each class-table ability its own citation list. A shared spell appearing in multiple classes can no longer add those citations to unrelated abilities from the same source class.

## Corrected snapshots

The version 2 class-table batch `raw/2026-10-13-214014-456434-archive-bulk/` predates the citation fix. Prefer the independently cited class-table records in `raw/2026-10-13-214748-908906-archive-enriched-v3/`; earlier raw snapshots remain immutable.

That cache-only pass saved 3,313 research records, including 3,009 ability records, from 390 cached pages. It later attempted to follow an un-cached class ability reference and stopped; no network request occurred. Its records passed structural validation. The cache-only queue promotion was fixed to stay within the cached input list, and a subsequent pass saved 34 more records without that error. Failed/pending references in the earlier report remain an accurate audit of that run.

Names repeated across classes or sources retain candidate variants and low confidence. The ability count does not mean every ability has complete costs, damage, tooltip text or timing. Individual pages are still being downloaded and checked. No values were blended across contradictory candidates.

## Validation

75 distinct tests pass across converter, collector, cache enrichment, explicit-source extraction and evidence indexing. Tests include citation isolation between class rows, reward conflicts, incomplete objectives, unknown units/resources, fractional protocol modifiers, network policy, graceful stopping and publish-before-checkpoint behavior. `build_evidence_index.py` found no malformed research rows in the delivered batches at this review.

All project changes are under `crowdsourced/`. The background process continues collecting public canonical pages at the archive's requested rate. No server content is imported and no commits have been made.
