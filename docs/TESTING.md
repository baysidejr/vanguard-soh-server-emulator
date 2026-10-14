# Testing checklist

How each feature has been tested, and what still needs a person at the keyboard.

- **Unit tests:** `cd server && python -m unittest discover -p "test_*.py"` (110 tests, all must pass before a commit), plus `python content.py` (checks every content JSON file links up: "content OK").
- **In game:** every feature in the README checklist was tried in the real client while it was built, by scripted key presses and clicks, often with two clients at once. That run was once per feature: there is no automated in-game regression run yet, so an older feature can break without anyone noticing.

Legend: ✅ seen working in the client · 🧪 unit tests only · 👤 needs a person (scripted input can't do it, or the result can't be checked by a screenshot) · ⛔ blocked (no UI in the shipped client, or no data)

## Needs a person

| Feature | Status | How to test |
|---|---|---|
| Griffon flight | 👤 | Buy a Griffon Whistle (5000c) from Orin, summon it, jump, then press jump again while falling. Expect to take off. Scripted double presses never triggered it. |
| Combat-form recovery bar | 👤 | As a Psionicist, switch mindsets on the forms bar. Expect a short recovery sweep before you can switch again. The server sends it (0x140) but it was never seen on screen. |
| Caster energy | 🧪 | Make a Sorcerer or Cleric and use an ability with a cooldown. Expect the blue energy bar to drop by 15, not the endurance bar. Only Ranger (endurance) was tried in game. |
| Raid of 24 | 👤 | Only tried with 2 clients. Needs several people to check four raid groups, ready checks and loot. |
| Caravan login | 👤 | Join a caravan, stay offline 3+ hours, log in. Expect to appear at the caravan. Never waited out the real 3 hours. |
| Feel of the numbers | 👤 | XP per kill, damage, health, regen, prices. All placeholders (docs/CONTENT_EDITOR.md); someone who played the game should say what feels wrong. |

## Blocked

| Feature | Why |
|---|---|
| Psionic points | ⛔ Messages are decoded, but the shipped UI has no window to show them. |
| Civic stats display | ⛔ Civic diplomacy works server-side; no window shows the stats. |
| Doors | ⛔ No door exists in the shipped maps or the cottage. |
| Real game data | ⛔ Waiting for the first batch in `crowdsourced/`. |

## Regression run (by hand)

A full pass to check nothing old has broken. Start with `run_test.sh --dev-commands` (or `python login_stub.py --dev-commands`), and a second client for the ✦ items.

**Login and world**
- [ ] Log in, see "Stub World", create a character, delete one, enter the world
- [ ] HUD, minimap, chat, message of the day; character window (C) shows attributes, health, armor class
- [ ] Walk, run, jump, fall damage; cross a chunk edge; `/unstuck`; `/camp` back to character select
- [ ] ✦ Two players see each other move, emote and chat (say, shout, tell, ooc, group)

**Combat**
- [ ] Target a mob, auto-attack, see hits, misses, dodges, crits in the Combat tab
- [ ] Hotbar abilities, cooldown sweep, cast bars, damage over time icon on the target
- [ ] Warrior chain: Brutal Strike → Savage Cut → finisher; counter Venom Spit with Riposte
- [ ] Get stunned, rooted and feared (`!cc stun`, `!cc root`, `!cc fear`)
- [ ] Kill a mob, XP bar rises, level up heals you and raises attributes
- [ ] Die, release, recover the tombstone, bind at the altar
- [ ] ✦ Duel to 1 HP; a challenge times out after 30 s

**Items**
- [ ] Loot a corpse; buy and sell from Orin; buyback tab; repair
- [ ] Equip gear: model changes, tooltip shows stats, attributes on the sheet change
- [ ] Ctrl+click splits a stack; Small Pouch on the main bar holds 8 items
- [ ] Bank items and coins; mail a letter with an item; list and buy on the broker
- [ ] ✦ Trade an item; group loot with Need/Greed/Pass; master looter `/giveplayerlootitem`

**Quests and NPCs**
- [ ] Wanderer Trouble: offer, tracker, kill counts, pick a reward
- [ ] Wildgrowth Forest (`!tp -223200 29400 3500`): Elara's two quests, the Forester's Cloak
- [ ] Conversation trees, faction colors on name plates, `/showfactions`
- [ ] Win and lose a parley; a parley win unlocks the Thestran Guard's new line

**Crafting and gathering**
- [ ] Mine a copper vein, smelt an ingot at the Camp Forge, quality grades
- [ ] A work order from Garret Holm; an assembly at the Assembly Bench
- [ ] Fish on the beach (`!tp -43000 -49500 200 49152`), a combo, the Achievements tab

**Social**
- [ ] ✦ Group invite and group window bars; Find tab Request to Join
- [ ] ✦ Guild create, invite, ranks, guild chat; brotherhood invite and XP bonus
- [ ] Friends, ignore, `/who`, `/afk`, `/random`, `/inspect`, `/bug`

**Travel and the world**
- [ ] Ride the horse, dire wolf and camel; `/dismount`
- [ ] Riftway map travel; travel journal Locations tab and `/traveldirections`
- [ ] Buy a plot, build a cottage, place furniture, use a storage chest
- [ ] Summon Ashfang and use Savage Bite; a Necromancer abomination; Bone Charm minions
- [ ] Swim, dive, the breath bar, drowning
