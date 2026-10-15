# Alternate advancement (AA)

> **Verified live (2026-10-14):** with 12 points the "Alternate Advancement" window listed the server's General abilities (rank, cost, the Passive line, "Requirements: Level 10" / "Requires Hardiness rank 2"). Train → the client's confirm popup ("Are you sure you wish to train Hardiness up to Rank 1 at a cost of 1 AA Point?") → Yes sent **0x85a** `{i32 id}`; the server answered 0x860 and MsgScore: Available 12 → 10, Spent 2, Hardiness 2/5, "You have trained Hardiness to rank 2.", and Constitution 40 → 44 (Hit Points 354 → 374) on the character sheet.

**Opening the window:** the shipped UI has no button or default key for it. The client command `SGOUI toggle "Alternate Advancement"` (quotes needed; a keybinding alias in bin\User.ini) toggles it; for the test an alias was pointed at it temporarily.

**Server** (`server/aa.py`, `login_stub.handle_aa_event`, content `server/content/aa.json`):
- The lists go out at spawn (0x85d, one 0x85f per ability, 0x85e), because the client never asks for them; `/aalist` (0x85c) sends them again.
- Training (0x85a from the window, or `/aatrain <title>` 0x85b) is checked again on the server: rank below the maximum, adventuring level, 100 points spent per list index before Archetype / Class / Special (the client's own rule, inferred), prerequisites (`requires`), and points. Refusals are chat lines (the client has no AA error strings). A success sends 0x860, MsgScore (fields 25 available / 26 spent), the changed attributes, and 0x861 for abilities whose prerequisites flipped.
- Ranks add their `stats` per rank to the attributes (`zone.aa_bonus`, applied with the gear and race bonuses).
- AA experience (placeholder): from level 10, a quarter of every adventuring experience award; 1000 makes a point ("You have gained 1 alternate advancement point!"); MsgScore field 41 shows the bar.
- `/aaclear` (0x851, refund everything) and `/aaadd <n>` (0x852 `{eid64 defensive target, i32 n}`, grant points) are GM tools (dev commands or access level).
- Saved per character: `aa_ranks`, `aa_points`, `aa_spent`, `aa_xp`.

The client analysis below is by a research agent (static, addresses as evidence).


[O] means the claim was observed in the code (address given). [I] means it is inferred.
The AA manager singleton is `[0x1463990]` (it is ecx in every handler below). The player stats object is `[0x1463a58]`.

## 0. AA manager state (`[0x1463990]`)
| off | meaning | evidence |
|---|---|---|
| +0 | "batch loading" flag: set by 0x85d, cleared by 0x85e. While it is set, 0x85f does not insert rows into the UI | [O] 0x44ea24, 0x44e9e9, 0x44e138 |
| +1..+4 | per-list "scroll/refresh UI list" flags (General, Archetype, Class, Special) | [O] 0x44c3b1.., 0x44ce48.. |
| +5 | refresh the selected-ability panel on the next tick | [O] 0x44e9ec, 0x449efd, 0x44ce06 |
| +6 | recompute the Trainable flags on the next tick | [O] 0x44ad15, 0x44cdcf |
| +8 | f32 timer used to delay refiltering | [O] 0x44c6e8 |
| +0xc / +0x10 | cached AA points available / adventuring level (-1 after a clear) | [O] 0x44e9d7, 0x44cda8 |
| +0x14 | id of the selected ability (-1 = none) | [O] 0x44ba09, 0x44a9d6 |
| +0x18..+0x1c | filter flags: MaxedOut, Untrainable, Trainable, Passive, Activated | [O] 0x449e90, 0x44cf60.. |
| +0x20..+0x4c | sort type per tab: current, previous1, previous2 (saved to VGClient.ini [General] `Current/PreviousAA*TabSortingType`) | [O] 0x44e750 |
| +0x50/+0x60/+0x70/+0x80 | ability vectors for list 0 General, 1 Archetype, 2 Class, 3 Special | [O] 0x44e0f4..0x44e112. The names come from `_AA_general_list` etc. at 0x44ce65.. |

## 1. Server -> client (dispatcher FUN_0044ea00)
- [O] The dispatcher handles only 0x85d..0x861: `eax = id - 0x85d; cmp eax,4; ja -> return 0`, jump table at 0x44ea90 (0x44ea04). No other ids.

### 0x85d: no payload, "begin AA list / clear"
- [O] FUN_0044c6c0 does the following:
  - zeroes flags +0..+6 and the timer +8;
  - sets +0xc and +0x10 to -1;
  - empties all four ability vectors (FUN_0044bfb0 ×4);
  - tail-calls FUN_0044a850, which resets the UI game vars `AlternateAdvancementGeneralList`, `...ArchetypeList`, `...ClassList` and `...SpecialList` (FUN_006b4ac0).
- [O] The dispatcher then calls FUN_004494d0, which syncs the `_AAO_filter_*` checkboxes, and sets **+0 = 1** (batch mode).
- [O] FUN_0044c6c0 is also called from the global reset at 0x5e7b8a (zone change or logout).

### 0x85e: no payload, "end AA list"
- [O] FUN_0044e9c0:
  - FUN_0044e750 re-sorts each tab by its saved sort types and rebuilds each UI list (FUN_0044bd70 ×4);
  - caches points available (`[player+0x1e8]`) and level (`[player+0x284]`);
  - sets **+0 = 0** and **+5 = 1**.

### 0x85f MsgAlternateAdvancementAbilitiesAdd (deserializer 0x4493b0, handler FUN_0044dfc0)
Wire layout, in order. "msg off" is the offset in the message object; "ability off" is the offset in VGClientAlternateAdvancementAbility (0x78 bytes, ctor FUN_0044d4e0/0x44d160).
| # | type | msg off | ability off | meaning | UI game var (VGUIGameVarDataAlternateAdvancement, registered at 0x671760) |
|---|---|---|---|---|---|
| 0 | i32 | 0x14 | +0x04 | **ability id** (unique; train requests send only this) | `ID` [O 0x6717b1] |
| 1 | i32 | 0x18 | (none) | **list**: 0 General, 1 Archetype, 2 Class, 3 Special. Any other value: the ability is freed and dropped | [O 0x44e0ec-0x44e124] |
| 2 | wstr | 0x1c | +0x08 | **title / name** | `Title`, `ColoredTitle` [O 0x671520] |
| 3 | wstr | 0x38 | +0x24 | **description** | `Description` [O 0x671560] |
| 4 | i32 | 0x54 | +0x40 | **current rank** | `Rank` = "%d/%d" (cur/max) [O 0x671335] |
| 5 | i32 | 0x58 | +0x44 | **max rank** | MaxedOut when cur >= max [O 0x6714be] |
| 6 | i32 | 0x5c | +0x48 | **training cost** (AA points for the next rank) | `TrainingCost`: "%d", or "N/A" if < 0 [O 0x671375] |
| 7 | i32 | 0x60 | +0x4c | **minimum adventuring level** | `MinLevel`, `LevelString` = "Level %d" [O 0x67198a, 0x6713c5] |
| 8 | f32 | 0x64 | +0x50 | **refresh (recast) time**, in seconds [I unit] | `RefreshTime`. `TypeString` = "Activated" if <= 0, else "Activated - Refresh: %s" [O 0x67169d] |
| 9 | bool8 | 0x68 | +0x54 | **passive** | `Passive`. TypeString = "Passive" [O 0x671690] |
| 10 | wstr | 0x6c | +0x58 | **requirements text** | `RequirementsText` [O 0x6715a0] |
| 11 | bool8 | 0x88 | +0x74 | **server eligibility** (prerequisites met); gates Trainable | [O 0x449dd7] |

The readers are 0xcca810 i32, 0xcca950 wstr, **0xcca900 f32**, and **0xccaa90 bool8**. The f32 and bool8 readers are pinned down by the movss and byte copies at 0x44e0aa and 0x44e0b5 [O].
- [O] Computed fields:
  - +0x75 Trainable (`Trainable`);
  - +0x76 Visible after filters (`Visible`);
  - `Untrainable` and `MaxedOut` are gv+0x91 and gv+0x90 (0x6714b1).
- [O] The handler does **not** look for an existing id; it always appends (0x44df50). Resend full lists inside a 0x85d ... 0x85e bracket.
- [O] If not in batch mode, the row is inserted into the UI immediately (FUN_00449c00 at 0x44e147).

### 0x860 MsgFourInts {i32 abilityId, i32 list, i32 newRank, i32 newCost} (FUN_0044e880)
- [O] The ability is found by (list, id) with FUN_0044aa30 (0x44e8e0; arg1 = msg+0x18 is the list, arg2 = msg+0x14 is the id).
- [O] If rank or cost changed, it sets +0x40 = rank and +0x48 = cost, then calls FUN_0044e490(list, ab, 1). That function removes the row, reinserts it in sorted order, and keeps the selection.
- [O] It does not recompute Trainable. That happens only when the cached points or level change (tick at 0x44cd9e), or after 0x861.
- [I] This is the "train succeeded" or "rank up" update. Send MsgScore with the new points afterwards; that also triggers the Trainable recompute.

### 0x861 MsgTwoIntsAndBool {i32 abilityId, i32 list, bool8 eligible} (FUN_0044aca0)
- [O] Looks up the ability the same way as 0x860.
- [O] If the bool differs, sets ability +0x74 = bool and manager +6 = 1. On the next tick all Trainable flags are recomputed (0x44cdd3 -> FUN_0044ba30 ×4).
- [I] Use it to unlock or lock an ability when a prerequisite changes.

## 2. Client -> server
| id | trigger | payload | evidence |
|---|---|---|---|
| **0x85a** | **Train**: `_AA_train_button` (event `AA_train_selected_ability`, 0x6892a0) only toggles the `_AA_train_ability_confirm` window. Pressing `_AA_train_ability_confirm_yes` (event `AA_confirm_train_selected_ability`, 0x689300) calls FUN_0044a9b0 | `{i32 abilityId}` (selected id at mgr+0x14; MsgSingleInt-style class with vtable 0x1062b54 and writer 0x4200f0). Nothing is sent if the id is -1. **No list index is sent** | [O] 0x44a9d6-0x44a9fe |
| 0x85b | `/aatrain <text>` (handler 0x612250) | `{wstr}`: the argument, upper-cased by 0xcdacc0 (a-z -> A-Z). Class 0x4277e0; writer 0x4201f0 uses 0xcca950 | [O] 0x61231d, 0x5ebde9. [I] the text is an ability name |
| 0x852 | `/aaadd <amount>`, needs a defensive target ("You must select an amount..." / "...defensive target...") (0x612140) | `{eid64 target, i32 amount}`. Writer 0x4a20c0: eid64 at +0x18, i32 at +0x20 | [O] 0x612217, 0x5e2960. [I] GM grant of AA points |
| 0x851 | `/aaclear` (0x5fd0c0 -> 0x5de4a0) | none | [O]. [I] GM reset of AA |
| 0x85c | `/aalist` (0x5fd0b0 -> 0x5de490) | none | [O]. [I] the server should answer with 0x85d, 0x85f×N, 0x85e |

- Command table entries are at 0x13eea80.. (flags 0x13 for aatrain and aaadd; 0x1c13 for aalist and aaclear) [O]. The meaning of the flags is unknown.
- [O] **The client never requests the lists by itself.** 0x85c is pushed only by /aalist (xref search). Opening the window, `_AA_select`, sorting and filtering send nothing.
- [I] The server must push 0x85d / 0x85f… / 0x85e unsolicited, for example at login or zone-in. The global reset at 0x5e7b8a clears the lists on zone change.
- UI events that send nothing [O]:
  - `_AA_select` (0x689170 -> FUN_0044bb90 -> FUN_0044b8b0) sets `aaSelectedAbility`, `bAlternateAdvancementAbilitySelected` and `bAlternateAdvancementSelectedAbilityTrainable`.
  - `AA_list_sort` (0x689050; columns Title, Rank, TrainingCost) is local only.
  - `AAO_filter_option_changed` (0x688f30) writes `Filter*AlternateAdvancementAbilities` to VGClient.ini [General] and refilters.
  - `_AA_pagelist` tab change (0x689330 -> 0x44bbc0).
- Event-id table: 0x69f5bf.. (AAO_filter_option_changed, AA_list_sort, _AA_select=0xd8, AA_train_selected_ability=0xd9, AA_confirm_train_selected_ability) [O].

## 3. Opening the window and point totals
- Window `VGUIWindow name="Alternate Advancement"`, searchKey `_AA_window` (VGUIAlternateAdvancementWnd.xml:981) [O].
- No main-bar or other XML button opens it (grep of VGUIAssets) [O].
- [I] It can be opened with `/togglewindow` (0x610f70 looks a window up by name), or with a keybind or button added to the shell.
- Point totals come from MsgScore (0x3de) [O 0x5e861a-0x5e8757]:
  - field 25 -> player+0x1e8 (**AA points available**, `nAAPointsAvailableSelf`);
  - field 26 -> player+0x1e4 (**AA points spent**, `nAAPointsSpentSelf`);
  - field 41 -> `AAExpPctSelf` / `nAAExpPctSelf`;
  - field 8 -> player+0x284 (adventuring level).

## 4. Client-side checks and strings
- **Trainable** (FUN_00449d80, 0x449dc1) [O]:
  `Trainable = eligible(+0x74) && level(field 8) >= MinLevel && pointsAvailable(field 25) >= cost && rank < maxRank`.
  - The recompute for list N is skipped (the flag keeps its old value) when `N*100 > pointsSpent(field 26)`.
  - On 0x85f the check uses N = 0.
  - [I] Archetype, Class and Special appear meant to unlock at 100, 200 and 300 points spent.
  - Recompute triggers: 0x85f; the tick when points or level change (0x44cd9e); 0x861.
- [O] The Train button is enabled only by `enabledGameVar="bAlternateAdvancementSelectedAbilityTrainable"` (XML).
- [O] FUN_0044a9b0 itself only checks that an ability is selected. The server must re-validate everything.
- Confirm text (FUN_0044b020) [O 0x44b087]:
  - "Are you sure you wish to train <color=green>%s</color> up to <color=blue>Rank %d</color> at a cost of <color=red>%d AA Point(s)</color>?"
  - The arguments are (title, rank+1, cost); the singular form is used when cost == 1.
  - With no selection it shows "You have not selected an ability to train."
- [O] There are no AA error or result strings in the client. Results must come from the server as chat text.
- [O] Row color (`ColoredTitle`, 0x6712d0): maxed -> `[0x1924f30]`, trainable -> `[0x143d630]`, else `[0x143d620]`. The row has trainable, untrainable and maxed-out bead images.
- [O] Filters (0x449e90):
  - MaxedOut hides rows with rank >= max;
  - Untrainable hides rows that are !trainable && rank < max;
  - Trainable hides trainable rows;
  - Passive hides passive rows;
  - Activated hides non-passive rows.
