# Combat forms and Psionicist mindsets

> **Verified live (2026-10-13), with `!forms` on Ranger:**
> - The server sends the forms on the zone connection. The world connection logs them as unhandled.
> - `!ui Forms` shows the Forms bar with the three mindsets from `content/forms.json`. The bar did not show by itself.
> - Clicking one sends 0x13e {2, 0}. The server answers 0x13f {0} and 0x38d {2, 0}, applies it as a maintained stance and prints "You assume Mindset of Focus."
> - A new form replaces the old one. A change is allowed once every 5 seconds.
> - `/combatformset <name>` answered "You don't have knowledge of that." in the test, so use the bar.
> - Implemented in `server/forms.py` and `login_stub.handle_form_event`.

Tags: [O] read in decompiled code (combat UI manager DAT_014639a0, dispatcher FUN_005fb9e0). [I] inferred. For class 0xe (Psionicist) the client only renames the labels to "Mindsets" (FUN_006b4020); every other part is the generic combat-form system.

| Dir | Id | Payload | Meaning |
|---|---|---|---|
| S->C | 0x38a | none | Clear all forms; the current form becomes -1 [O]. |
| S->C | 0x38e | wstr name, wstr desc, i32 id, u8 type (0), i32 icon [I], u8 0, bool8 show | Add a form (up to 45) [O]. |
| S->C | 0x38b | i32 count, i32 ?, then count x the 0x38e body | Replace the whole list [O]. |
| S->C | 0x38f | i32 id, i32 ? | Remove a form [O]. |
| S->C | 0x38d | i32 form id, i32 flag | Set the current form. -1 prints "You are no longer in a combat form!" [O] |
| S->C | 0x13f | i32 result | Answer to 0x13e. 0 is silent. 1-3: already changing / not ready / not a valid choice. 4-6: other refusals [O]. |
| S->C | 0x140 | i32 0, f32 0..1 | Change cooldown, shown on the recovery bar [O]. |
| S->C | 0x142 | i32 | Answer to a priority change ("Priority set.") [O]. |
| C->S | 0x13e | i32 form id, i32 0 | Choose a form: clicking it on the bar, `/combatformset`, or auto-change [O]. |
| C->S | 0x141 / 0x143 | {i32 id, i32 priority} / none | `/psionicsetmindsetpriority`, `/psionicclearmindsetpriorities` [O]. |

Abilities list the forms they can be used in: MsgAbilityInfo fields #61-68, where -1 means any form [O]. The server sends -1, so every ability works in every form.

## Psionic pool

Read in the client [O], not implemented: the shipped UI files (VGUIAssets) contain no window bound to these game variables, so nothing on screen would show them.

| Dir | Id | Payload | Meaning |
|---|---|---|---|
| S->C | 0x26d | MsgTwoInts {i32 current, i32 max} | Sets the game vars PsionicPointPoolCurr, PsionicPointPoolMax and PsionicPointPoolStatus (FUN_00589f50, FUN_00589a10). |
| S->C | 0x26b | {i32 id, i32 ?, i32 ?, wstr name, i32 ?, i32 ?} | MsgClientPsionicPoolConcentrationAdd: adds a row to the PsionicConcentrationList (FUN_0058b760, FUN_0058a4e0). |
| S->C | 0x26c | MsgSingleInt {i32 id} | Removes that row and prints "You stop concentrating on <name>" (FUN_0058b160). |
| C->S | 0x250 | MsgSingleInt {i32} | /psioniccancelconcentration and the UI command psionic_pool_cancel_concentration (0x120) (FUN_00589ed0). |

**Recovery bar:** 0x140 `{i32 0, f32 fraction}` (FUN_005f4630) sets the gamevar AdvCannotChangeFormStatus to fraction x 100; VGUIMainBar.xml draws it as a DOWN_TO_UP StatusBar (graphic VgrdFormRefresh) over each form icon. The server sends 1.0 on a change and counts it down once a second to 0 over the 5 s cooldown (`login_stub.form_bar_tick`). Not confirmed on screen: the blue rings seen on the inactive forms stayed after the countdown, so they are something else.

Not done: per-form ability restrictions. The real forms were server data; see CONTENT_EDITOR.md.

## Forms and death (verified live 2026-10-13)

`/applyformondeath [on|off]` sends **0x5b2 {u8 on}** (FUN_00611610) and the client prints "Your forms will (NOT) automatically re-apply after death." The option exists because dying ends the active form. The server now does that (`drop_form_on_death`: the form's stance ends and the Forms bar shows none) and, with the option on (saved as `apply_form_on_death`), puts the form back on release or resurrection. Seen live on a Psionicist: "You are no longer in a combat form!", "Mindset of Focus wears off." at death, then "You assume Mindset of Focus." after Release to Bind. (`!die` drops you dead for such tests.)

**Recovery bar seen live (2026-10-13):** right after a change, a dark overlay covers the bottom of every form icon and the chosen one gets a blue ring.

`/forcecombatstance [on|off]` sends **0x571 {u8 on}** (FUN_00609010). The server keeps `m_CombatState` = 1 (weapons drawn, ready pose) until it is turned off, whatever auto-attack does. Verified live: the character takes the combat pose and chat says "Combat stance forced on."
