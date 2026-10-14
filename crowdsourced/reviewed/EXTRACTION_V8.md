# Item-effect coverage — parser version 8

The inventory contains 2,573 canonical item-effect detail pages plus one effect index page. These detail routes now enter the bulk collection queue after the previously supported entity categories. The existing queue is retained; restarting the collector adds newly supported inventory URLs without discarding completed work.

Effects use the ability research record format with `record_kind: item_effect` and category `item effect`. They are not trainable class abilities. Names exclude activation pills; activation labels, short explicit tooltips, numeric effect observations, and linked item names are retained. Missing mechanics, timings, and resource costs remain null. Search links containing query parameters are never requested.

The cache-only batch `raw/2026-10-13-224225-751455-archive-item-effects-v8/` contains the Abnegation of X effect and its explicit item relationship. It validates with zero issues. This replay made no network requests and did not revise prior raw batches.

All 99 tests pass. The live downloader was checkpointed and restarted with version 8. The previous published checkpoint contains 1,009 pages; the newly supported effect inventory increases the remaining queue, rather than implying those pages were already downloaded.
