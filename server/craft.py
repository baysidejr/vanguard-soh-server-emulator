"""Crafting (refining) at a station (docs/CRAFTING.md; client VGClientRefining,
dispatchers FUN_005bad40 / FUN_005ac760 / FUN_004b7550).

At login: 0x2ef recipe into the book (silent), 0x2e8 known action (silent).
client 0xfa (use station, current target) -> 0x2ea {i32 slots, i32 station, bool8}
client 0xfe {i32 recipe, bool8}           -> 0x2eb {u8 0xff ok, i32 recipe, wstr, wstr}
client 0xfb (confirm recipe)              -> 0x303 "You may now set up your workbench."
client 0xfc (begin)                       -> 0x2f6 {ap used}, 0x2f8 {quality}, 0x2f7 {stage, u8}, 0x2f5
client 0xf6 {i32 action, i32 -1}          -> 0x2ed, 0x2f6, 0x2f7 {0, 252 = stage full},
                                             0x2f8, 0x2fa {wstr grade, wstr, i32 step}
done: remove inputs (0x1a5 / 0x1ae), 0x197 output, 0x3d5 crafting XP, 0x2fd ends.
client 0xfd / 0x102 cancel                -> 0x2fd."""
import struct

USE_STATION, SELECT, CONFIRM, BEGIN, ACTION, CANCEL, CANCEL2 = 0xFA, 0xFE, 0xFB, 0xFC, 0xF6, 0xFD, 0x102
CLIENT_EVENTS = (USE_STATION, SELECT, CONFIRM, BEGIN, ACTION, CANCEL, CANCEL2)
STATION = 0x4                        # EntityTypes bit
MAX_AP = 100
RECIPE_OK, RECIPE_MISSING = 0xFF, 2


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def recipe_record(r):
    """0x2ee / 0x2ef layout (FUN_005bb100)."""
    steps = r["steps"]
    data = (_w(r["name"]) + _w(r.get("description", ""))
            + struct.pack("<iiii", r.get("icon", 443), r["id"], len(steps), MAX_AP)
            + struct.pack("<ii", -1, -1)
            + struct.pack("<iii", 0, 1, 0)
            + struct.pack("<BBi", 0, 0, r.get("skill", 0x28))   # 0x28 Smelting (stat id)
            + _w(r.get("stage", "")) + _w("") + _w("") + _w(""))
    for n, st in enumerate(steps):
        data += (_w(st["name"]) + struct.pack("<iiiii", r.get("icon", 443), n, step_id(r, n), 0, 0)
                 + _w(st.get("description", "")))
    return data


def step_id(r, n):
    return r["id"] * 10 + n


def learn_recipe(r):
    return _event(0x2EF, recipe_record(r))


def learn_action(r, n):
    """0x2e8 {i32 action, wstr name, wstr desc, i32 icon, i32 family, i32 ap}: the
    window offers actions whose family equals the clicked step's id."""
    st = r["steps"][n]
    return _event(0x2E8, struct.pack("<i", st["action"]) + _w(st["name"]) + _w(st.get("description", ""))
                  + struct.pack("<iii", r.get("icon", 443), step_id(r, n), 10))


def open_window():
    return _event(0x2EA, struct.pack("<iiB", 8, 1, 0))


def recipe_result(result, recipe_id):
    return _event(0x2EB, struct.pack("<Bi", result, recipe_id) + _w("") + _w(""))


def workbench():
    return _event(0x303)


def started():
    return [_event(0x2F6, struct.pack("<i", 0)), _event(0x2F8, struct.pack("<i", 500)),
            _event(0x2F7, struct.pack("<iB", 0, 0)), _event(0x2F5)]


def action_done(r, n, ap_used):
    return [_event(0x2ED), _event(0x2F6, struct.pack("<i", ap_used)),
            _event(0x2F7, struct.pack("<iB", 0, 252)), _event(0x2F8, struct.pack("<i", 750)),
            _event(0x2FA, _w("Great!") + _w("") + struct.pack("<i", step_id(r, n)))]


def ready():
    return _event(0x2F5)


def end():
    return _event(0x2FD)


def station_error(code):
    return _event(0x2E9, struct.pack("<B", code))
