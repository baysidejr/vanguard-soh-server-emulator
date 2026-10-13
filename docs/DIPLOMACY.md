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

## Deck and strategy slots

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

Errors use `0x330 {i32 code, i32 arg}`. Examples: 4 card not prepared, 5 refreshing, 7–10 not enough Inspire/Reason/Flatter/Demand, 0xc not your turn, 0xf parley over, 0x11 need more presence.

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
- unlocked dialogue as a reward. Faction (`reward.faction`) and items (`reward.item`: a name or [name, qty], given on every win; verified live: "You receive 2 Travel Rations.") are done; dev `!parleywin` wins the open parley
- opening the repertoire window by script (slotting a card from it uses the same `0xd7`)
- the `0x321` option format with presence requirements
- the civic stats display (0x340 MsgThreeInts, 0x341 list; gamevars CivicDiplomacyStats / bDisplayCivicStats have no window in the shipped UI)

Unknown fields: the trailing wstr in `0x31d`; card fields 3 and `+0xa0`; the bool in `0x31f`; client messages `0x126`, `0x129` and `0x12d`.
