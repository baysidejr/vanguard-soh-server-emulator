# Supplemental archive pages — parser version 10

Published canonical guide, world, race, mount, harvesting, crafting and diplomacy pages can now enter the download queue alongside entity detail pages. They follow the same robots policy, shared request clock, cache and resumable publication rules. Query URLs remain excluded.

These supplemental pages produce `source_pages.json` metadata: title, source URL, short explicitly labelled fields, headings and canonical supported links. They do not become guessed zone, mount or other game entities. Every page produces an explicit extraction-pending gap. The original response stays in the local cache for later parser work; the metadata is not conversion-ready content.

The immutable batch `raw/2026-10-13-224739-682041-archive-supplemental-v10/` saves the Wildgrowth Forest world page and its metadata. No typed game record is claimed for this page. An earlier stop-signalled attempt remains as an honest zero-page batch with its pending URL.

All 104 tests pass. New tests cover canonical route classification, query exclusion, explicit links, metadata publication and pending extraction gaps. The original bulk queue was restored from its latest immutable batch before restarting, and the run planner adds newly supported sitemap URLs. The coverage audit marks supplemental routes with `source_only` so download support does not imply full typed extraction.
