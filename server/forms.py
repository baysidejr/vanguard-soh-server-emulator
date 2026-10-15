"""Combat forms (docs/FORMS.md; client combat UI manager, dispatcher FUN_005fb9e0). For a
Psionicist the client calls them Mindsets (FUN_006b4020); the protocol is the same for every class.

Server -> client:
  0x38a: clear all forms        0x38e {wstr name, wstr desc, i32 id, u8 type 0, i32 icon, u8 0,
                                       bool8 show}: add a form (sets bHasCombatForms: the Forms bar)
  0x38d {i32 form id, i32 0}: the current form (-1 = none, "You are no longer in a combat form!")
  0x13f {i32 result}: answer to a change; 0 silent, 1-6 errors
  0x140 {i32 0, f32 0..1}: the change cooldown bar
Client -> server:
  0x13e {i32 form id, i32 0}: choose a form (clicking it on the bar, /combatformset <name>)
  0x141 {i32 form id, i32 priority}, 0x143: Psionicist mindset priorities -> 0x142 {i32 0}"""
import struct

CHOOSE, SET_PRIORITY, CLEAR_PRIORITIES = 0x13E, 0x141, 0x143
CLIENT_EVENTS = (CHOOSE, SET_PRIORITY, CLEAR_PRIORITIES)
ID_BASE = 1
CHANGE_SECONDS = 5


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def class_forms(table):
    """[(form id, name, spec)] from forms.json's entry for a class."""
    return [(ID_BASE + n, name, spec) for n, (name, spec) in enumerate(table.items())]


def allowed_forms(forms, ability_name):
    """Form ids whose forms.json "abilities" list names this ability; [] = usable in any form."""
    return [fid for fid, _name, spec in forms if ability_name in spec.get("abilities", [])]


def form_fields(ids):
    """MsgAbilityInfo #61-68 for allowed form ids. All -1 skips the client's form check; the
    list is padded with its first id (not -1, which is also "no form")."""
    if not ids:
        return {}
    ids = (list(ids) * 8)[:8]
    return {61 + n: fid for n, fid in enumerate(ids)}


def describe(spec):
    return spec.get("description") or f"Increases {spec['stat'].capitalize()} by {spec['bonus']}."


def form_list(forms):
    out = [_event(0x38A)]
    for fid, name, spec in forms:
        out.append(_event(0x38E, _w(name) + _w(describe(spec))
                          + struct.pack("<iBiBB", fid, 0, spec.get("icon", 560), 0, 1)))
    return out


def current(form_id):
    return _event(0x38D, struct.pack("<ii", form_id, 0))


def result(code=0):
    return _event(0x13F, struct.pack("<i", code))


def cooldown(fraction):
    return _event(0x140, struct.pack("<if", 0, float(fraction)))


def priority_result(code=0):
    return _event(0x142, struct.pack("<i", code))
