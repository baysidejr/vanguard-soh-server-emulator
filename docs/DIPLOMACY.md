# Diplomacy (parleys)

**Verified live:** Orin the Trader offers a parley. Playing "Reasoned Argument" twice moves the bar from 11 to 17. The window then shows "You Win!" and chat prints "You gain 150 diplomacy experience!". The Complete button closes the parley. A second parley in the same session opens with the deck refilled.

The client's parley manager handles server messages in `FUN_00556560`. All messages below are zone events (type 2). `wstr` means UTF-16LE text ending in a 0 character. Server code is in `server/diplomacy.py`; the handler is `handle_parley_event` in `login_stub.py`.

## Starting a parley

- An NPC dialogue option of **type 10** is a parley option. Add it to the normal `0x2bf` option list as `{wstr text, i32 id, i32 10}`. When the player clicks it, the client sends `0x125 {i32 id}`.
- The server answers with **`0x31d`** MsgParlayBeginToClient:
  `{eid64 npc, u8 status, u8 dp, u8 opp dp, u8 x8 expression pools (Inspire, OppInspire, Reason, OppReason, Flatter, OppFlatter, Demand, OppDemand), u8 parley type, wstr}`.
- Parley types: 0 Entertain, 1 Convince, 2 Interview, 3 Gossip, 4 Incite. The window title becomes "Parley - <type>".
- The bar (`ParlayDialogStatus`) runs from 0 to 21 and starts at 11. Above 11 the player controls the conversation. The window shows the bar as an offset from the middle (3, 6, ...).
- An NPC opts in with `"parley": true` in `mobs.json`.
- **Parley offer line (verified live 2026-10-15):** after the options the server sends **0x321** `{eid64 npc, i32 n, n x {wstr text, i32 option id, i32 shown, i32, i32, bool8, bool8, u8 type}}` (FUN_00555e40). The client redraws the parley option as the text over "<Type> <expression icons> : <shown>": Entertain shows Reason/Inspire/Flattery icons, Convince Demand/Reason/Flattery, Interview all four, Gossip Demand/Inspire/Flattery, Incite Demand/Reason/Inspire (type 0-4). Seen on Orin: "Let's talk business." over "Entertain [icons] : 10"; clicking it still sends 0x125 {9001} and starts the parley. The text and number come from the parley's diplomacy.json `offer` and `presence`. The number is presumably the presence the parley asks for (the client has the strings "You need more presence for that." and Academic / Clergy / Crafter / Domestic / Merchant / Noble / Outsider / Soldier Presence) [I]. The other two i32s and the bools go into client lists that were not decoded, so they are sent as 0.

## Deck and strategy slots

**Update (verified live 2026-10-15):** the deck is now also sent when the client reports that its UI finished loading (client event **0x6c**, also after /reloadui). This is after the rebuild, so the ability book's Diplomacy page (the `DiplomacyRepertoire` page list) shows the character's cards outside a parley; it was empty before. A parley then resends with the usual 0x239 clean-up. The card icons are still the client's missing-icon placeholder (443), because the real card icons are server data.

The deck must be sent **when the parley starts, not at login.** A UI rebuild after login (`FUN_005e1f40` → `FUN_0054f140`) recreates the `DiplomacyRepertoire` and `DiplomacyStrategy` lists empty, so cards sent at login disappear. The slot count survives, which is why the bar showed 3 empty slots.

At every `0x125`, before `0x31d`, the server sends:

```
0x239 {i32 card, bool8 1}   x each card   (only from the second parley on: removes stale slot entries,
                                           because a card already in the same slot is ignored)
0x331 {i32 3}                             strategy slot count
0x21c                                     clear the deck (0x21f does not de-duplicate)
0x21f {i32 n} + n x card                  the deck
0x237 {i32 card, i32 slot}  x each card   put each card in a slot (0-based) and refresh the UI list
```

The card format is MsgAbilityParlayCard (parser `FUN_0041fe00`):
`i32 id, wstr name, i32, i32 icon, i32 influence, i32 influence max, u8 x4 costs (reason, inspire, flatter, demand), i32 x8 results, u8 x3 refresh (min, max, left), wstr special text, i32 statement type, i32 expression (0x11 Demand, 0x12 Reason, 0x13 Inspire, 0x14 Flatter), i32, bool8 equipped, i32 x3 required items (-1 = none)`.

A card can only be played if it is in a strategy slot and its refresh count is 0.

Other card messages:
- `0x217`: add one card.
- `0x21a {i32}`: remove a card.
- `0x220 {i32, bool8}`: set the equipped flag.
- `0x238`: same as `0x237` but does not refresh the UI list.
- `0x256`: a new round; every card's refresh count goes down by 1.
- `0x266` and `0x267`: refresh timers.

The client sends `0xd7 {card, slot}` and `0xd8 {card, bool8}` when the player drags cards into or out of slots. The server does not handle them yet.

## A round

1. The player clicks a slotted card. The client sends **`0xd9 {i32 card}`** and the server answers with **`0x332 {i32 card}`** (the card is shown as "my statement").
2. The player presses Speak. The client sends **`0xda`** (Listen / pass sends `0x12c`). The server answers with, in order:

| Message | Payload | Effect |
|---|---|---|
| `0x32c` | 9 x u8: status + 8 pools | the bar and expression pools |
| `0x337` | `{i32 dp, i32 opp dp}` | dialog points (the speech-bubble counters) |
| `0x333` | none | my turn ends |
| `0x218` | one card | the NPC's statement card |
| `0x325` | `{wstr}` | NPC line in the Dialogue window |
| `0x32c` | 9 x u8 | the bar after the NPC's card |
| `0x256` | none | new round (refresh countdown) |
| `0x334` | none | my turn. The client prints "You've gained/lost control of the conversation!" when the bar crosses the middle |

Errors use `0x330 {i32 code, i32 arg}`. Each code shows a red popup and a chat line (switch FUN_005531e0 on code - 1, jump table 0x553950; text from VGClient.int):

| Code | Key | Text |
|---|---|---|
| 1 | ParlayPrepareCardNotFound | That statement could not be found. |
| 2 | ParlayCannotPrepareInParlay | You can't do that while you are in a conversation. |
| 3 | ParlayInvalidSlot | That isn't a valid place to put a statement. |
| 4 | ParlayCardNotPrepared | You can only make statements that are part of your strategy. |
| 5 | ParlayCardFresfreshing | That statement is not ready yet. |
| 6 | ParlayNoCardToPlay | You don't have a statement selected. |
| 7-10 | ParlayFail{Inspire,Reason,Flatter,Demand}Cost | You don't have enough inspire / reason / flatter / demand for that. |
| 11 | ParlayFailItemRequired | You don't have the right items equiped to use that. |
| 12 | ParlayNotYourTurn | It isn't your turn. |
| 13 | ParlayFailMissingItemReq | You don't have the right items on for that. |
| 14 | ParlayFailInvul | You can't start a parley while invulnerable. |
| 15 | ParlayOver | The parley is already over. |
| 16 | CivicDiplomacyNoCivicStats | You're unable to find any civic diplomacy in this area. |
| 17 | ResponseLocked | You don't have enough presence to talk about that. |
| 18 | DiplomacyLevelNotHighEnough | You need at least a diplomacy level of %1 for that. (arg = the level) |
| 19 | FailPCTurnInProgress | Your turn is already in progress. |

The server sends 2 when the strategy bar is changed (drag, /deckload, /deckclear) during a parley, and 3 for a slot outside the bar.

## Ending

- Won: **`0x324`**. The window shows "You Win!" and the Farewell button becomes Complete. Then `0x3d5` MsgExperienceRewardResult with kind 2 prints "You gain N diplomacy experience!".
- Lost: `0x31f {bool8}`.
- Aborted: `0x31e` ("Your parley has ended.").
- The client sends `0x12a` if the player closes the dialogue mid-parley. The server answers with `0x31e` and `0x338`.
- The client sends `0x12b` when Complete is pressed after the parley is over. `0x338` from the server closes the parley UI.

## What the emulator does now

Verified live (2026-10-12): Compelling Case is refused while the Reason pool is too low. Reasoned Argument fills it, both sides play cards, and the bar reaches 17. The window shows "You Win!", and chat prints 1 silver and 150 diplomacy XP.

Cards, the player's deck and per-NPC parleys are data in `server/content/diplomacy.json`. The rules are in `diplomacy.Parley`, which has unit tests.

**Cards**
- A card has a `push`, a `cost` and a `gain`.
- `push` is bar points toward whoever plays it.
- `cost` and `gain` are expression points.
- The card face shows costs and gains in the client's colours: red Demand, green Reason, blue Inspire, yellow Flatter.

**A round**
1. When the player selects a card, the server checks that its cost is affordable. If not, it sends `0x330` code 7–10.
2. When the player plays it, the server applies the card and sends `0x32c` and `0x337`.
3. The NPC plays an affordable card from its `npc_cards`, usually its strongest, which pushes the bar back. This uses `round_messages`.

**Outcome**
- The player wins at `win_at`: `0x324`, then the coin and XP `reward`.
- The player loses at `lose_at`: `0x31f`.
- Selecting or playing after the parley ended gets `0x330` code 0xf ("The parley is already over.").

**Pools**
- The 8 pool bytes in `0x31d` and `0x32c` are pairs (mine, theirs): Inspire, Reason, Flatter, Demand.
- The window draws the Reason, Inspire and Flatter columns, but the Demand (red) column stays empty in an Entertain parley. So the placeholder cards don't use Demand.

## Per-character decks (verified live 2026-10-12)

Each character keeps its own deck (`diplomacy_deck`) and strategy-bar layout (`diplomacy_slots`, one card id or null per slot) in `characters.json`. New characters start from `deck` in `diplomacy.json`; `slots` sets the bar size (4). Only slotted cards can be played.

- Moving a card on the bar sends **`0xd7 {i32 card, i32 slot}`** (seen live: `59 9c 00 00 03 00 00 00`, Reasoned Argument to slot 4). Taking it off sends `0xd8 {i32 card, bool8}`. The server answers `0x239` then `0x237`: the client ignores `0x237` for a card that is already in a slot. The layout survived a restart.
- A parley's `reward.card` is added to the deck on the first win: beating Orin printed "You learn a new diplomacy strategy: Rousing Toast." (card 40029). Cards beyond the bar size wait in the repertoire.

## Civic diplomacy (verified live 2026-10-13)

A parley reward `"civic": {"stat": name, "delta": n, "start": 50}` moves a server-wide civic value, saved in `server/civic.json` (not committed). The server sends **0x33d** MsgCivicDiplomacyUpdateStat `{wstr stat, i32 now, i32 delta}` (FUN_005518f0) and the client prints "You have increased Thestran Wastes Camp Prosperity by 5. It is now 55." (VGClient.int CivicDiplomacyVarInc; a negative delta uses CivicDiplomacyVarDec). What civic values did in the real game was server data (CONTENT_EDITOR.md).

## Card refresh (verified live 2026-10-13)

A card with diplomacy.json `"refresh": N` can't be played again for N rounds. After it is played the server counts down at the end of each round and sends **0x266** `{i32 card, f32 rounds left, f32 total}` (FUN_0054e1a0; stored at card +0x70); the card on the strategy bar shows "2 Rounds Remaining". Selecting it meanwhile gets 0x330 code 5 ("That statement is not ready yet."). **0x267** (no payload) clears every timer; the server sends it when the parley ends. Compelling Case has refresh 2 (placeholder).

**Not done yet**
- (done, verified live 2026-10-13) unlocked dialogue: a parley reward `"flag": name` (+ optional `"flag_text"`) is saved per character (`flags`); dialogs.json responses with `"requires_flag"` only show once the player has it. Beating Orin adds "Orin says I can be trusted." to the Thestran Guard's conversation. Faction (`reward.faction`) and items (`reward.item`: a name or [name, qty], given on every win; verified live: "You receive 2 Travel Rations.") are done; dev `!parleywin` wins the open parley
- opening the repertoire window by script (slotting a card from it uses the same `0xd7`)
- what 0x321's last two i32s and two bools do (the line itself is done, above), and presence itself (no presence stats are sent)
- the civic stats display (0x340 MsgThreeInts, 0x341 list; gamevars CivicDiplomacyStats / bDisplayCivicStats have no window in the shipped UI). `/citystatus` (0x12d, no payload; FUN_0054cf00 clears the stats first) is therefore answered with chat lines "<stat>: <value>" (the server's own wording; verified live: "Thestran Wastes Camp Prosperity: 60"), or, with no civic stats, 0x330 `{i32 16, i32 0}`: the client's "No civic diplomacy here." popup (code switch FUN_005531e0, CivicDiplomacyNoCivicStats; unit-tested, not seen live).

Unknown fields: the trailing wstr in `0x31d`; card fields 3 and `+0xa0`; the bool in `0x31f`; client messages `0x126`, `0x129` and `0x12d`.

## Saved strategy decks (verified live 2026-10-13)

`/decksave N` and `/deckload N` send **0x33a / 0x33b {i32 N}** (the client itself refuses anything outside 1-10: "You must specify a deck number for this command (1-10)"); `/deckclear` sends **0x33c** with no payload. The server keeps up to ten saved strategy bars per character (`deck_presets` in characters.json). Load and clear re-slot the bar with the usual 0x237/0x238 messages and save it. No reply message is known, so the server prints "Strategy deck 1 saved.", "Strategy deck 1 loaded.", "Strategy bar cleared." or "You have no strategy deck 7."
