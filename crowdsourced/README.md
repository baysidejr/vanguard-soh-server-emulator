# Crowdsourced game data

Facts about the live game (2007-2014) that were only ever on its servers, gathered from fan wikis, guides and archived pages: quests, loot tables, merchant lists, item stats, ability numbers, spawn locations and so on. The game client doesn't contain this data, so the emulator's placeholders (`server/content/`, see [docs/CONTENT_EDITOR.md](../docs/CONTENT_EDITOR.md)) are replaced from here over time.

The server never reads this folder. Records are checked, converted to the server's formats and copied into `server/content/` by hand (or by a converter script), so a bad batch can't break anything.

## Layout

| Path | What it holds |
|---|---|
| [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md) | The instructions for an AI agent (or a person) collecting data: what to look for, the record format, the rules. |
| `raw/<YYYY-MM-DD>-<topic>/` | Batches as delivered: `*.jsonl` files (one JSON record per line), `gaps.jsonl` and a `REPORT.md`. Never edited after delivery. |
| `reviewed/` | Checked records and generated `proposed/` candidates; proposals with issues still require human review before import. |
| [validate.py](validate.py) | Read-only batch validation, including common fields, duplicate keys, gaps and the delivery report. |
| [COLLECTION.md](COLLECTION.md) | Archive inventory, automated collection, background controls, coverage and known extraction gaps. |
| `imported.md` | A log of what was imported into `server/content/`, from which batch, and when. |

## Current conversion handoff

[reviewed/conversion-handoff/HANDOFF.md](reviewed/conversion-handoff/HANDOFF.md) is the consolidated import-agent handoff. It contains generated server-format candidates, exact raw source file/line pointers, input hashes, withheld-record dispositions and unresolved-reference reports. These are review candidates, not replacement content files or an automatic import.

Rebuild after closed-batch updates with `python -B crowdsourced/build_handoff.py` from the repository root. The builder reads all closed raw batches, selects source replays without merging fields, withholds identity ambiguity, and leaves live server files untouched. Refer to `SUMMARY.json` for current counts, not collection-page totals.

## Converting a batch

```
python crowdsourced/convert.py raw/<YYYY-MM-DD>-<topic>
```

writes `reviewed/<batch>/proposed/` with entries in the server's own formats (`mobs.json`, `items.json`, `loot.json`, `merchants.json`, `quests.json`) and an `ISSUES.md` listing everything that needs a human: unknown creature races, unsupported item stats, quest steps it can't express, record types it doesn't convert yet. Names that already exist in `server/content/mobs.json` keep their key (e.g. "Ashen Wolf" stays `wastes_wolf`), so a record updates the placeholder instead of duplicating it. Records with no sources are dropped and low-confidence ones are skipped unless `--include-low` is given. Item icons are set to the client's fallback (443) until someone picks the right icon id. The proposed files are merged into `server/content/` by hand, then `python server/content.py` must print "content OK".

Drop chances are percentages: numeric `1` and text `"1%"` both mean one percent. Qualitative descriptions such as `"rare"` are reported for manual review rather than assigned an invented probability. Quests with unsupported step kinds are withheld entirely to avoid exporting incomplete completion requirements.

Unknown NPC/creature client models, levels or required health withhold the template. Race matching is exact (ignoring spaces and case); model IDs are not guessed from entity names. Unknown bag capacity, weapon delay and aggro radius are omitted with an issue. Loot tables with unknown chances or quantities and merchant inventories with unknown prices are withheld as a whole. Unknown quest targets or required counts withhold the quest. Duplicate records and output-key collisions withhold all conflicting records.

`ISSUES.md` also reports unresolved references against the proposed and current live files. A proposal with unresolved references is not ready to merge. Unmapped item restrictions and properties stay in `_unsupported` for manual handling. `PROVENANCE.json` retains every accepted record's complete source list, confidence and notes; keep it with the proposals. It includes records withheld from conversion and is not a server content file.

Validate a delivered batch before conversion:

```text
python -B crowdsourced/validate.py raw/<YYYY-MM-DD>-<topic>
```

Validation accepts explicit unknown values and low-confidence research records. Conversion still skips low-confidence records by default. A clean structural validation does not mean a record is complete or historically verified.

Quest IDs reuse matching keys from live content and earlier proposals, reserving their IDs before assigning new ones starting at 6000. Run conversions sequentially: ID allocation does not lock against concurrent runs. Every rerun rewrites all five proposed JSON files, including empty ones, so removed records cannot linger. Treat `proposed/` as generated output and keep manual edits elsewhere.

## Tests

From the repository root, run:

```text
python -B -m unittest discover -s crowdsourced/tests -v
```

The tests use Python's standard library and synthetic records. Temporary batches and proposals are created inside `crowdsourced/tests/` and cleaned up afterward. They check conversion and input validation; they do not prove historical accuracy or validate a merged server content set.

## Licensing and sources

- Every record carries `sources` (URL, page title, date). Keep them: they are the attribution that CC BY-SA wiki content requires, and they let anyone check a value.
- **Facts** (levels, stats, prices, coordinates, drop lists) are not copyrightable and can be stored from any public source.
- **Text** copied from fan wikis licensed CC BY-SA (e.g. Fandom/Wikia) may be stored with its source link; this folder's text content is shared under the same license (CC BY-SA 4.0) as far as it comes from such sources.
- **Text from sites whose terms forbid reuse** (e.g. commercial database sites) is not stored: only the facts.
- **In-game text** (quest text, NPC lines, item descriptions) belongs to the game's owner, like the client itself. Short quotes are kept only where the emulator needs them to reproduce the game.
- Never store personal data: no forum usernames, emails, or anything from logged-in or private pages.
- Never put game client files (anything from the install outside this repository's own folders) in here.
