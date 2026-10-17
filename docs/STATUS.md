# Vanguard Emulator: Status Review

*Written 2026-10-16, updated 2026-10-17. Repository: https://github.com/baysidejr/vanguard-soh-server-emulator (branch `main`).*

This document is for a full review: what the emulator does today, what is placeholder, what is left, what is blocked, and what needs a decision from you. Each section links to the detailed doc. The README's checklist and `PROGRESS.md` stay the running records; this is a snapshot of both, organised for reading.

---

## 1. Summary

| | |
|---|---|
| **Goal** | Rebuild the server side of *Vanguard: Saga of Heroes* from the game client alone (client 1.324.1.139565). |
| **State** | The unmodified client logs in, creates characters, enters a 3D world and plays: combat, quests, crafting, harvesting, diplomacy, groups, guilds, raids, mail, the broker, housing, mounts, flight, pets, fishing, and more. |
| **Content** | 93 regions populated from a crowdsourced archive scrape: ~2,100 NPCs, ~300 creatures, 368 playable archive quests. Most numbers (stats, prices, rewards) are placeholders. |
| **Code** | 55 server modules (~27,000 lines of Python, standard library only), 15 tools. 1,069 commits since 2026-10-11. |
| **Checks** | 282 unit tests, 26 multiplayer scenarios, a load test, a fuzzer (packet log on) and a client smoke test: `tools/check_all.py --client` passes 7 of 7 (last run 2026-10-17), on a scratch copy of the save, so the real database is never touched. GitHub CI runs the tests on every push (green). |
| **Protocol coverage** | The client handles 720 zone messages; 682 (94%) are sent by the server or not needed. 38 optional ones remain. |
| **Load** | 50 bots for 15 minutes in Khal (the busiest chunk): memory flat at 150 MB, ping p95 11 ms. |

---

## 2. How to run and test

- **Server:** `cd server && python login_stub.py` (add `--dev-commands` for the `!` testing commands). Ports: UDP 10101 login, 10100 world, 10102 zone; HTTP 10180 launcher.
- **Log in:** `python tools/play.py` (launcher, account password), or for testing `bin\VGClient.exe --sessionid=12345678`.
- **Accounts:** `python server/accounts.py create <name> <password>`; `--allow-registration` lets players make their own.
- **Saved data:** SQLite `server/vanguard.db`; automatic backups in `server/backups/`; `python server/storage.py set <char> <field> <json>` edits a character.
- **All checks:** `python tools/check_all.py --client` (unit tests, content validation, scenarios, load test, server-log scan, fuzzing, client smoke test).
- **Content editor:** `python tools/editor.py` then http://127.0.0.1:8099.
- **Refresh from the archive scrape:** `python tools/refresh_archive.py --apply`.
- **Hosting for others:** [docs/HOSTING.md](HOSTING.md).

Tools in `tools/`:

| Tool | What it does |
|---|---|
| `check_all.py` | Runs every automated check; `--client` adds the game-client smoke test |
| `smoke_test.py` | Starts server and client, enters the world, types ~49 commands, fails on any error |
| `scenarios.py` | 14 multiplayer scenarios with headless players (chat, group, trade, tell, friend, guild, brotherhood, duel, AA, quest reply, parley line, ignore, riftway...) |
| `loadtest.py` | Many headless players; `--at=CX,CY,X,Y,Z` puts them in any chunk |
| `fuzz.py` | Protocol fuzzer (found and fixed several handler crashes) |
| `editor.py`, `editor_ui.html`, `editor_e2e.mjs` | Local web content editor, its UI, and a headless click-through test |
| `import_zone.py` | Imports archive NPCs, creatures, camps, zone-map people, altars and mailboxes into a zone |
| `quest_readiness.py` | Finds archive quests the world can support; adds them (with placeholder camps / deliveries) |
| `refresh_archive.py` | One command: zone import + quests + chain links + content check |
| `winbreak.py` | Breakpoint logger for the running client (Windows runtime debugging) |
| `play.py` | Launcher (password login, one-time session token, HTTPS) |
| `unsent_messages.py`, `notice_table.py`, `ability_names.py` | Generate the protocol coverage table, the client notice table and ability names |

---

## 3. What is done

Everything below works with the real, unmodified client. Items marked **(live)** were checked in the game; the rest are covered by unit tests or scenarios.

### 3.1 Connection, login and characters
- Login server, server list ("Stub World"), character list with 3D previews; create, customise, delete characters.
- World and zone server hand-off; the full Unreal Engine 2 handshake (HELLO → CHALLENGE → LOGIN → WELCOME → JOIN); package map built from the client's own files.
- Accounts with salted PBKDF2 passwords, a launcher with one-time session tokens, optional HTTPS, suspensions, one connection per character, characters per account.
- Reliable-packet resends and in-order delivery; long messages arrive intact.
- Saving: position, chunk, level, XP, coins, bags, equipment, hotbars, quests, factions, skills, titles, presence and more, per character in SQLite; backups every 6 hours.
- Server console: `who`, `announce`, `kick`, `backup`, `reload` (content changes go live), `stop` (saves everyone and closes clients cleanly).
- Caravans (log in at the caravan's location after being offline).

### 3.2 The world
- 3D world with the real terrain; standing on the ground anywhere; crossing chunk edges into neighbouring zones; teleporting; `/unstuck`.
- Other players and NPCs drawn with name plates, minimap entries, gear and correct gender.
- NPCs: wandering, chasing, leashing (walk home and heal when they give up), fleeing at low health, calling friends for help, idle chatter and attack lines, greeting voices, facing each other.
- Creatures: any of the client's 330 creature races.
- Riftways between regions (`/rift` and the Riftway map), 36 of 39 destinations open. **(live)**
- Altars of Binding in many regions; releasing to a bind in another region travels there. **(live)**
- Travel journal (Locations tab, discovered by walking near places, `/traveldirections` compass marker).
- Swimming, breath and drowning; fall damage.
- The game clock (`/time`), `/played`.

### 3.3 Combat and abilities
- Targeting, auto-attack, hotbar abilities with real animations and particle effects, cast bars, cooldown sweeps.
- Misses, dodges, parries, blocks, critical hits; resist chances; combat text in the client's Combat tab.
- Buffs, damage over time with debuff icons, heals (on others too), stuns, roots, fear; maintained stances.
- Combat chains (opener → next step → finisher via the client's reaction button); NPC spell casts players can counter.
- Experience scaled by level difference (no XP from gray mobs), a rising XP curve, level-ups that heal and raise attributes.
- Death, the death window, release, experience debt, tombstones (recover to win back half the debt), resurrection offers, corpse summoning, consent and corpse drag.
- Wounds from critical hits; resting heals them.
- Encounters (group-of-mobs display), NPC hate lists, rescues.
- Combat forms / Psionicist mindsets, forms ending on death and `/applyformondeath`.
- Pets (a summoned wolf with its own ability bar), minions, class summons (Necromancer abomination, Shaman attendants, Psionicist simulacrum).
- Alternate Advancement (AA window, points from experience, ranks that raise attributes).

### 3.4 Character
- Character window: attributes, health/endurance/energy pools, armor class, attack, defense, critical chance, skills, harvesting and crafting tabs, attribute points to spend.
- Race and class attribute strengths; gear raises attributes, armor class, health and damage.
- Titles (prefix/suffix, `/titleset`, quest rewards, shown overhead).
- Gender change, race change, rename and experience-debt-clearing items using the client's own service windows.
- Hint popups (first login, kill, loot, level, death).
- **Diplomacy presence:** the eight station ranks (Newcomer, Known 75, Respected 225, Renowned 900, Famous 4,500) in Character > Diplomacy. **(live)**

### 3.5 Items, inventory and economy
- Bags, stacks, splitting (Ctrl+click), extra bags on the bar, moving and destroying items; equip/unequip with models on the character; real item tooltips; item links in chat.
- Item flags (No Trade, Soulbound, Bind On Equip...), an unbinding tool; durability and repairs.
- Loot from corpses, coin on corpses, the loot sparkle; group loot modes (Free For All, Round Robin, Master Looter, Need/Greed/Pass rolls).
- Merchants (buy, sell, buyback tab, repair); 76+ imported merchants sell role-matched placeholder stock (weapons, ranged, heavy/medium/light armor). **(live)**
- Bank (items and coins), escrow for rewards that don't fit, mail (letters, coin, items, cash on delivery, returns), the broker (list, search, buy, sell via mail).
- Player-to-player trading.
- Usable items: food with reuse timers, item conversion (ore to ingot), salvage kits, a spyglass, fireworks (sparklers). **(live)**

### 3.6 Social
- Chat: say, shout, tell, OOC, group, emotes, social animations; `/who`, friends, ignore (refuses invites, trades, duels), `/afk`, `/anon`, `/lfg`, `/random`, `/inspect`, `/report`, `/bug`.
- Groups (window with live bars, Find tab, request to join, invite referrals, `/groupboot`, `/grouppromote`, marks, `/rope`), raids up to 24 with ready checks, mentoring.
- Guilds (ranks, MOTD, notes, points, recruiting, headquarters), brotherhoods (with an XP bonus).
- Duels (challenge popup, countdown, fight to 1 HP, timeouts).
- Summoning a player (`!call`, the client's Call Confirmation).

### 3.7 Crafting, harvesting, fishing
- Harvesting nodes with tools and skill-ups; quest-relevant nodes marked.
- Multi-stage crafting at refining and finishing stations with quality grades, complications, utilities, catalysts, the toolbelt; recipe trainers; choosing a trade (Blacksmith, Outfitter, Artificer).
- Work orders (task master, turn-in for coin, crafting XP and faction).
- Assembly crafting at an assembly bench.
- Fishing with the pull minigame, combos, bait, skill-ups, achievements and best-catch boards.

### 3.8 Diplomacy
- Parleys: statement cards, expression pools, the conversation bar, NPC opponent, win and loss, diplomacy XP, card refresh timers, reward cards, per-character decks, saved deck presets.
- Civic diplomacy (`/citystatus`), dialogue unlocked by winning a parley, parley item rewards.
- Imported NPCs offer their archive parley types (Gossip, Convince, Interview...); the reward scales with the archive's parley level (a level-37 parley paid 370 XP). **(live)**
- Winning raises presence with the NPC's station (+10, placeholder). **(live)**

### 3.9 Quests
- Quest offers from NPCs and conversation replies, the quest page, tracker, kill/collect/talk steps, prerequisite chains, item reward choice, turn-in, abandon, share, quest icons over NPCs (available / in progress / done), turn-in location on the page.
- **368 archive quests playable** (see section 4), every one checked by a test that plays it through the server's quest code. One delivery quest played end to end. **(live)**

### 3.10 Travel, mounts, housing
- Mounts: horse, dire wolf, camel, griffon; barding; no mounting indoors.
- **Flight:** take-off, climbing and diving (in first person the view steers), landing without fall damage. **(live, fixed 2026-10-16)**
- Housing: plots for sale, building a cottage (or a home from materials), furniture placement, storage chests with permissions, guild headquarters, building inventory, transferring a plot.

### 3.11 Content pipeline and editor
- All content is JSON in `server/content/` (mobs, spawns, items, loot, merchants, quests, abilities, dialogues, diplomacy, recipes, factions, work orders, riftways, forms, songs, titles, hints, outposts, AA, housing plots), validated by `server/content.py`.
- Content editor with forms for every file, a terrain map for spawns, validation before saving, live reload into a running server, proposals reviewed by an admin, archive drafts, the "Archive quests" tab (playable vs blocked per zone, with reasons) and **"Placeholders to review"** (every invented spawn and delivery quest).
- Archive import pipeline (sections 4 and 5).

### 3.12 Testing and operations
- Unit tests (277), scenarios (14), load test, fuzzer, client smoke test, CI on GitHub.
- Soak tests: 50 bots, 15 minutes, flat memory.
- Performance fixes this week: obstacle maps built in a worker process (a 2-second stall became under 22 ms), quest icons indexed (6 ms to 0.1 ms in Khal), quest-page spawn lookups cached.
- Movement sanity checks (logged; optionally enforced).

### 3.13 Reverse-engineering notes
50+ topic docs in `docs/` record what was decoded from the client: [PROTOCOL](PROTOCOL.md), [ZONE_MESSAGES](ZONE_MESSAGES.md) (all 720 messages), [UNSENT_MESSAGES](UNSENT_MESSAGES.md) (coverage), and one doc per system (quests, diplomacy, housing, mounts, crafting...). [TESTING](TESTING.md) records what was tested and how.

---

## 4. The crowdsourced archive content

A separate scraper agent collects pages from a fan archive into `crowdsourced/raw/` on the branch `crowdsourced/archive-collection` (merged into `main` up to commit `2ed0b4b`). The importer turns those pages into server content.

**Imported so far:**

| What | Count | How it is placed |
|---|---|---|
| Regions with archive content | 93 | zone names matched to the client's `ChunkNames.txt` (with case, alias, map-label, sub-area and location-chunk matching) |
| NPCs | ~2,100 | recorded positions; quest start locations for givers; zone-map places for people with no position; map labels |
| Creatures | ~300 | recorded locations; plural map places become camps of three |
| Altars and mailboxes | 59 | zone-map service places |
| Quests | 368 | see below |
| Merchants on role stock | 76+ | titles naming a role (weapons, armor...) |

**The 368 quests:**
- **70** with their real objectives from the archive. Where a kill target has no recorded location, an **invented placeholder camp** stands 1,500 units from the giver (never in water; on the terrain or the giver's floor). 61 camps, 167 spawns, each marked `_placeholder`.
- **298** with no recorded objectives, played as **deliveries**: "Speak with <hand-in NPC>" (marked `_placeholder_steps`, a quarter of the placeholder XP). One also gathers its listed item first.
- 24 quest chains linked (a quest waits for the one before it).

**Things fixed in the data along the way:** heights the archive got wrong (dropped above 150,000), mislabelled merchants ("Object"), zone names spelled differently, NPCs underground being real dungeons, archive location notes ending up as titles, the archive's diplomacy station clashing with the crafting-station field.

---

## 5. What is placeholder

These work in the game but use invented values, because the archive (or the client) does not record them. All are listed in [CONTENT_EDITOR.md](CONTENT_EDITOR.md) and editable in the content editor.

| Area | Placeholder |
|---|---|
| Creature and NPC stats | Health and damage from level and difficulty dots |
| XP and coin | Kill XP formula, level curve, quest XP (100 per level, 25 for deliveries), coin rewards without a unit |
| NPC looks | Race only where the archive records one or a zone mostly agrees (Mekalia, Hathor Zhi, Lomshir, Magi Hold, Tanvu); otherwise the continent's human race. Gender only from titles (Priestess, Lady...). Bordinar's Cleft's dwarves look human |
| Merchant wares | Role stocks (12 archive items of the right kind, 25 copper per level) or general goods |
| Item icons | By equipment slot (the archive has none) |
| Quest text | Greeting, description and summary are generated ("the archive has no dialogue yet") |
| Invented positions | 61 quest-target camps (`_placeholder`) |
| Invented objectives | 298 delivery quests (`_placeholder_steps`) |
| Presence | Everyone starts at 0; +10 per parley win; parleys don't require presence |
| Aggression | Only creatures the archive marks Aggressive attack first (137 of 207 placed) |
| Hand-made content | The camp in the Sundering Wastelands and the Wildgrowth Forest outpost (Orin, Veyla, Garret Holm, Elara...) are invented test content |

---

## 6. What is left

### 6.1 Waiting on you (decisions)
1. **Import the archive NPCs into the two original camp zones?** A dry run is in `crowdsourced/drafts/`:
   - Sundering Wastelands: +4 NPCs (Agents Jargo, Nuraga, Zyrax, Muerden).
   - Wildgrowth Forest: +19 NPCs, including quest givers and hand-in NPCs (Tracker Nok, Warseer Gulkar, Gazzit Bramble the merchant...), which would make more archive quests playable.
   They would stand beside the hand-made camps, not replace them.
2. **Keep the 298 delivery placeholders?** Some are real delivery quests ("A Dire Message"); others probably had objectives the archive never recorded ("A Battle Rages"). They are marked and listed in the editor; they can be removed in one step.
3. **Merging the scrape branch** happens when you ask (it was merged twice on 2026-10-16).
4. **Start new characters in the real starting areas by default?** Today everyone starts at the hand-made camp. `--start-areas` (verified live 2026-10-17) uses the start the client sends: the Isle of Dawn (the create screen's "trial island" button) or the race's home town (Tursh Village, Shang Village or Karibasa Village, from each race's intro text in the client). They would no longer start where the hand-made tutorial quests are. Backlog B-017.
5. **Gate parleys on presence?** The client has the refusal message, but starting presence and gain rates are unknown (backlog B-010).

### 6.2 Waiting on the scrape (data the archive does not have yet)
In order of what each would unlock (numbers from 2026-10-16):
1. **Quest objective targets:** 1,722 objectives name a creature or item with no archive page yet. These are most of the ~1,400 quests whose giver is placed but which can't be done.
2. **Creature locations:** known creatures with no location (currently replaced by invented camps).
3. **Who drops an item:** 92 objectives name an item no placed creature drops.
4. **Quest givers with no position:** 1,786 quests.
5. **Quest objectives:** 1,520 quests with a placed giver record none (298 played as deliveries).
6. **NPC race and gender:** missing on ~98% of NPCs.
7. **Merchant wares:** not recorded anywhere.
8. **Creature stats** (health, damage): fields exist but are empty on every page.
9. **Quest item sources:** collect items come only from named bosses (e.g. 60 Bags of Searing Stones from one phoenix), because ordinary creature spawn areas aren't recorded.
10. **Unmatched zones:** sub-areas with no map label (Dead Glade, Graystone, Gaxton Village...) need locations that include the chunk.

### 6.3 Cannot be done with the shipped client
- **Instances / dungeons with their own maps** (e.g. Ancient Port Warehouse, 127 archive records): the client ships no instance maps, so they cannot be hosted.
- **Doors:** none exist in the shipped maps (the protocol is worked out).
- **Psionicist psionic points:** the messages are known, but the shipped UI has no window for them.
- **The civic stats window:** none in the shipped UI (`/citystatus` lists them in chat instead).
- **Other diplomacy lists** (attributes, parley skills, expendables, traits): decoded, but no shipped UI file reads them (VGUIAssets references only `PCDiplomacyPresenceList`, checked 2026-10-17), so nothing can display them.
- **Adventure Journal quests section** (messages 0x2a2/0x2a7/0x2a8/0x2ab decoded): no window shows it in the shipped UI.

### 6.4 Server features still open
- **38 optional messages** never sent: encounter-window details, combat-form state details, map-window signals, petition windows (left alone on purpose), pet ability examine, scripted NPC alert lines, a camera field-of-view message and a few more. The game works without them; list in [UNSENT_MESSAGES.md](UNSENT_MESSAGES.md).
- **Invisible quest-node particles:** the quest-node glow is attached by the client but was not seen. Its emitters are small sparkles at the node's pivot (`tools/fx_props.py`), but size is not why it is unseen: spawned on open ground next to a visible sparkler it still showed nothing (live, 2026-10-17); attached to an NPC (Orin) with the same messages it does render (gold sparkles around his head, live 2026-10-17), so only the harvest-node pawns hide it: the client places it at twice the node's collision height (50 for an ore vein, read with winbreak) above its base, inside the taller boulder. Client data; left as is. (The corpse loot sparkle does show: small white glints, seen live 2026-10-15, docs/LOOT.md. Fireworks show via sparkler emitters.)
- **Flight landing** can't trigger where the server's terrain lookup has no height (far east end of the Sundering Wastelands); the flier just stops on what it touches.
- **Presence gating:** parleys don't require presence yet (deliberately, until presence has a real source).
- **Feel of the numbers:** someone who played the original should judge XP, damage, prices.

### 6.5 Testing a person should do
[TESTING.md](TESTING.md) has a hand-run regression list (about 70 items). Many were checked live during development, but the list itself was not walked through in one sitting. Items marked ✦ need two players. The ones added this week:
- An archive quest giver offers its quest (`!visit Inquisitor Nalstom`); a delivery plays end to end (`!visit Acolyte Terlan`, then Acolyte Weylan).
- A placeholder camp stands on dry ground (`!visit Dread Waylayer`).
- An archive parley raises presence (`!visit Afshin Budjiri`, `!parleywin`).
- Griffon flight down to the ground in first person.
- `!visit <NPC>`.

**Note:** automated in-game testing stopped on 2026-10-16 around 10:00. A hidden window of the Windows **GameInput service** (`GameInputServiceWindow`) holds the foreground, so the game never gets keyboard focus and ignores scripted input. Clicking into the game yourself, restarting the "GameInput Service", or a reboot should clear it.

---

## 7. Recent work (2026-10-15 to 2026-10-17)

**Archive content**
- Bulk import of 93 regions; camps from zone maps; 734 NPCs placed from zone-map places; altars and mailboxes; NPCs at map labels; role stocks and slot icons for merchants; real races where recorded, zone default races, female titles.
- Import fixes: case-insensitive zone names, aliases, sub-areas, location chunks, mislabelled merchants, impossible heights, title cleanup.
- Quest readiness tool, placeholder camps (never in water), delivery placeholders, chain links: 22 → 368 playable quests.
- Merged the scrape branch into `main` twice.

**Server**
- Diplomacy presence decoded and sent; won parleys raise it (fixed so the row updates after a parley); rank thresholds decoded; archive parley XP scales with level.
- Flight descent fixed (a dive no longer counts as a fall).
- Fireworks made visible.
- Performance: obstacle maps in a worker process; quest icon index; quest-page spawn index.
- `!visit <NPC>` dev command; `loadtest --at`.

**Editor**
- Archive quests tab (per zone: playable / blocked and why), Placeholders to review, parley list fix.

**Fixes to my own mistakes this week**
- 215 NPCs briefly became crafting stations (field-name clash); fixed and guarded by the content check.
- A test character's XP was restored by hand arithmetic and was off; restored from a backup.

**2026-10-16 evening to 2026-10-17 (the backlog loop; docs/MASTER_BACKLOG.md)**
- Checks never write the real save: every phase of `check_all.py` and `smoke_test.py` runs on a read-only scratch copy (`storage.scratch_copy`); verified with a row fingerprint before and after (B-001).
- New scenarios: second login, reconnect after a crash, chunk hand-off and return, walking across a chunk edge, /report, /bug, lockout commands, rescue rope, appearance settings, item links (B-005, B-015); unit tests for leaving a chunk.
- Deep fuzzing found one bug: the packet logger failed on 2-3 byte reliable packets and dropped them (B-016, fixed); the fuzz phase now runs with logging on.
- `tools/provenance.py` (sourced / placeholder / unmarked records per content file), `tools/fx_props.py` (effect emitter properties), `tools/stop_servers.ps1`, `fuzz.py --context`.
- Quest-node particles explained (B-006): the client places them at twice the pawn's collision height above its base (Ghidra), an ore vein's is 50 (winbreak), so they sit inside the boulder; on an NPC they show. Client data.
- Fixed: the editor's quest form could drop turn_in (B-013); `--branch` reads leaked temp folders (B-014).

---

## 8. Where things live

| What | Where |
|---|---|
| Server code | `server/` (`login_stub.py` main loop, `zone.py`, `combat.py`, `quest.py`, `diplomacy.py`, ...) |
| Content | `server/content/*.json`, spawns in `server/content/spawns/<chunk>.json` |
| Saved data | `server/vanguard.db` (not committed), backups in `server/backups/` |
| Archive scrape | `crowdsourced/raw/` (merged), branch `crowdsourced/archive-collection`; import log `crowdsourced/imported.md` |
| Tools | `tools/` |
| Docs | `docs/` (this file, PROTOCOL, TESTING, CONTENT_EDITOR, one per system) |
| Progress log | `PROGRESS.md` (next action, test results, dated log of everything done) |
| Feature checklist | `README.md` |
