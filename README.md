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
- [x] Standing and walking on the real terrain anywhere in the chunk; spawn on flat ground
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
- [x] Ability trainer: buy the next class abilities
- [x] Multi-stage crafting with quality grades and complications
- [x] Bank: items and coins, saved per character
- [x] Item durability (worn on death) and repairs at a merchant
- [x] /who, friends and ignore lists, /afk /anon /lfg, /random, /inspect
- [x] Ability effects: buffs with timers and stat bonuses, damage over time with target debuff icons, heals, cooldowns
- [x] Guilds: create, invite, join, ranks, kick/quit/delete, guild chat, message of the day, rank names, /guildstatus
- [x] Brotherhoods: invite popup, join, leave, kick, promote, MOTD, notes, rename
- [x] Combat text written by the client (Combat tab) for hits, heals and damage over time; cast bars; NPC special attacks
- [x] Per-character diplomacy decks, card slotting and reward cards; crafting catalysts
- [x] Factions: standings saved per character, kill/quest/parley changes, /showfactions, NPC name plates colored by standing
- [x] Crafting work orders: task master window, accept, craft the work-order recipe, turn in for coin, crafting XP and faction
- [ ] Crafting toolbelts and utilities; the hotbar cooldown sweep

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for everything decoded so far. Topic docs: [INVENTORY](docs/INVENTORY.md), [ITEM_FIELDS](docs/ITEM_FIELDS.md), [GEAR](docs/GEAR.md), [ABILITIES](docs/ABILITIES.md), [ABILITY_VISUALS](docs/ABILITY_VISUALS.md), [LOOT](docs/LOOT.md), [MERCHANTS](docs/MERCHANTS.md), [GROUPS](docs/GROUPS.md), [CHAT](docs/CHAT.md), [TRADE](docs/TRADE.md), [QUESTS](docs/QUESTS.md), [CHUNK_TRAVEL](docs/CHUNK_TRAVEL.md), [CREATURES](docs/CREATURES.md), [HARVESTING](docs/HARVESTING.md), [CRAFTING](docs/CRAFTING.md), [DIPLOMACY](docs/DIPLOMACY.md), [TRAINERS](docs/TRAINERS.md), [BANK](docs/BANK.md), [SOCIAL](docs/SOCIAL.md), [EFFECTS](docs/EFFECTS.md), [GUILDS](docs/GUILDS.md), [BROTHERHOODS](docs/BROTHERHOODS.md), [FACTIONS](docs/FACTIONS.md), [WORK_ORDERS](docs/WORK_ORDERS.md), [CONTENT_EDITOR](docs/CONTENT_EDITOR.md).

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

Characters are saved to `server/characters.json`: position, chunk, level, XP, coins, bag, equipment and hotbar. The emulator prints every packet it receives, decoded where the format is known.

Several clients can connect at once. Start a second copy with a different `--sessionid`; players in the same chunk see each other and share the NPCs.

### Things to try in game
- Click an NPC to target it. Use your hotbar abilities, or press **`** (auto-attack). Press **U** on a corpse to loot it.
- Press **U** on Orin the Trader, or say "Hail", then pick "Show me your wares." Right-click an item to buy it; right-click a bag item while the window is open to sell it.
- Right-click bag items to equip them, and right-click paper-doll items to take them off.
- Group with another player using `/invite Name` and `/groupacceptinvite`.
- Chat with `/shout`, `/tell Name …`, `/ooc`, `/g`, `/emote …`, `/wave`. Use `/sit` to rest and `/camp` to camp.
- Walk or teleport past a chunk edge to enter the neighbouring zone.

### Developer commands
Start the server with `python login_stub.py --dev-commands`, then type these in the game's chat box:

| Command | Effect |
| --- | --- |
| `!tp x y z` | Teleport (`~` keeps the current coordinate) |
| `!target <name>` | Target an NPC by name |
| `!hurt N` | Lose N health |
| `!anim id [me]` | Play an animation on the target or yourself |
| `!prop <property> <value> [me]` | Set a replicated pawn property |
| `!move dx dy` | Move the targeted NPC |
| `!item`, `!stat`, `!upd`, `!event`, `!chat`, `!sys`, `!exec` | Send raw messages (see `dev_command` in `login_stub.py`) |

World content (mobs, loot, items, vendors and spawns) lives in `server/content/`. Run `python content.py` to check it for mistakes.

## How it was built

Each message format was found by static analysis of `VGClient.exe` (Ghidra, via REA), then verified by running the real client against the emulator. Function addresses in the notes refer to Ghidra's names for that exact client build.

## License

[GNU Affero General Public License v3.0](LICENSE). If you run a modified version of this emulator as a public server, you must publish your changes.

*Vanguard: Saga of Heroes is a trademark of its respective owners. This project is not affiliated with or endorsed by them.*
