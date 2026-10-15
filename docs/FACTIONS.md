# Factions

Every NPC can belong to a faction, and each character has a standing with each faction, from -20000 to 20000. Standing changes when you kill a faction's members, finish quests or win parleys. The client shows standings in its Factions window and colors NPC name plates by them.

Client dispatcher: `FUN_004ccc50`. Server module: `server/faction.py`. Content: `server/content/factions.json`.

## Messages

Server to client:

| id | layout | meaning |
| --- | --- | --- |
| 0x35b | `{wstr name, i32 faction id, i32 value, bool8 prestige}` | Adds a faction to the Factions window (gamevar `PCPlayerFactions`; `PCPrestigeFactions` when prestige is set). Handler `FUN_004cc720`. [O] |
| 0x358 | `{i32 faction id, i32 value}` | New standing for a faction the client already knows. If the value moves into another tier, the client recolors the name plates of every NPC whose `m_FactionId` is that faction (`FUN_004cca10` → `FUN_004ca8c0`, `FUN_004ca950`, `FUN_00b74020`). [O, verified live: a wolf's name turned red at Kill on Sight] |
| 0x35d | same as 0x35b | "You've unlocked a new prestige faction: %s!" [O] |
| 0x35c | none | **publishes** the rows 0x35b stored into both lists, PCPrestigeFactions (FUN_004cb110) and PCPlayerFactions (FUN_004cb240). Without it the Diplomacy - Factions tab stays empty. Sent after the login rows, after a requested row and on the UI-loaded notice (0x6c). [O, verified live 2026-10-15] |

Client to server:

| id | layout | sent by |
| --- | --- | --- |
| 0x18d | `{i32 page}` | `/showfactions` (page -1 = all) prints "Requesting all faction ratings that you have changed from the server." (`FUN_00613240`) [O] |
| 0x18c | `{wstr name}` | `/showfactionbyname <name>` (`FUN_006130d0`) [O] |

The client prints nothing for the reply; our server answers with chat lines listing the standings.

**Faction info request (0x35e).** When the client needs a faction it has no row for (for a name plate colour, say), FUN_004cc5d0 sends **0x35e {i32 faction id}**, once per id, and waits for the usual **0x35b** MsgFactionInfo. The server sends every content faction at login, so this only fires for ids it never sent. It now answers from factions.json and stays silent for unknown ids. Unit-tested.

## Tiers

From `FUN_004ca950` (name plate color, BGRA bytes) and the string keys `FactionKOS` ... `FactionAlly`:

| standing | tier | name plate |
| --- | --- | --- |
| below -8000 | Kill on Sight | red (200, 0, 0) |
| -8000 to -5001 | Untrustworthy | orange (230, 160, 0) |
| -5000 to -2001 | Wary | (255, 200, 0) |
| -2000 to 1999 | Neutral | yellow (255, 255, 0) |
| 2000 to 4999 | Sociable | (220, 255, 0) |
| 5000 to 7999 | Goodwill | (140, 255, 0) |
| 8000 and up | Ally | green (0, 255, 0) |

The cursor check for attacking (`EntityTypes 0x10000000`, see HARVESTING.md) also compares the faction value with -7999.

## Name plates

`m_FactionId` is a replicated property of `SGONPCPawn` only. `SGOPCPawn` (the class our humanoid NPCs use) doesn't have it, so the server sets it only for `SGONPCPawn` mobs. The color only changes on a tier change after login (0x358); at login the plate keeps its normal color.

## Server behaviour

- At login every faction in `factions.json` is sent with 0x35b (the character's standing, or the faction's `start`).
- Killing a faction member changes standing by the faction's `kill` value (default -50). Factions in `allies` change the same way, and factions in `enemies` change by half the amount in the other direction. Group members in the same zone are all affected.
- Quest and parley rewards can include `"faction": {"<id>": amount}`.
- Each change sends 0x358 and "Your standing with X has improved/worsened."; a tier change adds "X now regards you as <tier>."
- Standings are saved per character (`factions` in characters.json).
- An NPC whose faction holds the player Kill on Sight attacks when the player comes within 1000 units ("Dust Bear notices you!"), even if it is normally passive. Merchants, trainers, bankers and stations never do. [verified live]
- `/con` adds "Dwarf Scout (Thestran Wastes Camp) regards you as Neutral." [verified live]
- Dev command: `!faction <id> <amount>`.

The real faction list (ids, names, starting values per race) lived in the server database and is listed as a gap in CONTENT_EDITOR.md.

## Prestige factions (verified live 2026-10-15)

factions.json `"prestige": true` (placeholder: 1005 Order of the Riftwatch, rewarded by Supplies for the Forge) keeps a faction out of the lists until the character first gains standing with it. That change sends **0x35d** instead of 0x358: "You've unlocked a new prestige faction: Order of the Riftwatch!" and the row goes to the Character window's Diplomacy - Factions tab under "Prestige Factions:" with its standing bar (seen live with `!faction 1005 250`). At login unlocked prestige factions are sent with 0x35b prestige = 1.
