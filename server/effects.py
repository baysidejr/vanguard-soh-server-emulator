"""Ability effects (docs/EFFECTS.md): buffs, damage over time, heals,
cooldowns and cast bars.

Player effects window (dispatcher FUN_00467f80):
  0x23a add {i32 id, wstr name, wstr desc, u8, i32 icon, u8, i32 seconds left, bool8 show,
             bool8 no expiry, bool8 harmful, bool8 short list, f32 duration}
  0x23b {i32 id} remove (the client never expires effects itself)
  0x23c {i32 id, i32 left, i32 duration, bool8} timer update
Target window effects (FUN_004b4210): 0x3c5 {i32 id, wstr name, wstr desc, i32 icon, bool8 show,
  bool8 debuff, eid64 caster} add, 0x3c6 {eid64, i32 id} remove, 0x3c9 clear (the list is
  the current target's: resend on retarget).
Hotbar: 0x259 {i32 ability id, f32 left, f32 total} cooldown sweep, 0x25b {f32} global.
Casting: 0x25c {wstr name, f32 seconds} cast bar (ends by itself), 0x260 interrupted.
Combat text: 0x27b {eid64 source, eid64 target, i32 instance, bool8 heal, u8 kind, i32 amount,
  i32 bonus, u8 outcome (2 hit, 3 crit), u8 damage type, u8, wstr ability, bool8, bool8}
  -> "Your Rend hits X for N damage." / "Your Mend heals you for N hit points."
Stat buffs: 0x2d4 with current = base + bonus (vgmsg.stat_update)."""
import itertools
import struct

_instances = itertools.count(0x7000000)

# Ability name keywords -> effect kind (overridable per ability in content/abilities.json).
KEYWORDS = [
    (("rend", "bleed", "venom", "poison", "burn", "wound", "gash", "lacerat", "decimate"), "dot"),
    (("heal", "mend", "restor", "salve", "renew", "cure", "recover"), "heal"),
    (("might", "strength", "fortitude", "resolve", "ward", "foeman", "adamant", "defens",
      "guard", "command", "rally", "stance", "aura", "shout", "style", "grace", "ferocity",
      "endowment", "gift", "fervor", "resolution", "blessing", "shield"), "buff"),
]
DEFAULTS = {
    "dot": {"damage": [3, 6], "ticks": 4, "interval": 3.0, "icon": 553},
    "heal": {"amount": [20, 35], "icon": 692},
    "buff": {"stat": "strength", "bonus": 10, "duration": 30.0, "icon": 607},
}


def classify(name, overrides=None):
    """The effect spec for an ability name: {"kind": "strike"|"dot"|"heal"|"buff", ...}."""
    spec = dict((overrides or {}).get(name, {}))
    if "kind" not in spec:
        low = name.lower()
        spec["kind"] = next((kind for words, kind in KEYWORDS if any(w in low for w in words)), "strike")
    for k, v in DEFAULTS.get(spec["kind"], {}).items():
        spec.setdefault(k, v)
    return spec


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def effect_add(eid, name, desc, icon, left, duration, harmful=False):
    return _event(0x23A, struct.pack("<i", eid) + _w(name) + _w(desc)
                  + struct.pack("<BiBiBBBBf", 0, icon, 0, int(left), 1, 0, int(harmful), 0, float(duration)))


def effect_remove(eid):
    return _event(0x23B, struct.pack("<i", eid))


def effect_timer(eid, left, duration):
    return _event(0x23C, struct.pack("<iiiB", eid, int(left), int(duration), 1))


def target_effect_add(eid, name, desc, icon, caster, debuff=True):
    return _event(0x3C5, struct.pack("<i", eid) + _w(name) + _w(desc)
                  + struct.pack("<iBBQ", icon, 1, int(debuff), caster))


def target_effect_remove(target, eid):
    return _event(0x3C6, struct.pack("<Qi", target, eid))


def target_effects_clear():
    return _event(0x3C9)


def cooldown(ability_id, seconds):
    """0x259 {i32 ability id (MsgAbilityInfo field 20, not the handle), f32 left, f32 total}."""
    return _event(0x259, struct.pack("<iff", ability_id, float(seconds), float(seconds)))


def cast_bar(name, seconds):
    return _event(0x25C, _w(name) + struct.pack("<f", float(seconds)))


def interrupted():
    return _event(0x260)


RESIST_CHANCE_PLAYER = 0.15    # a player shrugs off an NPC's harmful effect
RESIST_CHANCE_NPC = 0.10       # an NPC shrugs off a player's damage over time


STANCE_SECONDS = 10 * 365 * 86400   # a stance lasts until replaced or cancelled
CANCEL_MAINTAINED = 0x24E            # client {i32 id}: right-click in Effects Maintained, /cancelmaintained


def maintained_add(eid, name, desc, icon):
    """0x23e {i32 id, wstr name, wstr desc, u8 0, i32 icon, bool8 0, f32 0}: an entry in the
    Effects Maintained window (resending the id replaces it)."""
    data = (struct.pack("<i", eid) + (name + "\0").encode("utf-16-le") + (desc + "\0").encode("utf-16-le")
            + struct.pack("<BiBf", 0, icon, 0, 0.0))
    return struct.pack("<HII", 2, 0x23E, len(data)) + data


def maintained_remove(eid):
    return struct.pack("<HIIi", 2, 0x23F, 4, eid)


def resisted(other_eid, ability, effect="", you=True):
    """0x278 (you resisted, "YouResistedAbilityEffect") / 0x279 (your target resisted,
    "EnemyResistedAbilityEffect"): MsgPCResistedAbilityEffect {eid64 other, wstr ability,
    wstr effect}."""
    data = struct.pack("<Q", other_eid) + (ability + "\0").encode("utf-16-le") + (effect + "\0").encode("utf-16-le")
    return struct.pack("<HII", 2, 0x278 if you else 0x279, len(data)) + data


def combat_text(source, target, ability, amount, heal=False, crit=False, kind=1, dmg_type=0):
    """0x27b: the client writes the sentence ("Your X hits/heals ...")."""
    return _event(0x27B, struct.pack("<QQiBBiiBBB", source, target, next(_instances), int(heal), kind,
                                     amount, 0, 3 if crit else 2, dmg_type, 0) + _w(ability) + struct.pack("<BB", 0, 0))
