# Crowdsourced game data

Facts about the live game (2007-2014) that were only ever on its servers, gathered from fan wikis, guides and archived pages: quests, loot tables, merchant lists, item stats, ability numbers, spawn locations and so on. The game client doesn't contain this data, so the emulator's placeholders (`server/content/`, see [docs/CONTENT_EDITOR.md](../docs/CONTENT_EDITOR.md)) are replaced from here over time.

The server never reads this folder. Records are checked, converted to the server's formats and copied into `server/content/` by hand (or by a converter script), so a bad batch can't break anything.

## Layout

| Path | What it holds |
|---|---|
| [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md) | The instructions for an AI agent (or a person) collecting data: what to look for, the record format, the rules. |
| `raw/<YYYY-MM-DD>-<topic>/` | Batches as delivered: `*.jsonl` files (one JSON record per line), `gaps.jsonl` and a `REPORT.md`. Never edited after delivery. |
| `reviewed/` | Records that were checked and are ready to import, in the same format. |
| `imported.md` | A log of what was imported into `server/content/`, from which batch, and when. |

## Licensing and sources

- Every record carries `sources` (URL, page title, date). Keep them: they are the attribution that CC BY-SA wiki content requires, and they let anyone check a value.
- **Facts** (levels, stats, prices, coordinates, drop lists) are not copyrightable and can be stored from any public source.
- **Text** copied from fan wikis licensed CC BY-SA (e.g. Fandom/Wikia) may be stored with its source link; this folder's text content is shared under the same license (CC BY-SA 4.0) as far as it comes from such sources.
- **Text from sites whose terms forbid reuse** (e.g. commercial database sites) is not stored: only the facts.
- **In-game text** (quest text, NPC lines, item descriptions) belongs to the game's owner, like the client itself. Short quotes are kept only where the emulator needs them to reproduce the game.
- Never store personal data: no forum usernames, emails, or anything from logged-in or private pages.
- Never put game client files (anything from the install outside this repository's own folders) in here.
