# Client requests the server does not handle yet

Every event id the client can send (the last `push imm` before a call to its send functions `FUN_004cfb00` / `FUN_004cfb50`) that the server code never mentions. Generated 2026-10-13 by a scan of VGClient.exe; 370 ids are sent in all. "Command" is the slash command whose handler (the client's command table: 24-byte rows `{handler, wstr name, ...}`) sends it; "Context" is the nearest UI strings before the call site, a hint only. Commands starting with `/.` and `/hideme`, `/chunk`, `/gotoplayer`, `/fly`, `/summonplayer`, `/summongroup`, `/debuggameplay`, `/attach` are GM tools.

The scan only sees ids pushed right before `FUN_004cfb00` / `FUN_004cfb50`. A second scan (2026-10-14, scratchpad scan409.py) took the id pushed before every call to `FUN_00409210` and added the rows for `/location`, `/copycharacter`, `/aggro`, `/invulnerability` and `/attach`; 0x10b, harvest reward records, is now handled. Some commands send through `FUN_00409210` instead (`/walk`, `/run`, `/cyclewieldpreference`, ...), so an in-game sweep of the slash commands (`sweep.sh`) finds more; the "Command" column for those was filled in from that sweep. Contexts are the nearest strings and can mislead (0x113 is `/hidehood`, not a lockout prompt).

Rows marked **Unreachable** were checked on 2026-10-14: the function around every call site has no caller, no jump to it and no pointer to it anywhere in VGClient.exe (or, for 0x18f and 0x1e7, every caller up the chain has none) (MSVC vtables and Unreal native tables would hold one), so the shipped client can't send them. They need no server code.

Many are GM or debug commands (chunk travel, set hour, character flags, "defensive target" commands). The rest are player features with no server side yet. When one is implemented, remove its row.

| Id | Command | Call sites | Context |
|---|---|---|---|
| `0xd` | `/chatconnect` | | no payload; reconnects the chat service (a separate SOE service in the original) |
| `0x10e` | `/location` | `0x5feded` | no payload; sent after the client prints the "Loc" line itself. A notice; no reply needed |
| `0x591` | `/copycharacter` | `0x61126c` | developer tool (copy a character); not a player feature |
| `0x772` | `/aggro` | `0x613b99` | GM tool (access level 8) |
| `0x776` | `/invulnerability` | `0x613ac9` | GM tool (access level 5) |
| `0x5aa` / `0x5ab` | `/attach` | `0x4691dc` `0x4692a5` | attachment tool (also UI cases); not a player feature |
| `0x17d` | `/fallthroughattacktoggle` | | no payload; a server-side combat option whose effect is not known |
| `0x104` | `/craftingselectstep` | `0x5b7dc6` `0x5b82d6` | no payload; sent whenever the crafting action-family list is shown (ui `crafting_select_action_family`). A notice; no reply needed (docs/CRAFTING.md) |
| `0x105` |  | `0x5b03eb` | no payload; the recipe type filter (ui `setup_cra_ref_select_type` / `setup_cra_fin_select_type`). A notice; no reply needed |
| `0x108` |  | `0x5aa9f4` | {i32 recipe id}: journal recipe info (ui 0xf7 / 0xf8, `journal_cra_*_select_recipe`). The client shows the recipe from its own data; not needed (docs/CRAFTING.md) |
| `0x120` |  | `0x451fc7` | {i32 bag item handle, i32 pending value}: an item dropped while the assembly manager (DAT_014639a8) is in cursor mode 1 (UI 0x8a, FUN_00693980). Purpose unclear (docs/ASSEMBLY.md) |
| `0x126` | `/parleyassess` | `0x54ac25` | a debug request, only during a parley ("You can only request debug information during a parley session."); the answer format is not known |
| `0x127` |  | `0x4c0b55` `0x4c7985` | no payload; an ack the client sends after building an NPC dialog (and from `farewell_confirm_yes`). No reply needed (docs/MERCHANTS.md, QUESTS.md) |
| `0x128` |  | `0x54abfe` | **Unreachable:** nothing calls or points to the sending function. |
| `0x129` |  | `0x54cc16` | **Unreachable:** nothing calls or points to the sending function. |
| `0x137` |  | `0x5d5f0a` | TJTrackEntryChange / TravelJournalIsTracking. No payload; sent when travel-journal tracking changes. Tracking is client-only (docs/TRAVEL.md), so nothing to answer. |
| `0x167` |  | `0x4c47e6` | no payload: the NPC dialog option of type 11, "summon my corpse" (FUN_004c4640 case 11, docs/QUESTS.md). Only sent if an NPC's dialog offers that option, which is server content (no such NPC yet) |
| `0x17e` |  | `0x5d9145` | tutorial popup closed (ui `tutorial_done`). Tutorials are server content (docs/CONTENT_EDITOR.md); no reply needed |
| `0x17f` |  | `0x5d9155` | tutorial popup closed with "do not show again" (ui `tutorial_done`). Tutorials are server content |
| `0x183` |  | `0x68b207` | death-penalty tutorial closed (ui `death_penalty_tutorial_done`, docs/DEATH.md). Tutorials are server content |
| `0x189` |  | `0x4bfd97` | no payload; Done on the altar's corpse list (ui `corpse_list_done`, docs/DEATH.md). No reply needed |
| `0x18a` |  | `0x5de743` `0x5ef0f2` | no payload: getting up from feign death. While dead-feigning (pawn +0x3e9, with +0x3e8 set), moving or /sit sets +0x3eb (FUN_009db5a0, FUN_005fdfb0) and the effects tick (FUN_005eef50) clears it and sends 0x18a. Notices 93 "You may not do that while feigned." and 334 "You must stand up to do this." belong to it. No feign-death ability exists here yet (content), so it is ignored quietly |
| `0x18f` |  | `0x4439b6` | **Unreachable:** the sender's only caller chain (FUN_004439f0 <- FUN_00445610) ends in a function nothing calls or points to. |
| `0x1e7` |  | `0x4d1b9b` | **Unreachable:** sent (no payload, only when grouped) by FUN_004d1b90, whose only caller is a wrapper (FUN_005de750) nothing calls or points to. |
| `0x214` |  | `0x5de6e5` | **Unreachable:** nothing calls or points to the sending function. |
| `0x250` | `/psioniccancelconcentration` | `0x589f16` | {i32}: the psionic pool, which has no window in the shipped UI (docs/FORMS.md) |
| `0x27a` |  | `0x433a1e` | {u64 entity id}: the console command `active_ability_self_impact_on <hi> <lo>` (FUN_004107e6 area), run by animation notifies when an ability's impact frame lands. Seen 19 times in one fight (the target and the player). This server applies damage at use, so it is ignored quietly (`CLIENT_NOTICES`) |
| `0x280` |  | `0x432e9d` | **Unreachable:** nothing calls or points to the sending function. |
| `0x3a0` |  | `0x4a62c6` | {eid64, bool8 1}: the encounter display's entity no longer exists client-side (combat-group tick FUN_004b3bd0); the client clears the display itself (FUN_004acd90, the 0x3a2 handler). A notice; ignored quietly |
| `0x45f` |  | `0x47e69f` | **Dead path:** FUN_0047e600 sends it only when FUN_00483c90 gets 0, and its only caller passes 1 (docs/HOUSING.md) |
| `0x584` | `/.maxattributes` | `0x5fe35f` | Error: You must have a defensive target to use this command on. / Error: You must have a defensive target to use this command on. |
| `0x585` | `/.minattributes` | `0x5fe40f` | Error: You must have a defensive target to use this command on. / Error: You must have a defensive target to use this command on. |
| `0x586` | `/.summongear` | `0x614118` | Error: You must have a defensive target to use this command on. |
| `0x587` | `/.setuphotkeys` | `0x5fe4bf` | Error: You must have a defensive target to use this command on. / Error: You must have a defensive target to use this command on. |
| `0x588` | `/.classflag` | `0x6142a5` | Error: You must have a defensive target to use this command on. / Error: You must have a defensive target to use this command on. |
| `0x5b1` | `/.g1` `/.g2` | `0x5fee93` `0x5fef43` | %.0f / ssssiis |
| `0x5d9` |  | `0x69ac74` | {i32 selected lockout, i32 handle of the template 1454021 item}: clear a raid lockout with the service item (ui `clear_selected_lockout_timer`). This server has no raid lockouts (docs/INVENTORY.md) |
| `0x5e5` (see Raid lockout list) |  | `0x4fc100` | Could not find that item to unlock. / Programmer error: no unlock item for handle |
| `0x764` |  | `0x503e6e` | **Unreachable:** nothing calls or points to the sending function. |
| `0x765` |  | `0x4f972e` | Programmer error: no item matching valid handle / Cannot store a container inside another container. **Unreachable:** nothing calls or points to the sending function. |
| `0x766` |  | `0x429884` | NoSkillsOrSpells / SkillsAndSpellsHeader **Unreachable:** nothing calls or points to the sending function. |
| `0x767` |  | `0x429954` | **Unreachable:** nothing calls or points to the sending function. |
| `0x768` |  | `0x61c5be` | Character flags cleared. **Unreachable:** nothing calls or points to the sending function. |
| `0x7ae` |  | `0x5ab55e` | Unknown crafting recipe. **Unreachable:** nothing calls or points to the sending function. |
| `0x7af` |  | `0x5ab61e` | Unknown crafting recipe. **Unreachable:** nothing calls or points to the sending function. |
| `0x7b0` |  | `0x457eae` | ----- Learned Assembly Recipes ----- / You don't know any assembly recipes. **Unreachable:** nothing calls or points to the sending function. |
| `0x7b1` |  | `0x457f6e` | **Unreachable:** nothing calls or points to the sending function. |
| `0x7b6` |  | `0x41c235` | **Unreachable:** nothing calls or points to the sending function. |
| `0x7b7` |  | `0x4c09db` | **Unreachable:** nothing calls or points to the sending function. |
| `0x7c0` |  | `0x5059c0` | none / Invalid resource grade. **Unreachable:** nothing calls or points to the sending function. |
| `0x7c4` | `/fly` | `0x613968` | Setting the hour to %d. |
| `0x7ce` | `/debuggameplay` | `0x60b0ce` | zones / Invalid option. |
| `0x7e9` | `/attach` | `0x608b0a` |  |
| `0x7ec` |  | `0x479dae` | _chest_permission_edit / _chest_guild_rank_select_list **Unreachable:** nothing calls or points to the sending function. |
| `0x7ed` |  | `0x48230b` | **Unreachable:** nothing calls or points to the sending function. |
| `0x81f` |  | `0x4ba7ac` | No available work orders. / ----- Available work orders ----- **Unreachable:** nothing calls or points to the sending function. |
| `0x82c` |  | `0x624a51` | the client's answer to a server query handled in FUN_00622350: it sends the pawn's location values and a byte. Only sent when the server asks, which this server never does |
| `0x82f` |  | `0x476404` | Avatar Inspect {objType, objId} (FUN_004763b0, same layout as 0x460). The housing click menu has the option (table 0x13e5f38, key 14) but no m_BuildingType offers it (docs/HOUSING.md). |

## Appearance and movement (verified live 2026-10-14)

- `/hidehood` 0x113, `/hidehelm` 0x114, `/hidecloak` 0x59e `{u8 hidden}`: the client hides the piece on its own pawn first (pawn +0x3a8 / +0x3a9 / +0x3aa), then tells the server. The server saves them (characters.json `pawn_prefs`) and replicates `m_bHideHood` / `m_bHideHelm` / `m_bHideCloak` to everyone in the chunk; they are part of the pawn's properties at login (checked in client memory after a relog).
- `/setwearpreference <sphere>` 0x110 `{i32}`: 0 Adventuring, 1 Crafting, 2 Diplomacy, 3 Harvesting (FUN_00608d40, any other word prints "Invalid sphere"). `/setwieldpreference <n>` 0x111 `{i32}`: the typed number clamped to 0-3 (FUN_00608f10; words give 0). Saved and replicated as `m_WearPreference` / `m_WieldPreference`. Seen live (2026-10-14): `m_WieldPreference` 0 sheathes every weapon and 3 draws the ranged weapon (a Ranger's bow moves from the back to the hand); 2 put something small in the right hand; 1 and 2 are presumably the melee settings (the test sword's mesh did not draw). `/cyclewieldpreference`, the Z key, sends 0x112 (no payload); the server steps the value 0 -> 1 -> 2 -> 3 -> 0 (verified live).
- `/walk`, `/run` 0x72 `{u8 1 walk, 2 run}` (FUN_005fccf0): the client changes its own pawn only when the send fails (FUN_00b73620 -> FUN_00bb5ae0 sets GroundSpeed from the race table: walk 185, run 555). With a server it waits, and replicated `bIsWalking` alone did not slow it (live: same distance in 2 s). The server sends GroundSpeed 185 for walking and the normal 337.889 for running (pawn speed read live: 337.9 -> 185 -> 337.9; distance walked in 2 s 673 -> 374), `bIsWalking` for other clients, and MsgScore field 28 (character sheet "walking"/"running").
- `/cancelability` (also `/stopcasting`, `/cancelattack`, FUN_005fc8a0): FUN_005f3d00 first cancels what is running on the client and sends 0x25f while casting, else 0xe2 while a bar runs (+0xe0c/+0xe14), else 0xe1 after clearing a queued ability (FUN_00428700); then it sends 0x144. None has a payload. The server drops its pending cast for any of them (it queues no abilities). Checked through the dispatcher with a cast in progress; not seen live (no hostile target with a cast-time ability on the hotbar in the test).
- `/lockoutdecline` 0x273 `{u8 0}` answers a prompt the server never sends yet. (`/callpcaccept` / `/callpcdecline` 0x271 now answer the server's summon offer 0x270; docs/TRAVEL.md.)
- `/toggleeppearancegear` 0x115 (no payload): the server flips a saved per-character flag and answers 0x116 `{bool8 shown}` (FUN_004f9ea0: inventory manager +0x6c0, then gamevars bAppGearVisible / bAppGearInvisible via FUN_004f7d60); resent at login when on. The request and the save were seen live; what the switch changes on screen was not identified (the server has no appearance-gear slots).
- `/cleartargets` 0x5e (no payload): the server forgets the offensive and defensive targets and answers 0x3e0 with none.

## Raid lockout list (verified live 2026-10-14)

`/lockouttimerlist [name]` sends 0x4fc `{wstr name}` (empty for yourself). The lockout dispatcher `FUN_00588c50` takes s2c ids 0x4f2-0x502 (id - 0x4f2 indexes a 17-entry jump table at 0x588d9c); 0x4fd `{wstr name}` (`FUN_00583b70`) prints "Displaying lockout timers for %s:" and lists the timers the client already holds. The server answers 0x4fd with the player's name; with no raid lockouts on this server the list is empty. The messages that add timers are not decoded yet. `/sharelockouttimer <id>` (0x4fb `{i32 id}`) gets notice 159 "Invalid lockout timer.", and `/lockoutaccept` / `/lockoutdecline` (0x273 `{u8 1/0}`) get notice 158 "No one is offering you a lockout timer." (ids seen live).

The unlock tool (template 1464362, 0x5e5 `{i32 target, i32 tool}`) has an answer, 0x5e6 `{i32 handle}`: "%s has been unlocked and can now be used without a Gold Membership." (FUN_00506d70). "Locked" means Gold-Membership-only, and this server has no membership tiers, so nothing is locked and the request stays unanswered.

## Deconstruction (2026-10-14)

The item menu's deconstruct actions (UI switch around 0x68e71e) send 0x58e / 0x58f `{i32 item handle}` (FUN_004fbc40 / FUN_004fbda0; the client itself refuses containers and unknown items). The answer 0x590 `{i32 handle, i32 code}` (FUN_00506ee0) prints "You are not high enough level to deconstruct %s." for code -2 and "%s can not be deconstructed." otherwise. What an item breaks down into was server data, so the server answers -1 for everything, matching the tooltips' "This item cannot be deconstructed." The answer was checked live with `!event 0x590 ea030000 ffffffff` ("Travel Rations can not be deconstructed."); the menu action itself wasn't clicked.

## Target marks (2026-10-14)

`/mark <STAR, FIST, DIAMOND, SPADE, COG, FIRE, TRIDENT, PLUS or CLEAR> [DEFENSIVE or OFFENSIVE]` (also the target menu's MOMark* entries; FUN_0060c150 -> FUN_004d5400) is sent only while grouped: 0x592 MsgTwoEntityIdsAndInt `{eid64 -1, eid64 target, i32 mark}` (seen live: `ff..ff, 0x1505300, 0` for STAR on a groupmate). The server sends the same 20 bytes back to every group member as **0x593** (FUN_004e1640, group dispatcher FUN_004e2910): the client finds the target's pawn and attaches the mark to it (FUN_004d0420; -1 removes it). The relay was seen live; the icon itself wasn't checked on screen (first-person camera).

## Rescue rope (verified live 2026-10-14, two clients)

`/rope` (FUN_0060d340) needs a **defensive** target (the name it checks is the client's defensive target; F1, clicking a player, or `/targetgroupmember`), prints "Attempting to throw %s a rope." and sends 0x190 with no payload. The server offers the rope to that player with 0x58a `{wstr thrower}` (FUN_005ed620): a "Help on the way!" popup, "Ranger would like to toss you a rope.", Accept / Decline. Accept (or `/ropeaccept`) sends 0x191 (no payload); the server moves the player beside the thrower and sends notice 465 "You grab the rope and are hauled to safety.", or 464 "No one is holding the other end of the rope." when there is no offer or the thrower left the chunk. Decline (`/ropedecline`) only closes the popup on the client. Notices 463 (rope cooldown) and 466 (can't see the other end) are not used: their conditions were server rules we don't know.

## Player reports (verified live 2026-10-14)

`/report <name>` sends 0x4ac `{i32 line count, wstr reported name, per line {wstr text, i32 channel, u16}}` with the recent chat lines (FUN_00601b90 -> FUN_0063d2c0; stale bytes follow the last line). The server saves it in `server/player_reports.json` (not committed) and answers notice 0x0e `{i16 149}` ("Player report submitted. Customer service will review the last 10 lines of chat..."); a second report within a minute gets 148 ("You must wait longer to submit another player report."), a malformed one 150. Codes are the client's notice switch FUN_0061d530 (code = jump-table entry + 1).

## Handled from static analysis only

- `0x18e` (claim window list request): answered with 0x5ed (clear) + 0x5f0 (end); the claim dispatcher FUN_004458f0 then prints "You don't qualify to claim any account rewards.". Not seen live: `/claim` itself talks to a separate SOE account-claim service (FUN_006f03d0, ClaimSystem.log), not the game server.

## GM commands

The server handles the client's `/chunk` (0x770 {i32 x, i32 y}; the client starts loading the chunk itself, FUN_00613440), `/gotoplayer` and `/summonplayer` (0x79d / 0x7c7 {wstr name}), `/summongroup` (0x7c6 {wstr name}: that player's whole group) and `/hideme` (0x76c {u8 1 on, 2 off, 3 toggle}), only when it runs with `--dev-commands`. Each command-table row has an access level in the high byte of its second field (`/chunk` 0x14, `/gotoplayer` 0x0a, `/summonplayer` 0x05, `/hideme` 0x01, `/fly` 0x19; ordinary commands 0), and the client offers a command only when that level is at most the player's (FUN_005feba0). The player's level is the last field of SetNameID (world event 10, record +0x248). Set `"access_level": 255` on a character in characters.json to make it a GM: the client's `/chunk -19 12` then works (verified live; the client sends the ordinary chunk change itself, so the server lands the player at the chunk centre when the jump isn't to a neighbouring chunk). The same actions work through dev chat commands, verified live with two clients: `!chunk x y` (a full chunk hand-off to the chunk centre), `!goto <name>`, `!summon <name>` (teleport beside them, or a chunk hand-off), `!hide` (the pawn's `m_bGMHide`: other players no longer see the body, but the name plate still shows).

GM test tools on the defensive target: `/.learnabilities` 0x582 {u64 target}, `/.maxskills` 0x583 {u64 target}, `/.setupall <level>` 0x589 {u64 target, i32 level} (FUN_005fe180 / FUN_005fe230 / FUN_006143c0). The server learns every class ability, raises every skill to the cap, and sets the level. The client only sends them with a defensive target (since player pawns carry EntityTypes 0x20, `/targetself` / F1 gives one). They were verified through the matching dev commands on yourself: `!setupall 20` (verified live: a Psionicist learned its abilities, skills went to 50 and the portrait shows 20), `!maxskills`, `!learnall`.
