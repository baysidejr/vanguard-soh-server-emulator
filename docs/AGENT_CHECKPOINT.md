# Agent Checkpoint

Recovery aid for the next session. Always re-check the real repository state (`git status`, `git log`) before relying on this.

- **Updated:** 2026-10-16
- **Branch:** `main` (tracks `origin/main`)
- **Latest commit at writing:** see `git log -1` (this checkpoint is committed with B-001)

## Last completed task
2026-10-17: owner decisions applied (B-017 default + create screen verified live, B-010 deferred, B-008 imported, B-007 17+1 kept / 294 disabled, B-009 merged twice: 0f14182, 6c9ee94); B-018 quest_check 99/99; B-020 chunk_audit moved 40 mislabelled archive NPCs (Tracker Nok was in the sea), checked live; B-021 "Leafsaw Crawlers" and "Report To Officer Yu" played end to end in the client. TESTING.md: create/delete/enter, /report, wounds, archive quest + delivery, !visit ticked.

## In progress / next action
- B-019 (Isle of Dawn has no quests): BLOCKED: OWNER DECISION, options in the backlog.
- Scraper: suspended per its own report ("blocked by policy"); merge again when the branch moves (B-009 cycle).
- Next unblocked: more TESTING.md hand-run items with the UI driver (scratch save, PC idle; recipe in memory harness-pitfalls); any defect found becomes a backlog item.
- Resume: `/ralph-loop:ralph-loop "Read VANGUARD_CLAUDE_CONTINUE.md. ..." --max-iterations 100`, or read this file.

## Uncommitted files
- `server/.claude/ralph-loop.local.md`: the loop tool's state file (not ours to commit).
- `AGENT_MISSION.md`: user-provided, ignored by `.gitignore` (`/*`), intentionally not committed.

## Tests
- Passed (latest `check_all.py`, 2026-10-17): unit tests (294), content check, scenarios (26), load test, server-log scan, fuzzing; `--client` 7/7 earlier today.
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
