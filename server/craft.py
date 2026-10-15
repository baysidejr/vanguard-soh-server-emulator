"""Crafting (refining) at a station (docs/CRAFTING.md; client VGClientRefining,
dispatchers FUN_005bad40 / FUN_005ac760 / FUN_004b7550).

At login: 0x2ef recipe into the book (silent), 0x2e8 known action (silent).
client 0xfa (use station, current target) -> 0x2ea {i32 slots, i32 station, bool8}
client 0xfe {i32 recipe, bool8}           -> 0x2eb {u8 0xff ok, i32 recipe, wstr, wstr}
client 0xfb (confirm recipe)              -> 0x303 "You may now set up your workbench."
client 0xfc (begin)                       -> 0x2f6 {ap used}, 0x2f8 {quality}, 0x2f7 {stage, u8}, 0x2f5
client 0xf6 {i32 action, i32 -1}          -> 0x2ed, 0x2f6 {ap used}, 0x30a {step, pct},
                                             0x2f7 {stage, progress 0..252}, 0x2f8 {quality 0..1000},
                                             0x2fa {wstr grade, wstr, i32 step} (2 s flash)
stage done: 0x30d (next stage), then 0x2f7 {new stage, 0}. 0x2f5 only once, at begin
  (it repaints the window as stage 1).
complications: 0x2f9 = 3 slots {wstr name, i32 icon, wstr desc, i32 counter family,
  wstr counter label, wstr counter tooltip, i32 counter icon, i32 health max, i32 health};
  a name in an empty slot adds it, "" removes it. The counter is an action (0x2e8) of
  that family; using it sends the usual 0xf6. 0x308 {wstr, wstr, i32} red screen text.
reject an action: 0x2ec {wstr, u8 code} (6 out of action points, 7 not now).
done: remove inputs (0x1a5 / 0x1ae), 0x197 output, 0x3d5 crafting XP, 0x2fd ends.
client 0xfd / 0x102 cancel                -> 0x2fd."""
import struct

USE_STATION, SELECT, CONFIRM, BEGIN, ACTION, CANCEL, CANCEL2 = 0xFA, 0xFE, 0xFB, 0xFC, 0xF6, 0xFD, 0x102
CATALYST = 0xF7                      # {i32 item handle}: the player adds the offered catalyst
# Table Setup buttons: the auto-fill checkbox (crafting_auto_fill_inventory_toggle, FUN_005b0400)
# sends 0x106 and is redrawn by 0x30f {bool8} (FUN_005b3640); Back (refining_setup_back,
# FUN_005b05e0) sends 0x107 and 0x310 returns the window to recipe selection. This server always
# places the recipe's utilities and tools itself (0x300 lists them selected), so the checkbox
# stays on.
AUTO_FILL, BACK = 0x106, 0x107
CLIENT_EVENTS = (USE_STATION, SELECT, CONFIRM, BEGIN, ACTION, CANCEL, CANCEL2, CATALYST, AUTO_FILL, BACK)
STATION = 0x4                        # EntityTypes bit
MAX_AP = 100
RECIPE_OK, RECIPE_MISSING = 0xFF, 2
# 0x2ec action rejected {wstr name, u8 code}: 1 missing item, 3 missing tool,
# 4 missing tool of type, 6 not enough action points, 7 not now.
MISSING_TOOL, NO_AP, NOT_NOW = 3, 6, 7


def auto_fill(flag):
    return _event(0x30F, struct.pack("<B", int(flag)))


def back_to_recipes():
    return _event(0x310)


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def stages(r):
    """[(stage name, [step, ...])]: a recipe has "stages" (up to 4), or one
    stage named "stage" with "steps"."""
    if "stages" in r:
        return [(s["name"], s["steps"]) for s in r["stages"]][:4]
    return [(r.get("stage", ""), r["steps"])]


def all_steps(r):
    """[(global index, stage index, step)] in order."""
    out = []
    for si, (_, steps) in enumerate(stages(r)):
        for st in steps:
            out.append((len(out), si, st))
    return out


def recipe_record(r):
    """0x2ee / 0x2ef layout (FUN_005bb100)."""
    steps = all_steps(r)
    names = [name for name, _ in stages(r)] + [""] * 4
    data = (_w(r["name"]) + _w(r.get("description", ""))
            + struct.pack("<iiii", r.get("icon", 443), r["id"], len(steps), r.get("max_ap", MAX_AP))
            + struct.pack("<ii", -1, -1)
            + struct.pack("<iii", 1 if r.get("kind") == "finishing" else 0, r.get("category", 1), 0)
            + struct.pack("<BBi", 0, 0, r.get("skill", 0x28))   # 0x28 Smelting (stat id)
            + b"".join(_w(n) for n in names[:4]))
    for n, si, st in steps:
        data += (_w(st["name"]) + struct.pack("<iiiii", r.get("icon", 443), n, step_id(r, n), 0, si)
                 + _w(st.get("description", "")))
    return data


def step_id(r, n):
    return r["id"] * 10 + n


def missing_steps(r, have, stage=None):
    """Step ids of recipe r (only stage `stage` if given) whose tool or utility item is not among
    `have` (item names)."""
    out = []
    for n, si, st in all_steps(r):
        if stage is not None and si != stage:
            continue
        need = [st.get("tool"), (st.get("utility") or {}).get("item")]
        if any(x and x not in have for x in need):
            out.append(step_id(r, n))
    return out


# Journal recipe view (verified live 2026-10-15): selecting a recipe in the journal's crafting
# pages sends 0x108 {i32 recipe id} (FUN_005aa990); 0x309 {i32 count, count x i32 step id}
# (FUN_005ac490) fills JournalRefRecipeMissingItems / JournalFinRecipeMissingItems with
# "Steps missing items:  <step>, <step>" for the recipe on show.
JOURNAL_RECIPE = 0x108
JOURNAL_MISSING = 0x309


def journal_recipe(r):
    """0x2f2 (same layout as the recipe add, FUN_005ac180): the recipe's details for the journal
    pane, which it waits for after 0x108 (name, icon, description, steps)."""
    return _event(0x2F2, recipe_record(r))


def journal_missing(step_ids):
    return _event(JOURNAL_MISSING, struct.pack("<i", len(step_ids)) + b"".join(struct.pack("<i", s) for s in step_ids))


def step_flag(step, on=True):
    """0x30b / 0x30c {i32 step id}: set or clear the "needs an item" flag on a step's entry in the
    crafting window (FUN_005bcdd0 / FUN_005bcfa0; only the current stage's steps)."""
    return _event(0x30B if on else 0x30C, struct.pack("<i", step))


def learn_recipe(r):
    return _event(0x2EF, recipe_record(r))


def forget_recipe(r):
    """0x2f4 {i32 id}: remove a recipe from the book."""
    return _event(0x2F4, struct.pack("<i", r["id"]))


def forget_action(action_id):
    """0x2e6 {i32 action id}: remove one known crafting action (FUN_004b66b0; 0x2e4 clears all)."""
    return _event(0x2E6, struct.pack("<i", action_id))


def learn_action(r, n):
    """0x2e8 {i32 action, wstr name, wstr desc, i32 icon, i32 family, i32 ap}: the
    window offers actions whose family equals the clicked step's id."""
    st = all_steps(r)[n][2]
    return _event(0x2E8, struct.pack("<i", st["action"]) + _w(st["name"]) + _w(st.get("description", ""))
                  + struct.pack("<iii", r.get("icon", 443), step_id(r, n), st.get("ap", 20)))


def learn_counter(c, icon=443):
    """A complication's counter action (its own family, used by no step)."""
    k = c["counter"]
    return _event(0x2E8, struct.pack("<i", k["action"]) + _w(k["name"]) + _w(k.get("description", ""))
                  + struct.pack("<iii", icon, k["family"], k.get("ap", 15)))


def station_recipes(ids):
    """0x304 {i32 n, n x i32 recipe id} (FUN_005bac40): the recipes this station offers.
    The Crafting Setup window shows the refining or the finishing page by the kind of the
    first one (nRecipeSelectRefineOrFinish, FUN_005aa0c0) and lists these recipes."""
    return _event(0x304, struct.pack(f"<i{len(ids)}i", len(ids), *ids))


def open_window():
    return _event(0x2EA, struct.pack("<iiB", 8, 1, 0))


def recipe_result(result, recipe_id):
    return _event(0x2EB, struct.pack("<Bi", result, recipe_id) + _w("") + _w(""))


def workbench():
    return _event(0x303)


def catalyst_offer(handle):
    """0x2fb: shows "Add secondary ingredient" and an "Add <item>" catalyst entry;
    clicking it sends 0xf7 {handle}."""
    return _event(0x2FB, struct.pack("<i", handle))


def catalyst_clear():
    return _event(0x2FC)


def quality(value):
    return _event(0x2F8, struct.pack("<i", value))


def started(quality=500):
    return [_event(0x2F6, struct.pack("<i", 0)), _event(0x2F8, struct.pack("<i", quality)),
            _event(0x2F7, struct.pack("<iB", 0, 0)), _event(0x2F5)]


def action_done(r, n, stage, ap_used, progress, quality, grade):
    return [_event(0x2ED), _event(0x2F6, struct.pack("<i", ap_used)),
            _event(0x30A, struct.pack("<iB", step_id(r, n), 100)),
            _event(0x2F7, struct.pack("<iB", stage, progress)), _event(0x2F8, struct.pack("<i", quality)),
            _event(0x2FA, _w(grade) + _w("") + struct.pack("<i", step_id(r, n)))]


def next_stage(stage):
    """0x30d moves the window to the next stage; 0x2f7 then starts its bar."""
    return [_event(0x30D), _event(0x2F7, struct.pack("<iB", stage, 0))]


def complications(slots, icon=443):
    """0x2f9 with up to 3 (complication, health) pairs; missing slots are empty."""
    data = b""
    for i in range(3):
        if i < len(slots):
            c, health = slots[i]
            k = c["counter"]
            data += (_w(c["name"]) + struct.pack("<i", icon) + _w(c.get("description", ""))
                     + struct.pack("<i", k["family"]) + _w(k["name"]) + _w(k.get("description", ""))
                     + struct.pack("<iii", icon, 100, health))
        else:
            data += _w("") + struct.pack("<i", 0) + _w("") + struct.pack("<i", 0) + _w("") + _w("") \
                + struct.pack("<iii", 0, 0, 0)
    return _event(0x2F9, data)


def alert(text):
    """0x308: red screen text "New Complication: <text>"."""
    return _event(0x308, _w(text) + _w("") + struct.pack("<i", 0))


def screen_text(text):
    """0x2fa with step -1: white floating screen text."""
    return _event(0x2FA, _w(text) + _w("") + struct.pack("<i", -1))


MISSING_ITEM = 1                     # 0x2ec code 1 "Missing item: %s"
# Toolbelts: 0xa4 {i32 slot 67..69} (/craftingchangeactivetoolbelt 1-3) or 0xf8 {i32 belt handle}
# (click in the Toolbelts window) choose the active belt; reply 0xa5 {i32 slot} (checkmarks).
ACTIVE_TOOLBELT, PICK_TOOLBELT = 0xA4, 0xF8
TOOLBELT_SLOTS = (67, 68, 69)


def active_toolbelt(slot):
    return _event(0xA5, struct.pack("<i", slot))


def table_items(entries):
    """0x300 {i32 n, n x (i32 item handle, i32 step id, bool8 selected)}: the Table Setup lists
    (steps and the items under them; step -1 "Other Items", -2 "Catalysts"). Before 0x2eb."""
    return _event(0x300, struct.pack("<i", len(entries))
                  + b"".join(struct.pack("<iiB", h, sid, int(sel)) for h, sid, sel in entries))


def rejected(code, name=""):
    return _event(0x2EC, _w(name) + struct.pack("<B", code))


def grade_letter(quality):
    return "D" if quality < 250 else "C" if quality < 500 else "B" if quality < 750 else "A"


def end():
    return _event(0x2FD)


STATION_INVALID, STATION_NO_DATA, STATION_TOO_FAR = 0, 1, 2
STATION_RANGE = 800


def station_error(code):
    return _event(0x2E9, struct.pack("<B", code))
