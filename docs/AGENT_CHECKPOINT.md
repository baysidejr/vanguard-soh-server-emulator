# Agent Checkpoint

Recovery aid for the next session. Always re-check the real repository state (`git status`, `git log`) before relying on this.

- **Updated:** 2026-10-16
- **Branch:** `main` (tracks `origin/main`)
- **Latest commit at writing:** see `git log -1` (this checkpoint is committed with B-001)

## Last completed task
**B-005 (a): "second login" scenario** (tools/scenarios.py): a second connection for an online character terminates the first; the new one plays. Passed on a scratch copy with all other scenarios (0 failed); real DB fingerprint `e53c48100b5e8a63` unchanged.
Also fixed: B-013, the editor's quest form could drop turn_in when used before its NPC lists loaded (the intermittent test_forms_round_trip failure); full suite 3/3 OK after the fix.
Earlier this session: B-001 (checks on a scratch DB copy, verified), B-002 (flight landing gap: root cause documented, no code change).

## In progress / next action
B-005 (a) second login and (b) reconnect after a drop are done and pass. **Next: B-005 (c)** chunk change and return: teach `tools/loadtest.py` Bot to follow world event 8 (connect to zone) with a new zone login on the same session, then add a scenario that crosses into Khal by riftway and back.

## Uncommitted files
- `server/.claude/ralph-loop.local.md`: the loop tool's state file (not ours to commit).
- `AGENT_MISSION.md`: user-provided, ignored by `.gitignore` (`/*`), intentionally not committed.

## Tests
- Passed: unit tests (278), content check, scenarios, load test, server-log scan, fuzzing.
- Not run: `check_all.py --client` smoke test, because the game client cannot take keyboard focus (B-003).

## Blockers and user decisions
- B-003: GameInput service window holds the foreground (user: click into the game, restart "GameInput Service", or reboot).
- B-007: keep or remove the 298 delivery placeholders.
- B-008: import archive NPCs into Sundering Wastelands / Wildgrowth Forest.
- B-009: merge newer scrape-branch commits (only on request).

## Data-integrity notes
- Never run tests on `server/vanguard.db`; use `--data-dir` with `storage.scratch_copy`.
- A server started by `run_test.sh` may still be running on the real data (`login_stub.py --dev-commands`); stop it with `kill_all.ps1` before checks (check_all refuses to start if port 10101 is busy).
