# Healing and periodic restoration — parser version 14

Numeric effect observations now include explicit healing amounts, optional printed healing durations, target labels, group-heal radii and periodic resource restoration intervals. Conditions remain unparsed. No tick count, total periodic restoration, character-adjusted formula or unspecified duration is invented. A radius is stored separately from the healing amount; percentage healing is not mistaken for a flat value.

The immutable cache-only batch `raw/2026-10-13-230323-767791-archive-healing-v14/` reviews 31 cached ability pages and contains 30 primary research records with 51 recognized healing or periodic-restoration observations. A repeated name retains source variants, so these are research counts rather than a unique live-game ability count. Replay made zero network requests and previous raw batches were unchanged.

Examples of explicit printed facts now retained include Alleviate I's 704 healing over 18 seconds and Ancestor's Gift I's 555 healing within 10 meters. These values remain observations in their current or historical scope, not an operative combat ruleset.

All 114 tests pass. Regression cases cover healing duration, group radius, resource interval without an invented duration, and percentage rejection. The live downloader was checkpointed and restarted with version 14.
