# Crafting components — parser version 7

Recipe component lists now preserve ingredients, explicit parenthesized quantities, tools, utilities, enhancements, and candidate products. Embedded item tooltips are excluded from component names. Unlinked names and duplicate rows remain as printed; absent counts remain null. Ingredient lists do not establish whether every material is required together or whether rows represent alternatives.

Launch-era guide markers are recorded per component and lower confidence because the archive reports those details as unconfirmed. Nonnumeric level placeholders such as `xx` remain unknown. Candidate products do not select a guaranteed output.

The new immutable cache-only batch `raw/2026-10-13-224056-514671-archive-enriched-v7/` contains 3,516 research records from 995 cached pages, with no network requests during replay. Three recipe pages were examined, including Aged Leather and Amateur Bag; their missing outputs remain null. Previous raw batches are unchanged.

All 97 tests pass. New cases cover embedded tooltip contamination, explicit counts, repeated utilities, level placeholders, and multiple candidate products. The live downloader runs with parser version 7. Its published checkpoint reports the parser of its last completed batch until the next batch is delivered.
