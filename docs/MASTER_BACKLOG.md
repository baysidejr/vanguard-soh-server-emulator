# Master Backlog

Actionable engineering backlog for the Vanguard server emulator (see `AGENT_MISSION.md`). Ordered by impact × confidence × feasibility; data integrity and gameplay defects first.

States: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `IMPLEMENTED_UNVERIFIED`, `VERIFIED`, `COMPLETE`.

Baseline (verified 2026-10-16 from code and content, not copied from STATUS.md): 278 unit tests pass; `content.py` OK; 372 quests (368 archive: 298 delivery placeholders `_placeholder_steps`); 2,755 spawns (167 invented `_placeholder`, 61 camps); 2,502 mob templates (2,438 archive).

---

## B-001 Automated checks must never write the real save database
- **Priority:** P0 · **Category:** data integrity · **State:** VERIFIED
- **Evidence:** `tools/check_all.py` ran the scenario and load-test phases against `server/vanguard.db` (bots written to the live save, guilds/brotherhoods/mail created there, cleanup by deletion); `tools/smoke_test.py` logged in as Ranger on the live save and typed ~49 commands. Only fuzzing used a scratch `--data-dir`.
- **Paths:** `tools/check_all.py`, `tools/scenarios.py`, `tools/smoke_test.py`, `server/storage.py`
- **Done when:** every phase of `check_all.py` (and `smoke_test.py` on its own) runs on a scratch copy; a fingerprint of every row of the real database is identical before and after a full run; the scratch folder is removed.
- **Progress:** `storage.scratch_copy` (read-only SQLite online backup into a temp folder); `scenarios.py --data-dir`; `check_all.py` uses one scratch copy for server, scenarios, load test and smoke test, and deletes it; `smoke_test.py` defaults to its own scratch copy.
- **Last validation:** 2026-10-16: `check_all.py` 6/6 twice; DB fingerprint `e53c48100b5e8a63` (7 characters) identical before and after both runs; no `vgemu-check-*` folder left. The `--client` smoke phase not run (B-003).
- **Next action:** run `check_all.py --client` once B-003 clears, confirm the fingerprint again, then mark COMPLETE.

## B-002 Flight landing where the terrain lookup has no height
- **Priority:** P1 · **Category:** gameplay defect · **State:** COMPLETE (root cause documented; no safe server-side fix)
- **Evidence:** live 2026-10-16: diving at (-12891, -4871) in chunk_n19_12 the client stopped at z 4093 while `content.ground_z` returned -12677; `flight_check` never landed the griffon (docs/MOUNTS.md "Descending").
- **Paths:** `server/login_stub.py` (`flight_check`, `LAND_HEIGHT`), `server/terrain.py`, `server/content.py` (`ground_z`)
- **Done when:** the cause of -12677 there is known (terrain hole, mesh above terrain, or a lookup bug) and either the lookup is fixed or landing also triggers from the client's own reports (e.g. no height change while moving down for N reports); a unit test covers it.
- **Result (2026-10-16):** terrain samples show a pit down to the heightmap floor (-20,410) east of x -12,500; no water volume and no listed obstacle within 3,000 units, so the surface is large static meshes the server doesn't model. The lookup is correct for the terrain. No code change: a "height stopped changing" fallback would also land hovering fliers. /dismount ends flight there safely. Documented in docs/MOUNTS.md. A real fix needs mesh-surface heights (collision from the map's static meshes), a larger project.
- **Next action:** none (reopen if mesh collision is ever modelled).

## B-003 GameInput service window blocks client focus for automated tests
- **Priority:** P1 · **Category:** test infrastructure · **State:** BLOCKED (system service / user action)
- **Evidence:** 2026-10-16 ~10:00 onward: `GetForegroundWindow` returns an invisible `GameInputServiceWindow` (process GameInputSvc); scripted clicks reach the game window's coordinates but the game never gets focus. `AttachThreadInput` + `SetForegroundWindow` (focus.ps1) fails.
- **Done when:** the client takes focus again and `check_all.py --client` passes.
- **Blocker:** needs the user to click into the game window, restart "GameInput Service", or reboot. Not doing it from the agent (system service).
- **Next action:** re-check `GetForegroundWindow` at the start of each session.

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
- **Priority:** P2 · **Category:** stability · **State:** VERIFIED (a, b, c, edge walk)
- **Evidence:** scenarios cover chat, group, trade, tell, friend, guild, brotherhood, duel, AA, quest reply, parley line, ignore, riftway; none log the same character in twice, reconnect after a dropped connection, or cross a chunk edge and come back. The fuzzer covers malformed event payloads.
- **Paths:** `tools/scenarios.py`, `tools/loadtest.py`
- **Done when:** scenarios cover (a) a second login of an online character (old session closed cleanly), (b) reconnect after an abrupt drop (character saved, NPC state reset), (c) chunk change and return; all pass in `check_all.py`.
- **Progress:** (a) done 2026-10-16: scenario "second login" (a second connection for the same character; the old one gets UdpLibrary Terminate via `kick_other_session`, the new one plays and its chat reaches the other bot). The test bot now records Terminate (`loadtest` `terminated`). Passes on a scratch copy; real DB fingerprint unchanged.
- (b) done 2026-10-16: scenario "reconnect after a drop" (the socket closes without Terminate, as in a crash; a new login works at once and coins, items, level, quests are unchanged). 18 scenarios, 0 failed on a scratch copy; no server tracebacks; real DB fingerprint unchanged.
- (c) done 2026-10-16: `loadtest.Bot.join_zone` (zone login + UE2 handshake, returns the WELCOME level) lets bots follow a chunk hand-off; scenario "chunk hand-off and return": /rift KHAL, reconnect, WELCOME chunk_n13_n9; /rift SUNDERINGWASTELANDS at the Khal brazier, reconnect, WELCOME chunk_n19_12. check_all 6/6 (load test p95 11.0 ms), real DB fingerprint unchanged.
- Edge walk done 2026-10-16: scenario "walk across a chunk edge": zone event 0x9 {i32 -18, i32 12, u8} from the camp chunk; world event 8 names chunk_n18_12, the bot reconnects, WELCOME chunk_n18_12, saved chunk [-18, 12]. 20 scenarios pass twice in a row on a scratch copy; check_all 6/6; real DB fingerprint unchanged.
- **Remaining idea:** a check that the other players' clients close the leaving actor's channel (needs UE bunch parsing in the test bot). Malformed packets are covered by the fuzzer.

## B-006 Invisible runtime particle effects (quest-node glow, loot sparkle)
- **Priority:** P3 · **Category:** fidelity · **State:** NOT_STARTED
- **Evidence:** docs/QUESTS.md and docs/ABILITY_VISUALS.md: the client reaches the attach calls but nothing renders; `FXmystical_IOParticle001fx` shows nothing even spawned alone with 0x553, while other emitters do.
- **Done when:** the emitter renders on a node or corpse in a screenshot, or the reason is documented with runtime evidence (winbreak).
- **Blocker:** live client testing (B-003).

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

## B-010 Presence requirements for parleys
- **Priority:** P3 · **Category:** fidelity · **State:** NOT_STARTED (needs evidence)
- **Evidence:** archive NPC pages record a presence number (1, 200, 700...) shown on the parley option; the server does not gate on it and presence starts at 0. Real starting presence and gain rates are unknown.
- **Done when:** documentary or client evidence for how presence gates parleys and how it is earned; until then stays ungated (an approximation, labelled).

## B-011 Content provenance audit
- **Priority:** P2 · **Category:** content accuracy · **State:** VERIFIED
- **Evidence:** archive imports set `_source` on templates; placeholders are flagged; but hand-made camp content (Orin, Veyla...) and placeholder stats are not flagged per record.
- **Done when:** `content.py` (or a report tool) lists, per content file, how many records are archive-sourced, flagged placeholder, or unflagged hand-made, so no placeholder can be mistaken for original data.
- **Done 2026-10-16:** `python tools/provenance.py` prints, per content file, records citing an archive page, records marked invented, and unmarked ones (`--unmarked FILE` lists them); unit test ProvenanceTests. Current: mobs 2,438 sourced / 64 unmarked; quests 70 sourced / 298 placeholder / 4 unmarked; items 112 / 66 unmarked; spawns 2,452 sourced / 167 placeholder / 136 unmarked; riftways, factions, titles, hints, recipes, dialogs, plots all unmarked (hand-made). "Sourced" records still carry placeholder values the archive lacks (stats, prices).

## B-012 Optional unsent messages
- **Priority:** P4 · **Category:** protocol · **State:** NOT_STARTED
- **Evidence:** docs/UNSENT_MESSAGES.md: 38 optional. Only worth doing where they unlock behaviour.

## B-013 Editor quest form lost turn_in when used before its lists loaded
- **Priority:** P1 · **Category:** data integrity (content editing) · **State:** VERIFIED
- **Evidence:** intermittent unit-test failure `EditorPageTests.test_forms_round_trip` (twice on 2026-10-16): `quest forge_supplies` saved without `"turn_in"`. `initQuests` set `questDoc` before fetching mobs.json, so the form could be read while the giver / turn-in selects were still empty; `storeQuest` keeps unknown fields from the original except `turn_in`, so the turn-in NPC was silently dropped. A builder clicking a quest right after opening the tab could lose it the same way. Grew likelier as mobs.json reached 2,500 templates.
- **Paths:** `tools/editor_ui.html` (`initQuests`, `setMode`)
- **Fix:** `questDoc` is assigned only after the selects are filled; a `questLoading` flag stops a second concurrent load.
- **Last validation:** 2026-10-16: EditorPageTests 5/5 alone, full unit suite 3/3 OK.
