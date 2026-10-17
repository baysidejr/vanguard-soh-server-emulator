# Archive collection

Alternate-source transport groundwork is in `multisource_client.py`. It requires
the calling process to own the existing collector lock, uses the archive's shared
request clock and persisted minimum interval, and evaluates robots separately for
each allowed host (including query URLs). Robots denial or HTTP errors propagate
without retry; waits check graceful stop every 250 milliseconds. Cached bodies are
checked against source URL and SHA-256 metadata. This module is not yet wired into
the live archive runner: alternate-source queue scheduling, transient recovery and
article extraction remain required before live alternate-source collection.

The strategy is a whole-site canonical URL inventory followed by batches of linked game records. Sundering Wastelands and Wildgrowth Forest come first. Zone maps supply useful entity/quest relationships, but their links do not enumerate every record associated with a zone. The subsequent site-wide pass collects pages that would otherwise be missed, including items whose zone is unknown.

The initial sitemap inventory contains **104,855 distinct URLs**, including 100,666 supported detail pages: 75,066 items, 15,418 archive mob entries, 4,776 quests, 3,057 abilities, 401 zones, 1,582 recipes and 366 diplomacy cards. The collector also reads 27 canonical class/profession indexes, which can supply many ability rows per request. Remaining URLs include other indexes, effects, races, class subpages and guide/lore pages requiring additional extraction rules. The URL inventory is not a dump of all game records.

The archive's [robots.txt](https://vgsoharchive.com/robots.txt) permits crawling, requests five seconds between requests, and disallows query URLs. The collector uses a user-requested minimum of **15 seconds between request starts** (four requests per minute), honors any longer robots crawl delay, and rejects redirects. Its inventory comes from [canonical sitemaps](https://vgsoharchive.com/sitemap.xml). No linked structured export was found on the homepage or sitemap-pages listing. At 15 seconds per request, the remaining 82,447 pages require at least 14.3 days, before interruptions and review. The computer must remain running; there is no scheduled restart after a reboot.

## What gets saved

The initial detail-route count above describes the original collector. Current route support and download coverage are recorded in `reviewed/COVERAGE_AUDIT.json`: effects and supplemental pages are now recognized too. Supplemental pages currently supply source metadata rather than complete typed game facts. Coverage distinguishes zero-issue published batches, published research in batches with unresolved validation issues, cached-only pages, and pages not downloaded. None of these states proves historical game accuracy or complete mechanics.

Parser versions 19–23 add explicit quest repeatability, reject unresolved template chain links, retain level-qualified XP separately from unconditional rewards, recover inline objective counters, match explicit Slay/Kill trackers to exactly linked mob names, and recognize additional exact item-type labels. Earlier immutable batches retain their earlier parser versions. `reviewed/EXTRACTION_V*.json` identifies each targeted cache replay and its checks; replays overlap downloaded pages and must not be counted as new downloads.

Pending items were prioritized after repeated timeouts on distinct mob pages while an item page succeeded. Every pending URL was retained; this changes collection order, not scope. See `reviewed/QUEUE_PRIORITY_ITEM_RECOVERY.json` for the recorded queue change. Failure records and queue checkpoints preserve pages still needing download.

- New immutable `raw/<timestamp>-archive-*/` batches with singular-type JSONL files, source URLs, confidence, notes, `gaps.jsonl` and `REPORT.md`.
- `archive_fields`, `archive_stats`, `archive_conflicts`, `map_places`, rank and card-pool fields preserve labelled facts beyond the current server converter's coverage.
- `manifest.json` records exact fetched-page coverage. `queue.json` lists uncollected pages. `VALIDATION.json` lists structural/review issues in subsequent automated batches.
- New manifests distinguish successful network responses during the batch from attempted requests, including failed requests. Cache hits contribute neither. Older manifests used a process-wide successful-response count; do not sum their request counts as batch totals.
- Complete-page caches and working checkpoints stay in ignored `.cache/`; dependency packages stay in ignored `.tools-current/` (with `.tools/` retained for older installs). Neither is server content or a committed data batch.
- `reviewed/COLLECTION_STATUS.json` updates when a batch is published. Background stdout logs each processed page.

Parser versions 2 and 3 extract explicit tracker counters, hand-in NPCs, XP, denominated money, reward-choice tables and class restrictions printed on the page. Partial counter matches remain in `candidate_steps`; they do not become a complete quest unless objective coverage and exact targets are established. Bare ability timing, cost and range numbers retain unknown units or resources. Exact spawns, missing merchant inventories and unclear binding triggers remain unresolved. Observed loot frequencies are not developer probabilities, unlabelled coin numbers are not copper, item level is not required level, a previous quest is not necessarily an enforced prerequisite, and a rebuilt tooltip is not a screenshot. Mob pages without a clear NPC role still require entity-kind review. Names shared by multiple pages retain variants and low confidence; no statistics are blended.

Version 3 fixes shared citation lists in class-table rows. Prefer its independently cited class-table records over version 2 class-table snapshots. Version 4 extracts named resource costs, Instant casts, weakness tags and numeric effect observations. Conflicting cost labels withhold the operative cost. Current, alternate and historical effect observations remain separate; they are not complete combat formulas. Short current tooltips are copied only when at most 25 words. The immutable older snapshots remain available for audit. Code changes never rewrite delivered raw batches.

The converter maps archive stat codes such as `HIT_POINTS`, `ENERGY` and `SPELL_DAMAGE_FOCUS` to the server's existing stat/modifier names. Conflicting aliases and fractional values without verified integer scaling are retained as unsupported data rather than overwritten or truncated. This changes proposal generation only.

Version 5 adds class-trainer pages. Fifteen trainer indexes were discovered through cached class-page links even though they were absent from the sitemap inventory. Their NPC names, class relationships, continent labels, linked zones and source `/loc` strings are extracted. Descriptive directions are not treated as coordinates, and unlinked region labels are not guessed as chunks. The underlying NPC detail pages are promoted for additional evidence. Cache URL sidecars preserve discoveries outside the sitemap so later enrichment can replay them without making network requests.

Facts are collected automatically. Conversion proposals still require review, and no server imports happen automatically. Earlier hand-reviewed batches remain unchanged and can contain stronger evidence, such as direct VGOPlayers item records.

The converter explicitly withholds loot tables containing `observed_sample` values, including blank samples, even when confidence or quantity fields are later supplied. Printed sample percentages remain research observations rather than operative drop probabilities. `reviewed/LOOT_CONVERSION_SAFEGUARD_20261016T2334.json` records a 41-record counterfactual check with quantities supplied only in memory; immutable source records remain unchanged.

## Setup and operation

From the repository root:

```powershell
python -B -m pip install --no-cache-dir --no-compile --target crowdsourced/.tools-current -r crowdsourced/requirements.txt
python -u -B crowdsourced/collect_archive.py inventory
```

Only one collector can run at a time. Start, inspect or request a graceful stop with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File crowdsourced/collection.ps1 Start
powershell -NoProfile -ExecutionPolicy Bypass -File crowdsourced/collection.ps1 Status
powershell -NoProfile -ExecutionPolicy Bypass -File crowdsourced/collection.ps1 Stop
```

Start launches a hidden background Python process. It resumes the queue and promotes class indexes, then their explicitly listed abilities learned through level 20, before the remaining inventory. The broader pass covers zones, abilities, quests, mobs, items, recipes and cards. Each batch has at most 100 fetched pages; class tables and loot relationships can add many extra records. Class starting-attribute metadata is preserved separately in `class_metadata.json`. Start checks the previous process before removing a stale lock. It does not schedule itself with Windows. Stop writes a signal and allows the current batch to publish; it does not kill a process midway through writing.

For a bounded collection run:

```powershell
python -u -B crowdsourced/collect_archive.py collect --seed https://vgsoharchive.com/zones/wildgrowth-forest --follow-links --limit 100 --topic archive-zone-followup
```

The collector stops on an HTTP, parser or disk error rather than repeatedly requesting a failing page. Failed URLs remain pending. Cached pages and the last published completion checkpoint allow resumption without repeating successful network downloads. Sitemap lastmod is an archive timestamp, not a historical game-data date. robots.txt is refreshed daily during long runs.

## Checks

Downloaded pages can be re-extracted without any network fallback or changes to the live downloader's checkpoint:

```powershell
python -u -B crowdsourced/enrich_cached.py --limit 1000
python -B crowdsourced/build_evidence_index.py
```

Cache enrichment has a separate completion checkpoint for each parser version. It publishes a new batch and never edits an earlier one. `reviewed/EVIDENCE_INDEX.json` groups research rows by normalized name and explicitly recorded zone; it retains separate candidate versions and source-file line references. Row counts and name groups are not counts of distinct game entities. New collector processes rebuild this index automatically after publishing each live download batch; the command above also refreshes it after an offline enrichment run.

```powershell
python -B -W error::ResourceWarning -m unittest discover -s crowdsourced/tests -v
python -B crowdsourced/validate.py raw/<batch-name>
```

Tests use synthetic fixtures and temporary files inside `crowdsourced/tests/`; they make no network requests. Coverage includes source parsing, malformed rank tables, conflicting item values, card pools, safe URLs, crawl spacing, unknown values, and completion checkpoints after successful publication. A clean batch validation is not historical authentication or proof that the zone is fully covered.

Transient connection recovery (read/connect timeouts and closed/reset connections) in continuous runs preserves the partial batch and failed URL, then increases the request interval from 15 to 30, 45 and 60 seconds. Further transient failures retain the 60-second interval; a longer robots delay always takes precedence. The interval is persisted across restarts and is not reset after success. Cooldown respects graceful stop requests. Other failures (including HTTP access/rate errors and parser errors) still stop for review.

Network-unreachable/down transport errors (including Windows 10051) use the same persisted cooldown recovery. Permission, disk and HTTP errors remain fatal for review.

Parser version 32 exposes explicit creature continent, locations-seen and difficulty labels in dedicated observation fields, matching existing NPC coverage. Ambiguous or missing labels remain null. reviewed/EXTRACTION_V32.json records a zero-network targeted replay of 404 cached pages and 1,212 independent DOM field checks; these overlap prior downloads and do not resolve entity-kind or historical review. The already-running collector retains its loaded parser until a later normal restart.

Parser version 33 preserves explicit mob-page Where they stood entries in map_location_observations, including exact linked zones and printed coordinate pairs. Coordinate format and spawn certainty remain null; these observations do not replace operative locations or establish spawns. reviewed/EXTRACTION_V33.json documents the three-page, zero-network targeted replay and source comparisons. Earlier batches remain unchanged; the live collector retains its loaded parser until a normal restart.

Parser version 34 extracts canonical item links from merchant Sells sections, with unknown purchase prices retained as null. Tooltip values are not purchase prices; missing or empty sections retain unknown stock. reviewed/EXTRACTION_V34.json records a 14-page cache-only replay checked against the prior independent DOM audit: 54 stock links, zero network requests and zero structural validation issues. Earlier immutable batches remain unchanged; the running collector retains its loaded parser until a normal restart. Merchant conversion remains withheld where prices are unknown.

Parser version 35 recognizes all 24 canonical sitemap landing/index routes identified in reviewed/INVENTORY_ROOT_PAGE_GAP_REVIEW_20261017.json, including /stats, /skills and /gameplay. These pages publish source metadata and explicit extraction gaps; they do not create guessed typed entities. Normal run startup merges the authoritative inventory into the saved queue, so a graceful stop/restart loads this support and adds the missing roots without manually editing checkpoints. Tests exercise every excluded inventory URL, linked-item discovery and query rejection. Typed extraction and historical review remain pending.
