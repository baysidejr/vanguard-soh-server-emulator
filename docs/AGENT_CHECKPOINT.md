# Agent Checkpoint

Recovery aid for the next session. Always re-check the real repository state (`git status`, `git log`) before relying on this.

- **Updated:** 2026-10-16
- **Branch:** `main` (tracks `origin/main`)
- **Latest commit at writing:** see `git log -1` (this checkpoint is committed with B-001)

## Last completed task
**B-005 (c): chunk hand-off and return** scenario (bots follow world event 8 with `Bot.join_zone`; Khal and back). `check_all.py` 6/6; 19 scenarios, 0 failed; real DB fingerprint `e53c48100b5e8a63` unchanged.
This session also: B-001 (checks on a scratch DB copy), B-002 (flight landing gap documented), B-005 (a) second login and (b) reconnect after a drop, B-013 (editor quest form dropped turn_in).

## In progress / next action
B-011 provenance report, B-004 (spike not reproduced in 5 runs), B-014 (temp-folder leak) done. B-005 edge walk done (20 scenarios). B-012 reviewed (nothing unlocks gameplay; blocked on the live client). Scrape branch: 29 new commits, no newly playable quests, not merged (B-009). B-015: scenarios "player report", "rescue rope", "appearance settings saved", "item link", "bug report", "lockout commands" (26 scenarios). B-005 COMPLETE (LeaveWorldTests: actor close and NPC release on leaving). B-003: 2026-10-16 the foreground is Windows Terminal again (GameInput no longer holds it), but the user was active, so the client smoke test was not run; run `check_all.py --client` when the PC is idle (GetLastInputInfo). B-015 VERIFIED.

B-016 (packet logger on short packets, found by a deep fuzz with logging on) fixed and verified.

**Actionable queue is empty without the user or the live client** (2026-10-16 21:45): every open STATUS.md 6.4 item is blocked: optional messages and particles need the client (B-012, B-006), presence gating needs a user decision (B-010: refusal text exists in the client, gain rates do not), flight landing needs mesh collision (B-002), placeholders/camp imports/scrape merge need user decisions (B-007, B-008, B-009). 2026-10-17 00:40: `check_all.py --client` 7 of 7 (unit 282, 26 scenarios, steady p95 11.2 ms, fuzz clean with packet log on, smoke PASS); DB fingerprint unchanged; B-001 and B-003 COMPLETE. B-006: tools/fx_props.py decodes effect emitters; the quest-node effect is tiny sparkles at the pivot (static evidence), live close-up check pending. Next session: `git fetch` and report scrape-branch commits; B-006 live check with the user's go-ahead; otherwise wait for user decisions.

## Uncommitted files
- `server/.claude/ralph-loop.local.md`: the loop tool's state file (not ours to commit).
- `AGENT_MISSION.md`: user-provided, ignored by `.gitignore` (`/*`), intentionally not committed.

## Tests
- Passed (latest `check_all.py`): unit tests (282), content check, scenarios (26), load test (steady p95 11.1 ms), server-log scan, fuzzing.
- `check_all.py --client` 7 of 7 on 2026-10-17 (smoke test with the game client).

## Blockers and user decisions
- B-007: keep or remove the 298 delivery placeholders.
- B-008: import archive NPCs into Sundering Wastelands / Wildgrowth Forest.
- B-009: merge newer scrape-branch commits (only on request); 31 new as of 2026-10-16 evening.
- B-010: gate parleys on presence with placeholder gain rates, or keep them open.

## Data-integrity notes
- Never run tests on `server/vanguard.db`; use `--data-dir` with `storage.scratch_copy`.
- A server started by `run_test.sh` may still be running on the real data (`login_stub.py --dev-commands`); stop it with `powershell -File tools/stop_servers.ps1` before checks (check_all refuses to start if port 10101 is busy).
