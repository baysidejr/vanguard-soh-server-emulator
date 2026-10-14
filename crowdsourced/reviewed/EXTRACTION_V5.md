# Trainer extraction review — parser version 5

The archive's canonical class pages link fifteen trainer pages that were absent from the downloaded sitemap inventory. Collection now discovers and prioritizes those published links. Their NPC detail pages are subsequently promoted in the download queue.

The immutable cache-only batch `raw/2026-10-13-222934-851050-archive-enriched-v5/` saved 199 NPC research records from 26 cached trainer/detail pages. Repeated names retain candidate variants; the row count is not proof of 199 distinct live-game actors. The extraction made zero network requests.

## Fields captured

- Explicit trainer service and taught class.
- Continent labels and linked zone names.
- Exact source `/loc` strings; descriptive directions such as Training Center remain descriptive.
- Unlinked region/place labels retained separately, without assigning an inferred chunk.
- Canonical NPC references and per-record source lists.

Race, health, level and precise spawn behavior remain null when unrecorded. When trainer/detail records explicitly reference the same canonical NPC page, newly known service and class relationships may be preserved together; conflicting level, race and location values remain separate candidate evidence.

## Validation

90 tests passed for this version, including numeric versus descriptive locations, class relationships, ambiguous region labels, supported trainer routes, discovery of off-sitemap links from cache and enrichment of an explicitly linked NPC's service relationship. A trainer shared by multiple classes retains every class without selecting the first class as the sole trainer role.

Cache enrichment now considers the inventory, published completion checkpoint, pending queue, discovered trainer links and new URL sidecars. It cannot fall back to the network. Earlier raw batches are unchanged. The live worker remains active and no server imports or commits have occurred.
