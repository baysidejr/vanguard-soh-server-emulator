# Testing checklist

How each feature has been tested, and what still needs a person at the keyboard.

- **Unit tests:** `cd server && python -m unittest discover -p "test_*.py"` (about 150 tests, all must pass before a commit), plus `python content.py` (checks every content JSON file links up: "content OK").
- **In game:** every feature in the README checklist was tried in the real client while it was built, by scripted key presses and clicks, often with two clients at once.
- **Everything at once:** `python tools/check_all.py` runs the unit tests, the content check, the multiplayer scenarios, a 20-bot load test and a short fuzz run (on scratch data), and prints one summary; `--client` adds the smoke test with the game client. Last run (2026-10-14): 6 of 6 passed.
- **Smoke test:** `python tools/smoke_test.py` (Windows) starts the server and client, enters the world with the character selected on the select screen, types about 40 chat commands and fails on any server traceback, dropped message or client "unhandled message" line. Run it after changes; it takes about two minutes.

Legend: ✅ seen working in the client · 🧪 unit tests only · 👤 needs a person (scripted input can't do it, or the result can't be checked by a screenshot) · ⛔ blocked (no UI in the shipped client, or no data)

## Multiplayer scenarios (2026-10-14)

`python tools/scenarios.py` (after `--setup`, against a running server) logs in two headless players and checks what otherwise needs two people: a chat line from one reaches the other; a group invite and accept; a trade of an item for 50 copper, verified in the database afterwards (and in `audit.log`); a private tell; adding a friend; founding a guild, inviting and joining (checked in the database), disbanding it; a brotherhood invite, join and leave; a duel challenge, accept, countdown and start. Last run: all eight PASS.

## Load test (2026-10-14)

`python tools/loadtest.py` runs headless players that speak the client's protocol: launcher token, world login, character Play, zone login, the UE2 handshake (HELLO / LOGIN / JOIN), then ShortServerMove 4 times a second while walking in a circle near the camp, and a ping (zone type 9, echoed at once) every second. `--setup N` makes the `loadtest` account and N characters (copies of Ranger), `--cleanup` removes them, `--procs` spreads the bots over several processes (one Python process manages about 50). Start the server with `--quiet-packets`.

All bots crowd the camp (within about 1400 units), so every move goes to every other player: the worst case. Results on the development PC (one server process):

| Bots | Before the fixes (ping median / p95) | After (median / p95) | Server CPU after |
|---|---|---|---|
| 25 | 32 ms / 1340 ms | 11 ms / 23 ms | |
| 50 | 828 ms / 1050 ms | 7 ms / 120 ms | |
| 100 | 2.7 s / 5.3 s (7 failed to join) | 11 ms / 450 ms (p95 from the join burst) | 62% of a core |
| 150 | | 2.6 s / 5.1 s | saturated |

What made the difference (found with cProfile under load): packet bits are packed in one integer instead of a bit list; net-field and object lookups are cached; the encoded property update and the pawn open payload are reused for every recipient; movement goes out as unreliable bunches queued per connection and sent 20 times a second, many to a packet; the loop drains every waiting packet per wake-up; position prints follow `--quiet-packets`; the database connection stays open. Verified with two real clients afterwards: the other player's walking (and walking back into view) shows as before.

**Second round (later on 2026-10-14).** Steady-state figures (pings from 5 s after the last bot joined, so the join burst is left out; `--spread 40000` spreads the bots over the chunk, 400 is a crowd at the camp):

| Bots | Where | Steady ping median / p95 |
|---|---|---|
| 100 | crowd | 10.5 ms / 11.4 ms |
| 150 | crowd | 3.2 s / 4.1 s (saturated); 10.5 ms / 12.4 ms once crowds thin out above 25 nearby players instead of 40 |
| 200 | crowd | 7.8 s / 13.4 s (saturated) |
| 150 | spread | 10.6 ms / 11.2 ms |
| 200 | spread | 10.6 ms / 1.4 s (near the limit) |
| 250 | spread | 4.9 s / 11.4 s (saturated) |

What changed since the first round: a resend storm was found and fixed (an overloaded server read acknowledgements late, resent packets that had arrived and fell further behind; the resend timeout now follows each connection's measured round trip, at least 1 s, and resends are rationed per connection and per tick); NPC movement uses the same batched path as players (encoded once, unreliable bunches; distant viewers get moving steps less often, stops always); players are kept in a 12000-unit grid so a movement update only visits nearby viewers (everyone on every 10th update); in a dense crowd each viewer gets every kth update; characters are looked up by account and name in SQL (an indexed column) instead of reading every character on each login.

The load test itself had to behave like a real client before the numbers meant anything: one account per bot (one shared account listed hundreds of characters on every login), acknowledgements batched every 100 ms (one per packet flooded the server with acknowledgements), and resends of the bots' own packets. The server logs `!!! load` (how late pings arrive, packets read, idle time) and `!!! network` (send buffer full, client packets after a lost one) when it falls behind.

So one zone process holds about 200 moving players spread over a chunk, or about 150 in one spot. Beyond that it needs a faster encoder (the per-bunch Python work dominates) or more processes (one per chunk).

**Packet loss.** `--drop 0.1` makes every bot ignore 10% of the server's reliable packets (no acknowledgement, as if lost; bots deliver in order and send Ack1 after a gap, like UdpLibrary). With the server's resends (docs/PROTOCOL.md) 10 of 10 bots logged in (login median 2.9 s instead of 0.1 s) and the ping median stayed at 12 ms (p95 372 ms); at 2% loss p95 is 181 ms.

## Soak test (2026-10-14)

50 bots spread over 4000 units ran for 10 minutes against one server (`loadtest.py --bots 50 --seconds 600 --procs 2 --spread 4000`), with the server's memory sampled every 30 s. The working set stayed at 205 MB from the first sample to the last (no growth), and the server used about 5 s of CPU per 30 s (17% of one core). Over 29,850 pings the median round trip was 10.5 ms and p95 11.1 ms, with a 56 ms maximum. All 50 bots joined and none lost a packet. The server log had no errors.

## Soak test (2026-10-15)

The same 50 bots (`soak.sh 50 300`: `--procs 2 --spread 4000 --stagger 0.1`) after the day's features (FX packages in the package map, NPC chatter, wounds, quest nodes). Memory stayed flat at 220 MB (the bigger package map accounts for the extra 15 MB), pings were unchanged (14,558 steady-state pings: median 10.6 ms, p95 11.5 ms) and the log had no errors. CPU was about 10 s per 30 s (34% of one core), twice the 2026-10-14 figure. An A/B run without the FX packages used about 9 s, so they are not the cause. A profile shows movement broadcasting (`zone.broadcast_movement`) as the main cost, as before. Skipping the per-NPC quest-icon pass when nothing changed (`refresh_quest_icons`) did not change the total. In a 100 s profile under the same load the new per-second checks (chatter, wounds, quest nodes) took under 0.2 s each; incoming movement handling took 33 s, broadcasting 17 s and packet flushing 9.5 s. There is no regression: the server at the 2026-10-14 soak commit (b94321c, run from a worktree with its own `--data-dir`) used 9.6 s per 30 s under the identical 90 s load, and today's server 9.7 s. The 17% figure above came from a different measurement.

## Soak test (2026-10-15, evening)

The same 50 bots (`soak.sh 50 300`) after the evening's changes (NPC give-up and evade, fleeing, parley offer line, quests from conversations). Memory stayed flat at 222 MB, CPU was about 9.5 s per 30 s as in the earlier run, and all 50 bots joined. Over 14,554 steady-state pings the median was 10.6 ms and p95 11.3 ms (42.6 ms max). The bots saw no lost packets and the server log had no errors.

## Soak test, 15 minutes (2026-10-15)

50 bots for 900 s (`soak.sh 50 900`) after the day's changes. Memory stayed at 223 MB from the first sample to the last (no growth over 15 minutes), the server used about 8.7 s of CPU per 30 s, all 50 bots joined, and over 44,398 steady-state pings the median was 10.6 ms and p95 11.3 ms (171 ms max). The bots saw no lost packets and the server log had no errors.

## Content editor (2026-10-15)

- Unit tests (test_systems): saving checks the content first and keeps a backup (EditorTests), saves keep the file's key order, archive search and drafts for mobs, items, quests and loot (ArchiveDraftTests), accounts and proposals (EditorAccountsTests).
- EditorPageTests opens the page in headless Edge (skipped without Edge) and runs its `#selftest`: every quest, mob, item and ability goes through its form and back unchanged, and every field of the Recipes, Parley, Factions, Work orders, Riftways and Forms & songs forms gets change/input events with its value untouched without changing the file. It caught forms that added `"start": 0`, `push: 0` and step `action`/`ap` values that were not in the file.
- EditorSaveTests (skipped without Edge and Node) drives the page with `tools/editor_e2e.mjs` (headless Edge over the DevTools protocol): it changes one value in the Factions and Recipes tabs, clicks Save, and requires each file on disk to differ from before in exactly that line.
- By hand (2026-10-15): the same driver edited and saved the Factions, Recipes, Parley and Work orders tabs against a copy of the content folder; each saved file differed from the original only in the edited lines.

## Fuzzing (2026-10-14)

`python tools/fuzz.py` logs a load-test bot into the zone and sends every client event id from 1 to 0x900 with random payloads of awkward sizes (empty, 1-3 bytes, small ints, 600 bytes), then rounds of random UE2 packets, unknown message types and raw datagrams that skip the reliable layer. After each id a ping checks the server still answers; a silent server gets a fresh login to tell a closed connection from a hang. Run it against a server with its own `--data-dir` (see the script's help), since random events change saved data.

Bugs it found, all fixed:
- A random chunk change (event 0x9) saved the character in chunk (0, 0), which has no map; that character could never log in again. Chunk changes to missing maps are ignored, jumps of more than one chunk need GM access, and a character saved in a missing chunk starts at the default spawn.
- Printing player text that the Windows code page can't show (any CJK character, for example) raised UnicodeEncodeError inside the handler when the log went to a file, so the message was dropped. The server's output is UTF-8 now.
- A zone connection could enter the world without logging in, as "Someone", and a second login request on a logged-in connection replaced its player with nothing (which then crashed the NPC aggro check every tick). Unknown sessions are refused, a second login is ignored, UE2 packets before the login are ignored (`--anonymous-zone` keeps the old debugging behaviour), and a reconnect from the same address leaves the world first.
- A truncated Group length raised struct.error.
- `--world` sweeps the login connection (where character create / delete arrive) and the world server first. Reading those handlers showed Customize (world 0x13b) saved a new appearance for any character named in it, with no account check (even without logging in); it now only changes the account's own characters. Character create now applies the name rule (letters, 3 to 20) and stores this server's world name instead of the one the client sent.

Last run: 0x900 event ids x 20 payloads and 200 raw rounds: no handler errors, no hang. With `--contexts` (and the server started with `--dev-commands`) the sweep runs 7 times, each after setting up a situation first (crafting at the forge, a merchant, the banker, the task master, a fight with the Canyon Widow, the mailbox): 7 x 0x900 ids x 12 payloads in 190 s, no handler errors, no hang.

## Needs a person

| Feature | Status | How to test |
|---|---|---|
| Griffon flight | 👤 | Buy a Griffon Whistle (5000c) from Orin, summon it, jump, then press jump again while falling. Expect to take off. Scripted double presses never triggered it. |
| Combat-form recovery bar | ✅ | Seen 2026-10-13 on a Psionicist: choosing a mindset darkens all three form icons for a moment and rings the chosen one in blue. |
| Caster energy | ✅ | Seen 2026-10-13: a Sorcerer casting See Invisibility I drains the blue energy bar; endurance stays full. |
| Raid of 24 | ✅ (bots) | 2026-10-14: the real client (Ranger) invited 23 load-test bots (`tools/loadtest.py --auto-accept`) and made a raid: "Raid of 24 led by Ranger; raid groups: 1: 6, 2: 6, 3: 6, 4: 6" (`!groupinfo`), every join shown in chat, the group window filled, `/readycheck` answered "You have requested a raid ready check." and, with the bots answering the popup (0xa9 status 1), the leader saw "LbotXX is ready!" for each member. Still for people: what the other members see, and raid loot. |
| Caravan login | ✅ | 2026-10-14: a caravan (Ranger leading, Justins a member) written to the database and Justins' last logout set 4 hours back (`storage.py set`). Pressing Play showed the client's own "Caravan options" popup (0 s left); "Go to caravan's last location" sent Play mode 3 and Justins entered the world at the caravan's spot by the camp riftway instead of his own saved place. |
| Feel of the numbers | 👤 | XP per kill, damage, health, regen, prices. All placeholders (docs/CONTENT_EDITOR.md); someone who played the game should say what feels wrong. |

## Race and class pass

- **Races (2026-10-14, all 19):** a Warrior of each race was shown on the character select screen and entered the world (`racepass.sh` in the work folder: set the race, start server and client, screenshot the preview, press Play, scan both logs). Every race drew correctly and joined; no server tracebacks. Orc (race 11) adds client warnings that `UEM_halfOrc_F_char` / `UEM_halfOrc_M_char` skeletons are missing: the client asks for the half-orc package, which the shipped client lacks. The Orc still draws.
- **Classes (2026-10-14, all 15):** each class entered the world and used its first four hotbar abilities on the Canyon Widow (`classpass.sh`). No server tracebacks and no new client errors for any class. Many class ability names show run together (for example "Bladedancersfocus I", "Lightningstrike I", "Unionofthought I"): the server builds them from the client's internal tags, which have no word breaks. The crowdsourced ability list has the spaced names for many of them. Since 2026-10-15 `tools/ability_names.py` re-spaces 386 tag names in `server/content/ability_names.json`: 271 from the archive's spellings and 115 split into known words ("Formofthespiritdragon I" -> "Form of the Spirit Dragon I"; source "word split", a guess that can be wrong for lore names, e.g. "Bite of Nag Suul").

## Blocked

| Feature | Why |
|---|---|
| Psionic points | ⛔ Messages are decoded, but the shipped UI has no window to show them. |
| Civic stats display | ⛔ Civic diplomacy works server-side; no window shows the stats. `/citystatus` lists them in chat instead. |
| Doors | ⛔ No door exists in the shipped maps or the cottage. |
| Real game data | ⛔ Waiting for the first batch in `crowdsourced/`. |
| Client-side furniture placement | ⛔ Dragging furniture onto the cottage floor gives the client's delete prompt: its "inside a house" check finds no house-interior zone (docs/HOUSING.md). Right-click placement works. |
| Building NPC Spawn / Goto / Remove | ⛔ The shipped VGUIBuildingNPCs.xml has those buttons' names commented out, so they never fire. The lists show. |
| Journal "Forget" (X) button | 👤 Clicks on it showed no tooltip and no confirmation in scripted tests. The server side works (`!cev 0x138 <entry id>`). |

## Regression run (by hand)

A full pass to check nothing old has broken. Start with `run_test.sh --dev-commands` (or `python login_stub.py --dev-commands`), and a second client for the ✦ items.

**Login and world**
- [ ] Log in, see "Stub World", create a character, delete one, enter the world
- [ ] A female character shows as female on the select screen and in the world
- [ ] HUD, minimap, chat, message of the day; character window (C) shows attributes, health, armor class
- [ ] Loot something, click the item link in the "You loot" line: the item tooltip pops up
- [ ] `/report <name>` prints "Player report submitted", a second one within a minute "You must wait longer"; the report is in server/player_reports.json
- [ ] `/reloadui`: the UI comes back with the hotbars filled
- [ ] `/walk` slows the character, `/run` restores it; `/hidehood` / `/hidehelm` / `/hidecloak` toggle (✦ the other client sees it) and stay after relogging
- [ ] Walk, run, jump, fall damage; cross a chunk edge; `/unstuck`; `/camp` back to character select
- [ ] ✦ Group with the second player, `/targetgroupmember 2`, `/rope`: they get "Help on the way!"; Accept hauls them to you ("You grab the rope and are hauled to safety.")
- [ ] ✦ Two players see each other move, emote and chat (say, shout, tell, ooc, group)
- [ ] ✦ `!call <other>`: they get "Call Confirmation"; Accept moves them to you ("You have been summoned!")

**Combat**
- [ ] Target a mob, auto-attack, see hits, misses, dodges, crits in the Combat tab
- [ ] Hotbar abilities, cooldown sweep, cast bars, damage over time icon on the target
- [ ] Warrior chain: Brutal Strike → Savage Cut → finisher; counter Venom Spit with Riposte
- [ ] Get stunned, rooted and feared (`!cc stun`, `!cc root`, `!cc fear`)
- [ ] `/forcecombatstance on` keeps the combat pose; as a Psionicist, pick a mindset, `/applyformondeath on`, `!die`, release: the mindset comes back
- [ ] Kill a mob, XP bar rises, level up heals you and raises attributes
- [ ] Die, release, recover the tombstone, bind at the altar
- [ ] Ability book General page: Sprint (faster for 45 s), Recall (bind point), Recall to House
- [ ] `!wound 2 2`: "Right Arm - Mid"; `/sit` heals it to Minor, then Unwounded
- [ ] A lootable corpse sparkles; spell effects show (Blade of Winter tints the target)
- [ ] Wound an Ashen Wolf, run past its leash: it walks home, heals to 100%, the target frame turns white and its target line reads "--"; no "notices you!" flood
- [ ] Let two Ashen Wolves notice you, then `!tp -28900 -9400 ~`: each gives up once at the leash and walks home; they do not notice you again on the way (no "gives up" loop)
- [ ] Die to a Canyon Widow: it walks home and heals instead of standing over the corpse
- [ ] Summon Ashfang (Wolf Whistle): it uses Savage Bite on its own; right-click the bite on the pet bar: the green "+" goes away ("will no longer"), right-click again brings it back
- [ ] ✦ Duel to 1 HP; a challenge times out after 30 s
- [ ] Hit an Ashen Wolf below 20% health: "Ashen Wolf turns to flee!", it runs for a few seconds and comes back

**Items**
- [ ] Loot a corpse; buy and sell from Orin; buyback tab; repair
- [ ] Equip gear: model changes, tooltip shows stats, attributes on the sheet change
- [ ] Ctrl+click splits a stack; Small Pouch on the main bar holds 8 items
- [ ] Service items (`!give` each): Experience Debt Clearance (refused with a tombstone out), Gender Change, Race Change, Character Rename (a taken name is refused), Unbinding Tool on a Bind On Equip item
- [ ] Jewelry tooltip says "Required Level: 1 Adventuring"; Copper Ore says "Crafting Resource"
- [ ] Bank items and coins; mail a letter with an item; list and buy on the broker
- [ ] ✦ Trade an item; group loot with Need/Greed/Pass; master looter `/giveplayerlootitem`
- [ ] Fill the bags, `!give` an item: "waiting for you in escrow"; Hollis Grent's escrow option hands it over
- [ ] Right-click 4+ Copper Ore: the Conversion window turns them into a Copper Ingot
- [ ] Salvage Kit: right-click, click a Rusted Dagger, Resource gives a Copper Ingot
- [ ] Brass Spyglass zooms the camera in and out
- [ ] Right-click the Thestran Riding Horse inside your house: "You need more open space around you to do that."; outside it summons

**Quests and NPCs**
- [ ] Wanderer Trouble: offer, tracker, kill counts, pick a reward
- [ ] Click the chosen reward again: Complete hides; choose again and complete
- [ ] NPCs talk now and then (Thestran Guard, Garret Holm); Orin's greeting voice plays
- [ ] With a tombstone out, Veyla's "I'd like to summon my earthly remains." brings it to you
- [ ] Character window, Diplomacy - Factions tab: the factions under Other Factions; `!faction 1005 250` unlocks a prestige faction
- [ ] Wildgrowth Forest (`!tp -223200 29400 3500`): Elara's two quests, the Forester's Cloak
- [ ] Conversation trees, faction colors on name plates, `/showfactions`
- [ ] Thestran Guard, "Any dangers I should know about?", then the quest reply: the Wanderer Trouble page (offer for a new character, progress if taken)
- [ ] Win and lose a parley; a parley win unlocks the Thestran Guard's new line
- [ ] Orin's parley option reads "Let's talk business." over "Entertain [icons] : 10"
- [ ] `/decksave 1`, `/deckclear`, `/deckload 1` re-slot the strategy bar

**Crafting and gathering**
- [ ] Mine a copper vein, smelt an ingot at the Camp Forge, quality grades; Table Setup's Auto Setup Table box ticks, Back returns to the recipe list
- [ ] A work order from Garret Holm; an assembly at the Assembly Bench
- [ ] Buy Copper Wire from Brenna: "New action acquired: ..." lines; a multi-stage recipe shows the orange stage banner
- [ ] Using a station while sitting: "You cannot do that while resting."
- [ ] Fish on the beach (`!tp -43000 -49500 200 49152`), a combo, the Achievements tab

**Social**
- [ ] ✦ Group invite and group window bars; Find tab Request to Join
- [ ] ✦ Guild create, invite, ranks, guild chat; brotherhood invite and XP bonus
- [ ] Friends, ignore, `/who`, `/afk`, `/random`, `/inspect`, `/bug`

**Travel and the world**
- [ ] Ride the horse, dire wolf and camel; `/dismount`
- [ ] Riftway map travel; travel journal Locations tab and `/traveldirections`; `!cev 0x138 <entry id>` forgets a location (still gone after relogging)
- [ ] Buy a plot, build a cottage, place furniture, use a storage chest
- [ ] Plot window: Admin > Make Guild Headquarters (as the guild leader: confirm popup, "Your guild has a new guild headquarters."), then Relinquish; Buildings > Building Inventory lists the fixtures ("Chests: (1 of 3)"), Move Fixture to me, Manage NPCs lists the banker
- [ ] Summon Ashfang and use Savage Bite; a Necromancer abomination; Bone Charm minions
- [ ] Swim, dive, the breath bar, drowning
