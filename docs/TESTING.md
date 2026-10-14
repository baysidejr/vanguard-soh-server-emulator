# Testing checklist

How each feature has been tested, and what still needs a person at the keyboard.

- **Unit tests:** `cd server && python -m unittest discover -p "test_*.py"` (about 150 tests, all must pass before a commit), plus `python content.py` (checks every content JSON file links up: "content OK").
- **In game:** every feature in the README checklist was tried in the real client while it was built, by scripted key presses and clicks, often with two clients at once.
- **Smoke test:** `python tools/smoke_test.py` (Windows) starts the server and client, enters the world with the character selected on the select screen, types about 40 chat commands and fails on any server traceback, dropped message or client "unhandled message" line. Run it after changes; it takes about two minutes.

Legend: ✅ seen working in the client · 🧪 unit tests only · 👤 needs a person (scripted input can't do it, or the result can't be checked by a screenshot) · ⛔ blocked (no UI in the shipped client, or no data)

## Needs a person

| Feature | Status | How to test |
|---|---|---|
| Griffon flight | 👤 | Buy a Griffon Whistle (5000c) from Orin, summon it, jump, then press jump again while falling. Expect to take off. Scripted double presses never triggered it. |
| Combat-form recovery bar | ✅ | Seen 2026-10-13 on a Psionicist: choosing a mindset darkens all three form icons for a moment and rings the chosen one in blue. |
| Caster energy | ✅ | Seen 2026-10-13: a Sorcerer casting See Invisibility I drains the blue energy bar; endurance stays full. |
| Raid of 24 | 👤 | Only tried with 2 clients. Needs several people to check four raid groups, ready checks and loot. |
| Caravan login | 👤 | Join a caravan, stay offline 3+ hours, log in. Expect to appear at the caravan. Never waited out the real 3 hours. |
| Feel of the numbers | 👤 | XP per kill, damage, health, regen, prices. All placeholders (docs/CONTENT_EDITOR.md); someone who played the game should say what feels wrong. |

## Race and class pass

- **Races (2026-10-14, all 19):** a Warrior of each race was shown on the character select screen and entered the world (`racepass.sh` in the work folder: set the race, start server and client, screenshot the preview, press Play, scan both logs). Every race drew correctly and joined; no server tracebacks. Orc (race 11) adds client warnings that `UEM_halfOrc_F_char` / `UEM_halfOrc_M_char` skeletons are missing: the client asks for the half-orc package, which the shipped client lacks. The Orc still draws.
- **Classes:** see below once run.

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
- [ ] ✦ Duel to 1 HP; a challenge times out after 30 s

**Items**
- [ ] Loot a corpse; buy and sell from Orin; buyback tab; repair
- [ ] Equip gear: model changes, tooltip shows stats, attributes on the sheet change
- [ ] Ctrl+click splits a stack; Small Pouch on the main bar holds 8 items
- [ ] Service items (`!give` each): Experience Debt Clearance (refused with a tombstone out), Gender Change, Race Change, Character Rename (a taken name is refused), Unbinding Tool on a Bind On Equip item
- [ ] Jewelry tooltip says "Required Level: 1 Adventuring"; Copper Ore says "Crafting Resource"
- [ ] Bank items and coins; mail a letter with an item; list and buy on the broker
- [ ] ✦ Trade an item; group loot with Need/Greed/Pass; master looter `/giveplayerlootitem`

**Quests and NPCs**
- [ ] Wanderer Trouble: offer, tracker, kill counts, pick a reward
- [ ] Wildgrowth Forest (`!tp -223200 29400 3500`): Elara's two quests, the Forester's Cloak
- [ ] Conversation trees, faction colors on name plates, `/showfactions`
- [ ] Win and lose a parley; a parley win unlocks the Thestran Guard's new line
- [ ] `/decksave 1`, `/deckclear`, `/deckload 1` re-slot the strategy bar

**Crafting and gathering**
- [ ] Mine a copper vein, smelt an ingot at the Camp Forge, quality grades; Table Setup's Auto Setup Table box ticks, Back returns to the recipe list
- [ ] A work order from Garret Holm; an assembly at the Assembly Bench
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
