# Instructions for the data-collection agent

You are collecting crowdsourced game data for a fan-made server emulator of the MMORPG **Vanguard: Saga of Heroes** (launched 2007, shut down July 2014). The game client survives, but everything the servers knew is gone: quests, loot, merchant stock, item stats, ability numbers, spawn locations. Find those facts on public fan sites and save them as structured records.

Read [README.md](README.md) in this folder first for the licensing rules.

## Where to write

- Write **only** inside `crowdsourced/raw/<YYYY-MM-DD>-<topic>/`, e.g. `crowdsourced/raw/2026-10-14-wastelands-quests/`. Create a new folder for each batch; never edit an earlier batch or any file outside it.
- In each batch folder write:
  - one `<type>.jsonl` file per record type you found (one JSON object per line, UTF-8);
  - `gaps.jsonl`: things you searched for and could not find (`{"type": ..., "name": ..., "searched": [urls or queries], "notes": ...}`);
  - `REPORT.md`: files written, record counts, the best sources, and anything a human should check.
- If you use git: commit only your batch folder, with a message like `crowdsourced: <topic> batch (<n> records)`. Never add or commit anything outside `crowdsourced/`.

## Where to look

Fan wikis (the Vanguard wikis on Fandom/Wikia and their archive.org copies), vgplayers.com, Silkyvenom, Ten Ton Hammer, Allakhazam/ZAM (facts only, see licensing), MMORPG and Vanguard forum guides, and archive.org snapshots of the official site (vanguardsoh.com / station.sony.com) and its forums. Use the Wayback Machine for sites that are gone.

## Record format

Every record MUST have:

| Field | Meaning |
|---|---|
| `type` | The record type, singular: `npc`, `creature`, `spawn`, `item`, `loot`, `merchant`, `quest`, `ability`, `recipe`, `diplomacy`, `faction`, `dialogue`, `mount`, `fish`, `zone`. |
| `name` | The exact in-game name, spelled and capitalized as in the game. The same name links records across files (e.g. a loot record's `source` is a creature's `name`). |
| `sources` | `[{"url": "...", "title": "...", "date": "page or snapshot date if shown"}]` |
| `confidence` | `"high"` (several sources agree, or a screenshot shows it), `"medium"` (one clear source), `"low"` (vague or contradictory). |
| `notes` | Anything uncertain, contradictory or worth a human check. |

Rules for values:

- Use `null` for anything unknown. **Never invent or estimate a value.** Say why it is missing in `notes`.
- If sources disagree, keep the best-supported value and list the others in `notes`.
- Keep numbers as numbers; money in copper (1 silver = 100 copper, 1 gold = 100 silver, 1 platinum = 100 gold).
- Copy in-game text (quest text, NPC lines, item descriptions, tooltips) exactly. Do not copy wiki commentary or strategy prose.
- Coordinates: record them exactly as written, plus what they are (`"location": {"raw": "-31250, -5450", "format": "/loc", "chunk": "Sundering Wastelands"}`).

### Fields per type (all optional apart from the common ones)

**npc**: `title` (text under the name, e.g. "Merchant"), `race`, `gender`, `level`, `zone`, `chunk`, `location`, `services` (any of `merchant`, `banker`, `trainer`, `repair`, `quest giver`, `task master`, `broker`, `mailbox`, `riftway`, `altar`, `crafting station`), `faction`, `quests_given` [quest names], `trainer_of` (class or craft), `dialogue_ref`.

**creature**: `level`, `level_range` [min, max], `creature_kind` (wolf, bear, spider, undead, ...), `difficulty` (solo, `^`, `^^`, `^^^`, raid), `health`, `damage`, `abilities` [names], `social` (calls for help: yes/no), `aggressive` (yes/no), `aggro_range`, `faction`, `zone`, `spawn_areas` [text or coordinates], `respawn_time`, `loot_ref`.

**spawn**: `what` (npc or creature name), `zone`, `chunk`, `location`, `count`, `movement` (stationary, wanders, patrols + path), `respawn_time`.

**item**: `item_type` (weapon, armor, shield, jewelry, container, food, drink, resource, fishing, tool, mount, quest, misc), `slot` (head, chest, legs, hands, feet, waist, cloak, shoulders, wrists, neck, ear, finger, primary, secondary, two-hand, ranged, ammo, bag), `rarity` (mundane, common, uncommon, rare, heroic, fabled, legendary), `level_required`, `class_restrictions`, `race_restrictions`, `stats` {"strength": n, ...}, `armor`, `damage` [min, max], `delay_seconds`, `weapon_skill`, `bag_slots`, `stack_size`, `value_copper`, `description`, `bind` ("on equip", "on pickup", "none"), `no_drop`, `quest_item`, `effects` (procs, clicks, worn effects, text as shown), `icon_name` (only if a source shows the client icon file or name).

**loot**: `source` (creature or container name), `drops` [{"item": name, "chance": a percentage or the source's wording, "quantity": [min, max]}], `coin_range`.

**merchant**: `npc`, `zone`, `sells` [{"item": name, "price_copper": n}], `buys` (if the merchant only buys certain things).

**quest**: `level`, `zone`, `giver`, `turn_in`, `prerequisites` [quest names], `quest_chain` (name and position), `repeatable`, `requirements` (class, race, faction, level), `start_text` (the giver's offer text), `description`, `summary`, `steps` [{"objective": tracker text, "kind": "kill" | "collect" | "talk" | "use" | "go", "target": name, "count": n, "location": ...}], `completion_text`, `rewards` {"xp": n, "coin_copper": n, "items": [names], "choice": [names], "faction": {"faction name": amount}, "title": text}.

**ability**: `class`, `level_learned`, `rank` ("I", "II", ...), `category` (melee, spell, song, chain, finisher, counter, rescue, combat form or stance, ...), `cost` {"endurance" | "energy" | "mana": n}, `cast_time_seconds`, `refresh_seconds`, `range`, `duration_seconds`, `tooltip` (exact), damage or heal numbers per rank, `chain` (what it follows or unlocks), `trainer`, `icon_name`.

**recipe**: `craft` (blacksmith, outfitter, carpenter, ...), `level`, `station`, `ingredients` [{"item": name, "count": n}], `tools`, `utilities`, `output` (item and count), `steps` (actions and stages if described), `trainer`, `price_copper`.

**diplomacy**: either `"kind": "card"` with `expression` (reason, inspire, flatter, demand), `cost`, `gain`, `push`, `effects`, `level`, `how_obtained`; or `"kind": "parley"` with `npc`, `parley_type` (entertain, convince, interview, gossip, incite), `rewards`, `npc_lines`.

**faction**: `standing_levels`, `members` (NPCs and creatures), `changes` (what raises or lowers it), `allies`, `enemies`.

**dialogue**: `npc` and the conversation as a tree: [{"npc_says": text, "responses": [{"player_says": text, "leads_to": the next npc_says or "end", "requires": text, "reward": text}]}].

**mount**: `how_obtained`, `price_copper`, `speed`, `movement` (ground, flying, aquatic), `creature`, `color`, `level_required`.

**fish**: `water` (fresh, salt), `zones`, `weight_range`, `bait`, `combo` (sequence of up/right/down/left), `skill_needed`.

**zone**: `continent` (Thestra, Qalia, Kojan), `chunks` (names or coordinates), `level_range`, `cities_and_outposts`, `riftways`, `bind_spots`.

## Priorities

1. The Sundering Wastelands and the Wildgrowth Forest (where the emulator's world is), then the starting areas of each race.
2. Starting quests, trainers and class abilities (ranks I-III) for every class.
3. Merchants, item stats and loot tables for levels 1-20.
4. Crafting recipes, diplomacy cards and parleys, mounts, fishing.

[docs/CONTENT_EDITOR.md](../docs/CONTENT_EDITOR.md) lists every kind of data the emulator is missing, if you want more ideas.

## Rules

- Public pages only; respect each site's terms and robots.txt. Don't log in, don't scrape behind paywalls, keep request rates polite.
- Facts from any public source; text only from sources that allow reuse (see README.md). Always keep the source link.
- No personal data: no forum usernames, emails or profile details.
- One record per thing. If you find more data about something already recorded in this batch, update that record instead of adding a second one.
- Finish every batch with `gaps.jsonl` and `REPORT.md`.

## Example records

```json
{"type": "creature", "name": "Ashen Wolf", "level": 8, "creature_kind": "wolf", "difficulty": "solo", "aggressive": "yes", "zone": "Sundering Wastelands", "abilities": ["Rending Bite"], "loot_ref": "Ashen Wolf", "sources": [{"url": "https://example.org/wiki/Ashen_Wolf", "title": "Ashen Wolf - Vanguard Wiki", "date": "2008-03-02"}], "confidence": "medium", "notes": "Level shown as 8-9 on another page."}
{"type": "quest", "name": "Wanderer Trouble", "level": 10, "zone": "Sundering Wastelands", "giver": "Orin the Trader", "steps": [{"objective": "Defeat Robed Wanderers", "kind": "kill", "target": "Robed Wanderer", "count": 3}], "rewards": {"xp": null, "coin_copper": 250, "items": [], "choice": ["Copper Ring"]}, "sources": [{"url": "https://example.org/quests/123", "title": "Wanderer Trouble", "date": null}], "confidence": "low", "notes": "Example only; XP not given by the source."}
```
