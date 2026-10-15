# Death penalty: tombstones and experience debt

> **Verified live (2026-10-13):** killed by the Canyon Widow, Ranger gets "You have gained experience debt. Recover your tombstone to win some of it back." and the XP bar shows a red debt segment (MsgScore field 19). Release to Bind (0x542) respawns at camp and leaves a tombstone (race 587, EntityTypes 0x2|0x20, m_bIsDead 1, DrawScale 0.35) at the death spot, named "Ranger's corpse". It is saved per character and comes back after a server restart. Standing at it and pressing U (the pawn's ServerUse RPC) prints "You recover your tombstone and win back 50 experience." and removes it; the debt drops from 100 to 50. Experience earned while in debt pays half of it off.
>
> **Altars (verified live):** the Altar of Binding (race 586 Bindstone at DrawScale 0.3, EntityTypes 0x1000000|0x10) shows the client's tooltip "Right-click to interact with this altar.". Right-click sends 0x2b0 {eid64, bool8}; the server binds the player there ("You have set your bind location.", 0x40a code 0; release then returns to the bind point) and sends 0x2bc with the tombstone, which opens the client's "Your Remains" window ("Remains in the Sundering Wastes", "Summoned items will take a durability hit."). Summon sends 0x188 {corpse id}; the tombstone moves next to the altar ("Corpse moved." = 0x0e code 0x48). /bind (0x10d) works only within 800 units of an altar (0x40a 3 "You may not bind here.", 4 while dead). The bind point is saved per character (`bind`) and shown on the character sheet (MsgScore fields 0-2).
>
> **Resurrection (verified live, offered by a dev command):** `!rezme` sends 0x26e {"Veyla Brightsteel", "Rebirth I", 60}; the client opens its "Resurrection" dialog ("Veyla Brightsteel is trying to resurrect you with Rebirth I."). Accept sends 0xe0 {1}: the server closes the death popup (0x540 {0, 1}: the close must use the same popup kind that opened it), stands the player up at half health where they died, removes the tombstone and gives back half the debt ("You have been resurrected by Veyla Brightsteel and win back 75 experience."). Decline (0xe0 {0}) tells the caster 0x0e 0x9b; an answer after 60 seconds gets 0x9d ResurrectionTimerExpired. No class rez ability uses it yet.
>
> **Map marker (verified live):** after an 0x2ae category message, a 0x382 travel journal entry with type 1 and category -2 draws a tombstone icon on the minimap at the tombstone; 0x383 {id} removes it when the tombstone is recovered.
>
> **Clearing debt with an item (verified live 2026-10-13):** right-clicking an item whose template id is 1454022 (items.json `"template_id"`; placeholder name "Experience Debt Clearance", `!give` only) opens the client's "Clear Experience Debt" dialog. Submit sends **0x5da {i32 item handle}**; the server answers **0x5db {i32 code}** (zone dispatcher FUN_00622350, jump-table index 17): **0x16** done, and the client shows its own "Experience Debt Cleared" window and "Your experience debt has been successfully cleared."; **0x17** "You are not allowed to clear your exp debt."; **0x18** "You have no experience debt. Press Cancel."; **0x19** "You may not clear your experience debt while you have corpses." (seen live with a tombstone out). On 0x16 the server zeroes the debt, uses up the item and resends MsgScore.
>
> **Not verified:** /targetmynearestcorpse (0x3d7 did not reach the server when typed; maybe it is sent only with a corpse in range).

Server: `login_stub.player_death`, `place_tombstone`, `use_tombstone`, `recover_tombstone`; `zone.tombstone_spawn`. Dev command: `!tombstone` (leave one at your feet).

## Server behaviour

- Each death adds 100 experience debt (`DEBT_PER_DEATH`, capped at 500; a level is 1000). Half of all experience earned pays debt instead.
- Release (0x541, 0x542 or 0x543) places the tombstone where the player died and replaces an older one.
- U at your tombstone (the target, or your own within 600 units) recovers it and returns half of the debt.
- The release popup's bool chooses the popup: 0 = one Release button (0x541), 1 = "Release to Bind" (0x542) and "Release to Altar" (0x543).

The rest of this file is the client analysis (static, by a research agent).


[O] = read in code (address given). [I] = inferred. Wire types follow docs/ZONE_MESSAGES.md.
Client->server events go through FUN_004cfb00(id,msg) / FUN_004cfb50(id) (zone connection, type 2) unless noted.

## 0. What the server already does, and a correction

- Death: `Health=0`, `m_bIsDead=1`, `0x2e` anim 1, and `0x540` MsgIntAndBool {i32 seconds, bool8}. Release: client `0x542` -> teleport to `spawned_at`, `0x540 {0,0}` closes it.
- **Correction [O] (FUN_005e70b0):** the bool in `0x540` is not "show". It chooses which popup opens:
  - `0` -> `_death_release_popup` / gamevar `DeathReleasePopup`. The button is `_death_release_spirit` (UI cmd 0x1fb, FUN_0068bb20) and sends **`0x541`** (no payload).
  - `1` -> `_pvp_option_death_release_popup` / `PVPDeathReleasePopup`. The buttons are `_pvp_death_release_spirit_to_bind` (0x1fc, FUN_0068bba0) which sends **`0x542`**, and `_pvp_death_release_spirit_to_altar` (0x1fd, FUN_0068bc20) which sends **`0x543`**.
  - `seconds <= 0` sets that popup's gamevar to 0, which closes it. `seconds > 0` opens it and prints "Your spirit will release in %d %s.".
  - The server sends `death_popup(300)` with bool 1, so today it opens the PvP-style popup with Bind and Altar buttons. That is why release arrived as 0x542. **The server should accept 0x541, 0x542 and 0x543**, and use 0x543 (release to altar) for the tombstone flow. To close the popup, send `0x540 {0, same bool}`. The client button also clears its own gamevar.
- **ZONE_MESSAGES fix [O]:** `0x57d/0x57e/0x57f/0x580` are not about corpses or consent. Each has no payload and acts on the local pawn `+0x3c0`:
  - `0x57d` sets bit 2 and `0x57e` clears it. Bit 2 is `bCanLevitate`. `0x57e` also calls vfunc+0x178(2,...).
  - `0x57f` sets bit 1 and `0x580` clears it. Bit 1 is `bCanFeatherFall`.

## 1. Server -> client messages

| what | event | layout | handler | notes |
|---|---|---|---|---|
| Corpse list (altar summon list) | **0x2bc** | `i32 count`, then count x MsgStringAndTwoInts `{wstr location, i32 corpseId, i32 unk}` | FUN_004c04b0 (registrar FUN_004c0740) | [O] It clears the list (FUN_004beca0/FUN_004bfc00). For each record it prints chat line type 0x39 "CorpseId: <id> Location: <str>" and stores {id, unk, str} (FUN_004c0440). It then sets gamevar **CorpseListPresent = 1**, which is what shows the `_corpse_list` window [I: XML binding]. The second i32 is stored but not displayed (it could be zone id or decay time) [I]. count 0 does nothing. |
| Tombstone map marker | **0x382** MsgSingleTravelJournalEntryToClient | `i32 id, i32 b, f32 x, f32 y, f32 z, wstr name, i32 chunkX, i32 chunkY, i32 c, u8 type, wstr desc, i32 categoryId, bool8 flag, i32 d` | FUN_005d83a0 -> FUN_005d8300 | [O] **type 1 -> `_map_tombstone` icon** on the map and minimap (FUN_005335f0, at xyz in chunk (chunkX,chunkY)). Any other type gives a basic POI (FUN_00533900). type 0 also prints "The locations section of your Adventure Journal has changed." The entry is dropped unless `categoryId` exists (FUN_005d4df0). The built-in categories are **-3 All Locations, -2 Corpses, -4 Player Housing**. They are created by the first **0x2ae** {wstr name, i32 id, i32} (FUN_005d86d0), which also adds the named category. type 1 or flag=1 also calls FUN_005d5c90(id) (auto-select/track) [I]. |
| Bulk journal entries (login) | 0x381 | `i32 count` + count x the 0x382 record | FUN_005d8c60 | [O] Same as 0x382, without the chat line. |
| Remove journal entry / marker | **0x383** | `i32 id` | FUN_005d61f0 | [O] Removes the entry and its map markers (FUN_0052e350/e440/e270). Use it when the corpse is recovered or decays. |
| Update entry | 0x2aa | same record | FUN_005d60d0 | [O] Updates the xyz, chunk and name of an existing id (for example after /corpsedrag or a summon). |
| Corpse decay time | **0x688** | `i32 seconds` | FUN_005e1e90 | [O] Prints the localized `CorpseDecayTimeSecond(s)` with the number. It is chat only and the client keeps no timer. |
| XP debt | **0x3de MsgScore field 19** (f32 0..1, fraction of the level) | | FUN_005e8260 | [O] `AdvExpDebtPctSelf` = bar of clamp01(field19 + field35). field35 is the current XP fraction. Field **20** = recovery fraction (`AdvExpRecoveryPctSelf` = field35 + field20). `bRestGTDebt` = field36 (rest) > field19. There is no absolute debt number; resend MsgScore whenever debt changes. |
| Debt notices | 0x0e | i16 `0x35` WipingDebtYou, `0x36` WipingDebtDef | FUN_0061d530 | [O] codes. The texts come from the localization table. |
| Clear-debt result | **0x5db** | `i32 result` | inline in FUN_00622350 | [O] 0x16 success: closes `_inventory_clear_exp_debt` and pops `CharacterExpDebtCleared` (FUN_006b8ec0(4)). 0x17 "You are not allowed to clear your exp debt." 0x18 "You have no experience debt. Press Cancel." 0x19 "You may not clear your experience debt while you have corpses." |
| Resurrection offer | **0x26e** MsgTwoStringsAndInt | `wstr rezzerName, wstr abilityName, i32 unk` | FUN_005eace0 | [O] Sets a pending flag (mgr+0x2c8). A second offer while one is pending gives "Error: resurrect message received while still pending a decision." It prints "%s is trying to resurrect you with %s." (chat type 0x20) and opens the **"Resurrection"** Accept/Decline dialog, whose buttons run `/rezaccept` and `/rezdecline`. The i32 is stored at mgr+0x304 and is not echoed back. Its meaning is unknown [I: timeout or rez id]. |
| Rez notices | 0x0e | `0x9a` NoOneIsResurrectingYou, `0x9b` ResurrectionDeclined, `0x9c` ResurrectionFailedIn3DS, `0x9d` ResurrectionTimerExpired | FUN_0061d530 | [O] |
| Corpse / altar notices | 0x0e | `299` CannotSummonCorpseYet, `300` NoCorpses, `0x12d` NoCorpsesReadyForSummon, `0x2d` YouHaveBeenSummoned, `0x47` CorpseLocSaveFail, `0x48` CorpseMoved, `0xab` CorpseLocDBSaveFailed, `0xf7` CorpseIsInvalid, `0x70` NotWhileDead, `0x82` CantBindInCombat, `0x8e` SetBindLocation, `0xe8` CantLootWhenDead | FUN_0061d530 | [O] |
| Bind result | **0x40a** | `u8` | FUN_005e1d90 | [O] 0 "You have set your bind location.", 1/2 set + IsDev notes, 3 "You may not bind here.", 4 "You may not bind while dead." |
| Corpse drag result | **0x5fa** | `u8` | FUN_006204a0 | [O] 1 CorpseDragSuccessDev, 2 FailConsent, 3 FailNoTarget, 4 FailZone, 5 FailInvalidTarget, 6 TooFarAway. |
| Consent | 0x55a/0x55b {wstr}, 0x55c/0x55d {wstr}, 0x55e | | already in ZONE_MESSAGES | ConsentAdded/Lost, EchoGave/Revoked, FailTimer (allow another player to drag your corpse). |
| Pending-death text | 0x193 / 0x194 | `eid64, wstr, i32` | FUN_00438f90 / FUN_00439050 | Names only (MsgClientMessagePendingDeath / MsgDisplayAlertPendingDeath). Not decoded further. |

There is no client code that parses an altar-specific window. An altar is a pawn with the `0x1000000` hover cursor (AltarHover, 0x4189b1); see section 2.

## 2. Client -> server events

| trigger | event | payload | code |
|---|---|---|---|
| `/rezaccept` (also the dialog's Accept button) | **0xe0** | MsgSingleByte `u8 1` | 0x5fd050 -> FUN_005e27b0. Clears the pending flag and closes "Resurrection" [O] |
| `/rezdecline` / Decline | **0xe0** | `u8 0` | 0x5fd060 -> FUN_005e2850 [O] |
| `/targetnearestpccorpse` | **0x3d6** | none | 0x5fc770 [O] |
| `/targetmynearestcorpse` | **0x3d7** | none | 0x5fc780 [O]. The server picks the corpse and sets the target [I: confirm with 0x3e0] |
| `/targetnextcorpse` | none (client side) | | 0x5fc800 -> FUN_004cff60(2,0,1,0) cycles nearby pawns locally, then the normal target event 0x5d [I] |
| `/corpsedrag`, `/tombstonedrag` | **0x17a** | none (uses the current target) | 0x5fcea0 (both names share the handler) [O]. Reply 0x5fa |
| `/consent <name>` | **0x17b** | `wstr name` | FUN_0060f180 [O] |
| `/releasecorpse` | **0xbe** | none | 0x5fc190 -> FUN_00521100 [O]. This is the **loot** "stop looting / release the corpse lock", the same as closing the loot window. It prints "You aren't looting anything." if no loot is open. It is not a death command. |
| `/bind` | **0x10d** | none | 0x5fcdd0 [O]. Reply 0x40a |
| `/gotocorpse <name> [n]` (CSR, access 2067) | **0x7d7** on the **world-server** connection | MsgStringAndInt-like `{wstr name, i32 index or -1}` (ctor FUN_0041a670) | FUN_00613dd0 -> FUN_00409350 -> [net+0xa0cc]+0xa4 -> FUN_006ee620. This is a type-2 frame on the world/chat connection, not the zone one [O] |
| `/corpselist <name>` (CSR, access 276) | **0x7da** on the world-server connection | `{wstr name}` (ctor FUN_004277e0) | FUN_00613f50 [O] |
| Altar / any "other" pawn interact (U / click) | **0x2b0** | MsgEntityIDAndBool `{eid64 target, bool8 0}` | FUN_00417da0. For EntityTypes bits outside 2/0x8000/0x800/4/0x800000/0x20000/0x20, which includes **altar 0x1000000**, the client sends 0x2b0 (the same event as hail/NPC talk) [O] |
| Corpse-list window: Summon | **0x188** | MsgSingleInt `i32 corpseId` | UI cmd `corpse_summon` 0xd3 -> FUN_00688eb0 -> FUN_004bf220. The id must be one received in 0x2bc, otherwise "Invalid corpse!" [O] |
| Corpse-list window: Done | **0x189** | none | UI cmd `corpse_list_done` 0xd2 -> FUN_004bfd60. Also clears the list and sets CorpseListPresent=0 [O] |
| Release (normal popup) | **0x541** | none | FUN_0068bb20 [O] |
| Release to bind / to altar (PvP-option popup) | **0x542 / 0x543** | none | FUN_0068bba0 / FUN_0068bc20 [O] |
| Death-penalty tutorial "done" | **0x183** | none | UI cmd 0x12e -> FUN_0068b180. Sent when the `_death_penalty_tutorial_do_not_show_sel` checkbox read returns 0 [O]. Probably "don't show again" bookkeeping; the server can ignore it [I] |
| Clear XP debt: confirm OK | **0x5da** | MsgSingleInt `i32 itemHandle` | UI cmd `inventory_clear_exp_debt_ok` 0x263 -> FUN_0068eee0 [O]. This is an **item** flow. Using an inventory item whose template id is **1454022 (0x162fc6)** (item-id switch at 0x500045, case -> FUN_004f6ce0) opens `_inventory_clear_exp_debt` with "Are you sure you wish to clear all your experience debt?" and stores the item handle. OK sends 0x5da with that handle and shows "Submitting clear experience debt request..." Reply 0x5db. There is no altar-based debt clear in the client. |
| Loot own corpse | 0xbb `{u64 eid}` | | FUN_005203d0 (EntityTypes & 2) [O]. Existing loot path |

## 3. How the player's corpse should look

- The client has **no "my corpse" flag**. "Mine" is decided by the server, for example in 0x3d7, 0x188 and the 0x2bc list.
- Corpse-related client checks [O]:
  - **EntityTypes (+0xaf8) bit 0x2 = corpse.** It sets the CorpseHover gamevar and makes interact send loot (0xbb). The loot cursor shows if `m_bHasLoot` (+0x37c bit0), EntityTypes 0x800, **or `m_iRaceId == 0x24b (587)`** (0x4187bb).
  - **Race 587 = "Tombstone"** (static mesh `Ra8001_P1_C1_Tombstones_Tombstone003_Large01`, races_checked OK). It is the only hard-coded corpse race. Races 773-775 TombstoneThestranSm/Med/Lg are other tombstone meshes.
  - Name plate (0xbbabea): if `m_bIsDead` (+0x3e8) **and** EntityTypes & 0x20 (player), the name is drawn as **"%s's corpse"** with the pawn's name (+0x718).
- **Recommended corpse entity:** a separate SGONPCPawn (like the NPCs and resource nodes) with:
  - name = the player's name
  - `m_iRaceId = 587` (Tombstone)
  - `EntityTypes = 0x2 | 0x20`
  - `m_bIsDead = 1`
  - a fresh eid, at the death location

  It shows "Name's corpse" with a loot cursor, and U sends 0xbb, so the existing loot code can return the items. Alternative: use the player's own race and appearance with 0x2|0x20 for a body-style corpse (not verified live). The player's own pawn must get `m_bIsDead = 0` when they release, otherwise the player's name plate also reads "'s corpse".

## 4. Recommended server flow

1. **Die:** keep the current steps (Health 0, m_bIsDead 1, anim 0x2e).
   - Add XP debt to the player (for example a fraction of the level); MsgScore field 19 = debt fraction. Resend MsgScore.
   - Send `0x540 {seconds, 1}` to offer Release to Bind / Release to Altar, or `{seconds, 0}` for a single Release.
2. **Release (0x541/0x542/0x543):**
   - Spawn the tombstone pawn (section 3) at the death xyz and store `corpse{id, owner, zone, xyz, chunk, items, created, decay_at}`. Optionally move unequipped inventory onto it.
   - Close the popup with `0x540 {0, same bool}`.
   - Reset the player pawn (`m_bIsDead 0`, Health up) and teleport to the bind point (0x542 or 0x541) or the nearest altar (0x543).
   - Send `0x2ae {"Corpses"-or-any name, id, 0}` once per session to create the built-in categories. Then send `0x382` with `type=1`, `categoryId=-2`, `name="<Name>'s corpse"`, the tombstone xyz and chunk, and `id=corpse.id`, which puts a tombstone on the map.
   - Optionally send `0x688 {decay seconds}`.
3. **Run back:** /targetmynearestcorpse (0x3d7) targets the owner's nearest corpse.
   - U on the tombstone sends 0xbb: open the loot window (0x1ed/0x1e8/0x1f2/0x1ef). The take or Take All events return the items.
   - When it is empty or recovered: despawn the pawn, send `0x383 {id}`, reduce the debt (for example restore part of it via field 20 "recovery"), and resend MsgScore.
4. **Altar summon:** the altar is a pawn with EntityTypes 0x1000000 (|0x10 for a nameplate). Interacting sends `0x2b0 {altar eid, 0}`. Check range, then:
   - no corpses -> `0x0e 300` NoCorpses
   - too soon -> `0x0e 299` CannotSummonCorpseYet or `0x12d`
   - otherwise send `0x2bc {count, [location wstr, corpseId, 0]...}`, which opens the corpse list.

   On `0x188 {corpseId}`: move the corpse pawn next to the altar (despawn and spawn, or a position update). Update the marker with `0x2aa` or `0x382`, optionally send `0x0e 0x48` CorpseMoved, and apply any summon debt penalty. On `0x189` do nothing.
5. **Bind at altar:** `/bind` (0x10d) or an altar dialogue option -> set bind = position, reply `0x40a {0}` (3 = not here, 4 = while dead).
6. **Decay:** when `decay_at` passes, despawn the corpse and send `0x383 {id}`. Debt can stay.
7. **Resurrection:** when a caster uses a rez ability on a dead or released player's corpse, send that player `0x26e {casterName, abilityName, i32 seconds}`.
   - `0xe0 {1}` -> teleport to the corpse, restore partial HP, refund part of the debt, remove the corpse and marker.
   - `0xe0 {0}` -> tell the caster `0x0e 0x9b` ResurrectionDeclined.
   - On timeout -> `0x0e 0x9d` ResurrectionTimerExpired.
   - If 0xe0 arrives with nothing pending -> `0x0e 0x9a`.
8. **Clear-debt item (optional):** handle `0x5da {itemHandle}` for template 1454022: no debt -> 0x5db {0x18}; has corpses -> {0x19}; otherwise set debt to 0, consume the item, resend MsgScore, then {0x16}.
9. **Corpse drag:** `/consent` 0x17b {name} (reply 0x55c to the giver, 0x55a to the receiver). `0x17a` drags the target corpse if the owner gave consent and it is in range, by moving the corpse to the dragger. The reply is 0x5fa {u8}.

## Server-only data gaps (for CONTENT_EDITOR.md)
- Debt amount per death and per level, the debt recovery fraction, the summon cooldown and debt penalty, corpse decay time, and release-timer length.
- Altar placements: race model (altar meshes such as PantheonAltar01 / KaerellunAltar* / DarkElfAltar exist in the race strings; the ids are not looked up yet), plus the bind-allowed flag.
- Which items go on the tombstone (none, inventory, or coin).
- The meaning of 0x26e's i32 and of 0x2bc's second i32.

## Consent and corpse drag (verified live 2026-10-13, two clients)

- `/consent <name>` sends **0x17b** `{wstr name}`; the server answers 0x55c `{wstr name}` to the giver ("You have given Justins consent to drag your corpses.") and 0x55a `{wstr giver}` to the other player ("You have been given consent to drag Ranger's corpses."). `/revoke <name>` sends **0x17c**; answers 0x55d / 0x55b (ConsentEchoRevoked / ConsentLost). Consent lasts for the session.
- `/corpsedrag` and `/tombstonedrag` send **0x17a** (no payload). The server moves the targeted tombstone (or your own) to your feet for everyone in the chunk if it is yours or its owner consented to you and it is within 1500 units ("You drag Ranger's tombstone."; the owner's map marker moves too). Failures are 0x5fa `{u8}`: 2 no consent, 3 no target ("You must first target a corpse that you wish to drag."), 4 zone, 5 invalid target, 6 too far (1 is a developer-only success line).
- `/decaytime` sends **0x3dd**; the answer is 0x688 `{i32 seconds}` ("The corpse will decay in 172789 seconds."). Tombstones last 48 hours (reported only; they don't decay yet).
- A group member's death sends 0x691 `{eid64}` to the rest of the group ("<name> died!!").

## Summoning your tombstone (verified live 2026-10-15)

An NPC with mobs.json `"corpse_summoner": true` (Veyla Brightsteel) adds the client's dialog option 0x2b9 while you have a tombstone: "I'd like to summon my earthly remains." Choosing it sends **0x167** (no payload); the tombstone moves to your feet ("Veyla Brightsteel summons your tombstone to you.", `login_stub.summon_corpse`). Free and in the same chunk; who offers it and what it costs is content.
