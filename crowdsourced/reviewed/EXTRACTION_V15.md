# NPC trainer-role facts — parser version 15

NPC detail records now preserve the taught class when the Role field explicitly prints `Class Trainer - <class>`. This supplements relationships already recorded from trainer indexes. Continent, difficulty wording and Locations seen labels are retained separately. A location label does not establish an inferred zone or spawn coordinate; unknown health remains null.

The immutable cache-only batch `raw/2026-10-13-230720-560621-archive-trainer-roles-v15/` contains 199 NPC research records with explicitly labelled taught classes. The replay reviews 199 cached detail pages, makes zero network requests and leaves previous delivered batches unchanged.

All 115 tests pass. The new regression case checks explicit taught class and continent while ensuring an unlinked location label does not fill an unknown zone or health value. The live downloader was checkpointed and restarted with version 15.
