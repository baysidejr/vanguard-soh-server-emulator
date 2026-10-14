# Overnight backlog

Working list for autonomous sessions, so progress survives context resets. Newest first in each section. The README checklist and docs/TESTING.md are the public record; this file is the to-do list.

## Next action

Scan the client's own logs (`bin/Logs/*.log`, `UnhandledMessagesClient.log` lines in `server/stub_log.txt`) across a few scripted sessions for more dropped or malformed messages.

## Prioritized tasks

0. **Unhandled client requests:** docs/CLIENT_REQUESTS.md lists 105 ids the client can send that the server never handles. Classify (GM/debug vs player feature) and implement the player ones that need no invented data.
1. **Protocol correctness:** run the client through login, combat, bags, guild, mail, crafting; collect every "unhandled message" and client error line; fix each.
5. **Integration gaps:** grep for handlers that print "unknown"/"unhandled" client events in stub_log.txt and implement the ones with known payloads.
6. **Crowdsourced import:** convert and import the first batch when it lands in `crowdsourced/raw/`.

## Blocked (needs the user or data)

- Griffon flight take-off: the take-off request (client event 0x5a) never reaches the server even with a scripted running double jump; chain documented in docs/MOUNTS.md. Needs a runtime breakpoint (or a person to try by hand).
- Psionic points, civic stats display: no window in the shipped UI.
- Real formulas and content: waiting on crowdsourced data. Do not invent more.
- Class abilities without an abilities.json entry act as plain damage spells (a Sorcerer's See Invisibility I "hits"). The client has only their visuals; what each does needs real data.
- Raids with more than 2 clients, caravan login after a real 3 hours offline.

## Done

- 2026-10-14: In-game sweep of ~60 harmless slash commands found client requests the static scan missed (sent through FUN_00409210). Implemented, verified live: /walk and /run (GroundSpeed 185 / 337.889; replicated bIsWalking alone did not slow the owner), /hidehood /hidehelm /hidecloak, /setwearpreference, /setwieldpreference (saved as pawn_prefs, replicated, restored after relog), /cleartargets. Still unhandled from the sweep: /citystatus 0x12d, /aalist 0x85c, /lockouttimerlist 0x4fc (reply formats unknown), /cyclewieldpreference 0x112, /toggleeppearancegear 0x115.
- 2026-10-14: crowdsourced/convert.py now converts dialogue (dialogs.json), factions (factions.json, ids 2001+), recipes (inputs/output; stages left for a person), spawns (spawns_unplaced.json) and formulas (FORMULAS.md mapped to the placeholder constants they'd replace). Unit-tested.
- 2026-10-14: tools/smoke_test.py: automated in-game smoke test (server + client, Enter to play, ~20 commands, log scan, PASS/FAIL). Passes.
- 2026-10-14: Persistence: character loading extracted into player_from_character; a round-trip test loads a record with every saved field set and checks each value, and a guard test fails if a saved field is never read back.
- 2026-10-14: /transferplot (0x5c6) verified live with two clients.
- 2026-10-14: Fuzzed the inline zone and world dispatch chains (every event id x 5 payloads, player in a world): no hangs; the only exceptions are short-payload struct errors already caught per message. Guarded /unstuck before spawn.
- 2026-10-14: Defensive targeting fixed: player pawns lacked EntityTypes 0x20, so the client refused them as defensive targets (clicking a player, F1, /targetself did nothing). Verified live.
- 2026-10-14: GM test tools /.learnabilities, /.maxskills, /.setupall (server side) and !learnall, !maxskills, !setupall <level>, verified live. 
- 2026-10-14: GM access level found: SetNameID record +0x248 (characters.json "access_level"). With it the client's own /chunk works (verified live); a GM jump lands at the chunk centre in one hand-off.
- 2026-10-14: Admin teleports: server side of the client's GM commands (/chunk, /gotoplayer, /summonplayer, /hideme) plus dev chat commands !chunk, !goto, !summon, !hide, verified live with two clients. The client gates its own GM commands on an access level whose source is not found yet. Chunk hand-off refactored into travel_to_chunk (edge walking uses it too).
- 2026-10-14: All save files (characters, guilds, brotherhoods, mail, market, housing, caravans, civic, bug reports) are written atomically (temp file, fsync, rename), so a crash mid-write can't truncate them. Saves verified live.
- 2026-10-14: `--quiet-packets` option: no per-packet hex dumps or ack lines (a login session logs about 15x less).
- 2026-10-14: Unreal layer: incoming reliable bunches were compared with `<=`, so after a channel's 12-bit sequence wrapped (4095 -> 0) every later reliable bunch would be dropped. Now wrap-aware (UE2 BestSignedDifference). Outgoing sequences already wrapped on the wire. Login and walking re-checked live.
- 2026-10-14: Long-session fixes: reliable sequence numbers are u16 on the wire. The server's outgoing counter now wraps (struct.pack used to raise after 65,536 messages, cutting the player off), and resend detection keeps a window of 4,096 recent numbers instead of every number ever seen (after the client's counter wrapped, every new message would have been dropped as a resend). Unit-tested; a live test would need 65,536 real messages.
- 2026-10-14: Connections silent for 180 s are dropped from the server's client table (it used to grow forever, e.g. from connects that never log in). Live clients send keep-alives about every 30 s; verified /who and guild chat still work after 3.5 idle minutes.
- 2026-10-14: Fixed a second one-packet freeze: a connect packet claiming a maximum packet size below the header size made the fragmenter loop forever (no login needed). The size is now clamped to at least 64 and the fragmenter always advances. Every other parsing loop reviewed: all advance.
- 2026-10-14: Fixed a server freeze: nine UTF-16 string readers (house permissions, mail, broker, songs, bug reports) looped forever on a string with no terminator, so one malformed packet hung the server for everyone. Found by an in-process fuzz of all 28 event handlers (every event id x 5 payloads, each handler under a timeout): now no hangs and no crashes. Regression test added.
- 2026-10-13: Robustness: every packet and tick runs under a guard that logs the traceback instead of stopping the server for everyone. Fuzzed 3000 malformed packets at all three ports: server kept running, no errors (unauthenticated traffic is dropped early).
- 2026-10-13: Login smoke test runs all 13 zone-login hooks, and a guard test fails if a new hook is added without it. Mail sending re-checked live after the item-restriction changes.
- 2026-10-13: Form recovery bar confirmed on screen with a Psionicist test character; form lost on death and re-applied on release verified live. `!die` dev command.
- Parked: item links in chat. Markup and click path found (docs/CHAT.md); the server's reply to 0x158 is still unknown.
- 2026-10-13: /forcecombatstance (0x571) and /applyformondeath (0x5b2); death now ends the active form.
- 2026-10-13: /decksave, /deckload, /deckclear (0x33a-0x33c) diplomacy deck presets, verified live. docs/CLIENT_REQUESTS.md now names the slash command behind each unhandled request.
- 2026-10-13: Crafting items use the client's Crafting Resource / Crafting Component item types instead of misc.
- 2026-10-13: Jewelry tooltips said "Required Level: 1 Diplomacy" (item type 10 is diplomacy jewelry); now type 13, "1 Adventuring".
- 2026-10-13: Item flags (field 102) from items.json, Bind On Equip, trade/mail/broker/sell restrictions, unbinding tool (0x5e3) verified live.
- 2026-10-13: Character rename item (0x5d3/0x5d4) with name migration across all save files; character-select preview now shows gender (record +0x1a0).
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
