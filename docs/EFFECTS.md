# Ability effects: buffs, damage over time, heals, cooldowns

**Verified live (2026-10-12, Ranger):**
- Ferocity I (a buff) puts an icon with a countdown ("26s", then "9s") in the player's effects area. Expiry (`0x23b` plus the "wears off" line) is implemented but its end was not watched live.
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
| `0x259` | `i32 ability handle, f32 left, f32 total` | hotbar cooldown sweep |
| `0x242` | `u8 code` | ability failure sound (7 = too soon, 3 = too far, 0x22 = no energy, 0x24 = no endurance) |
| `0x25c`* / `0x260`* | `wstr name, f32 seconds` / none | cast bar / interrupted. An ability with `cast` seconds in abilities.json shows the bar ("You begin to cast Deadly Shot I.") and goes off when the time is up. Moving during the cast interrupts it ("Your Deadly Shot I is interrupted."). Verified live |
| `0x27b` | `eid64 source, eid64 target, i32 instance, bool8 heal, u8 kind, i32 amount, i32 bonus, u8 outcome, u8 type, u8, wstr ability, bool8, bool8` | client-built combat sentence. **Sent live, but nothing printed.** The layout or a pending-instance rule is off, so tick and heal lines use system text for now |

Not done yet:
- maintained effects (`0x23e`)
- confirming whether the `0x259` sweep shows on the hotbar (the abilities tested weren't on the bar)
