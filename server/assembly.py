"""Assembly crafting (docs/ASSEMBLY.md): combine finished components into an item.

Client -> server (zone): 0x11f assemble {5 x (i32 recipe id, i32 item handle, i32 qty)};
  0x121 {i32 tree node} open a recipe-tree node; 0x122 {recipe} recipe details;
  0x123 {recipe} item templates missing; 0x124 {recipe} which bag items fit;
  trainer: 0x16e begin, 0x170 {recipe} buy, 0x16f done.
Server -> client: 0x34c learn a recipe silently / 0x34d with "New assembly recipe" text
  (MsgAddAssemblyRecipe); 0x350 {i32 n, n x (wstr name, i32 node, i32 parent)} tree;
  0x351 recipe details; 0x352 {recipe} re-check templates; 0x353 item template (item record
  with field 1 = template id); 0x354 {i32 n, n x (i32 item handle, i32 recipe)} candidates;
  0x34b {wstr, f32 seconds} timer; 0x349 success; 0x34a {u8} failure (8 wrong station, 9 too far).
  Trainer: dialogue option 0x2b8, 0x49c begin, 0x49d {i32 n, n x (wstr name, i32 id, i32 icon,
  f32 cost, wstr description)}, 0x49e {id, u8 result}, 0x49f {u8} end.
Stations have EntityTypes 0x800000 (the client opens its Assembly page without asking the
server); trainers 0x100000. Ingredients are matched on item field 1 = template id."""
import struct

ASSEMBLE, TREE, DETAILS, TEMPLATES, CANDIDATES = 0x11F, 0x121, 0x122, 0x123, 0x124
TRAIN_BEGIN, TRAIN_DONE, TRAIN_BUY = 0x16E, 0x16F, 0x170
CLIENT_EVENTS = (ASSEMBLE, TREE, DETAILS, TEMPLATES, CANDIDATES, TRAIN_BEGIN, TRAIN_DONE, TRAIN_BUY)
STATION, TRAINER = 0x800000, 0x100000
OPTION = 0x2B8
ROOT_NODE = 900000
FAILED, NOTHING, NO_SKILL, NO_KNOWLEDGE, BUSY, WRONG_STATION, TOO_FAR = 1, 2, 4, 5, 7, 8, 9


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def recipe_record(r, template_id):
    """MsgAddAssemblyRecipe for content r: {name, id, reward, ingredients [{item, qty}]}."""
    data = (_w(r["name"]) + _w(r.get("description", "")) + struct.pack("<iiii", 0, r["id"],
                                                                      template_id(r["reward"]), 0))
    ings = (r["ingredients"] + [None] * 5)[:5]
    for ing in ings:
        if ing is None:
            data += struct.pack("<iiB", -1, 0, 0) + _w("")
        else:
            data += struct.pack("<iiB", template_id(ing["item"]), ing.get("qty", 1), 1) + _w(ing["item"])
    return data


def learn(r, template_id, announce=False):
    return _event(0x34D if announce else 0x34C, recipe_record(r, template_id))


def details(r, template_id):
    return _event(0x351, recipe_record(r, template_id))


def recheck(rid):
    return _event(0x352, struct.pack("<i", rid))


def template(record):
    return _event(0x353, record)


def tree(nodes):
    """nodes: [(name, node id, parent id)]."""
    return _event(0x350, struct.pack("<i", len(nodes))
                  + b"".join(_w(n) + struct.pack("<ii", nid, parent) for n, nid, parent in nodes))


def candidates(pairs):
    """pairs: [(item handle, recipe id)]."""
    return _event(0x354, struct.pack("<i", len(pairs)) + b"".join(struct.pack("<ii", h, r) for h, r in pairs))


def timer(text, seconds):
    return _event(0x34B, _w(text) + struct.pack("<f", float(seconds)))


def success():
    return _event(0x349)


def failure(code):
    return _event(0x34A, struct.pack("<B", code))


def trainer_begin(offers):
    """offers: [(name, recipe id, icon, cost, description)]."""
    data = struct.pack("<i", len(offers))
    for name, rid, icon, cost, desc in offers:
        data += _w(name) + struct.pack("<iif", rid, icon, float(cost)) + _w(desc)
    return [_event(0x49C), _event(0x49D, data)]


def trainer_result(rid, code):
    return _event(0x49E, struct.pack("<iB", rid, code))


def trainer_end(reason=5):
    return _event(0x49F, struct.pack("<B", reason))
