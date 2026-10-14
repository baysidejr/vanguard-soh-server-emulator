# Overnight backlog

Working list for autonomous sessions, so progress survives context resets. Newest first in each section. The README checklist and docs/TESTING.md are the public record; this file is the to-do list.

## Next action

Scan the client's own logs (`bin/Logs/*.log`, `UnhandledMessagesClient.log` lines in `server/stub_log.txt`) across a few scripted sessions for more dropped or malformed messages.

## Prioritized tasks

1. **Protocol correctness:** run the client through login, combat, bags, guild, mail, crafting; collect every "unhandled message" and client error line; fix each.
2. **Caster energy in game:** create a Sorcerer (or use a dev command to switch class) and confirm the energy bar, not endurance, drops on an ability.
3. **Persistence audit:** for each saved field, check it survives /camp and a server restart (bag contents, bank, discovered locations, fish records, factions, titles, songs, spheres). Add a unit test that round-trips a character through save/load.
4. **Automated smoke test:** a script that launches the client, enters the world and checks the stub log and client log for errors, so old features get re-checked after changes.
5. **Integration gaps:** grep for handlers that print "unknown"/"unhandled" client events in stub_log.txt and implement the ones with known payloads.
6. **Crowdsourced import:** convert and import the first batch when it lands in `crowdsourced/raw/`.

## Blocked (needs the user or data)

- Griffon flight take-off (needs a hand-pressed double jump).
- Psionicist form recovery bar on screen (needs a person to watch it).
- Psionic points, civic stats display: no window in the shipped UI.
- Real formulas and content: waiting on crowdsourced data. Do not invent more.
- Raids with more than 2 clients, caravan login after a real 3 hours offline.

## Done

- 2026-10-13: Guild member list request was answered on the world connection, which the client drops ("Received unhandled message id 1259/1260/1261"); now answered on the zone connection.
- 2026-10-13: docs/TESTING.md testing checklist.
