# Ability effects: buffs, damage over time, heals, cooldowns

**Verified live (2026-10-12, Ranger):**
- Ferocity I (a buff) puts an icon with a countdown ("26s", then "9s") in the player's effects area. Expiry was watched live: after 30 s Evasive Style I's icon goes away and "Evasive Style I wears off." prints.
- Deadly Shot I (a DoT) hits once, then shows a "Deadly Shot I" debuff icon in the target window. It ticks 4 times every 3 s ("Your Deadly Shot I hits Ashen Wolf for 4 damage.") and the wolf's health bar drops.
- Reusing an ability before its refresh time is refused.

**NPC special attacks (verified live):** after a melee swing, a mob template's `abilities` may fire, for example the Canyon Widow's Venom Bite: "Canyon Widow uses Venom Bite on you!". This adds a harmful effect icon with a countdown (`0x23a` harmful=1). It ticks "Canyon Widow's Venom Bite hits YOU for 5 damage.", and `0x23b` removes the icon at the end. A reapply refreshes the tick count.

The code is in `server/effects.py` and `login_stub.use_ability` / `apply_buff` / `apply_dot` / `effects_tick`. The dev commands `!learn <ability>` and `!use <ability>` help with testing.

## What an ability does

Real ability data (costs, damage, durations) was server-side. The emulator guesses an ability's kind from its name (`effects.KEYWORDS`):
- **dot** if the name contains words like rend, venom or decimate
- **heal** for heal, mend or restore
- **buff** for might, ward, style, shield and similar words
- **strike** (direct damage) for everything else

`server/content/abilities.json` overrides the guess per ability name: `kind`, with `damage/ticks/interval`, `amount`, or `stat/bonus/duration`, plus `icon`.

## Messages (static analysis; the starred ones are verified live)

| Id | Payload | Meaning |
|---|---|---|
| `0x23a`* | `i32 id, wstr name, wstr desc, u8, i32 icon, u8, i32 seconds left, bool8 show, bool8 no expiry, bool8 harmful, bool8 short list, f32 duration` | adds an effect to the player's effects window (dispatcher `FUN_00467f80`) |
| `0x23b`* | `i32 id` | removes it (the client never expires effects itself) |
| `0x23c` | `i32 id, i32 left, i32 duration, bool8` | timer update (sent every 5 s) |
| `0x3c5`* | `i32 id, wstr name, wstr desc, i32 icon, bool8 show, bool8 debuff, eid64 caster` | adds an effect to the target window (the current target's list: `0x3c9` clears it, and the server resends on retarget) |
| `0x3c6` | `eid64 target, i32 id` | removes a target effect |
| `0x2d4`* | MsgStatUpdate with current = base + bonus | stat buff shown in the character window |
| `0x259` | `i32 ability id, f32 left, f32 total` | hotbar cooldown sweep |
| `0x242` | `u8 code` | ability failure sound (7 = too soon, 3 = too far, 0x22 = no energy, 0x24 = no endurance) |
| `0x25c`* / `0x260`* | `wstr name, f32 seconds` / none | cast bar / interrupted. An ability with `cast` seconds in abilities.json shows the bar ("You begin to cast Deadly Shot I.") and goes off when the time is up. Moving during the cast interrupts it ("Your Deadly Shot I is interrupted."). Verified live |
| `0x27b` | `eid64 source, eid64 target, i32 instance, bool8 heal, u8 kind, i32 amount, i32 bonus, u8 outcome, u8 type, u8, wstr ability, bool8, bool8` | client-built combat sentence, shown in the **Combat** tab (verified live: "Your Test Strike heals you for 12 hit points.", "Canyon Widow's Venom Bite hits you for 6 damage."; kind 0 gives the weapon form "You slash yourself for 12 damage."). Used for heals, DoT ticks and every melee hit both ways (auto-attack and NPC swings use kind 0 with damage type 3, giving "You hit Canyon Widow for 8 damage." / "Canyon Widow hits you for 7 damage."; abilities use kind 1 with the ability name). `!ctext [kind] [heal] [self]` sends a test line |

Not done yet:
- maintained effects (`0x23e`)
- the hotbar cooldown sweep: `0x259 {handle, left, total}` is sent for abilities used from the bar (Precision Style I, Ferocity I) but no sweep appears. The handler (`FUN_00427f00`) looks the ability up by handle, stores the floats at +0x124/+0x11c, sets +0x130 unless +0x166 is set, and calls `FUN_006ad020` for the book/bar slots it finds (`FUN_00421190`/`FUN_00421560`/`FUN_004216f0`); one of those lookups probably misses. The payload itself is right: the per-frame tick (`0x426300` area) subtracts the frame time from +0x124 ("left"), clears it at 0, and only shows it when it is longer than the global cooldown; +0x11c is the total. `FUN_00421560` returns ability *book* list widgets chosen by the ability's category flags (+0x174..+0x177, +0x76), so the hotbar shortcut is probably refreshed through a different path (`FUN_006ae0de` copies +0x124/+0x11c into a shortcut record only when the shortcut is built). Resending the hotbar (0x54e) right after 0x259 did not show a sweep either (tested live)

## Hotbar cooldown sweep (fixed, verified live 2026-10-13)

0x259 is keyed by the **ability id** (MsgAbilityInfo field 20, e.g. 1001), not the handle (field 5): FUN_00427c30 searches the ability-book map that FUN_00431be0 keys on obj+0x10c. With the handle the lookup missed and nothing was drawn. Sending the ability id darkens the hotbar slot and the client runs the sweep from its own clock (slot +0x9f4 total, +0x9f8 left). The update reaches the hotbar through the ability-book row the slot is linked to (FUN_006ad020 -> FUN_00c2bf90 -> FUN_006aace0). 0x25b {f32} is the optional global cooldown; MsgAbilityInfo field 36 must stay 0 or the per-frame tick stops.

## Stances and maintained abilities (verified live 2026-10-13)

Abilities with abilities.json `"stance": true` (the Ranger's Offensive / Precision / Evasive Style) are maintained stances: no timer, one at a time (assuming another takes the old one off: "You assume Evasive Style I." / "Offensive Style I wears off."), always on the caster. The server keeps the stat bonus as a buff internally but shows the stance only in the **Effects Maintained** window (`VGUIMaintainedAbilities.xml`, a frameless icon row): **0x23e** `{i32 id, wstr name, wstr desc, u8 0, i32 icon, bool8 0, f32 0}` adds it (resending the id replaces it), **0x23f** `{i32 id}` removes it, 0x24f clears all. Right-clicking the icon (or `/cancelmaintained <name>`) sends **0x24e** `{i32 id}` and the server ends the stance. The timed buff icon (0x23a) is removed for stances so it doesn't show "3650d". Right-clicking an ordinary buff icon sends **0x249** `{i32 id}` and the server ends it ("Adamant Foeman I wears off.", verified live). Not done: 0x254 ability-failure reasons.
