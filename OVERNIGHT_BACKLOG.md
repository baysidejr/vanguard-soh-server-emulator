# Overnight backlog

Working list for autonomous sessions, so progress survives context resets. Newest first in each section. The README checklist and docs/TESTING.md are the public record; this file is the to-do list.

## Next action

Keep sweeping slash commands in game (`sweep.sh`) for requests the static scan misses, and look up each reply format in docs/ZONE_MESSAGES.md (that is how the item link and lockout replies were found). Then the remaining unknown reply: guild usable/HQ (0x47a/0x47b).

## Prioritized tasks

0. **Client notices:** check the other invented server messages against docs/NOTICES.md (bags full, not online, cooldowns, guild/brotherhood permissions) and use the client's notice where the meaning matches exactly.
0. **Unhandled client requests:** docs/CLIENT_REQUESTS.md lists 90 ids the client can send that the server never handles. Classify (GM/debug vs player feature) and implement the player ones that need no invented data.
1. **Protocol correctness:** run the client through login, combat, bags, guild, mail, crafting; collect every "unhandled message" and client error line; fix each.
5. **Integration gaps:** grep for handlers that print "unknown"/"unhandled" client events in stub_log.txt and implement the ones with known payloads.
6. **Crowdsourced import:** convert and import the first batch when it lands in `crowdsourced/raw/`.

## Blocked (needs the user or data)

- Client-side furniture placement: dragging furniture onto the cottage floor gives the client's delete prompt, because FUN_004771d0 finds no house-interior zone (type byte +0x388 == 3, linked at +0xa8 to the house object) at the drop point. Needs a runtime look at the cottage prefab's zones. Right-click placement still works.
- Griffon flight take-off: the take-off request (client event 0x5a) never reaches the server even with a scripted running double jump; chain documented in docs/MOUNTS.md. Needs a runtime breakpoint (or a person to try by hand).
- Psionic points, civic stats display: no window in the shipped UI (`/citystatus` lists civic stats in chat).
- Real formulas and content: waiting on crowdsourced data. Do not invent more.
- Class abilities without an abilities.json entry act as plain damage spells (a Sorcerer's See Invisibility I "hits"). The client has only their visuals; what each does needs real data.
- Raids with more than 2 clients, caravan login after a real 3 hours offline.

## Done

- 2026-10-14: Building NPCs (Manage NPCs): available and placed lists (0x5cc / 0x5cd) verified live. Found that the docs had MsgBuildingNPCInfo's control value in the wrong field (it is the first i32: -1 clear, -2 end of batch), which left the list empty. Spawn / Remove / Go To (0x5ce / 0x5cf / 0x5d0) are handled (unit-tested), but the shipped VGUIBuildingNPCs.xml has those buttons' Settings names commented out, so the client can never send them. Refactored zone.populate_world into npc_from_template so house NPCs reuse the spawn code.
- 2026-10-14: Player summoning: 0x270 Call Confirmation offer, /callpcaccept /callpcdecline (0x271 {u8}) answered, the player moves to the caller with notice 45 "You have been summoned!". Verified live with two clients via `!call`. Which abilities summon is a content gap (CONTENT_EDITOR). 0x851 / 0x852 / 0x85b are /aaclear, /aaadd, /aatrain (alternate advancement, content).
- 2026-10-14: Travel journal: Forget a location (0x138 {id}) answered with 0x383 and saved (`journal_removed`), so it stays out at login and isn't rediscovered. Verified live through `!cev` (entry removed, still gone after relog); the client's own X button looked disabled and never fired. 0x137 identified as a tracking-changed notice (nothing to do).
- 2026-10-14: Building Inventory tab: the plot window now sends the fixture list (0x45a / 0x45c / 0x45b; first bool = chest, from the client's chest counter), and "Move Fixture to me" (0x465) moves the fixture to the player. Both verified live ("Chests: ( 1 of 3 )"; the chest reopened at Ranger's feet).
- 2026-10-14: Guild headquarters (0x47b / 0x47c, the leader confirms, the rules from the client's own tooltips) verified live: set, confirm popup, notice 28, button changes to Relinquish, cleared with notice 27. Guild usable toggle (0x47a -> 0x47a {bool} + notice 383/382) and the Buildings tab preview (0x474 -> 0x474 materials) unit-tested.
- 2026-10-14: The client's own furniture placement answered: 0x461 {item handle} -> 0x459 {wstr prefab, f32 1.0} ghost preview, 0x46d {handle, building, x, y, z, yaw, pitch, roll} (wire order from the field registration FUN_00473be0) places the fixture at the clicked pose if it is inside the house. Unit-tested. Live, the client never sends 0x461 (see Blocked). Found that 0x461 comes from dragging a bag item onto the world, not from a menu (no menu adds option 0x149).
- 2026-10-14: Callers followed up several levels (scratchpad reach2.py): 0x18f and 0x1e7 are unreachable too (their only caller chains end in functions nothing calls, jumps to or points at), marked in docs/CLIENT_REQUESTS.md. Other candidates from that pass were false positives from bad function-start guesses and were left alone.
- 2026-10-14: /toggleeppearancegear (0x115) answered with 0x116 {bool} and saved (app_gear_visible). Visible effect not identified.
- 2026-10-14: Deconstruct requests (0x58e/0x58f) answered with 0x590 code -1, "<item> can not be deconstructed." (found by pairing request ids with the next s2c id). Reply checked live.
- 2026-10-14: /mark (0x592) relayed to the group as 0x593 (same layout; group dispatcher handler FUN_004e1640). Request and relay seen live with two grouped clients; the overhead icon not checked visually.
- 2026-10-14: Rescue rope: /rope 0x190 -> 0x58a offer popup -> /ropeaccept 0x191 -> haul + notice 465 (464 with no thrower). Verified live with two clients.
- 2026-10-14: All 19 parley error codes (0x330) listed in docs/DIPLOMACY.md. Changing the strategy bar during a parley is now refused with code 2 and an out-of-range slot with code 3 (both the client's own messages).
- 2026-10-14: Reachability check of the unhandled client requests: 19 ids are sent only from functions nothing references (no call, jump or pointer in VGClient.exe), marked Unreachable in docs/CLIENT_REQUESTS.md.
- 2026-10-14: House chest drags inside the chest (0x153 {chest, item, count, slot}, from the drop handler FUN_00687a80): move, swap, split. The chest is redrawn silently (removing a split's new handle is a client "Programmer error"). Verified live with !chest <n> move. Deposits now honour the dropped slot and a split count (0x155), withdrawals a split count (0x157); verified live.
- 2026-10-14: /sharelockouttimer and /lockoutaccept, /lockoutdecline answered with the client's InvalidLockout / NoLockoutOffer notices. Unlock tool 0x5e5: its answer 0x5e6 is about Gold Membership locks, which this server doesn't have; documented, left unanswered.
- 2026-10-14: Item links: the answer to 0x158 is s2c 0x158 with the item record (FUN_005de090), found in ZONE_MESSAGES.md; the server resolves the item by name or template id. Tooltip popup verified live.
- 2026-10-14: /citystatus (0x12d): civic stats as chat lines (no shipped window), or the client's "No civic diplomacy here." popup (0x330 code 16) when there are none. Verified live / unit-tested. /aalist (0x85c) stays open: alternate advancement abilities are server content.
- 2026-10-14: /lockouttimerlist answered with 0x4fd {wstr name} (lockout dispatcher FUN_00588c50, ids 0x4f2-0x502); "Displaying lockout timers for Ranger:" verified live.
- 2026-10-14: docs/NOTICES.md: all 439 client notice codes (zone event 0x0e) with key and English text, generated by tools/notice_table.py from the client's jump table and VGClient.int. Twelve invented server errors now use the client's own notices (dead, too far, not/already in a group, can't afford, chest full, bags full, trade space, quest reward room, plot cost, defensive target, inspect); "You aren't in a group." and "Please target a PC." verified live. Left as text: messages that name a player or item, and zone.py helpers that return text.
- 2026-10-14: /report <name> (0x4ac) saved to player_reports.json with the chat lines; client notices 149/148/150 found in the notice switch. Verified live.
- 2026-10-14: /cancelability (0x25f / 0xe2 / 0xe1 / 0x144) drops a pending cast. Second command sweep logged /hintsenable, /craftinghintsenable, /fallthroughattacktoggle, /chatconnect in docs/CLIENT_REQUESTS.md. Fuzzing the zone dispatcher found /walk, /sit and /forcecombatstance before the Unreal channel opened raised KeyError (each caught, but the reply was lost): now guarded.
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
