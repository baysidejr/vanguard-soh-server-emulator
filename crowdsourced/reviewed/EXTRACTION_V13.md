# Off-sitemap discovery — parser version 13

An offline audit of delivered pages found seventeen supported canonical links absent from the sitemap: fifteen class-trainer pages and two ability indexes. `OFF_SITEMAP_DISCOVERY.json` retains their referring page URLs. This audit made no network requests.

Bulk runs now discover new supported canonical links automatically instead of relying only on the sitemap. Existing queued and completed URLs remain deduplicated. The saved off-sitemap audit also contributes its validated canonical URLs on restart so links found before this change are not missed. Discovery does not request query links, external hosts, or fragments.

`/abilities/as-it-was` and `/abilities/not-in-the-emulator` are explicitly source-only indexes. They are catalogued with extraction-pending gaps rather than being invented as individual abilities. All 106 tests pass, including the index classification checks. Prior raw batches remain unchanged.
