# Agent Checkpoint

**Paused 2026-10-17 (late) for a reboot / PC switch: start with docs/RESUME.md.**

Recovery aid for the next session. Always re-check the real repository state (`git status`, `git log`) before relying on this.

- **Updated:** 2026-10-19 (new PC: tools installed, 7/7 checks pass, B-009 merge ac58915; see docs/RESUME.md)
- **Branch:** `main` (tracks `origin/main`)
- **Latest commit at writing:** see `git log -1` (this checkpoint is committed with B-001)

## Last completed task
2026-10-17 (late): chunk hand-off audit in the real client: B-024 empty bags, B-026 riders/walkers lost their speed, B-027 pets lost and minions stranded (also after logouts) - all fixed and verified live; B-028 buff icons inconclusive. Also B-025 full bags, B-023 dead characters. Hand-run items ticked: Sprint/Recall/Recall to House, mining, conversion, mail, market window, bank deposit, escrow, equip, merchant. Scrape merged five times today (latest 7697232).

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
