# Client requests the server does not handle yet

Every event id the client can send (the last `push imm` before a call to its send functions `FUN_004cfb00` / `FUN_004cfb50`) that the server code never mentions. Generated 2026-10-13 by a scan of VGClient.exe; 370 ids are sent in all. "Command" is the slash command whose handler (the client's command table: 24-byte rows `{handler, wstr name, ...}`) sends it; "Context" is the nearest UI strings before the call site, a hint only. Commands starting with `/.` and `/hideme`, `/chunk`, `/gotoplayer`, `/fly`, `/summonplayer`, `/summongroup`, `/debuggameplay`, `/attach` are GM tools.

Many are GM or debug commands (chunk travel, set hour, character flags, "defensive target" commands). The rest are player features with no server side yet. When one is implemented, remove its row.

| Id | Command | Call sites | Context |
|---|---|---|---|
| `0x104` |  | `0x5b7dc6` `0x5b82d6` |  |
| `0x105` |  | `0x5b03eb` | type6 / type7 |
| `0x106` |  | `0x5b0405` | type6 / type7 |
| `0x107` |  | `0x5b05e5` | CraftingRecipeSelectDescription / CraftingRecipeSelectNumUses |
| `0x108` |  | `0x5aa9f4` | type6 / type7 |
| `0x110` | `/setwearpreference` | `0x608e81` | Harvesting / Diplomacy |
| `0x111` | `/setwieldpreference` | `0x608fc4` | Diplomacy / Invalid sphere: %s.  Please specify Adventuring, Crafting, Harvesting, or Diplomacy. |
| `0x113` |  | `0x5e2d7f` | Lockout Timer Confirmation |
| `0x114` |  | `0x5e2edf` |  |
| `0x117` |  | `0x5e2cc5` | Call Confirmation / Lockout Timer Confirmation |
| `0x120` |  | `0x451fc7` |  |
| `0x126` |  | `0x54ac25` | You can only request debug information during a parley session. |
| `0x127` |  | `0x4c0b55` `0x4c7985` | NPCDialogText |
| `0x128` |  | `0x54abfe` |  |
| `0x129` |  | `0x54cc16` |  |
| `0x12d` |  | `0x54cf16` | Error: That statement could not be found. |
| `0x137` |  | `0x5d5f0a` | TJTrackEntryChange / TravelJournalIsTracking |
| `0x138` |  | `0x5d3461` |  |
| `0x153` |  | `0x471da2` | You don't have that many items stacked there. / That item is not in your Chest. |
| `0x158` | `/itemlinkrequest` | `0x601594` | Pop: |
| `0x167` |  | `0x4c47e6` |  |
| `0x17e` |  | `0x5d9145` |  |
| `0x17f` |  | `0x5d9155` |  |
| `0x183` |  | `0x68b207` | _tutorial_do_not_show_sel / _death_penalty_tutorial_do_not_show_sel |
| `0x189` |  | `0x4bfd97` |  |
| `0x18a` |  | `0x5de743` `0x5ef0f2` |  |
| `0x18f` |  | `0x4439b6` | ClaimName / Some Claim |
| `0x191` | `/ropeaccept` | `0x5fc9a5` |  |
| `0x1e7` |  | `0x4d1b9b` | No more items to be randomed! / GroupRandomLootInvitationPopup |
| `0x214` |  | `0x5de6e5` |  |
| `0x24a` |  | `0x463dc2` `0x463e12` `0x463e68` |  |
| `0x250` |  | `0x589f16` |  |
| `0x271` |  | `0x5e2a53` `0x5e2ae3` | Resurrection |
| `0x273` |  | `0x5e2b76` `0x5ebf61` | Call Confirmation / Call Confirmation |
| `0x27a` |  | `0x433a1e` |  |
| `0x280` |  | `0x432e9d` |  |
| `0x35e` |  | `0x4cc6b0` |  |
| `0x3a0` |  | `0x4a62c6` |  |
| `0x45f` |  | `0x47e69f` |  |
| `0x463` |  | `0x47616d` |  |
| `0x465` |  | `0x476066` | bPlotIsHQ |
| `0x46d` |  | `0x47db00` | _building_guild_leader_headquarters_confirm / BuildingGuildLeaderHeadquartersConfirm |
| `0x474` |  | `0x476d2c` | BuildingGuildHeadquartersRelinquishConfirm |
| `0x47a` |  | `0x476668` `0x476a48` | PlotPurchaseConfirm / PlotRelinquishConfirm |
| `0x47c` |  | `0x47d8fd` `0x47da0d` | _building_guild_leader_headquarters_confirm / BuildingGuildLeaderHeadquartersConfirm |
| `0x4fb` | `/sharelockouttimer` | `0x60e73f` |  |
| `0x4fc` | `/lockouttimerlist` | `0x4ff2f9` `0x5ebf91` `0x60e664` | Choose a race and press submit. / _inventory_character_race_change_dropdown |
| `0x54d` |  | `0x682b45` |  |
| `0x584` | `/.maxattributes` | `0x5fe35f` | Error: You must have a defensive target to use this command on. / Error: You must have a defensive target to use this command on. |
| `0x585` | `/.minattributes` | `0x5fe40f` | Error: You must have a defensive target to use this command on. / Error: You must have a defensive target to use this command on. |
| `0x586` | `/.summongear` | `0x614118` | Error: You must have a defensive target to use this command on. |
| `0x587` | `/.setuphotkeys` | `0x5fe4bf` | Error: You must have a defensive target to use this command on. / Error: You must have a defensive target to use this command on. |
| `0x588` | `/.classflag` | `0x6142a5` | Error: You must have a defensive target to use this command on. / Error: You must have a defensive target to use this command on. |
| `0x58e` |  | `0x4fbd5f` | Programmer error: no deconstruct item for handle / You cannot deconstruct a container. |
| `0x58f` |  | `0x4fbebf` | Programmer error: no deconstruct item for handle / You cannot deconstruct a container. |
| `0x592` |  | `0x4d5476` | bShowLFGButton |
| `0x59e` |  | `0x5e2e2f` |  |
| `0x5a7` |  | `0x5e29db` | Resurrection / Resurrection |
| `0x5b1` | `/.g1` `/.g2` | `0x5fee93` `0x5fef43` | %.0f / ssssiis |
| `0x5c6` |  | `0x5ee89c` | Transfer Plot? / accept |
| `0x5ce` |  | `0x484abf` | BuildingNPCListSelection / PlacedBuildingNPCListSelection |
| `0x5cf` |  | `0x484b3e` | PlacedBuildingNPCListSelection |
| `0x5d0` |  | `0x484bbe` |  |
| `0x5d1` |  | `0x484343` | PlacedBuildingNPCList / _building_npc_window |
| `0x5d2` |  | `0x48434d` | PlacedBuildingNPCList / _building_npc_window |
| `0x5d9` |  | `0x69ac74` | _lockout_timer_list / RaidLockoutTimerList |
| `0x5e5` |  | `0x4fc100` | Could not find that item to unlock. / Programmer error: no unlock item for handle |
| `0x764` |  | `0x503e6e` |  |
| `0x765` |  | `0x4f972e` | Programmer error: no item matching valid handle / Cannot store a container inside another container. |
| `0x766` |  | `0x429884` | NoSkillsOrSpells / SkillsAndSpellsHeader |
| `0x767` |  | `0x429954` |  |
| `0x768` |  | `0x61c5be` | Character flags cleared. |
| `0x7ae` |  | `0x5ab55e` | Unknown crafting recipe. |
| `0x7af` |  | `0x5ab61e` | Unknown crafting recipe. |
| `0x7b0` |  | `0x457eae` | ----- Learned Assembly Recipes ----- / You don't know any assembly recipes. |
| `0x7b1` |  | `0x457f6e` |  |
| `0x7b6` |  | `0x41c235` |  |
| `0x7b7` |  | `0x4c09db` |  |
| `0x7c0` |  | `0x5059c0` | none / Invalid resource grade. |
| `0x7c4` | `/fly` | `0x613968` | Setting the hour to %d. |
| `0x7c6` | `/summongroup` | `0x613d85` |  |
| `0x7ce` | `/debuggameplay` | `0x60b0ce` | zones / Invalid option. |
| `0x7e9` | `/attach` | `0x608b0a` |  |
| `0x7ec` |  | `0x479dae` | _chest_permission_edit / _chest_guild_rank_select_list |
| `0x7ed` |  | `0x48230b` |  |
| `0x81f` |  | `0x4ba7ac` | No available work orders. / ----- Available work orders ----- |
| `0x82c` |  | `0x624a51` | Failed to save nicknames, make sure Nicknames.txt is not read-only. |
| `0x82f` |  | `0x476404` |  |
| `0x851` |  | `0x5de4a5` | nWoundsLeg / Your groupmate failed to call you because at least one of you is not in the right area. There are sp |
| `0x852` |  | `0x5e2965` | Resurrection / Resurrection |
| `0x85a` |  | `0x44a9fe` | AlternateAdvancementClassList / AlternateAdvancementSpecialList |
| `0x85b` |  | `0x5ebdee` | /lockoutaccept / Lockout Timer Confirmation |
| `0x85c` |  | `0x5de495` | nWoundsLeg / Your groupmate failed to call you because at least one of you is not in the right area. There are sp |

## Handled from static analysis only

- `0x18e` (claim window list request): answered with 0x5ed (clear) + 0x5f0 (end); the claim dispatcher FUN_004458f0 then prints "You don't qualify to claim any account rewards.". Not seen live: `/claim` itself talks to a separate SOE account-claim service (FUN_006f03d0, ClaimSystem.log), not the game server.

## GM commands

The server handles the client's `/chunk` (0x770 {i32 x, i32 y}; the client starts loading the chunk itself, FUN_00613440), `/gotoplayer` and `/summonplayer` (0x79d / 0x7c7 {wstr name}) and `/hideme` (0x76c {u8 1 on, 2 off, 3 toggle}), only when it runs with `--dev-commands`. Each command-table row has an access level in the high byte of its second field (`/chunk` 0x14, `/gotoplayer` 0x0a, `/summonplayer` 0x05, `/hideme` 0x01, `/fly` 0x19; ordinary commands 0), and the client offers a command only when that level is at most the player's (FUN_005feba0). The player's level is the last field of SetNameID (world event 10, record +0x248). Set `"access_level": 255` on a character in characters.json to make it a GM: the client's `/chunk -19 12` then works (verified live; the client sends the ordinary chunk change itself, so the server lands the player at the chunk centre when the jump isn't to a neighbouring chunk). The same actions work through dev chat commands, verified live with two clients: `!chunk x y` (a full chunk hand-off to the chunk centre), `!goto <name>`, `!summon <name>` (teleport beside them, or a chunk hand-off), `!hide` (the pawn's `m_bGMHide`: other players no longer see the body, but the name plate still shows).

GM test tools on the defensive target: `/.learnabilities` 0x582 {u64 target}, `/.maxskills` 0x583 {u64 target}, `/.setupall <level>` 0x589 {u64 target, i32 level} (FUN_005fe180 / FUN_005fe230 / FUN_006143c0). The server learns every class ability, raises every skill to the cap, and sets the level. The client only sends them with a defensive target, and `/targetself` (F1) gave none in our tests (probably something our own pawn lacks), so they are verified through the matching dev commands on yourself: `!setupall 20` (verified live: a Psionicist learned its abilities, skills went to 50 and the portrait shows 20), `!maxskills`, `!learnall`.
