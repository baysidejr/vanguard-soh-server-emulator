# Coverage audit

Run `python -B crowdsourced/audit_coverage.py` to refresh `reviewed/COVERAGE_AUDIT.json`. The audit performs no network requests and does not mutate the collector queue. It checks all 104,855 distinct sitemap URLs against current route support, cache files and delivered manifests with successful structural validation. Off-sitemap published URLs are listed separately.

At parser version 8, 103,266 sitemap URLs are supported and 1,589 remain unsupported. Unsupported does not mean irrelevant: world, diplomacy, crafting, race, mount and guide routes still require review and additional extraction rules. Index pages are included in that unsupported count. The effect family contains 2,573 detail pages plus its index, correcting the earlier family-total wording.

`cached_only` means a response is on disk but no delivered, validated extraction manifest yet records that URL. The running collector's current batch is intentionally in that category until publication. `published` confirms reviewed page coverage, not completeness or correctness of every game mechanic. Null values, conditional effects, unknown spawns and uncertain historical rules remain research gaps.

The manifest audit avoids counting cache-only replay versions multiple times. This differs from the evidence index's research-row counts, which intentionally preserve overlapping versions. The collector's checkpoint may include off-sitemap trainers and other discoveries, so its page total need not match sitemap-only published coverage.

All 101 tests pass, including checks that failed validation does not count as publication and cache presence remains distinct from delivered records. Downloads remain active under the archive's shared five-second request spacing.
