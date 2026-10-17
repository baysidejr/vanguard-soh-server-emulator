# Agent Checkpoint

Recovery aid for the next session. Always re-check the real repository state (`git status`, `git log`) before relying on this.

- **Updated:** 2026-10-16
- **Branch:** `main` (tracks `origin/main`)
- **Latest commit at writing:** see `git log -1` (this checkpoint is committed with B-001)

## Last completed task
Owner decisions 2026-10-17 applied (VANGUARD_CLAUDE_CONTINUE.md, gitignored): B-017 real starting areas by default (`--camp-start` override), B-010 deferred, B-008 23 camp-zone NPCs imported (11 heights flagged `_uncertain`), B-007 17+1 deliveries kept on title evidence / 294 disabled (reversible), B-009 scrape branch merged (0f14182) and promoted (77 quests with real objectives). B-018 quest_check: 99/99 offered quests finishable.

## In progress / next action
- B-019 (Isle of Dawn has no quests) is BLOCKED: OWNER DECISION; options in the backlog.
- Next unblocked: live look at the 11 `_uncertain` NPC heights (scratch save, PC idle); the client's own create screen with the default start (B-017 remainder); each session `git fetch` and repeat the B-009 merge cycle when the scrape branch moves.
- Resume: `/ralph-loop:ralph-loop "Read VANGUARD_CLAUDE_CONTINUE.md. ..." --max-iterations 100` or read this file.

## Uncommitted files
- `server/.claude/ralph-loop.local.md`: the loop tool's state file (not ours to commit).
- `AGENT_MISSION.md`: user-provided, ignored by `.gitignore` (`/*`), intentionally not committed.

## Tests
- Passed (latest `check_all.py`): unit tests (286), content check, scenarios (26), load test (steady p95 11.1 ms), server-log scan, fuzzing.
- `check_all.py --client` 7 of 7 on 2026-10-17 (smoke test with the game client).

## Blockers and user decisions
- B-007: keep or remove the 298 delivery placeholders.
- B-008: import archive NPCs into Sundering Wastelands / Wildgrowth Forest.
- B-009: merge newer scrape-branch commits (only on request); 31 new as of 2026-10-16 evening.
- B-010: gate parleys on presence with placeholder gain rates, or keep them open.
- Owner decisions 2026-10-17 (VANGUARD_CLAUDE_CONTINUE.md, gitignored): B-017 yes (done: default, `--camp-start` override), B-007 C, B-008 yes, B-009 selective merges, B-010 A (deferred).

## Data-integrity notes
- Never run tests on `server/vanguard.db`; use `--data-dir` with `storage.scratch_copy`.
- A server started by `run_test.sh` may still be running on the real data (`login_stub.py --dev-commands`); stop it with `powershell -File tools/stop_servers.ps1` before checks (check_all refuses to start if port 10101 is busy).
