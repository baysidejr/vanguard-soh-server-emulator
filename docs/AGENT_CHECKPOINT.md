# Agent Checkpoint

Recovery aid for the next session. Always re-check the real repository state (`git status`, `git log`) before relying on this.

- **Updated:** 2026-10-16
- **Branch:** `main` (tracks `origin/main`)
- **Latest commit at writing:** see `git log -1` (this checkpoint is committed with B-001)

## Last completed task
**B-005 (c): chunk hand-off and return** scenario (bots follow world event 8 with `Bot.join_zone`; Khal and back). `check_all.py` 6/6; 19 scenarios, 0 failed; real DB fingerprint `e53c48100b5e8a63` unchanged.
This session also: B-001 (checks on a scratch DB copy), B-002 (flight landing gap documented), B-005 (a) second login and (b) reconnect after a drop, B-013 (editor quest form dropped turn_in).

## In progress / next action
B-011 provenance report, B-004 (spike not reproduced in 5 runs), B-014 (temp-folder leak) done. B-005 edge walk done (20 scenarios). B-012 reviewed (nothing unlocks gameplay; blocked on the live client). Scrape branch: 29 new commits, no newly playable quests, not merged (B-009). B-015 started: scenario "player report" (21 scenarios). Next: more server-only TESTING.md items as scenarios (`!call`, `/rope`, escrow).

## Uncommitted files
- `server/.claude/ralph-loop.local.md`: the loop tool's state file (not ours to commit).
- `AGENT_MISSION.md`: user-provided, ignored by `.gitignore` (`/*`), intentionally not committed.

## Tests
- Passed (latest `check_all.py`): unit tests (279), content check, scenarios (21), load test (steady p95 11.1 ms), server-log scan, fuzzing.
- Not run: `check_all.py --client` smoke test, because the game client cannot take keyboard focus (B-003).

## Blockers and user decisions
- B-003: GameInput service window holds the foreground (user: click into the game, restart "GameInput Service", or reboot).
- B-007: keep or remove the 298 delivery placeholders.
- B-008: import archive NPCs into Sundering Wastelands / Wildgrowth Forest.
- B-009: merge newer scrape-branch commits (only on request).

## Data-integrity notes
- Never run tests on `server/vanguard.db`; use `--data-dir` with `storage.scratch_copy`.
- A server started by `run_test.sh` may still be running on the real data (`login_stub.py --dev-commands`); stop it with `powershell -File tools/stop_servers.ps1` before checks (check_all refuses to start if port 10101 is busy).
