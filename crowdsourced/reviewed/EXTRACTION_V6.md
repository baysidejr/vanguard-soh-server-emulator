# Ability timing review — parser version 6

Refresh and recast labels now contribute separate timing observations. Repeated cast-time labels are also retained. Explicit seconds and minutes are normalized for comparison; equivalent values agree, while contradictory values leave the operative timing null and confidence low. Unlabelled timing units remain unknown.

The cache-only batch `raw/2026-10-13-223857-981144-archive-enriched-v6/` reviewed 984 downloaded pages and produced 3,514 research records, including 3,009 ability records and 228 NPC records. These are evidence records with overlapping versions, not a count of unique game entities. The replay made zero network requests and left previous raw batches unchanged.

All 93 tests pass. New regression cases cover conflicting refresh/recast values, equivalent seconds/minutes, and conflicting repeated cast-time labels. The live collector was gracefully checkpointed and restarted with this parser. Downloads continue with the shared five-second request spacing.
