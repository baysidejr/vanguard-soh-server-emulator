# Resume here

Written 2026-10-17 (late) when the owner paused the session to reboot / switch PCs. Everything
below is committed and pushed to `main` on GitHub (baysidejr/vanguard-soh-server-emulator).

## How to resume (any PC)

1. `git clone https://github.com/baysidejr/vanguard-soh-server-emulator` (or `git pull` in an existing
   checkout). The game client files are not in Git: copy the client install around the repo as before
   (`bin/`, `Assets/`, `UnrealScript/`, `VGUIAssets/` ...). `server/vanguard.db` (accounts, characters)
   is not in Git either: copy it from the old PC if you want your characters.
2. Start Claude Code in the repo folder and say: **"Read docs/RESUME.md and continue."**
   To run it as a loop: `/ralph-loop:ralph-loop "Read docs/RESUME.md and VANGUARD_CLAUDE_CONTINUE.md if present. Follow the owner decisions. Continue autonomous development across the unfinished backend. Implement, test, commit, push, proceed to the next unblocked task. Never invent authentic Vanguard data." --max-iterations 100`
3. Then read, in order: `docs/AGENT_CHECKPOINT.md`, `docs/MASTER_BACKLOG.md` (B-001 ... B-028), `docs/STATUS.md`, `PROGRESS.md`.

## Owner decisions in force (2026-10-17)

`VANGUARD_CLAUDE_CONTINUE.md` holds them but is gitignored (not on GitHub), so here they are:

- **B-017 starting areas: YES.** New characters start where the create screen asks (Isle of Dawn, or the race's home town). `--camp-start` keeps the old camp for testing. Done.
- **B-007 delivery placeholders: C.** Keep only deliveries with evidence (title), switch the rest off reversibly. Done (18 kept, 294 disabled).
- **B-008 camp-zone NPCs: YES.** Imported. Done.
- **B-009 scrape branch: review and merge verified, non-destructive work regularly.** Merged five times today (latest 7697232). Repeat the cycle: `git fetch`, review paths/deletions/conflicts, run `crowdsourced/tests`, merge, `python tools/refresh_archive.py` (report) then `--apply`, review the diff.
- **B-010 parley presence: A.** Unrestricted until evidence. Deferred.
- Standing rules: never invent original game data; test on scratch copies, never the real `server/vanguard.db`; commit and push verified work; keep going after each task; only stop for true owner decisions (record them as `BLOCKED: OWNER DECISION`).

## Resumed on a new PC (2026-10-19)

- Tools set up: Ghidra 12.1.4 (`C:\tools\ghidra`), JDK 21, the ReVa extension and headless MCP server (`ReVa`, user scope), a persistent Ghidra project of the client at `C:\dev\vanguard\ghidra_projects\VGClient`, capstone, the `ralph-loop` plugin. Client files sit at the repo root; `bin/loginserver.txt` is 127.0.0.1; the client hash matches PROTOCOL.md.
- `check_all.py` 6/6 and the client smoke test PASS on 2026-10-19 (the real save, 8 characters, fingerprint unchanged). Step 1 below is done.
- B-009 cycle done 2026-10-19 (merge ac58915, review data only; refresh --apply changed nothing). The owner merged PR #1 on 2026-10-20 (499 scrape commits, d23e75d2); rebased, refresh --apply again changed nothing.
- 2026-10-20: hand-run items ticked with the UI driver (TESTING.md): Ctrl+click split, Small Pouch, Salvage Kit, jewelry/ore tooltips, Brass Spyglass, banking coins, all five service items. Found and fixed B-029 (the client's camera fade oscillates; the server now pins the view). Remaining single-player items: market Place Item For Sale (scripted click limit), forge smelting steps, the horse inside a house, and the combat/quest/diplomacy lines in TESTING.md.
- 2026-10-20 (later): the owner merged PR #2 (647619dd, the scrape's first new raw batch: 127 records). B-009 cycle done: rebased, crowdsourced tests 335 OK (run them from inside `crowdsourced/`; needs `beautifulsoup4`), `refresh_archive.py --apply` added 4 templates, 6 spawns, 2 kill quests with placeholder camps and 1 disabled delivery (101 of 101 finishable). Reviewing the batch found B-030 (loot rows named from URL slugs, "Zelser s Hoop"): fixed in the importer, 131 existing rows renamed.
- 2026-10-20 (later still): no open PRs; merged the scrape branch's conversion handoff (c6e35da6, 3,400 candidates, see B-009). `refresh_archive.py` now has a "== handoff items ==" step that promotes only candidates the world already refers to (19 added); the 16 handoff quests are unfinishable collect quests and stay out.
- This PC: the owner set the user execution policy to RemoteSigned on 2026-10-20, so `powershell -File tools/stop_servers.ps1` works as written (the earlier `-ExecutionPolicy Bypass` workaround is no longer needed). If `Get-ExecutionPolicy` fails with "module could not be loaded" from a shell started inside PowerShell 7, that is PSModulePath pollution, not the policy: run it with `PSModulePath` set to only `C:\Windows\system32\WindowsPowerShell\v1.0\Modules`.

## Where exactly I stopped (2026-10-17)

- Last commit before this file: `954abb4` (scenario: a group survives a chunk change).
- I was running `python tools/check_all.py --client`: **6 of 7 passed** (unit 307, content, 26+ scenarios, load test p95 11.6 ms, server log, fuzzing). The **client smoke test FAILED** without any server error: the server log stops before the character's Play, i.e. the scripted Enter on character select never reached the client (most likely the PC was in use / focus was elsewhere). **First thing to do: run `python tools/check_all.py --client` again with the PC idle** and confirm 7/7 (it passed 7/7 earlier today).
- The real save database was unchanged throughout (row fingerprint 3947564754418667, 8 characters).

## Done today (all verified, details in docs/MASTER_BACKLOG.md)

- B-017 start areas (default, live-verified, create screen checked), B-007, B-008, B-009 (x5), B-010.
- B-018 `tools/quest_check.py` (99/99 offered quests finishable), B-020 `tools/chunk_audit.py` (40 NPCs in mislabelled chunks moved; Tracker Nok at the Tracker Camp), B-022 parsing-leftover NPC names removed, B-021 archive quests played end to end.
- Player-facing bugs found in the real client and fixed: **B-023** dead characters could act; **B-024** bags looked empty after every chunk change; **B-025** six items hidden with full bags; **B-026** riders/walkers lost their speed after a chunk change; **B-027** pets lost and minions stranded (also after logouts). B-028: buffs, quest progress and groups survive chunk changes (checked).
- `tools/client_ui.py` drives the real client on a scratch save (start, play, say, click, rclick, drag, key, type, shot, stop); many docs/TESTING.md hand-run items ticked with it.

## Next actions (unblocked)

1. Re-run `check_all.py --client` (see above).
2. Remaining docs/TESTING.md hand-run items: banking coins; market Place Item For Sale (scripted click doesn't open the confirmation; verified by hand on 2026-10-13); forge smelting steps; Ctrl+click split, Small Pouch; service items; Salvage Kit; Brass Spyglass; items needing a second player.
3. B-009 cycle when the scrape branch moves (it was 0 commits ahead at the last check).
4. Keep auditing state across chunk changes / relogs with `tools/client_ui.py` (live) and `tools/scenarios.py` (bots).

## Open owner decision

- **B-019:** the Isle of Dawn (default start) offers no quests (its 10 were evidence-less deliveries, switched off; the archive's 127 island quests record no objectives). Options: (a) wait for the scrape, (b) send "trial island" picks to the home town until then, (c) re-enable the 10 placeholders, marked.

## Practical notes

- Live client checks only when the PC is idle (they take the keyboard and mouse); always on a scratch copy (`tools/client_ui.py start` does that).
- From Git Bash, chat lines starting with `/` need `MSYS_NO_PATHCONV=1 python tools/client_ui.py say "/who"`.
- Stop stray servers with `powershell -File tools/stop_servers.ps1`.
- Commit gate: `(cd server && python -m unittest discover -p "test_*.py" 2>&1 | grep -qx OK && python content.py | grep -qx "content OK")`.
