# Healing range boundary correction — parser version 16

A synthetic percentage-range example exposed regex backtracking: `Heals an ally for 10 to 20%` could previously contribute an incorrect flat amount of 10. The parser now rejects that partial range match while preserving explicit flat ranges such as 10 to 20. Integer and decimal percentage ranges are covered by regression checks. Duration-unit matching also requires a word boundary.

A read-only audit reviewed 831 cached ability pages and found no matching percentage-range wording. `HEALING_PERCENT_AUDIT.json` preserves that audit result. No affected existing research record was identified, and previous raw batches remain unchanged.

All 116 tests pass. The downloader was gracefully checkpointed and restarted with version 16; the correction applies to future extraction.
