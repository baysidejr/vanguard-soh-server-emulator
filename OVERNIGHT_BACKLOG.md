# Overnight backlog

Working list for autonomous sessions, so progress survives context resets. Newest first in each section. The README checklist and docs/TESTING.md are the public record; this file is the to-do list.

## Next action

Scan the client's own logs (`bin/Logs/*.log`, `UnhandledMessagesClient.log` lines in `server/stub_log.txt`) across a few scripted sessions for more dropped or malformed messages.

## Prioritized tasks

0. **Character rename item** (template 1463295): 0x5d3 request (verify field order live), 0x5d4 reply known. Renaming must also move the name in guilds, brotherhoods, mail, market, housing, caravans and friends lists.
1. **Protocol correctness:** run the client through login, combat, bags, guild, mail, crafting; collect every "unhandled message" and client error line; fix each.
3. **Persistence audit:** for each saved field, check it survives /camp and a server restart (bag contents, bank, discovered locations, fish records, factions, titles, songs, spheres). Add a unit test that round-trips a character through save/load.
4. **Automated smoke test:** a script that launches the client, enters the world and checks the stub log and client log for errors, so old features get re-checked after changes.
5. **Integration gaps:** grep for handlers that print "unknown"/"unhandled" client events in stub_log.txt and implement the ones with known payloads.
6. **Crowdsourced import:** convert and import the first batch when it lands in `crowdsourced/raw/`.

## Blocked (needs the user or data)

- Griffon flight take-off (needs a hand-pressed double jump).
- Psionicist form recovery bar on screen (needs a person to watch it).
- Psionic points, civic stats display: no window in the shipped UI.
- Real formulas and content: waiting on crowdsourced data. Do not invent more.
- Class abilities without an abilities.json entry act as plain damage spells (a Sorcerer's See Invisibility I "hits"). The client has only their visuals; what each does needs real data.
- Raids with more than 2 clients, caravan login after a real 3 hours offline.

## Done

- 2026-10-13: Player gender decoded from the create request (raw +6) and sent (pawn m_Gender, MsgScore); before, every character was drawn male. Gender and race change items (templates 1454016/1454015) verified live. docs/INVENTORY.md "Character service items" lists every special template id.
- 2026-10-13: Clear experience debt with an item (template 1454022): 0x5da request, 0x5db reply codes reverse-engineered and verified live (refused with a tombstone out, cleared after).
- 2026-10-13: Unit test builds the zone-in messages for all 19 races x 15 classes at levels 1 and 50.
- 2026-10-13: Slash-command sweep (~40 commands): no unhandled messages either way. Client-only notices with no reply needed: 0x6c (after UI load), 0x71 BECOME_PC, 0x10e (empty, seen once; sender not found by the push scan).
- 2026-10-13: Persistence audit (saved vs loaded fields): the active crafting toolbelt was saved but never restored; now sent at zone-in.
- 2026-10-13: Caster energy verified in game (Sorcerer). Fixed: a fresh login showed health/endurance/energy below their attribute-based maximums; pools now start full.
- 2026-10-13: All guild world-request replies (errors, NoGuild) go out on the zone connection, where the client handles them (verified: "You can't change that member's notes.").
- 2026-10-13: Canyon Widow and Webweaver spawn female (the only spider mesh package), so the client stops logging a failed mesh load for each one.
- 2026-10-13: Guild member list request was answered on the world connection, which the client drops ("Received unhandled message id 1259/1260/1261"); now answered on the zone connection.
- 2026-10-13: docs/TESTING.md testing checklist.
