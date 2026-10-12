"""Quests (docs/QUESTS.md; from the client's quest handlers):

  0x3ea {eid64 npc, wstr text}           NPC dialogue text (opens the Dialogue window)
  0x2bf {eid64, i32 n, n x {wstr text, i32 id, i32 type}}  dialogue options; types
        7/8/9 send client 0x15c {i32 id} when clicked
  0x2c0 quest page (offer / in progress / ready / done), 0x2cb same layout = journal entry
  client 0x15d {i32 quest id} accept    -> 0x2c1 {i32 id, i32 date, u8 0} + 0x2cb
  client 0x160 / 0x161 continue / complete
  0x2cc progress {eid64, i32 id, wstr chat, bool8, wstr status, bool8, bool8 completed}
  0x2c5 {i32 id, u8 0, u8 abandoned} quest completed / removed
XP is granted separately (0x3d5)."""
import struct
import time

OFFER, IN_PROGRESS, READY, DONE = 0, 1, 3, 4
OPTION_TYPE = 7
CLICK_OPTION, ACCEPT, CONTINUE, COMPLETE, REQUEST_INFO = 0x15C, 0x15D, 0x160, 0x161, 0x164
CLIENT_EVENTS = (CLICK_OPTION, ACCEPT, CONTINUE, COMPLETE, REQUEST_INFO)
END_CONVERSATION = 0x55F   # no payload: closes the Dialogue window, frees its options


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def npc_text(npc_eid, text):
    return _event(0x3EA, struct.pack("<Q", npc_eid) + _w(text))


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


def page(q, npc_eid, state, prog=None, journal=False, have=lambda name: 0):
    """0x2c0 (dialogue page) or 0x2cb (journal entry)."""
    data = (struct.pack("<Qi", npc_eid, q["id"]) + _w(q["name"])
            + struct.pack("<iB", q.get("level", 1), 0)
            + _w(q.get("description", "")) + _w(q.get("summary", ""))
            + _w(q.get("accept_text", "")) + _w(status_line(q, prog or new_progress(), have))
            + struct.pack("<iii", state, q.get("reward", {}).get("coin", 0), 0)
            + struct.pack("<BBB", 1, 0, 0)
            + struct.pack("<qff", int(time.time()), -1.0, -1.0)
            + struct.pack("<iiB", 0, 0, 0)
            + struct.pack("<iiiii", 0, 0, 0, 0, 0)
            + struct.pack("<iii", 0, -1, -1)
            + b"".join(struct.pack("<iiiB", -1, 0, 0, 0) for _ in range(30)))
    return _event(0x2CB if journal else 0x2C0, data)


def accepted(q):
    return _event(0x2C1, struct.pack("<iiB", q["id"], int(time.time()), 0))


def progress_update(q, source_eid, prog, completed, have=lambda name: 0):
    status = status_line(q, prog, have)
    return _event(0x2CC, struct.pack("<Qi", source_eid, q["id"]) + _w(status)
                  + struct.pack("<B", 1) + _w(status) + struct.pack("<BB", 0, int(completed)))


def finished(q):
    return _event(0x2C5, struct.pack("<iBB", q["id"], 0, 0))


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
