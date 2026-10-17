# Quests: NPC dialogue, offer/accept, journal, counters, turn-in (VGClient.exe static analysis)

> **Multi-step quests (verified live 2026-10-12):** `quests.json` entries can have `steps`, done in order. Each step is one of three kinds:
> - `kill {mob: n}`
> - `collect {item: n}`: counted from the bags, and the items are handed over at turn-in
> - `talk <mob>`: done when the player opens that NPC's dialogue; the optional `say` text replaces its greeting
>
> Each step also has an `objective` line for the tracker. When a step is done, the server sends `0x2cc` with the next step's objective, and the tracker changes to that line.
>
> Other fields:
> - `requires`: quest keys that must be finished first.
> - `turn_in`: the NPC that takes the quest back (default: the giver).
> - `reward.items`: items given at turn-in.
>
> Accepting only works at the giver, and completing only at the turn-in NPC. "Supplies for the Forge" was played through: kill 2 wolves → gather 2 Copper Ore → talk to the Thestran Guard → turn in to Orin (coin, Round Shield, XP). The dev command `!give <item> [qty]` helps testing.
>
> **Reward choice (verified live 2026-10-13):** `reward.choice` in quests.json lists items to pick one from. At turn-in the server sends a 0x2c7 item record per reward item, then the state-4 page (0x2c0) with the reward slots filled ("Select Reward(s)"). Fixed `reward.items` get a group each; the choice items share group 100. Clicking an icon sends 0x163 {quest, item}; the server answers 0x2cf (highlight) and 0x2c8 (Complete button). Complete sends 0x161 {quest, item}. **The cache key is item field 1**, which the server normally fills with the item template id, so the 0x2c7 records must carry the reward slot id there; otherwise the client sends 0x162 and shows nothing. On 0x162 the server resends the records and the page once. `!questreset <key>` forgets a quest for testing.

> **Note (2026-10-16):** accepting an archive quest live (A Grave Brownie Threat) made the client log "Received unhandled message id 705" (0x2c1) in UnhandledMessagesClient.log, while the accept itself worked (journal entry from the 0x2cb sent first, "You agree to help ...", tracker row). The quest page is apparently gone by then; harmless, left as is.

> **Sharing (verified live with two clients 2026-10-13):** select the quest row in the journal (this sets mgr+0x200; with nothing selected Share and /sharequest send nothing), then Share sends 0x166. Each groupmate who can take the quest gets the offer page and "Ranger shares the quest Wanderer Trouble with you."; Accept works without the giver. Accept sends 0x2cb (journal entry, caches the template) **before** 0x2c1, then 0x55f closes the dialogue; with 0x2c1 first the client asked 0x164 and left the offer page open.

> **Dialogue reset:** each dialogue opens with `0x55f` (end conversation: closes the window and frees every option) and an empty `0x3ea` (clears the text), so text and options no longer pile up.

> **Verified live (2026-10-12):** Orin's dialogue (0x3ea greeting + 0x2bf option, type 7) → click (0x15c) → quest page 0x2c0 with objectives and coin reward → Accept (0x15d) → 0x2c1 + 0x2cb: quest tracker "[10] Wanderer Trouble – Defeat Robed Wanderers (1/3)" updates on kills (0x2cc); turning in via the "(complete)" option sends 0x2c5, coin and 0x3d5 XP. Active quests are resent at login (0x2cb). Implemented in `server/quest.py`, `login_stub.npc_dialog/handle_quest_event`; quests are data in `server/content/quests.json`.


Tags: [O] = read directly in decompiled code or assembly. [I] = inferred. All payloads are packed little-endian in field-registration order (see ZONE_MESSAGES.md). wstr = UTF-16LE text ending in 0x0000. "C->S" means the client sends it through FUN_004cfb00(id, msg); a C->S id with no payload uses FUN_004cfb50.

The quest UI is data-bound. The client stores a `VGClientQuest` object, and the XML reads it through named members: `VGUIAssets/Shells/Default/Windows/DialogComponents/DialogQuests.xml`, `VGUIQuests.xml` (the journal) and `VGUIQuestStatus.xml` (the tracker). The member getters are registered in FUN_0067da90 [O].

## 0. Quest manager handlers
- The S->C quest sub-dispatcher is **FUN_005a6770** [O]: 0x2a9, 0x2c0, 0x2c1, 0x2c3, 0x2c5, 0x2c6, 0x2c7, 0x2c8, 0x2c9, 0x2cb, 0x2cc, 0x2ce, 0x2cf, 0x2d0, 0x2d1, 0x4ad.
- The NPC dialogue sub-dispatcher is **FUN_004c9170** [O]: 0x2af, 0x2b1-0x2ba, 0x2bb, 0x2bf, 0x581.
- 0x3ea is handled inline in FUN_00622350.
- The client keeps two lists [O]:
  - a **template cache** at mgr+0x26c, searched by FUN_005928c0(questId) and filled **only by 0x2cb**;
  - the **journal** at mgr+0x22c, holding VGClientQuest objects of 0x180 bytes (FUN_0059f800).

## 1. NPC dialogue

### 1a. Conversation text: 0x3ea MsgNPCQuestText `{eid64 npc, wstr text}` [O]
- Layout comes from the registrar in FUN_00620970: eid64, then wstr [O].
- The handler (inline in FUN_00622350, case 0x3ea) does the following [O]:
  - FUN_004c40a0(0) opens the Dialogue window and sets DialogActive.
  - FUN_004c4960 sets `TalkingNPCName` from the entity.
  - The text is formatted (FUN_006c7ea0) and put in the `NPCDialogText` field (FUN_004c2900). If the result is empty, the field is cleared (FUN_004c0ad0).
- One message is enough to show "greeting text + NPC name". It can be combined with 0x2bf or 0x2af options.

### 1b. Clickable options
**0x2bf** MsgEntityIDAndInt `{eid64 npc, i32 count}`, followed by count × MsgStringAndTwoInts `{wstr text, i32 id, i32 type}` (FUN_004c8d60) [O]:
- Each record becomes an option through FUN_004c6ee0(text, type, id) [O].
- The client then opens the dialogue (FUN_004c1e70(1,0)) and sends **0x127** (no payload, an ack) [O].
- Options of types 0-5, 0xb, 0xe, 0xf and 0x10 are de-duplicated by type. Options are sorted by type [O].

Clicking an option goes FUN_0068a680 → FUN_004c4860 → **FUN_004c4640** [O]. What happens for each type:

| type | client action on click | C->S |
|---|---|---|
| 0 | FUN_005ce010 (trainer) | — |
| 1 | FUN_005ac900 (recipes) | — |
| 2 | FUN_00460010 (assembly) | — |
| 3 | FUN_0046aa40 (bank) | — |
| 4 | FUN_004b76c0 (work orders) | — |
| 5 | merchant | 0xe5 |
| **6** | quest-dialogue response (created by 0x2af) | **0x15b** MsgIntAndByte `{i32 dialogIdx, u8 responseIdx}`, where idx = (id - id%5)/5 and response = id%5 [O] |
| **7, 8, 9** | quest option (giver / in-progress / turn-in) [I by type grouping] | **0x15c** MsgSingleInt `{i32 id}` [O] |
| 10 | FUN_0054cc70(id) (parley) | — |
| 0xb | corpse summon | 0x167 (no payload) |
| 0xc, 0xd | set local flags +0x35 / +0x36 | — |
| 0xe | escrow | 0xed |
| 0xf | market | FUN_00536740 |
| 0x10 | repair | 0xf1 |

**0x2af** MsgQuestDialogToClient `{eid64 npc, i32 dialogIdx, 5 × wstr response}` [O]:
- Registrar FUN_004c0a10. Handler FUN_004c7840.
- It removes earlier type-6 options (FUN_004c5c10).
- Each non-empty response i becomes a type-6 option with id = dialogIdx*5 + i. Text inside `<...>` is removed (FUN_004c4a80).
- The client then sends 0x127.
- Clicking response i sends **0x15b {i32 dialogIdx, u8 i}** [O].

Optional voice greeting: **0x581** MsgSingleInt `{i32}` [O]. Values: 0 GeneralGreet, 1 QuesterGreet, 2 QuesterProgress, 3 TrainerGreet, 4 MerchantGreet (FUN_004c64d0).

### 1c. Quest offer window: 0x2c0 MsgSimpleQuestInfoToClient (handler FUN_005a4e50, registrar FUN_0058e850) [O]
The offer page appears inside the Dialogue window. FUN_004c40a0(1) sets nDialogWindowState=1 and binds `qstOfferedQuest`.

The same layout is used by **0x2cb** (section 2). Wire order:

| # | type | msg off | becomes (VGClientQuest) | meaning |
|---|---|---|---|---|
| 1 | eid64 | +0x18 | — (not used by the handler) | giver NPC [I] |
| 2 | i32 | +0x20 | +0x04 | **questId** (mgr+0x84 = displayed quest) [O] |
| 3 | wstr | +0x24 | +0x08 | **Name** [O] |
| 4 | i32 | +0x40 | +0x24 | **Level**. Clamped to 1..55; if sphere=2 and level>51 it is set to 51; if sphere=1 and level>56 it is set to 56 [O] |
| 5 | u8 | +0x44 | +0x28 | **Sphere**: 0 adventuring (else-branch), 1 and 2 are the other journal lists (crafting / diplomacy) [O lists, I names] |
| 6 | wstr | +0x48 | +0x2c | **Description** (offer text) [O member mapping] |
| 7 | wstr | +0x64 | +0x48 | **Summary** [O] |
| 8 | wstr | +0x80 | +0x64 | text printed to chat when accepted (0x2c1) [O] |
| 9 | wstr | +0x9c | +0x80 | **Status**, the objective line shown in the journal and tracker (`ColoredQTStatus`) [O] |
| 10 | i32 | +0xbc | +0x9c | **state / nQuestDetailsState**: 0 offer (Accept/Decline), 1 in progress (giver view), 2 in progress (taker), 3 ready to complete ("Continue"/Cancel), 4 completed (rewards + "Complete"/Cancel) [O switch + XML] |
| 11 | i32 | +0xc0 | +0xc0 | **CoinReward** in copper. Shown only if ShowRewardInAdvance is set or state==4 (FUN_0067d140) [O] |
| 12 | i32 | +0xb8 | +0xa4 (mgr+0x124) | "opened from NPC dialogue" flag, used when the window closes (FUN_005a1200). Echoed in 0x160. Use 0 [O/I] |
| 13 | bool | +0xc4 | +0xa0 | ShowRewardInAdvance [O] |
| 14 | bool | +0xc5 | +0xa1 | reward already taken. If 1, the "Complete" (accept-reward) button is hidden in state 4 (FUN_0059ece0) [O] |
| 15 | bool | +0xc6 | +0xa8 | ? |
| 16 | i64 | +0xc8 | +0xb0 | StartDate [O member] |
| 17 | f32 | +0xd0 | +0xb8 | time limit. **-1 = untimed** (TimeRemaining is shown only if > -1) [O] |
| 18 | f32 | +0xd4 | +0xbc | time remaining in seconds [O] |
| 19 | i32 | +0xd8 | +0xc4 | ? (send 0) |
| 20 | i32 | +0xdc | +0xc8 | ? (send 0) |
| 21 | bool | +0xe0 | +0xcc | ? |
| 22 | i32 | +0xe4 | +0xd0 | CompletionChunkX [O member]. **Verified live 2026-10-15:** the server sends the turn-in NPC's chunk and spawn position in 22-26 (`login_stub.quest_where`, from the spawn files); with the journal's Details > "Show Completion Chunk" the quest row reads "Sundering Wastelands (-19,12)" |
| 23 | i32 | +0xe8 | +0xd4 | CompletionChunkY (name taken from FUN_00b70e80; "Unknown Zone" sets X and Y to 0) [O] |
| 24-26 | i32 ×3 | +0xec..+0xf4 | +0xf4..+0xfc | location x, y, z, converted to floats [O] |
| 27 | i32 | +0xf8 | +0x108 | **N = number of trailing records** [O] |
| 28 | i32 | +0xfc | +0x10c | start-location id (Travel Journal). -1 = none [O] |
| 29 | i32 | +0x100 | +0x110 | completion-location id. -1 = none [O]. Tried 2026-10-15: sending the travel-journal id of Orin's location (a known entry in the Locations tab) in 28 and 29 adds a "Locations" heading to the quest details, but the list under it stays empty, so the server keeps -1 (how the list is filled is open; perhaps the trailing records) |
| 30 | 30 × {i32 itemId, i32 b, i32 rewardGroup, bool8 d} | +0x104.. | reward groups (+0x11c) | **item rewards**. itemId -1 means an empty slot. Records are interleaved, 13 bytes each, 390 bytes total [O registrar loop] |

After that come N × MsgTwoInts `{i32 locationId, i32 sortOrder}`, the quest's Travel-Journal locations [O loop; I meaning]. Send N=0.

Two behaviours to know [O]:
- If a reward itemId is not in the item cache (FUN_00517390), the client sends **0x162 {i32 questId}** to ask for item data, and does not display the quest.
- If state=4 and there is one group holding one item, the client auto-selects it (0x163).

The handler then picks the page from field 10: 0 → FUN_0059ea10, 1 → FUN_0059ebf0, 3 → FUN_0059eb00, 4 → FUN_0059ece0. Each sets `nQuestDetailsState`, binds `qstOfferedQuest` and opens the page [O].

### 1d. Buttons in the details page (UI events, dispatcher FUN_006a8060) [O]
| button | UI cmd | handler | C->S |
|---|---|---|---|
| Accept (`accept_displayed_quest`) | 0x20b | FUN_00592390 | **0x15d** MsgSingleInt `{i32 questId}` |
| Decline (`decline_displayed_quest`) | 0x20c | FUN_005a2470 → FUN_005a1200(0) | **No decline message.** The window closes. If field 12 is 0 (or 1 with mgr+0x218==0), the client sends **0x2b0** MsgEntityIDAndBool `{eid64 currentTarget, bool8 1}` (FUN_004c40a0(2)) [O]. 0x2b0 is probably "return to / re-request the NPC conversation" [I] |
| OK / Cancel (`quest_details_generic_ok`) | 0x20d | FUN_005a1200(0) | same as Decline |
| Continue (`complete_displayed_quest`, state 3) | 0x20e | FUN_00592410 | **0x160** MsgIntAndByte `{i32 questId, u8 field12}` |
| Complete (`accept_reward_displayed_quest`, state 4) | 0x211 | FUN_00592530 | **0x161** MsgTwoInts `{i32 questId, i32 selectedReward (mgr+0x210)}` |
| Abandon → confirm yes | 0x20f confirm | FUN_005924b0 | **0x15f** `{i32 journalSelectedQuestId}` [I: confirm-yes path] |
| Share | 0x210 | FUN_00592af0 | **0x166** `{i32 questId}` [O send / I name] |
| select reward item | — | FUN_005925b0 | **0x163** MsgTwoInts `{i32 questId, i32 itemId}` |

Server replies on this path:
- **0x2cf / 0x2d0** MsgTwoInts `{i32 ?, i32 itemId}` highlight or clear a reward ("Selecting %s" / "De-selecting %s") [O].
- **0x2c8** MsgIntAndBool `{i32 questId, bool showAcceptRewardButton}` [O].

### 1e. Accept result: 0x2c1 MsgTwoIntsAndByte `{i32 questId, i32 startDate, u8 result}` (FUN_005a3e00) [O]

| result | client behaviour |
|---|---|
| 0 | Only acts if questId == displayed quest. Prints wstr #8 and "You have accepted %s". If the quest is not in the journal yet: when its template is cached, the client builds the journal entry itself (state copied from field 10, Tracked=1); when it is not cached, it sends **0x164 {i32 questId}** to ask for 0x2cb. Then it closes the page. |
| 1 | QuestTooMany |
| 2 | QuestAlreadyOn |
| 3 | QuestUnableToAccept |
| 4 | QuestDoNotMeetRequirements |
| 5 | QuestInventoryFull |
| 6 | Accepted without the offer page (for example a shared quest) |
| 0xff | "Unable to accept quest." |

startDate: if it is ≤ 0, the client uses the i64 from the offer.

## 2. Journal

### 2a. Add or update a quest: 0x2cb, same layout as 0x2c0 (FUN_005a5a60) [O]
- The client builds a template, stores it in the cache (+0x26c) and adds or updates the journal entry (FUN_005a1670 → FUN_005a2920 → FUN_0059efd0). A new entry is marked Tracked (+0x118 = 1).
- **This one message is enough to put a quest in the journal and tracker.** For an active quest, set field 10 = 1.
- Each journal row shows Name, Level, Status and so on.
- The same 0x162 rule for unknown reward items applies.

### 2b. Journal sync at login [O]
- **0x2a9** (no payload) clears every quest (FUN_005a3200).
- **0x2c9**: `{i32 count}` then count × MsgQuestInitClient `{i32 questId, wstr, i32 level, u8 sphere, i32 state, f32 timeRemaining, i64 startDate, i32 ?, i32 chunkX, i32 chunkY}` (registrar FUN_0058e6f0, record handler FUN_005a47f0).
  - For each quest id without a cached template, the client sends **0x164**.
  - It is simpler to send 0x2cb per quest instead.

### 2c. Objective counter / "quest updated": 0x2cc MsgQuestStatusUpdate `{eid64 source, i32 questId, wstr chatText, bool8 showChat, wstr newStatus, bool8 npcSays, bool8 completed}` (registrar FUN_0058e790, handler FUN_0059d530) [O]
- The client replaces the journal entry's **Status** (+0x80) with `newStatus`, sets Tracked, and refreshes the journal and the `_quest_status_list` tracker [O].
- If showChat=1, `chatText` is printed:
  - npcSays=0 → quest chat channel 0x1c (FUN_005e58f0);
  - npcSays=1 → said by entity `source` (FUN_00438dd0).
- completed=1 sets state = 3 (ready to complete) and prints "%s complete." on channel 0x1d. It also activates the completion location if field 29 ≠ -1.
- completed=0 sets state = 1.
- **There is no separate counter field.** "(1/3)" is just text in `newStatus`. Send the whole updated line.

Related messages:
- **0x2ce** MsgQuestConditionsMet `{eid64, i32 questId, bool8}` sets state=1 and refreshes; the bool is ignored [O].
- **0x2c6** MsgSingleInt `{i32 questId}` refreshes the details view [O].
- **0x2d1** MsgIntAndFloat `{i32 questId, f32 timeRemaining}` [O].
- **0x4ad** `{wstr, i32}` opens the "Quest Report" window [O].

### 2d. Complete / remove: 0x2c5 MsgIntAndTwoBytes `{i32 questId, u8 result, u8 abandoned}` (FUN_005a43d0) [O]
- result=0:
  - closes the details page if it is showing this quest and abandoned=0;
  - prints "<color=yellow>%s completed." (or "%s abandoned." when abandoned=1);
  - removes the quest from the journal (FUN_005a2c10);
  - plays UISounds.QuestComplete.
- result=1: "You are unable to complete that quest right now."
- result=0xff: "Unable to complete quest."

Abandon result: **0x2c3** `{i32 questId, u8 result, u8}` prints "Quest abandoned." and removes the quest [O].

Not used for this: **0x2a2/0x2a3** MsgQuestJournalAdd. That is the Adventure Journal (lore) section, not the quest log.

## 3. Turn-in and rewards
- Client flow [O]: the player is in state 3 and presses "Continue" → **0x160 {questId, u8}**. In state 4 the player presses "Complete" → **0x161 {questId, rewardItem}**.
- XP: no quest message carries an XP field. Grant it with the existing **0x3d5** MsgExperienceRewardResult (`combat.experience_reward(amount, npc_eid)`) [O for 0x3d5].
- Coin: field 11 is only for display. Pay with the existing coin messages (0x1aa as in MERCHANTS.md) [I].
- Item choice: fill reward slots (field 30) with item ids and send 0x2c7 item info first, with item field 1 = that id (otherwise the client sends 0x162). The choice comes back in 0x163 / 0x161 (implemented, see the note at the top).

## 4. Minimal recipe: "Kill 3 Robed Wanderers" (QID = 1001, NPC = giver eid)
1. **Hail or U on the NPC**:
   - 0x3ea `{npc, "Robed wanderers have been harassing travellers. Will you help?"}`
   - 0x2bf `{npc, 1, ["The robed wanderers", id=QID, type=7]}`
   - optional 0x581 `{1}` (QuesterGreet)
   - The client replies 0x127. Ignore it.
2. **Option clicked** → C->S 0x15c `{QID}`. Send 0x2c0 with:
   - npc, QID, "Robed Wanderers", level 1, sphere 0;
   - Description "Slay 3 Robed Wanderers.", Summary "", accept text "Return when the deed is done.", Status "Kill 3 Robed Wanderers (0/3)";
   - state=0, coin=0, field12=0, bools 0,0,0, startDate 0, timeLimit -1.0, timeRemaining 0;
   - 0, 0, false, chunk 0, 0, loc 0, 0, 0, N=0, startLoc -1, endLoc -1;
   - 30 × {-1, 0, 0, 0}.
   The Accept/Decline page opens.
3. **Accept** → C->S 0x15d `{QID}`. Send 0x2c1 `{QID, now, 0}`, then 0x2cb (same body, state=1). The journal and tracker show "Kill 3 Robed Wanderers (0/3)". The client may also send 0x164 `{QID}`; answer it with 0x2cb.
   **Decline** sends no quest message (at most 0x2b0 `{target, 1}`).
4. **Each kill** of a Robed Wanderer: send 0x2cc `{npc_or_0, QID, "Robed Wanderer slain: 1/3", 1, "Kill 3 Robed Wanderers (1/3)", 0, 0}`.
   On the third kill send newStatus "Return to <NPC> (3/3)" and completed=1. The client shows "Robed Wanderers complete." and sets state 3.
5. **Turn in**: on hail, send 0x2bf with the option type=9, id=QID. On 0x15c `{QID}`, send 0x2c0 with state=3 and Description set to the turn-in text. The client shows Continue/Cancel.
   - Continue → 0x160 `{QID, 0}`. Then:
     - Option (a): send 0x2c0 state=4 so the client shows "Complete", wait for 0x161 `{QID, -1}`, then finish.
     - Option (b): finish straight away.
   - To finish, send 0x2c5 `{QID, 0, 0}` ("Robed Wanderers completed.", the quest leaves the journal) and 0x3d5 XP `{amount, 0, 0, 0, 0, npc, 0, 0}`.

## 5. Open points
- **Option types 7/8/9 (verified live 2026-10-15):** the icon beside a quest option in the Dialogue window: **7** a green check (complete, ready to turn in), **8** blue dots (in progress), **9** a yellow star (available), the same symbols as the quest icons over NPCs. All three send 0x15c when clicked. The server used 7 for every state until then (in-progress quests showed the check); it now sends 9 / 8 / 7 (`quest.OPTION_AVAILABLE` / `OPTION_PROGRESS` / `OPTION_COMPLETE`). Seen: "Supplies for the Forge (in progress)" with blue dots, and clicking it opened the progress page.
- The meaning of 0x2b0, fields 15/19/20/21, and the records' fields b and d.
- That the client accepts 0x2c0 without a prior 0x2bb: 0x2c0 opens the dialogue page itself through FUN_004c40a0(1).
- Test live.

## Conversations (verified live 2026-10-13)

NPCs with an entry in `server/content/dialogs.json` talk in conversation trees. Hailing the Thestran Guard opens the Dialogue window with "Keep your wits about you, traveler..." and three replies; clicking "Any dangers I should know about?" shows the next node, and "I'll keep an eye out. (+ camp standing)" raises the camp faction ("Your standing with Thestran Wastes Camp has improved.").

- The window needs **0x2bb {eid64 npc}** first; 0x3ea text plus 0x2af replies alone do not open it (the client still answers 0x127).
- Each node is sent as an empty 0x3ea (clear), the node text (0x3ea) and **0x2af {npc, node index, 5 x wstr}**, which replaces the previous replies.
- A click sends **0x15b {i32 node index, u8 reply}**. The server echoes "You say, "...".", runs the reply's action (`faction:<id>:<n>`, `give:<item>`, `wares`, `end`; rewards are paid once per character, saved as `dialog_rewards`) and either sends the `goto` node or ends the conversation (0x55f).
- The client only opens the dialogue when the player is near the NPC (hailing from about 2900 units away does nothing).
- **Quests from a conversation (verified live 2026-10-15):** a reply with the action `quest:<quest key>` opens that quest's page in the same window (`login_stub.dialog_quest`). A quest not taken yet shows the offer, and Accept works even though the NPC is not the quest's giver (it counts as offered, like a shared quest). One in progress shows its progress. A quest already done, or still locked by `requires`, ends the conversation. Seen: the Thestran Guard's "Any dangers" node with a quest reply opened "Wolves at the Edge", and Accept put it in the journal and tracker ("You agree to hunt the timber wolves."). The shipped reply offers Wanderer Trouble.

## Abandoning and sharing (2026-10-13)

- **Abandon (verified live):** the journal's Abandon (after its confirmation) sends **0x15f** `{i32 quest id}`; the server drops the quest and answers **0x2c3** `{i32 quest id, u8 0, u8 0}`, which prints "Quest abandoned." and removes it from the journal and tracker.
- **Share (verified live with two clients 2026-10-13, re-checked 2026-10-15):** Share sends **0x166** `{i32 quest id}`; groupmates who don't have the quest (and have done its prerequisites) get the offer page (0x2c0) and "Ranger shares the quest Wanderer Trouble with you."; their Accept (0x15d) is allowed away from the quest giver for a shared quest. Re-check: on a freshly started client, without selecting a journal row, Ranger typed `/sharequest Wolves at the Edge` in a group with Justins and it sent 0x166 (so the name argument also selects the quest); Ranger got "You share Wolves at the Edge with 1 group member.", Justins got the line and the offer page, and Accept put the quest in Justins' tracker ("You agree to hunt the timber wolves.").

## Quest icons over NPCs (verified live 2026-10-14)

0x560 `{eid64 npc, u8 type}` puts a quest icon over an NPC; 0x561 `{eid64, u8}` removes it if the type matches, 0x562 removes all, 0x563 `{eid64}` removes one NPC's. type = sphere x 5 + state: states 0 Soon, 1 Available, 2 In progress, 3 Done, 4 Low; spheres 0 adventure, 1 crafting, 2 diplomacy (the client's FX table, FUN_0058df90: `FXspells_QuestIcon<State>[Craft|Diplo]001fx`). The server picks one icon per NPC (Done > Available > In progress > Low; Soon for a quest with a `min_level` the player has not reached; Low = 10 levels below, a placeholder) and refreshes them once a second (`refresh_quest_icons`). Seen: a gold star shield over Orin for Forge Supplies, a blue "..." shield once it was accepted.

## Quest harvest nodes (2026-10-15)

While a quest's current step still collects an item, the harvest nodes that give it are marked: 0x56a `{eid64}` (dispatcher FUN_0058e580, handler FUN_0058e4c0) starts the "mystical" interactive-object particles (`FXmystical_IOParticle001fx`), and 0x56b `{eid64}` (FUN_0058da80) stops them once the bags hold enough (`login_stub.refresh_quest_nodes`, run with the quest icons). Checked with tools/winbreak.py: 0x56b runs FUN_0058da80, and 0x56a reaches the spawn call FUN_0058ddf0 with the Copper Ore Vein's id. FUN_0058ddf0 only attaches the effect when the pawn's `m_bShowIOParticle` (SGONPCPawn, bit 0 of pawn +0xb18) is set, so the server replicates it to that player with the 0x56a (and clears it with 0x56b). With the flag set the client reaches the attach call (FUN_00bbb740, "ground" branch; winbreak), and the server now announces the FX packages (docs/PROTOCOL.md), but the particles were still not visible in screenshots. Spawned on its own with 0x553 at a point, `FXmystical.FXmystical_IOParticle001fx` shows nothing either, while other emitters spawned the same way do (a bonfire, the fireworks sparklers; docs/ABILITY_VISUALS.md), so the effect was guessed to need a skeletal owner. The class's own emitters say otherwise (`python tools/fx_props.py UnrealScript/FXmystical.u FXmystical_IOParticle001fx`, 2026-10-17): two SpriteEmitters (textures BB015 and BB019), 15 and 7 particles, StartSizeRange 1-10 and 5-15 units, StartLocationRange ±25 units around the owner, no mesh or skeletal spawning, warm-up 1 s. Live check 2026-10-17 (scratch save, first person): 0x553 spawns of the class 150 units from the player on open ground showed nothing even in a zoomed crop, while the red sparkler (FXspells_FireworksCastSparklerARed_P001fx) spawned at exactly the same point rendered clearly. `FXspells_Loot001fx` spawned the same way showed nothing too, although it renders when the client attaches it to a corpse (docs/LOOT.md). So particle size is not the reason, and a 0x553 spawn is no test for these classes: they render (Loot001fx at least) only when the client attaches them to an actor. Why the attached quest-node effect stays invisible is still open; the next check is a marked node seen up close.
