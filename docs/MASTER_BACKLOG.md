# Master Backlog

Actionable engineering backlog for the Vanguard server emulator (see `AGENT_MISSION.md`). Ordered by impact × confidence × feasibility; data integrity and gameplay defects first.

States: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `IMPLEMENTED_UNVERIFIED`, `VERIFIED`, `COMPLETE`.

Baseline (verified 2026-10-16 from code and content, not copied from STATUS.md): 278 unit tests pass; `content.py` OK; 372 quests (368 archive: 298 delivery placeholders `_placeholder_steps`); 2,755 spawns (167 invented `_placeholder`, 61 camps); 2,502 mob templates (2,438 archive).

---

## B-001 Automated checks must never write the real save database
- **Priority:** P0 · **Category:** data integrity · **State:** COMPLETE
- **Evidence:** `tools/check_all.py` ran the scenario and load-test phases against `server/vanguard.db` (bots written to the live save, guilds/brotherhoods/mail created there, cleanup by deletion); `tools/smoke_test.py` logged in as Ranger on the live save and typed ~49 commands. Only fuzzing used a scratch `--data-dir`.
- **Paths:** `tools/check_all.py`, `tools/scenarios.py`, `tools/smoke_test.py`, `server/storage.py`
- **Done when:** every phase of `check_all.py` (and `smoke_test.py` on its own) runs on a scratch copy; a fingerprint of every row of the real database is identical before and after a full run; the scratch folder is removed.
- **Progress:** `storage.scratch_copy` (read-only SQLite online backup into a temp folder); `scenarios.py --data-dir`; `check_all.py` uses one scratch copy for server, scenarios, load test and smoke test, and deletes it; `smoke_test.py` defaults to its own scratch copy.
- **Last validation:** 2026-10-16: `check_all.py` 6/6 twice; DB fingerprint `e53c48100b5e8a63` (7 characters) identical before and after both runs; no `vgemu-check-*` folder left. The `--client` smoke phase not run (B-003).
- **Closed 2026-10-17 00:40:** `check_all.py --client` 7 of 7 on a scratch copy (smoke test logged in, entered the world, ran 49 commands); real DB fingerprint `e53c48100b5e8a63` before and after; no scratch folder left.

## B-002 Flight landing where the terrain lookup has no height
- **Priority:** P1 · **Category:** gameplay defect · **State:** COMPLETE (root cause documented; no safe server-side fix)
- **Evidence:** live 2026-10-16: diving at (-12891, -4871) in chunk_n19_12 the client stopped at z 4093 while `content.ground_z` returned -12677; `flight_check` never landed the griffon (docs/MOUNTS.md "Descending").
- **Paths:** `server/login_stub.py` (`flight_check`, `LAND_HEIGHT`), `server/terrain.py`, `server/content.py` (`ground_z`)
- **Done when:** the cause of -12677 there is known (terrain hole, mesh above terrain, or a lookup bug) and either the lookup is fixed or landing also triggers from the client's own reports (e.g. no height change while moving down for N reports); a unit test covers it.
- **Result (2026-10-16):** terrain samples show a pit down to the heightmap floor (-20,410) east of x -12,500; no water volume and no listed obstacle within 3,000 units, so the surface is large static meshes the server doesn't model. The lookup is correct for the terrain. No code change: a "height stopped changing" fallback would also land hovering fliers. /dismount ends flight there safely. Documented in docs/MOUNTS.md. A real fix needs mesh-surface heights (collision from the map's static meshes), a larger project.
- **Next action:** none (reopen if mesh collision is ever modelled).

## B-003 GameInput service window blocks client focus for automated tests
- **Priority:** P1 · **Category:** test infrastructure · **State:** COMPLETE (cleared)
- **Evidence:** 2026-10-16 ~10:00 onward: `GetForegroundWindow` returns an invisible `GameInputServiceWindow` (process GameInputSvc); scripted clicks reach the game window's coordinates but the game never gets focus. `AttachThreadInput` + `SetForegroundWindow` (focus.ps1) fails.
- **Done when:** the client takes focus again and `check_all.py --client` passes.
- **Blocker:** needs the user to click into the game window, restart "GameInput Service", or reboot. Not doing it from the agent (system service).
- **Cleared:** by 2026-10-16 evening the foreground was an ordinary window again (no action by the agent). 2026-10-17 00:40, after waiting for 10 minutes without user input, `check_all.py --client` passed with the smoke test.
- **Next action:** if it recurs, re-check `GetForegroundWindow`; run client tests only when the PC has been idle (GetLastInputInfo).

## B-004 Intermittent load-test latency spike
- **Priority:** P2 · **Category:** stability · **State:** VERIFIED (not reproduced)
- **Evidence:** 2026-10-16 first `check_all.py` run after B-001: load test p95 43.7 ms, max 3092 ms (214 pings instead of 254); the next run p95 11.0 ms, max 11.8 ms. Earlier runs were all ~11 ms.
- **Paths:** `tools/loadtest.py`, `server/zone.py` (obstacle worker), `server/login_stub.py` main loop
- **Done when:** the spike is reproduced and explained (e.g. first obstacle-worker start, scratch DB not kept open) or 5 consecutive runs show none.
- **Result 2026-10-16:** the check_all sequence (fresh scratch copy, server, 19 scenarios, 20 bots for 20 s) run 5 times in a row: steady-state p95 10.9 to 11.2 ms, max 11.3 to 21.3 ms, 253 to 254 steady pings every run; overall max 53 to 64 ms (the login burst); no server errors. The one 3 s stall did not recur; most likely the PC was busy at that moment (the game client and other jobs were running then). Real DB fingerprint unchanged.
- **Next action:** reopen if check_all reports a steady-state max over 100 ms again (then keep the server log and per-second ping times).

## B-014 Leaked temp folders from scrape-branch reads
- **Priority:** P3 · **Category:** stability (disk) · **State:** VERIFIED
- **Evidence:** 111 `vgemu-raw-*` folders in %TEMP% (2026-10-15 21:00 onward): `import_zone.branch_raw` (used by `--branch` in import_zone, quest_readiness, refresh_archive) extracted the scrape branch with `git archive` and never removed it.
- **Fix:** the folder is removed at exit (`atexit`). Old folders (copies of git content) deleted.
- **Last validation:** `quest_readiness.py --branch origin/crowdsourced/archive-collection` leaves the count unchanged.

## B-005 Automated coverage: reconnects, repeated logins, zone transitions, malformed packets
- **Priority:** P2 · **Category:** stability · **State:** COMPLETE
- **Evidence:** scenarios cover chat, group, trade, tell, friend, guild, brotherhood, duel, AA, quest reply, parley line, ignore, riftway; none log the same character in twice, reconnect after a dropped connection, or cross a chunk edge and come back. The fuzzer covers malformed event payloads.
- **Paths:** `tools/scenarios.py`, `tools/loadtest.py`
- **Done when:** scenarios cover (a) a second login of an online character (old session closed cleanly), (b) reconnect after an abrupt drop (character saved, NPC state reset), (c) chunk change and return; all pass in `check_all.py`.
- **Progress:** (a) done 2026-10-16: scenario "second login" (a second connection for the same character; the old one gets UdpLibrary Terminate via `kick_other_session`, the new one plays and its chat reaches the other bot). The test bot now records Terminate (`loadtest` `terminated`). Passes on a scratch copy; real DB fingerprint unchanged.
- (b) done 2026-10-16: scenario "reconnect after a drop" (the socket closes without Terminate, as in a crash; a new login works at once and coins, items, level, quests are unchanged). 18 scenarios, 0 failed on a scratch copy; no server tracebacks; real DB fingerprint unchanged.
- (c) done 2026-10-16: `loadtest.Bot.join_zone` (zone login + UE2 handshake, returns the WELCOME level) lets bots follow a chunk hand-off; scenario "chunk hand-off and return": /rift KHAL, reconnect, WELCOME chunk_n13_n9; /rift SUNDERINGWASTELANDS at the Khal brazier, reconnect, WELCOME chunk_n19_12. check_all 6/6 (load test p95 11.0 ms), real DB fingerprint unchanged.
- Edge walk done 2026-10-16: scenario "walk across a chunk edge": zone event 0x9 {i32 -18, i32 12, u8} from the camp chunk; world event 8 names chunk_n18_12, the bot reconnects, WELCOME chunk_n18_12, saved chunk [-18, 12]. 20 scenarios pass twice in a row on a scratch copy; check_all 6/6; real DB fingerprint unchanged.
- Actor cleanup done 2026-10-16 as unit tests (LeaveWorldTests): leaving a chunk sends the actor close to every other member and not to the leaver, NPCs fighting the leaver drop it and give up, and a connection already replaced by a re-login leaves the new one alone. (An end-to-end check would need UE bunch parsing in the test bot.) Malformed packets are covered by the fuzzer.
- **State:** all done-when parts covered.

## B-006 Invisible runtime particle effects (quest-node glow)
- **Priority:** P3 · **Category:** fidelity · **State:** COMPLETE (reason documented with runtime evidence)
- **Evidence:** docs/QUESTS.md and docs/ABILITY_VISUALS.md: the client reaches the attach calls but nothing renders; `FXmystical_IOParticle001fx` shows nothing even spawned alone with 0x553, while other emitters do.
- **Done when:** the emitter renders on a node or corpse in a screenshot, or the reason is documented with runtime evidence (winbreak).
- **2026-10-17 (static, tools/fx_props.py):** FXmystical_IOParticle001fx's own emitters are two tiny sprite clusters (sizes 1-15 units, within ±25 units of the owner's pivot, no skeletal/mesh spawning), so "needs a skeletal owner" is not supported. The guess that followed ("too small / inside the mesh") was refuted live the same night, see below. (A first dump looked up `SpriteEmitter0` by name and got another class's emitter; the tool now lists only the class's own sub-objects.)
- **Loot sparkle is not part of this:** docs/LOOT.md records it seen live 2026-10-15 (white glints on a dead Canyon Widow); the old wording here was stale. Its class FXspells_Loot001fx has 12 particles of size 50 (plus 20 of 2-6) within ±10-20 units; the quest-node class tops out at 15, which fits "there but too small / inside the mesh".
- **Live 2026-10-17 (scratch save):** at a spot where a 0x553 red sparkler renders, 0x553 spawns of FXmystical_IOParticle001fx and FXspells_Loot001fx show nothing (zoomed screenshot compare). Loot001fx renders when attached to a corpse, so 0x553 spawns don't predict attached rendering; size is not the cause.
- **Up close 2026-10-17 (scratch save):** both camp Copper Ore Veins marked (quest step "Gather Copper Ore (0/2)"), camera 250 units away facing them: nothing visible. The spawn point (±25 units of the pivot) is probably inside the rock, so screenshots can't separate hidden from not rendered.
- **Renders on an NPC (live 2026-10-17, scratch save):** `!prop m_bShowIOParticle 1` + `!event 0x56a T` on Orin the Trader lit gold/orange sparkles around his head. The effect, packages, flag and message are right; the problem is specific to harvest-node pawns (attach "ground" branch; probably inside the rock).
- **Attach placement (Ghidra 2026-10-17):** FUN_00bbb740(fx, -9999, 1, 1) attaches at the pawn's "ground" point + (2 x pawn+0x330 + per-model table value + 20); pawn+0x330 presumably CollisionHeight, which the server cannot replicate (not in the net cache) and the client takes from race 537's data. Most likely the sparkles sit inside the boulder because the node's collision height is small [I]; no server-side fix short of a different node model.
- **Result 2026-10-17 (winbreak at 0xbbb740, scratch save):** vein pawn+0x330 = 50.0 (model 537), Orin 90.0 (model 14), same base z 351.5: the effect goes ~120 units above the vein's base (plus the model table value), inside a boulder taller than its 50-unit collision [I: rock height from screenshots]. Client data, not a server bug; closed. Reopen only to try a different node model.
- Superseded: **Next action (replaces the one below):** winbreak at 0xbbb740 on a marked vein to read pawn+0x330 and confirm; then decide (document as a client-data limit, or try another harvest-node race whose mesh is smaller). Old: winbreak after the 0x56a attach: does the emitter get particles (alive count) and where is the effect actor (Location vs. the vein's mesh bounds)? Low priority (P3). Superseded plans: marked node up close (done);  of the class on open ground, then at a marked node's pivot. The client works again (B-003 complete), but live runs log in as the real characters unless set up on a scratch copy; do it with the user's go-ahead.

## B-007 Placeholder content: delivery quests and invented camps
- **Priority:** P2 · **Category:** content accuracy · **State:** BLOCKED (user decision + scrape data)
- **Evidence:** 298 quests `_placeholder_steps`, 167 spawns `_placeholder`; listed in the editor's "Placeholders to review".
- **Done when:** each is replaced by archive evidence or the user decides to keep/remove them. Removal of all delivery placeholders needs explicit authorization (mission).
- **Next action:** after each scrape update, re-run `tools/quest_readiness.py --branch` and replace placeholders whose real objectives/locations appeared.

## B-008 Import archive NPCs into the two original camp zones
- **Priority:** P3 · **Category:** content · **State:** BLOCKED (user decision)
- **Evidence:** dry run 2026-10-16: Sundering Wastelands +4, Wildgrowth Forest +19 (drafts in `crowdsourced/drafts/`).

## B-009 Merge newer scrape-branch commits
- **Priority:** P3 · **Category:** content · **State:** BLOCKED (user authorization per merge)
- **Evidence:** `origin/crowdsourced/archive-collection` at 2ed0b4b, merged into main 2026-10-16 with the user's go-ahead. Mission: do not merge the active scrape branch without explicit authorization.
- **Next action:** at each session, `git fetch` and report new commits; merge only when asked.
- **2026-10-16 (later):** 29 new commits on the branch (cbbe68c: mob pages, loot-table and merchant-role reviews). `quest_readiness.py --branch` gives the same result as main (4,774 archive quests, 70 ready), so no delivery placeholder can be replaced from them yet. Not merged.
- **2026-10-17 01:40:** 58 commits ahead now (5355281: mob geography and loot audits, cached mob page replays); quest readiness with the branch still 70 ready of 4,774. Not merged.

## B-010 Presence requirements for parleys
- **Priority:** P3 · **Category:** fidelity · **State:** BLOCKED (user decision; gain rates unknown)
- **Evidence:** archive NPC pages record a presence number (1, 200, 700...) shown on the parley option; the server does not gate on it and presence starts at 0. Real starting presence and gain rates are unknown.
- **Done when:** documentary or client evidence for how presence gates parleys and how it is earned; until then stays ungated (an approximation, labelled).
- **Checked 2026-10-16:** the client has the refusal text (dialog response status 17 `ResponseLocked`, "You don't have enough presence to talk about that.", docs/DIPLOMACY.md) and the rank bands (Newcomer < 75 ... Famous >= 4500), so the gating mechanism exists. No client file gives starting presence or gain rates (searched Strings.txt, VGClient.int, VGUIAssets). Gating now would lock most archive parleys (many ask 700, everyone starts at 0, the server's gain of 10 per win is a placeholder).
- **State change:** BLOCKED (user decision): turn gating on with placeholder rates, or wait for archive evidence about presence gain.

## B-011 Content provenance audit
- **Priority:** P2 · **Category:** content accuracy · **State:** VERIFIED
- **Evidence:** archive imports set `_source` on templates; placeholders are flagged; but hand-made camp content (Orin, Veyla...) and placeholder stats are not flagged per record.
- **Done when:** `content.py` (or a report tool) lists, per content file, how many records are archive-sourced, flagged placeholder, or unflagged hand-made, so no placeholder can be mistaken for original data.
- **Done 2026-10-16:** `python tools/provenance.py` prints, per content file, records citing an archive page, records marked invented, and unmarked ones (`--unmarked FILE` lists them); unit test ProvenanceTests. Current: mobs 2,438 sourced / 64 unmarked; quests 70 sourced / 298 placeholder / 4 unmarked; items 112 / 66 unmarked; spawns 2,452 sourced / 167 placeholder / 136 unmarked; riftways, factions, titles, hints, recipes, dialogs, plots all unmarked (hand-made). "Sourced" records still carry placeholder values the archive lacks (stats, prices).

## B-012 Optional unsent messages
- **Priority:** P4 · **Category:** protocol · **State:** BLOCKED (live client, B-003)
- **Evidence:** docs/UNSENT_MESSAGES.md: 38 optional. Only worth doing where they unlock behaviour.
- **Review 2026-10-16:** none unlocks gameplay. They are encounter-window details (0x3a3-0x3c8; several tried live with no visible change), combat-form state (0x38b-0x399; forms work without them), petitions (0x508/0x50a; left alone at the user's request), camera FOV 0x728, client actor spawn 0x553 (tried, nothing visible), bUse250System 0x11a, pending-death lines 0x193/0x194 and group drain 0x246 (need content). Each needs a live client check to be worth anything.
- **Next action:** once B-003 clears, try the encounter-window messages again with a multi-mob encounter.

## B-013 Editor quest form lost turn_in when used before its lists loaded
- **Priority:** P1 · **Category:** data integrity (content editing) · **State:** VERIFIED
- **Evidence:** intermittent unit-test failure `EditorPageTests.test_forms_round_trip` (twice on 2026-10-16): `quest forge_supplies` saved without `"turn_in"`. `initQuests` set `questDoc` before fetching mobs.json, so the form could be read while the giver / turn-in selects were still empty; `storeQuest` keeps unknown fields from the original except `turn_in`, so the turn-in NPC was silently dropped. A builder clicking a quest right after opening the tab could lose it the same way. Grew likelier as mobs.json reached 2,500 templates.
- **Paths:** `tools/editor_ui.html` (`initQuests`, `setMode`)
- **Fix:** `questDoc` is assigned only after the selects are filled; a `questLoading` flag stops a second concurrent load.
- **Last validation:** 2026-10-16: EditorPageTests 5/5 alone, full unit suite 3/3 OK.

## B-015 Bot coverage for server-only hand-run checks
- **Priority:** P3 · **Category:** stability · **State:** VERIFIED
- **Evidence:** docs/TESTING.md hand-run items are all unchecked; some depend only on server answers and can run in `scenarios.py` while the client is blocked (B-003).
- **Progress:** 2026-10-16 scenario "player report": /report (0x4ac) answers 149 "Player report submitted", a second within a minute 148 (wait longer), the report lands in the data folder's player_reports.json (scratch copy, not server/). 21 scenarios; check_all 6/6; real DB fingerprint unchanged. The client's display of the line stays a hand-run check.
- 2026-10-16 scenario "rescue rope": B targets A and throws (/rope 0x190); A gets 0x58a naming B, accepts (0x191) and gets notice 465 (hauled). B throws so B stays at the brazier for the riftway. 22 scenarios; check_all 6/6.
- 2026-10-16 scenario "appearance settings saved": /hidehelm 0x114 and /setwearpreference 0x110 are saved in pawn_prefs. 23 scenarios; check_all 6/6.
- 2026-10-16 scenario "item link": /itemlinkrequest 0x158 for Copper Ore answers 0x158 with its item record. 24 scenarios; check_all 6/6. (/walk's answer is a UE property and MsgScore field, which the test bot does not parse.)
- 2026-10-16 scenarios "bug report" (0x4aa saved in the data folder, "Saved as bug report #n.") and "lockout commands" (0x4fc answered with 0x4fd, 0x4fb notice 159, 0x273 notice 158). 26 scenarios; check_all 6/6; server/bug_reports.json untouched.
- `!call` (CallPcTests) and full-bag escrow (test_full_bags_go_to_escrow_then_a_banker_hands_it_over) are already unit-tested; the remaining TESTING.md items are client display checks.
- **Next action:** none until the client can be driven (B-003).

## B-016 Packet logger failed on short reliable packets
- **Priority:** P2 · **Category:** stability · **State:** VERIFIED
- **Evidence:** deep fuzz 2026-10-16 (event ids 0x1-0x900, 16 payloads each, 7 context passes, 40 raw rounds, `--quiet-packets`): 0 handler errors. A second run with packet logging on (the default without `--quiet-packets`) showed 13 errors outside handlers: `describe()` read a u16 sequence from 2- and 3-byte reliable packets (struct.error), and the exception dropped the whole datagram. check_all never saw it because it runs with `--quiet-packets`.
- **Paths:** `server/login_stub.py` (`describe`), `server/test_login_hooks.py` (DescribeTests)
- **Fix:** a reliable packet shorter than 4 bytes is logged as too short. DescribeTests (3,000 random and truncated datagrams) fails before the fix, passes after.
- **Last validation:** fuzz with logging on, 200 raw rounds: 0 tracebacks. Broker events 0x52b-0x53f, which once failed the fuzzer's 3 s ping in the deep run, answered every ping when repeated (a timing effect, not a disconnect).
- **Full-range run with logging on (2026-10-16):** event ids 0x1-0x900 on the login, world and zone servers, 4 payloads each, 7 context passes, 100 raw rounds, seed 23: 0 tracebacks, 0 handler errors. The zone ping failed after some world/login-sweep ids (0x71d, 0x72c-0x737) and the fuzzer re-logged in; no server error was logged. Rechecked with the new `fuzz.py --context N` (one setup pass): ids 0x710-0x740, 16 payloads each, in every one of the 7 passes: no session closed, 0 tracebacks. These ids have no zone handler; the earlier ping failures were timing (the fuzzer's 3 s ping during a long run), not a server fault. Closed.