# Vanguard: Saga of Heroes — Server Emulator

An open-source server emulator for **Vanguard: Saga of Heroes** (SOE, shut down in July 2014), built by reverse-engineering the original game client.

> **No game files are included.** You need your own copy of the Vanguard client (version 1.324.1.139565). This repository contains only original emulator code and protocol notes.

## Status

The unmodified client, talking only to this emulator:

- [x] Logs into the login server
- [x] Sees the server list ("Stub World")
- [x] Lists, creates, customizes and deletes characters, with 3D previews
- [x] Connects to the world server, then to a zone server after **Play**
- [x] Completes the Unreal Engine 2 handshake (HELLO → CHALLENGE → LOGIN → WELCOME → JOIN) and loads a level
- [x] Enters the 3D world: loads the character's chunk (with neighbours) and takes control of a replicated PlayerController at a PlayerStart
- [x] Shows the in-game HUD (vitals, chat, minimap) and a message of the day
- [x] The character is visible and walks around; the server tracks its position
- [x] Character window: name, level, race and class
- [x] Attributes (Strength...), hit points, endurance and energy; full HUD bars
- [x] Skills list (weapon, combat, perception... groups)
- [x] Full character sheet: defense, attack, ranged, XP bars ([docs/MSGSCORE.md](docs/MSGSCORE.md))
- [x] Inventory: items in the bag and coins ([docs/INVENTORY.md](docs/INVENTORY.md))
- [x] Equipment on the paper doll; ability book with usable abilities ([docs/ABILITIES.md](docs/ABILITIES.md))
- [x] Standing on the ground; hotbar, compass, menu bar and bag bar shown at login
- [x] Other characters and NPCs drawn, with name plates and minimap entries
- [x] Targeting, target window, abilities that hit, NPCs that strike back, death animation, respawn, health regeneration
- [x] Per-class starting abilities with their real animations and effects; auto-attack
- [x] NPCs chase and attack; player death, death window and release; experience and level ups (saved)
- [x] Looting corpses into the bag (saved); appearance sliders on the player's character
- [x] Standing on the real terrain anywhere in the chunk; spawn on flat ground; teleporting
- [x] Walking, running and turning with WASD (the client controls its own character; see [MOVEMENT](docs/MOVEMENT.md))
- [x] Gear on the character model (armor, bow); NPCs dressed too
- [x] Several players in the same world: they see each other move, chat, and share the same NPCs
- [x] World content (mobs, loot, spawns) loaded from JSON files: see [docs/CONTENT_EDITOR.md](docs/CONTENT_EDITOR.md)
- [x] Groups (invite, accept, group window with live bars, group chat), merchants (buy/sell), equip/unequip, real item tooltips, NPC wandering
- [x] Chat: say, shout, tell, OOC, group, emotes and social animations
- [x] Walking (or teleporting) across chunk edges into the neighbouring zone
- [x] Quests from NPCs (offer page, tracker, kill counts, turn-in rewards) and player-to-player trading
- [x] Sitting and camping; endurance costs; NPCs in more than one zone
- [x] Creatures (wolves, bears, spiders... any of the client's 330 creature races)
- [x] Harvesting resource nodes (mining a copper vein) and crafting at a station (smelting a copper ingot)
- [x] Diplomacy: a parley with an NPC (statement cards, the conversation bar, winning, diplomacy XP)
- [x] Multi-step quests: kill, collect and talk steps, prerequisite quests, item rewards
- [x] Harvesting tools (equip slot 0x35) and skills with skill-ups
- [x] /camp returns to character select
- [x] Diplomacy card costs, expression pools, NPC opponent, win and loss (data-driven)
- [x] Ability trainer: buy the next class abilities; recipe trainers sell crafting recipes
- [x] Multi-stage crafting with quality grades and complications
- [x] Bank: items and coins, saved per character
- [x] Item durability (worn on death) and repairs at a merchant
- [x] /who, friends and ignore lists, /afk /anon /lfg, /random, /inspect
- [x] Ability effects: buffs with timers and stat bonuses, damage over time with target debuff icons, heals, cooldowns
- [x] Guilds: create, invite, join, ranks, kick/quit/delete, guild chat, message of the day, rank names, /guildstatus, notes and points, recruiting browser
- [x] Brotherhoods: invite popup, join, leave, kick, promote, MOTD, notes, rename
- [x] Combat text written by the client (Combat tab) for hits, heals and damage over time; cast bars; NPC special attacks
- [x] Per-character diplomacy decks, card slotting and reward cards; crafting catalysts
- [x] Factions: standings saved per character, kill/quest/parley changes, /showfactions, NPC name plates colored by standing
- [x] Crafting work orders: task master window, accept, craft the work-order recipe, turn in for coin, crafting XP and faction
- [x] Mail: mailboxes, inbox, reading, sending letters with coin or an item, cash on delivery, return, delete
- [x] Broker: list items for sale, search, buy (delivered by mail, seller paid by mail), cancel
- [x] Death penalty: experience debt, a tombstone at the death spot, recovering it wins back half the debt; altars bind you and summon your tombstone; resurrection offers (Accept/Decline)
- [x] NPC conversation trees (data-driven replies with faction and item rewards)
- [x] Mounts: summon a horse from an item, ride, /dismount
- [x] Titles (prefix/suffix, /titleset, quest rewards, shown over the head), the game clock (/time), /played
- [x] Duels: /duel challenge popup, countdown, auto-attack fight to 1 HP; caravans (invite, member list, remove, log in at the caravan after 3 hours offline)
- [x] Pets: summon a wolf from an item; it follows and attacks on /pet attack
- [x] Fishing: cast into water, the pull minigame, catch fish, bait use and Fishing skill-ups
- [x] Assembly crafting: assembly trainer, recipe categories, combine components into an item at an assembly bench
- [x] Riftways: /rift and the client's Riftway map travel between riftway stones (one destination placed)
- [x] Housing: buy a plot from its For Sale sign, build a cottage on it (instantly, or a home from construction materials), place and pick up furniture, storage chests
- [x] Hotbar cooldown sweep
- [x] Raids: /raidcreate, up to 24 players in four raid groups, ready checks; mentoring (a higher member drops to your level)
- [x] The Find window: search for groups or players looking for a group
- [x] Crafting utilities (consumables used by recipe steps) and the active toolbelt
- [x] Refining and finishing stations (the station picks the recipe page); fall damage; faster riding
- [x] Group loot: Free For All, Round Robin, Master Looter, Random For Magical and Need Before Greed with the Need/Greed/Pass roll popup; swimming breath and drowning
- [x] Combat chains: an opener unlocks the next step and the finisher for a few seconds (the client's reaction button); NPC spell casts that players can counter; coin on corpses
- [x] Rescues and NPC hate lists; heals and buffs on other players; bag management (move, stack, destroy); quest abandon and share; crafting and diplomacy levels; consent and corpse drag
- [x] Pet ability bar; quest reward choice (pick one item at turn-in); request to join a group from the Find window; chest View/Deposit/Withdrawal permissions
- [x] Travel journal (Locations tab: the chunk's merchants, trainers, services, stations, riftways and your house); in-game bug reports (/bug); Bard songs (compose, save, play, stop, energy cost); minions (the Minions window, timed skeleton servants from a Bone Charm); Psionicist mindsets (combat forms bar); fishing achievements and best-catch leaderboards (Achievements tab); quest feedback window (--quest-feedback)
- [x] Splitting stacks (Ctrl+click), bags on the main bar (Small Pouch), master looter /giveplayerlootitem, duel challenge timeouts, brotherhood XP bonus, parley item rewards, diplomacy card refresh timers, civic diplomacy, class summons (Necromancer abomination, Shaman attendants, Psionicist simulacrum), Fear
- [x] Maintained stances (Effects Maintained window, right-click to cancel); merchant buyback tab; encounter (group-of-mobs) display; /unstuck; resist chances; NPCs calling nearby friends for help
- [x] GM NPC list (`!npclist`) for content building; travel-journal tracking with `/traveldirections` (compass marker); locations discovered by walking near them; fishing combos (learned patterns shown on the Achievements page); minion special attacks; dialogue unlocked by winning a parley; NPC stuns, roots and fear on players (songs are interrupted); more mounts (dire wolf, camel, griffon) at the camp merchant; a second outpost in the Wildgrowth Forest with its own merchant, quest chain, creatures and faction; item stat bonuses and ratings in tooltips; equipped gear raises your attributes, armor class (less damage taken), maximum health (Constitution and level; a level up heals you), regeneration and weapon damage, all shown on the character sheet; misses, dodges, parries, blocks and critical hits in melee; kill experience scaled by level difference (gray mobs give none) and a rising experience curve per level; casters spend energy and fighters endurance, with pools sized by attributes; ability damage and heals grow with level and attributes; each race and class has its own attribute strengths, growing with level; combat reaction windows close when their enemy dies; clearing experience debt with an item (the client's own Clear Experience Debt dialog); gender, race and character rename items; item flags (No Trade, Soulbound, Quest, No Sell...) with Bind On Equip and an unbinding tool; saved diplomacy strategy decks (/decksave, /deckload, /deckclear); /forcecombatstance; forms end on death and /applyformondeath brings them back; clicking a player, F1 and /targetself set the defensive target; /transferplot gives your house to another player; female characters drawn as female (in the world and on the select screen); /citystatus lists the civic diplomacy stats; /lockouttimerlist; /report saves a player report with the recent chat lines; /walk and /run; /hidehood, /hidehelm, /hidecloak and wear/wield preferences (saved, shown to other players); /cleartargets

### Not done yet
- [ ] Doors: none exist in the shipped maps or our cottage (checked; see HOUSING.md). The protocol to open one is worked out for when a building with a door is used
- [ ] Flying: griffon/wyrm/wyvern mounts render, but taking off (second jump in the air) is untested by hand; mount barding
- [ ] Psionicist psionic points (messages known; the shipped UI has no window for them)
- [ ] Combat-form ability restrictions (which abilities each form allows is server data; every ability works in every form)
- [ ] The civic stats display (no window in the shipped UI)
- [ ] Real game data: every item, mob, quest, ability number and reward here is a placeholder until the content editor (docs/CONTENT_EDITOR.md)

Game data gathered from fan sites goes in [crowdsourced/](crowdsourced/README.md) ([agent instructions](crowdsourced/AGENT_INSTRUCTIONS.md)) before it is imported into `server/content/`.

What has been tested, and what still needs a person: [docs/TESTING.md](docs/TESTING.md). The client's own messages the server can show by number: [docs/NOTICES.md](docs/NOTICES.md) (generated by `tools/notice_table.py`).

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for everything decoded so far. Topic docs: [INVENTORY](docs/INVENTORY.md), [ITEM_FIELDS](docs/ITEM_FIELDS.md), [GEAR](docs/GEAR.md), [ABILITIES](docs/ABILITIES.md), [ABILITY_VISUALS](docs/ABILITY_VISUALS.md), [LOOT](docs/LOOT.md), [MERCHANTS](docs/MERCHANTS.md), [GROUPS](docs/GROUPS.md), [CHAT](docs/CHAT.md), [TRADE](docs/TRADE.md), [QUESTS](docs/QUESTS.md), [CHUNK_TRAVEL](docs/CHUNK_TRAVEL.md), [CREATURES](docs/CREATURES.md), [HARVESTING](docs/HARVESTING.md), [CRAFTING](docs/CRAFTING.md), [DIPLOMACY](docs/DIPLOMACY.md), [TRAINERS](docs/TRAINERS.md), [BANK](docs/BANK.md), [SOCIAL](docs/SOCIAL.md), [EFFECTS](docs/EFFECTS.md), [GUILDS](docs/GUILDS.md), [BROTHERHOODS](docs/BROTHERHOODS.md), [FACTIONS](docs/FACTIONS.md), [WORK_ORDERS](docs/WORK_ORDERS.md), [MAIL](docs/MAIL.md), [MARKET](docs/MARKET.md), [DEATH](docs/DEATH.md), [MOUNTS](docs/MOUNTS.md), [RIFTWAYS](docs/RIFTWAYS.md), [HOUSING](docs/HOUSING.md), [TITLES](docs/TITLES.md), [DUELS and CARAVANS](docs/DUELS.md), [PETS](docs/PETS.md), [FISHING](docs/FISHING.md), [ASSEMBLY](docs/ASSEMBLY.md), [MOVEMENT](docs/MOVEMENT.md), [TRAVEL](docs/TRAVEL.md), [SONGS](docs/SONGS.md), [FORMS](docs/FORMS.md), [CONTENT_EDITOR](docs/CONTENT_EDITOR.md).

## Requirements

- Python 3.10+ (standard library only)
- A Vanguard: Saga of Heroes client install

## Running

1. Put this repository's files in the root of the client install (next to `bin/`).
2. Set `bin/loginserver.txt` to `127.0.0.1`.
3. Start the emulator:
   ```
   cd server
   python login_stub.py
   ```
   It listens on UDP 10101 (login), 10100 (world) and 10102 (zone). It reads package GUIDs from the client's `UnrealScript/` and `Assets/Maps/` folders (nothing is copied or shipped).
4. In another terminal, start the client directly (this skips the old VGOEmulator launcher):
   ```
   cd bin
   .\VGClient.exe --sessionid=12345678
   ```

To check that nothing is broken, run `python tools/smoke_test.py`: it starts both, enters the world, types a set of commands and reports PASS or FAIL.

For a long-running server, add `--quiet-packets`: the log then keeps the decoded events but not a hex dump of every packet.

Characters are saved to `server/characters.json`: position, chunk, level, XP, coins, bag, equipment and hotbar. The emulator prints every packet it receives, decoded where the format is known.

Several clients can connect at once. Start a second copy with a different `--sessionid`; players in the same chunk see each other and share the NPCs.

### Things to try in game
- Click an NPC to target it. Use your hotbar abilities, or press **`** (auto-attack). Press **U** on a corpse to loot it.
- Press **U** on Orin the Trader, or say "Hail", then pick "Show me your wares." Right-click an item to buy it; right-click a bag item while the window is open to sell it.
- Right-click bag items to equip them, and right-click paper-doll items to take them off.
- Group with another player using `/invite Name` and `/groupacceptinvite`.
- Chat with `/shout`, `/tell Name …`, `/ooc`, `/g`, `/emote …`, `/wave`. Use `/sit` to rest and `/camp` to camp.
- Walk or teleport past a chunk edge to enter the neighbouring zone.
- At the camp in the Sundering Wastelands: Veyla trains abilities, Brenna sells recipes and assembly recipes, Garret Holm hands out work orders, Hollis Grent is the banker, Tamsin Vale the broker; the Mailbox, Camp Forge, Assembly Bench, Altar of Binding and a Riftseeker brazier stand nearby.
- Buy a Thestran Riding Horse, a Wolf Whistle (pet), a Fishing Pole with bait, or furniture from Orin, then right-click them in your bags.
- Inspect the For Sale sign south of camp (`!plot` with dev commands) to buy a plot and build a cottage.
- Fish on the beach far to the south (`!tp -43000 -49500 200 49152`).
- Group up and set the loot mode from the group window (or `!lootmode 4 6` with dev commands); kill something and roll Need/Greed/Pass on its items.
- As a Warrior, hit **1** (Brutal Strike), then **3** (Savage Cut) while the chain button glows, then the finisher; when the Canyon Widow casts Venom Spit, answer with the counter (Riposte).
- Swim out from the fishing beach and dive: the Breath bar drains, then you drown.
- With a plot, build the Thestran Home from materials (2 Rough Stone, 2 Tattered Cloth) in the Construction window, and give friends permissions on the Permissions tab.
- Summon Ashfang with the Wolf Whistle, target an enemy and click Savage Bite on the pet bar: the wolf runs in and bites.
- Finish "Wanderer Trouble" for Orin and pick one of three rewards on the turn-in page.
- In the Social window's Find tab, select a player looking for members and press Request to Join.
- With dev commands, `!give Gender Change` (or Race Change, Character Rename, Experience Debt Clearance, Unbinding Tool) and right-click it: the client opens its own service window.
- Save diplomacy strategy bars with `/decksave 1` and bring them back with `/deckload 1`.
- Admin helpers (with `--dev-commands`): `!goto Name`, `!summon Name`, `!chunk -19 12`, `!hide`, `!setupall 20` (level 20, every class ability, skills at the cap). Or make a character a GM with `"access_level": 255` in characters.json and use the client's own `/chunk`, `/gotoplayer`, `/summonplayer` and `/hideme`.
- Open your quest journal, click a quest and press Share to offer it to your group; its Locations tab lists the camp's services.
- Type `/bug` to file a bug report (saved in `server/bug_reports.json`).
- Visit the Wildgrowth Forest outpost next door (`!tp -223200 29400 3500` with dev commands, or walk west across the chunk edge): Warden Elara Thornwood offers "Wolves at the Edge" and then "Gifts for the Wardens" (pelts, a thornback bear, a word with Bram the merchant) for a Forester's Cloak; timber wolves can root you and the bear can stun.
- Ctrl+click a stack in your bags to split it.
- Buy a Small Pouch from Orin and right-click it: it goes on the bag bar; click it there to open it and drag items in.
- On the Achievements tab, pick a fish and switch the dropdown to "All Time Biggest Catches".
- As master looter, target a corpse and type `/giveplayerlootitem <member> <item>`.
- Win a parley against Orin: diplomacy XP, coin, faction, 2 Travel Rations and +5 camp prosperity. Compelling Case needs 2 rounds to refresh.
- Group with a brotherhood member and kill something for bonus experience.
- With dev commands, `!learn Awakenabomination` then `!use Awakenabomination` summons a pet; `!learn Fear` then `!use Fear` on an enemy makes it flee.
- As a Bard (or anyone, with `!songs`), compose a song in the Song window from a melody and verses, save it and play it.

### Developer commands
Start the server with `python login_stub.py --dev-commands`, then type these in the game's chat box:

| Command | Effect |
| --- | --- |
| `!tp x y z [yaw]` | Teleport (`~` keeps the current coordinate; yaw 0 = +x, 49152 = -y) |
| `!target <name>` | Target an NPC by name |
| `!hurt N` | Lose N health |
| `!anim id [me]` | Play an animation on the target or yourself |
| `!prop <property> <value> [me]` | Set a replicated pawn property |
| `!move dx dy` | Move the targeted NPC |
| `!give <item> [qty]` | Put an item from `content/items.json` in your bags |
| `!learn <ability>` / `!use <ability>` | Learn / use a class ability |
| `!faction <id> <amount>` | Change a faction standing |
| `!title <id>` | Grant a title |
| `!mount [id] [fly]` | Ride a mount (`!mount 0` dismounts) |
| `!questkill` | Count a kill of the target's kind toward quests |
| `!mailme` | Receive a test letter with coin and an item |
| `!tombstone` / `!rezme` | Leave your tombstone here / get a resurrection offer |
| `!plot [id]`, `!house [prefab] [type]`, `!chest <n> [put/take/close/manage]`, `!pickup <n>`, `!upkeep <copper>` | Housing tests |
| `!pet <item>` | Summon an item's pet without the item |
| `!questreset <quest key>` | Forget a quest so it can be taken again |
| `!lfm` | Show yourself as looking for members on the Find window |
| `!songs` | Learn the Bard's song parts and open the Song window |
| `!forms [class]` | Load a class's combat forms / mindsets (then `!ui Forms` shows the bar) |
| `!fishcatch <fish>` | Count a fish catch for the Achievements tab |
| `!npclist [radius]` | List nearby NPCs with their spawn index and mob key (for content work) |
| `!kill` | Kill the target with one hit |
| `!react` | Activate the newest open combat reaction (chain step) |
| `!spherexp <1 crafting / 2 diplomacy> <amount>` | Gain crafting or diplomacy XP (level-ups) |
| `!cev <event id> [i32 ...]` | Handle a client zone event as if the client sent it (e.g. `!cev 0x479 101 2`) |
| `!lootmode <0-4> [rarity 0-6]`, `!roll need/greed/pass` | Group loot mode (as the leader's popup) and roll answers |
| `!deftarget <player>` | Set another player as defensive target (then `/duel`) |
| `!fishbite` | Pretend the fishing bobber landed in water |
| `!ui <window>` | Toggle a client window (e.g. `!ui Social`) |
| `!guildcreate`, `!bankput`/`!bankget`, `!wear [n]`, `!ctext` | Guild, bank, durability and combat-text tests |
| `!item`, `!stat`, `!upd`, `!event`, `!chat`, `!sys`, `!exec` | Send raw messages (see `dev_command` in `login_stub.py`) |

World content (mobs, loot, items, vendors and spawns) lives in `server/content/`. Run `python content.py` to check it for mistakes.

## How it was built

Each message format was found by static analysis of `VGClient.exe` (Ghidra, via REA), then verified by running the real client against the emulator. Function addresses in the notes refer to Ghidra's names for that exact client build.

## License

[GNU Affero General Public License v3.0](LICENSE). If you run a modified version of this emulator as a public server, you must publish your changes.

*Vanguard: Saga of Heroes is a trademark of its respective owners. This project is not affiliated with or endorsed by them.*
