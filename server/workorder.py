"""Crafting work orders from task masters (docs/WORK_ORDERS.md; client dispatcher FUN_004bd850).

Task master NPCs have EntityTypes bit 0x200 and a dialogue option of type 4.
Client -> server:
  0x171 (none)    request work (dialogue option type 4 or the NPC mouse-over menu; uses the target)
  0x172 (none)    end requisition (Done buttons, closing the window) -> 0x4a4 code 5
  0x173 {i32 id}  select an available order -> 0x4a3 {id, code}, then 0x4a7 {order}
  0x174 {i32 id}  complete / turn in an active order -> 0x4a5 {id, code}
  0x175 {i32 id}  abandon -> 0x4a6 {id, code}
  0x178 {i32 id}  needed-items text request -> 0x4a9 {wstr, id}
Server -> client:
  0x4a1 (none) opens the window on the Available tab
  0x4a2 {i32 n, n x order} replaces the available list
  0x4a7 {order} adds an active order (Current tab and journal); ignored for an id it has
  0x4a8 {i32 id, i32} silently removes an active order
  0x4a3 select codes: 0 selected, 1 not requisitioning, 2 not available, 3 already completed,
        4 already on a work order, 0xff failed
  0x4a4 {u8}: 0 not a task master, 1 too far, 2 no work right now (window stays open),
        3 task master gone, 4 target a task master, 5 "Requisition ended.", 6 closes silently
  0x4a5 turn-in codes: 0 accepted, 1 not requisitioning, 2 not working on it, 3 need more items,
        4 return to the issuing task master, 5 complete others first, 6 trading, 0xff failed
  0x4a6 abandon codes: 0 abandoned, 1 talk to a task master, 2 not working on it, 0xff failed
Order record (MsgTaskMasterWorkOrder): wstr name, wstr description, i32 id, i32 icon,
  i32 con (8+ Trivial ... -8 or less Downright Impossible), i32 parent slot, wstr issued by,
  bool8 feeds another order, i32 orders needed, i32 recipes known, wstr needed items,
  wstr (unused), i32 crafting skill id (-1 none)."""
import struct

REQUEST, END, SELECT, COMPLETE, ABANDON, NEEDED = 0x171, 0x172, 0x173, 0x174, 0x175, 0x178
CLIENT_EVENTS = (REQUEST, END, SELECT, COMPLETE, ABANDON, NEEDED)
TASK_MASTER = 0x200                  # EntityTypes bit
OPTION_TYPE = 4                      # 0x2bf dialogue option type that sends 0x171
OPTION_ID = 9002
NOT_TASK_MASTER, TOO_FAR, NO_WORK, ENDED = 0, 1, 2, 5
OK, NOT_REQUISITIONING, NOT_AVAILABLE, ALREADY_DONE, ALREADY_WORKING = 0, 1, 2, 3, 4
NEED_ITEMS, WRONG_TASK_MASTER = 3, 4
NOT_WORKING = 2
FAILED = 0xFF


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def needed_text(wo):
    return ", ".join(f"{n} {name}" for name, n in wo["deliver"].items())


def con(skill, difficulty):
    """Difficulty colour: player skill against the order's difficulty, 5 points a step."""
    return max(-8, min(8, (skill - difficulty) // 5))


def record(wo, issuer, con_value=0, recipes_known=1):
    return (_w(wo["name"]) + _w(wo.get("description", "")) + struct.pack("<iiii", wo["id"], wo.get("icon", 443),
                                                                       con_value, 0)
            + _w(issuer) + struct.pack("<Bii", 0, 0, recipes_known) + _w(needed_text(wo)) + _w("")
            + struct.pack("<i", wo.get("skill", -1)))


def open_window():
    return _event(0x4A1)


def available(records):
    return _event(0x4A2, struct.pack("<i", len(records)) + b"".join(records))


def active(rec):
    return _event(0x4A7, rec)


def removed(wid):
    return _event(0x4A8, struct.pack("<ii", wid, 0))


def select_result(wid, code):
    return _event(0x4A3, struct.pack("<iB", wid, code))


def ended(code=ENDED):
    return _event(0x4A4, struct.pack("<B", code))


def complete_result(wid, code):
    return _event(0x4A5, struct.pack("<iB", wid, code))


def abandon_result(wid, code):
    return _event(0x4A6, struct.pack("<iB", wid, code))


def needed(wo):
    return _event(0x4A9, _w(needed_text(wo)) + struct.pack("<i", wo["id"]))
