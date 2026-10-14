# Supplemental metadata validation

`validate.py` now checks delivered `source_pages.json` alongside typed records and gaps. Source-page URLs and internal entity references must use canonical HTTPS archive URLs without queries or fragments. Names, record kinds, short labelled fields, headings, section lists and linked entity shapes are checked. Older metadata batches without section lists remain compatible.

These checks validate representation, not historical truth or extraction completeness. Supplemental pages retain extraction-pending gaps and are not server content. Existing raw files are unchanged.

All 110 tests pass. New cases cover valid older metadata, invalid query/external references, oversized prose fields, and malformed section links. `VALIDATION_AUDIT.json` records the read-only revalidation results for delivered batches.
