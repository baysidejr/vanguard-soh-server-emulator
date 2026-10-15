"""Alternate advancement (AA): the "Alternate Advancement" window (searchKey _AA_window).

Decoded from the client (dispatcher FUN_0044ea00; full notes in docs/AA.md):

server -> client
  0x85d (no payload)  start the lists: empties the four lists (FUN_0044c6c0)
  0x85f MsgAlternateAdvancementAbilitiesAdd {i32 id, i32 list (0 General, 1 Archetype, 2 Class,
        3 Special), wstr title, wstr description, i32 rank, i32 max rank, i32 cost of the next
        rank (< 0 shows N/A), i32 minimum adventuring level, f32 refresh (<= 0 "Activated"),
        bool8 passive, wstr requirements text, bool8 eligible}; always appends
  0x85e (no payload)  end the lists: sort and show them
  0x860 {i32 id, i32 list, i32 new rank, i32 new cost}  an ability trained
  0x861 {i32 id, i32 list, bool8 eligible}  prerequisites met / no longer met
client -> server
  0x85a {i32 id}  Train (after the confirm popup), 0x85b /aatrain {wstr name upper-cased},
  0x85c /aalist (no payload), 0x851 /aaclear (no payload), 0x852 /aaadd {eid64 target, i32 n}
The client never asks for the lists, so the server sends them at spawn. Points available and
spent are MsgScore fields 25 and 26, the AA experience bar field 41. The client only marks an
ability trainable when it is eligible, the level is high enough, the points cover the cost and
the rank is below the maximum; the server checks all of that again.
"""
import struct

START, ADD, END, TRAINED, ELIGIBLE = 0x85D, 0x85F, 0x85E, 0x860, 0x861
TRAIN, TRAIN_NAME, CLEAR, GRANT, LIST = 0x85A, 0x85B, 0x851, 0x852, 0x85C
CLIENT_EVENTS = (TRAIN, TRAIN_NAME, CLEAR, GRANT, LIST)
LISTS = {"general": 0, "archetype": 1, "class": 2, "special": 3}
# AA experience (placeholders): from MIN_LEVEL on, SHARE of every adventuring experience award
# also goes to AA experience; XP_PER_POINT of it makes one point.
MIN_LEVEL = 10
SHARE = 0.25
XP_PER_POINT = 1000


def _event(event_id, data=b""):
    return struct.pack("<HI", 2, event_id) + struct.pack("<I", len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def abilities(content, klass_name=None):
    """The AA abilities for a class: every General / Archetype / Special entry and the Class
    entries whose "classes" include it."""
    out = []
    for a in content.get("abilities", []):
        if a.get("list") == "class" and klass_name not in a.get("classes", []):
            continue
        out.append(a)
    return out


def cost(a, rank):
    """Points for the next rank (-1 when maxed). "cost" is one number or one per rank."""
    if rank >= a.get("max_rank", 1):
        return -1
    c = a.get("cost", 1)
    return int(c[rank] if isinstance(c, list) else c)


def eligible(a, ranks):
    return all(ranks.get(int(r), 0) >= n for r, n in (a.get("requires") or {}).items())


def requirements_text(a, by_id):
    parts = [f"{by_id[int(r)]['title']} rank {n}" for r, n in (a.get("requires") or {}).items()
             if int(r) in by_id]
    return ("Requires " + ", ".join(parts)) if parts else ""


def ability_add(a, rank, ranks, by_id):
    return _event(ADD, struct.pack("<ii", a["id"], LISTS[a.get("list", "general")]) + _w(a["title"])
                  + _w(a.get("description", "")) + struct.pack("<iiiifB", rank, a.get("max_rank", 1),
                                                                cost(a, rank), a.get("level", MIN_LEVEL),
                                                                float(a.get("refresh", 0)),
                                                                int(a.get("passive", True)))
                  + _w(requirements_text(a, by_id)) + struct.pack("<B", int(eligible(a, ranks))))


def list_messages(abs_, ranks):
    by_id = {a["id"]: a for a in abs_}
    return ([_event(START)] + [ability_add(a, ranks.get(a["id"], 0), ranks, by_id) for a in abs_]
            + [_event(END)])


def trained(a, rank):
    return _event(TRAINED, struct.pack("<iiii", a["id"], LISTS[a.get("list", "general")], rank, cost(a, rank)))


def eligible_update(a, ok):
    return _event(ELIGIBLE, struct.pack("<iiB", a["id"], LISTS[a.get("list", "general")], int(ok)))


def train_error(a, rank, ranks, points, spent, level):
    """Why training the next rank is refused (None = allowed)."""
    if rank >= a.get("max_rank", 1):
        return f"{a['title']} is already at its highest rank."
    if level < a.get("level", MIN_LEVEL):
        return f"You must be level {a.get('level', MIN_LEVEL)} to train {a['title']}."
    if spent < 100 * LISTS[a.get("list", "general")]:
        return f"You must spend {100 * LISTS[a.get('list', 'general')]} AA points before training {a['title']}."
    if not eligible(a, ranks):
        return f"You do not meet the requirements for {a['title']}."
    if points < cost(a, rank):
        return f"You do not have enough AA points to train {a['title']}."
    return None


def stat_bonus(abs_, ranks):
    """{attribute: total} from the "stats" (per rank) of the trained abilities."""
    out = {}
    for a in abs_:
        r = ranks.get(a["id"], 0)
        for k, v in (a.get("stats") or {}).items():
            out[k] = out.get(k, 0) + int(v) * r
    return out


def gain(xp, aa_xp, aa_points, amount, level):
    """AA experience from an adventuring award: returns (aa_xp, aa_points, points gained)."""
    if level < MIN_LEVEL or amount <= 0:
        return aa_xp, aa_points, 0
    aa_xp += int(amount * SHARE)
    got = aa_xp // XP_PER_POINT
    return aa_xp - got * XP_PER_POINT, aa_points + got, got
