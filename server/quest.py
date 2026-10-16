"""Quests (docs/QUESTS.md; from the client's quest handlers):

  0x3ea {eid64 npc, wstr text}           NPC dialogue text (opens the Dialogue window)
  0x2bf {eid64, i32 n, n x {wstr text, i32 id, i32 type}}  dialogue options; types
        7/8/9 send client 0x15c {i32 id} when clicked
  0x2c0 quest page (offer / in progress / ready / done), 0x2cb same layout = journal entry
  client 0x15d {i32 quest id} accept    -> 0x2c1 {i32 id, i32 date, u8 0} + 0x2cb
  client 0x160 / 0x161 continue / complete
  0x2cc progress {eid64, i32 id, wstr chat, bool8, wstr status, bool8, bool8 completed}
  0x2c5 {i32 id, u8 0, u8 abandoned} quest completed / removed
Reward choice (quests.json reward.choice): the turn-in shows the state-4 page whose reward
slots {i32 item id, i32 qty, i32 group, bool8} list the items (cached first with 0x2c7, an
item record, or the client asks 0x162 and shows nothing). Fixed items get a group each; the
choice items share one group. Clicking an item sends 0x163 {i32 quest id, i32 item id};
the server answers 0x2cf {quest id, item id} ("Selecting %s") and 0x2c8 {quest id, bool8 1}
(shows the Complete button). Clicking the chosen item again sends 0x163 again: 0x2d0 {quest id, item
id} takes the choice back and 0x2c8 {quest id, 0} hides Complete (verified live 2026-10-15).
Complete sends 0x161 {i32 quest id, i32 item id}.
XP is granted separately (0x3d5)."""
import struct
import time

OFFER, IN_PROGRESS, READY, DONE = 0, 1, 3, 4
# 0x2bf quest option types (verified live 2026-10-15, all clicks send 0x15c): the icon beside the
# option is the quest state's: 7 a green check (complete, turn in), 8 blue dots (in progress),
# 9 a yellow star (available).
OPTION_COMPLETE, OPTION_PROGRESS, OPTION_AVAILABLE = 7, 8, 9
OPTION_TYPES = (OPTION_COMPLETE, OPTION_PROGRESS, OPTION_AVAILABLE)
CLICK_OPTION, ACCEPT, CONTINUE, COMPLETE, REQUEST_INFO = 0x15C, 0x15D, 0x160, 0x161, 0x164
ABANDON, SHARE = 0x15F, 0x166          # {i32 quest id}: journal Abandon (after its confirm), Share
SELECT_REWARD, REWARD_INFO = 0x163, 0x162   # {i32 quest id, i32 item id} / {i32 quest id}
CLIENT_EVENTS = (CLICK_OPTION, ACCEPT, CONTINUE, COMPLETE, REQUEST_INFO, ABANDON, SHARE,
                 SELECT_REWARD, REWARD_INFO)
REWARD_ID_BASE = 970000
CHOICE_GROUP = 100


def reward_slots(q):
    """[(item id, name, qty, group, is choice)] for a quest's reward items."""
    r = q.get("reward", {})
    out = []
    for n, name in enumerate(r.get("items", [])):
        out.append((REWARD_ID_BASE + q["id"] * 20 + n, name, 1, n + 1, False))
    for n, name in enumerate(r.get("choice", [])):
        out.append((REWARD_ID_BASE + q["id"] * 20 + 10 + n, name, 1, CHOICE_GROUP, True))
    return out


def reward_selected(q, item_id):
    return _event(0x2CF, struct.pack("<ii", q["id"], item_id))


def reward_deselected(q, item_id):
    """0x2d0 {quest id, item id} (FUN_005971c0): "De-selecting %s", the item is unmarked."""
    return _event(0x2D0, struct.pack("<ii", q["id"], item_id))


def show_complete_button(q, show=True):
    return _event(0x2C8, struct.pack("<iB", q["id"], int(show)))


def abandoned(q):
    """0x2c3 {i32 quest id, u8 result, u8}: "Quest abandoned.", the quest leaves the journal."""
    return struct.pack("<HII", 2, 0x2C3, 6) + struct.pack("<iBB", q["id"], 0, 0)
END_CONVERSATION = 0x55F   # no payload: closes the Dialogue window, frees its options


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def npc_text(npc_eid, text):
    return _event(0x3EA, struct.pack("<Q", npc_eid) + _w(text))


DIALOG_RESPONSE = 0x15B             # client {i32 dialog index, u8 response index}


def responses(npc_eid, dialog_idx, texts):
    """0x2af MsgQuestDialogToClient: replaces the conversation replies (type-6 options)."""
    texts = (list(texts) + [""] * 5)[:5]
    return _event(0x2AF, struct.pack("<Qi", npc_eid, dialog_idx) + b"".join(_w(t) for t in texts))


def options(npc_eid, opts):
    """opts: [(text, id, type)]."""
    data = struct.pack("<Qi", npc_eid, len(opts))
    for text, oid, kind in opts:
        data += _w(text) + struct.pack("<ii", oid, kind)
    return _event(0x2BF, data)


def steps(q):
    """A quest's steps, in order. Each step is one of {"kill": {mob: n}},
    {"collect": {item: n}} or {"talk": mob}, plus "objective" (tracker text).
    A quest with a top-level "kill" is one kill step."""
    return q.get("steps") or [{"objective": q.get("objective", ""), "kill": q.get("kill", {})}]


def turn_in(q):
    """Mob template id of the NPC that takes the quest back (default: the giver)."""
    return q.get("turn_in", q.get("giver"))


def step_need(step):
    return sum((step.get("kill") or step.get("collect") or {}).values()) or 1


def step_count(step, prog, have):
    """Progress toward a step; have(item name) -> count in the bags."""
    if "collect" in step:
        return sum(min(have(name), n) for name, n in step["collect"].items())
    return prog["count"]


def step_done(step, prog, have):
    return step_count(step, prog, have) >= step_need(step)


def ready(q, prog, have):
    """All steps done: the quest can be turned in."""
    st = steps(q)
    return prog["step"] >= len(st) or (prog["step"] == len(st) - 1 and step_done(st[-1], prog, have))


def status_line(q, prog, have=lambda name: 0):
    st = steps(q)
    if prog["step"] >= len(st):
        return f"Return to {q.get('turn_in_name', 'the quest giver')}"
    step = st[prog["step"]]
    if "talk" in step:
        return step.get("objective", "")
    need = step_need(step)
    return f"{step.get('objective', '')} ({min(step_count(step, prog, have), need)}/{need})"


WHERE = None    # q -> (chunk x, chunk y, x, y, z) of the quest's turn-in NPC, or None (set by the server)


def page(q, npc_eid, state, prog=None, journal=False, have=lambda name: 0, rewards=False):
    """0x2c0 (dialogue page) or 0x2cb (journal entry). rewards: fill the reward slots (send
    their 0x2c7 item records first)."""
    slots = [(i, qty, g) for i, _, qty, g, _ in reward_slots(q)] if rewards else []
    slots += [(-1, 0, 0)] * (30 - len(slots))
    data = (struct.pack("<Qi", npc_eid, q["id"]) + _w(q["name"])
            + struct.pack("<iB", q.get("level", 1), 0)
            + _w(q.get("description", "")) + _w(q.get("summary", ""))
            + _w(q.get("accept_text", "")) + _w(status_line(q, prog or new_progress(), have))
            + struct.pack("<iii", state, q.get("reward", {}).get("coin", 0), 0)
            + struct.pack("<BBB", 1, 0, 0)
            + struct.pack("<qff", int(time.time()), -1.0, -1.0)
            + struct.pack("<iiB", 0, 0, 0)
            + struct.pack("<iiiii", *((WHERE and WHERE(q)) or (0, 0, 0, 0, 0)))
            + struct.pack("<iii", 0, -1, -1)
            + b"".join(struct.pack("<iiiB", i, qty, g, 0) for i, qty, g in slots))
    return _event(0x2CB if journal else 0x2C0, data)


def accepted(q):
    return _event(0x2C1, struct.pack("<iiB", q["id"], int(time.time()), 0))


def progress_update(q, source_eid, prog, completed, have=lambda name: 0):
    status = status_line(q, prog, have)
    return _event(0x2CC, struct.pack("<Qi", source_eid, q["id"]) + _w(status)
                  + struct.pack("<B", 1) + _w(status) + struct.pack("<BB", 0, int(completed)))


def finished(q):
    return _event(0x2C5, struct.pack("<iBB", q["id"], 0, 0))


# Quest icons over NPCs (decoded 2026-10-14): 0x560 {eid64, u8 type} shows one, 0x561 {eid64, u8}
# removes it if the type matches, 0x562 removes all, 0x563 {eid64} removes one entity's.
# type = sphere * 5 + state (client FX table FUN_0058df90: FXspells_QuestIcon<State>[Craft|Diplo]001fx).
ICON_SOON, ICON_AVAILABLE, ICON_IN_PROGRESS, ICON_DONE, ICON_LOW = 0, 1, 2, 3, 4
SPHERES = {"adventure": 0, "crafting": 1, "diplomacy": 2}
LOW_LEVELS = 10            # placeholder: a quest this many levels below the player is "low"


def icon_type(state, sphere="adventure"):
    return SPHERES.get(sphere, 0) * 5 + state


_BY_NPC = {}


def quests_of(quests, tpl):
    """[(key, quest)] in which the NPC template tpl is the giver or the turn-in NPC: an index
    built once per quest table (icons are worked out for every NPC in view)."""
    index = _BY_NPC.get(id(quests))
    if index is None or index[0] is not quests or index[1] != len(quests):
        by = {}
        for key, q in quests.items():
            if isinstance(q, dict):
                for t in {q.get("giver"), turn_in(q)}:
                    by.setdefault(t, []).append((key, q))
        _BY_NPC.clear()
        index = _BY_NPC[id(quests)] = (quests, len(quests), by)
    return index[2].get(tpl, [])


def npc_icon(quests, tpl, log, have, level):
    """The icon over the NPC with template tpl for a player (quest log, item counts, level), or
    None: something to hand in here beats a new quest, beats one in progress, beats a low one."""
    best = None
    rank = {ICON_DONE: 4, ICON_AVAILABLE: 3, ICON_IN_PROGRESS: 2, ICON_LOW: 1, ICON_SOON: 0}
    for key, q in quests_of(quests, tpl):
        if key in log.done:
            continue
        state = None
        if key in log.active:
            if ready(q, log.active[key], have) and turn_in(q) == tpl:
                state = ICON_DONE
            elif q.get("giver") == tpl or turn_in(q) == tpl:
                state = ICON_IN_PROGRESS
        elif q.get("giver") == tpl and all(r in log.done for r in q.get("requires", [])):
            if level < q.get("min_level", 0):
                state = ICON_SOON
            elif q.get("level", level) + LOW_LEVELS <= level:
                state = ICON_LOW
            else:
                state = ICON_AVAILABLE
        if state is not None and (best is None or rank[state] > rank[best[0]]):
            best = (state, q.get("sphere", "adventure"))
    return icon_type(*best) if best else None


def show_icon(eid, kind):
    return _event(0x560, struct.pack("<QB", eid, kind))


def clear_icon(eid):
    return _event(0x563, struct.pack("<Q", eid))


def new_progress():
    return {"step": 0, "count": 0}


class QuestLog:
    """A player's quests: active = {quest key: {"step": i, "count": n}};
    done = set of finished keys."""

    def __init__(self, data=None):
        data = data or {}
        # Older saves stored a plain kill count for the single step.
        self.active = {k: ({"step": 0, "count": v} if isinstance(v, int) else dict(v))
                       for k, v in data.get("active", {}).items()}
        self.done = set(data.get("done", []))

    def to_json(self):
        return {"active": self.active, "done": sorted(self.done)}
