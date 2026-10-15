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
- [x] Quests from NPCs (offer page, tracker, kill counts, turn-in rewards, quest icons over the NPCs) and player-to-player trading
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
- [x] Mounts: summon a horse from an item, ride, /dismount; fly a griffon (Jump to take off, climb, land by flying low); mount barding (cloth or plate armor on the horse); attribute points to spend on the character sheet (+ and Max buttons, points each level; crafting attributes too); the defensive target panel's health bar and level; the ability book's Diplomacy page (your statement cards); general abilities on the ability book's General page (Sprint, Recall to your bind point, Recall to House); escrow (rewards that don't fit in your bags wait with any banker); the loot sparkle on lootable corpses; NPCs that talk (idle chatter, a line when they attack, greeting voices); spell and ability particle effects (the FX packages load); item conversion (right-click Copper Ore for the Convert window); deconstruction with a Salvage Kit (resources or dust); wounds (critical hits wound a body part, resting heals it); a spyglass that zooms the camera; corpse summoning at Veyla; the crafting journal's recipe pages (details and steps missing items); choosing a crafting trade (Blacksmith, Outfitter, Artificer) at the camp trainer, with the trade's skills on the crafting Skills tab; the character window's Harvesting tab and Stats-tab critical chance; the Outpost icon on your portrait while you are in a camp; hint popups (the client's Hints window on first login, first kill, first loot, first level and first death; /hintsreset); alternate advancement (the AA window: points from experience, training ranks that raise attributes); usable food with a reuse timer (Travel Rations heal, the tooltip shows the time left)
- [x] Titles (prefix/suffix, /titleset, quest rewards, shown over the head), the game clock (/time), /played
- [x] Duels: /duel challenge popup, countdown, auto-attack fight to 1 HP; caravans (invite, member list, remove, log in at the caravan after 3 hours offline)
- [x] Pets: summon a wolf from an item; it follows and attacks on /pet attack
- [x] Fishing: cast into water, the pull minigame, catch fish, bait use and Fishing skill-ups
- [x] Assembly crafting: assembly trainer, recipe categories, combine components into an item at an assembly bench
- [x] Riftways: /rift and the client's Riftway map travel between riftway stones (one destination placed)
- [x] Housing: buy a plot from its For Sale sign, build a cottage on it (instantly, or a home from construction materials), place and pick up furniture, storage chests, make it your guild's headquarters (the guild leader confirms)
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
- [x] GM NPC list (`!npclist`) for content building; travel-journal tracking with `/traveldirections` (compass marker); locations discovered by walking near them; fishing combos (learned patterns shown on the Achievements page); minion special attacks; dialogue unlocked by winning a parley; NPC stuns, roots and fear on players (songs are interrupted); more mounts (dire wolf, camel, griffon) at the camp merchant; a second outpost in the Wildgrowth Forest with its own merchant, quest chain, creatures and faction; item stat bonuses and ratings in tooltips; equipped gear raises your attributes, armor class (less damage taken), maximum health (Constitution and level; a level up heals you), regeneration and weapon damage, all shown on the character sheet; misses, dodges, parries, blocks and critical hits in melee; kill experience scaled by level difference (gray mobs give none) and a rising experience curve per level; casters spend energy and fighters endurance, with pools sized by attributes; ability damage and heals grow with level and attributes; each race and class has its own attribute strengths, growing with level; combat reaction windows close when their enemy dies; clearing experience debt with an item (the client's own Clear Experience Debt dialog); gender, race and character rename items; item flags (No Trade, Soulbound, Quest, No Sell...) with Bind On Equip and an unbinding tool; saved diplomacy strategy decks (/decksave, /deckload, /deckclear); /forcecombatstance; forms end on death and /applyformondeath brings them back; clicking a player, F1 and /targetself set the defensive target; /transferplot gives your house to another player; female characters drawn as female (in the world and on the select screen); dragging items between house chest slots and splitting stacks into or out of a chest; clicking an item link in chat shows the item's tooltip; group target marks (/mark); /rope hauls a defensive-targeted player to you after they accept; /citystatus lists the civic diplomacy stats; /lockouttimerlist; /report saves a player report with the recent chat lines; /walk and /run; /hidehood, /hidehelm, /hidecloak and wear/wield preferences (saved, shown to other players); /cleartargets; guild headquarters (the guild leader confirms) and the Building Inventory list with Move Fixture to me; forgetting a travel-journal location; summoning a player with the client's Call Confirmation (accept to be moved); the crafting Table Setup's Back button and Auto Setup Table box; /reloadui keeps your hotbars; the house Manage NPCs lists; /groupboot and /grouppromote; group members suggesting invites to the leader (Invite Referral popup); a member's spell icon in the group window while they cast; the game's own messages for /random, binding and unbinding items, ability and auto-attack failures and item errors

- [x] Accounts with salted password hashes, a launcher (`tools/play.py`, HTTPS with a certificate), one-time session tokens, characters per account, suspensions; one connection per character
- [x] Server side: SQLite database (`server/vanguard.db`), reliable-packet resends and in-order delivery (long client messages arrive), a load test (`tools/loadtest.py`: 100 players moving in one spot at 62% of a core) and a protocol fuzzer (`tools/fuzz.py`) with the bugs it found fixed (docs/TESTING.md)

### Not done yet
- [ ] Doors: none exist in the shipped maps or our cottage (checked; see HOUSING.md). The protocol to open one is worked out for when a building with a door is used
- [ ] Descending while flying needs a person to try (take-off, flight and climbing work: Jump on a griffon, docs/MOUNTS.md)
- [ ] Psionicist psionic points (messages known; the shipped UI has no window for them)
- [ ] Combat-form ability restrictions (which abilities each form allows is server data; every ability works in every form)
- [ ] The civic stats window (none in the shipped UI; `/citystatus` lists the stats in chat instead)
- [ ] Real game data: every item, mob, quest, ability number and reward here is a placeholder until the content editor (docs/CONTENT_EDITOR.md)

Game data gathered from fan sites goes in [crowdsourced/](crowdsourced/README.md) ([agent instructions](crowdsourced/AGENT_INSTRUCTIONS.md)) before it is imported into `server/content/`.

What has been tested, and what still needs a person: [docs/TESTING.md](docs/TESTING.md). Which of the client's 720 zone messages the server sends, or doesn't need: [docs/UNSENT_MESSAGES.md](docs/UNSENT_MESSAGES.md) (628, 87%, on 2026-10-15). The client's own messages the server can show by number: [docs/NOTICES.md](docs/NOTICES.md) (generated by `tools/notice_table.py`).

**Content editor:** `python tools/editor.py` opens a local web editor (http://127.0.0.1:8099) for the server's content files, with validation before saving, a terrain map for placing spawns, and live reload in a running server. With `--accounts` others can log in with their game accounts and submit changes that an admin reviews and approves (docs/CONTENT_EDITOR.md).

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for everything decoded so far. Topic docs: [INVENTORY](docs/INVENTORY.md), [ITEM_FIELDS](docs/ITEM_FIELDS.md), [GEAR](docs/GEAR.md), [ABILITIES](docs/ABILITIES.md), [ABILITY_VISUALS](docs/ABILITY_VISUALS.md), [LOOT](docs/LOOT.md), [MERCHANTS](docs/MERCHANTS.md), [GROUPS](docs/GROUPS.md), [CHAT](docs/CHAT.md), [TRADE](docs/TRADE.md), [QUESTS](docs/QUESTS.md), [CHUNK_TRAVEL](docs/CHUNK_TRAVEL.md), [CREATURES](docs/CREATURES.md), [HARVESTING](docs/HARVESTING.md), [CRAFTING](docs/CRAFTING.md), [DIPLOMACY](docs/DIPLOMACY.md), [TRAINERS](docs/TRAINERS.md), [BANK](docs/BANK.md), [SOCIAL](docs/SOCIAL.md), [EFFECTS](docs/EFFECTS.md), [GUILDS](docs/GUILDS.md), [BROTHERHOODS](docs/BROTHERHOODS.md), [FACTIONS](docs/FACTIONS.md), [WORK_ORDERS](docs/WORK_ORDERS.md), [MAIL](docs/MAIL.md), [MARKET](docs/MARKET.md), [DEATH](docs/DEATH.md), [MOUNTS](docs/MOUNTS.md), [RIFTWAYS](docs/RIFTWAYS.md), [HOUSING](docs/HOUSING.md), [TITLES](docs/TITLES.md), [DUELS and CARAVANS](docs/DUELS.md), [PETS](docs/PETS.md), [FISHING](docs/FISHING.md), [ASSEMBLY](docs/ASSEMBLY.md), [MOVEMENT](docs/MOVEMENT.md), [TRAVEL](docs/TRAVEL.md), [SONGS](docs/SONGS.md), [FORMS](docs/FORMS.md), [AA](docs/AA.md), [CONTENT_EDITOR](docs/CONTENT_EDITOR.md).

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
   It listens on UDP 10101 (login), 10100 (world) and 10102 (zone), plus HTTP 10180 for the launcher. It reads package GUIDs from the client's `UnrealScript/` and `Assets/Maps/` folders (nothing is copied or shipped).
4. Make an account, then log in with the launcher (it checks your password with the server and starts the client with a one-time session token, like the original SOE launcher):
   ```
   python server/accounts.py create <username> <password>
   python tools/play.py
   ```
   Or let players make their own accounts: start the server with `--allow-registration` and run `python tools/play.py --register`.

**Accounts.** Every character belongs to an account and you only see, play and delete your own. Passwords are stored as salted PBKDF2 hashes in the server's database (never committed). On first start the server creates a `dev` account (it prints the password once) that owns the existing characters and the test tokens `12345678` / `22222222`, so `bin\VGClient.exe --sessionid=12345678` still works for testing. `python server/accounts.py list | password | token | suspend | unsuspend` manage accounts (a suspended account gets the client's own "Your account has been suspended" popup). The launcher endpoint is plain HTTP unless the server gets a certificate: start it with `--launcher-cert server.crt --launcher-key server.key` to serve HTTPS (passwords encrypted), and players log in with `python tools/play.py --server <address> --https` (add `--cafile server.crt` for a self-signed certificate, e.g. `openssl req -x509 -newkey rsa:2048 -nodes -keyout server.key -out server.crt -days 365 -subj "/CN=myserver"`). Key and certificate files are never committed. Use HTTPS before opening a server to the internet. A refused login shows the client's own popup (login event 2): "Login session timed out. Please exit and reenter the game through Launchpad. (1002)" for an unknown or used-up launcher token.

To check that nothing is broken, run `python tools/smoke_test.py`: it starts both, enters the world, types a set of commands and reports PASS or FAIL. `python tools/check_all.py` runs every automated check (unit tests, multiplayer scenarios with headless players, a load test, fuzzing) without the game client.

To run a server for other people (ports, HTTPS, accounts, backups, the operator console, how many players), see [docs/HOSTING.md](docs/HOSTING.md). For a long-running server, add `--quiet-packets`: the log then keeps the decoded events but not a hex dump of every packet.

Characters are saved in a SQLite database, `server/vanguard.db` (one row per character: position, chunk, level, XP, coins, bag, equipment, hotbar and the rest), together with accounts, guilds, mail, the market, housing and the other saved data. On first start the server imports the old JSON files and renames them to `*.imported`. `python server/storage.py export` writes everything out as JSON (backups, hand edits), `python server/storage.py import <file.json>` loads a file back in, and `python server/storage.py set <name> <field> <value>` changes one field of one character. The server also copies the database to `server/backups/` when it starts and every 6 hours (`--backup-hours`, keeps the last 10; `python server/storage.py backup` makes one by hand). The emulator prints every packet it receives, decoded where the format is known. In the server's window you can type `who`, `announce <text>` (shown to every player), `kick <name>`, `backup` and `stop`. Stop it with `stop`, Ctrl+C or a service stop: it tells the players, saves each one (position, play time) and closes their connections, so the clients exit instead of waiting for a dead server.

Several clients can connect at once (log in again with `tools/play.py`, or for testing start a second copy with `--sessionid=22222222`); players in the same chunk see each other and share the NPCs.

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
- Admin helpers (with `--dev-commands`): `!goto Name`, `!summon Name`, `!call Name` (the summon offer the player accepts), `!chunk -19 12`, `!hide`, `!setupall 20` (level 20, every class ability, skills at the cap). Or make a character a GM with `python server/storage.py set <name> access_level 255` and use the client's own `/chunk`, `/gotoplayer`, `/summonplayer`, `/summongroup` and `/hideme`.
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
| `!use <ability>` | Use a known ability by name, as from the hotbar (e.g. `!use Sprint`) |
| `!spawn <mob key> [wander]`, `!despawn` | Builder mode: place a mob at your feet and save it to the chunk's spawn file; remove the targeted one |
| `!wander <radius>`, `!respawn <seconds>`, `!path add` / `!path clear` | Builder mode: change the targeted spawned NPC (saved) |
| `!wound <part 0-4> <severity 0-4>` | Set a wound (0 head, 1 torso, 2 left arm, 3 right arm, 4 legs) |
| `!guildcreate`, `!bankput`/`!bankget`, `!wear [n]`, `!ctext` | Guild, bank, durability and combat-text tests |
| `!item`, `!stat`, `!upd`, `!event`, `!chat`, `!sys`, `!exec` | Send raw messages (see `dev_command` in `login_stub.py`) |

World content (mobs, loot, items, vendors and spawns) lives in `server/content/`. Run `python content.py` to check it for mistakes.

## How it was built

Each message format was found by static analysis of `VGClient.exe` (Ghidra, via REA), then verified by running the real client against the emulator. Function addresses in the notes refer to Ghidra's names for that exact client build.

## License

[GNU Affero General Public License v3.0](LICENSE). If you run a modified version of this emulator as a public server, you must publish your changes.

*Vanguard: Saga of Heroes is a trademark of its respective owners. This project is not affiliated with or endorsed by them.*
