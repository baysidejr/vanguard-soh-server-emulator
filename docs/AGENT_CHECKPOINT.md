# Agent Checkpoint

Recovery aid for the next session. Always re-check the real repository state (`git status`, `git log`) before relying on this.

- **Updated:** 2026-10-16
- **Branch:** `main` (tracks `origin/main`)
- **Latest commit at writing:** see `git log -1` (this checkpoint is committed with B-001)

## Last completed task
**B-001: automated checks no longer write the real save database.** `check_all.py` and `smoke_test.py` run on a read-only scratch copy (`storage.scratch_copy`); `scenarios.py --data-dir`.
Verification: `python tools/check_all.py` 6/6 twice; fingerprint of every row in `server/vanguard.db` identical before and after (`e53c48100b5e8a63`, 7 characters); scratch folders removed.

## In progress / next action
Next backlog item: **B-002** (flight landing where the terrain lookup has no height). Exact next step: sample `terrain.Terrain("Assets/Maps/chunk_n19_12.vgr").height` around (-12891, -4871) and its neighbours.

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
