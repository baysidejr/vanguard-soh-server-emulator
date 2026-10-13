"""Player housing: plots, buying, building (docs/HOUSING.md; client dispatcher FUN_00483d60).

World objects are Engine.PlayerPlacedObject actors (zone.open_placed_object): a plot for
sale is a sign (m_BuildingType 1), a house is type 2; right-click Inspect sends 0x460.
Client -> server:
  0x460 {i32 object type, i32 object id} inspect
  0x481 {i32 plot id} buy (after the client's cost confirmation)
  0x479 {i32 plot id, i32 building type} build
  0x480 {i32 plot id} tear down        0x47f {i32 plot id} sell
Server -> client:
  0x454 MsgPlotInfoFull (plot), 0x455 MsgBuildingInfoFull (house), 0x458 open the window,
  0x479 {bool8} plot has construction; notices 0x0e: 0x170 PurchasedPlot, 0x173 SoldPlot,
  0x192 ConstrCompleted, 0x1a7 RemovedBldgFromPlot, 0x172 FirstSellBldgs, 0x16d OnePlotPerAcct."""
import struct
import time

INSPECT, BUY, BUILD, TEAR_DOWN, SELL = 0x460, 0x481, 0x479, 0x480, 0x47F
PICK_UP, NUDGE = 0x462, 0x464          # {i32 fixture id}; {i32 id, i32, f32 dx, dy, dz, i32 dyaw, dpitch, droll}
# House chests (client chest dispatcher FUN_004733d0): 0x151 {chest id} open, 0x152 close,
# 0x155 {chest, bag item handle, count, slot} deposit, 0x157 {chest, chest item, count, container, slot}
# withdraw, 0x153 move inside. Server: 0x199 {chest id, capacity} opens "House Chest",
# 0x19f clear, 0x1a1 item (silent), 0x19e item (drawn), 0x1a0 refresh, 0x19c {item} removed, 0x19a close.
CHEST_OPEN, CHEST_CLOSE, CHEST_DEPOSIT, CHEST_WITHDRAW = 0x151, 0x152, 0x155, 0x157
UPKEEP_DEPOSIT = 0x47E                 # {i32 plot id, i32 copper} -> 0x483 {i32 balance}, 0x0e 0x17c
# Construction (a building with "materials"): 0x479 starts it, 0x473 {plot} views it,
# 0x475 {construction id, bag item handle, row data, row index} adds a material,
# 0x478 {construction id} completes, 0x476 {construction id} abandons. The construction id is
# the plot id. Server: 0x453 the construction window, 0x477 closes it.
VIEW_CONSTRUCTION, ADD_MATERIAL, COMPLETE_CONSTRUCTION, ABANDON_CONSTRUCTION = 0x473, 0x475, 0x478, 0x476
# Building permissions (owner only): 0x470 create / 0x472 edit {i32 plot, i32 perm id, wstr name,
# i32 guild rank, u32 flags, bool8 all players, bool8 all guild}, 0x471 {plot, perm id} delete,
# 0x46f {wstr player, i32 perm id, i32 0} add a friend, 0x46e {perm id, friend row} remove one.
# Server: 0x456 one permission, 0x46f {perm id, friend id (row + 1, not 0), wstr name} one friend
# (0x457 does not fill the Edit Permission name list); 0x46e names the friend by that id.
PERM_CREATE, PERM_EDIT, PERM_DELETE, PERM_ADD_FRIEND, PERM_REMOVE_FRIEND = 0x470, 0x472, 0x471, 0x46F, 0x46E
PERMISSION_EVENTS = (PERM_CREATE, PERM_EDIT, PERM_DELETE, PERM_ADD_FRIEND, PERM_REMOVE_FRIEND)
OPEN_DOOR, MOVE_FIXTURE, PLACE_FIXTURE, PICKUP_FIXTURE, ALLOW_MODIFY, PAY_UPKEEP, MANAGE_CONSTRUCTION = (
    0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40)
VIEW, NO_ACCESS = 0x1000, 0x80000000
MAX_PERMISSIONS, MAX_FRIENDS = 10, 20
CLIENT_EVENTS = (INSPECT, BUY, BUILD, TEAR_DOWN, SELL, PICK_UP, NUDGE, CHEST_OPEN, CHEST_CLOSE, CHEST_DEPOSIT,
                 CHEST_WITHDRAW, UPKEEP_DEPOSIT, VIEW_CONSTRUCTION, ADD_MATERIAL, COMPLETE_CONSTRUCTION,
                 ABANDON_CONSTRUCTION) + PERMISSION_EVENTS
HOUSE_RADIUS = 900                     # "inside the house": this close to the plot centre
FIXTURE_ID_BASE = 0x5100000
PURCHASED, SOLD, BUILT, REMOVED, SELL_BUILDINGS_FIRST, ONE_PLOT = 0x170, 0x173, 0x192, 0x1A7, 0x172, 0x16D
SIGN_PREFAB = "Ra1_P1_C1_Markers_ForSaleSign"
UPKEEP_PERIOD = 7 * 86400              # upkeep is taken from the plot's upkeep bank once a week


def charge_upkeep(plot, st, now):
    """Take every upkeep payment that is due; a short balance goes negative and counts as
    a missed payment (shown in red / "missed payments"). Returns the number charged."""
    n = 0
    last = st.get("upkeep_paid", st.get("bought", now))
    while now - last >= UPKEEP_PERIOD:
        last += UPKEEP_PERIOD
        bal = st.get("upkeep_balance", 0) - plot.get("upkeep", 0)
        if bal < 0:
            st["missed"] = st.get("missed", 0) + 1
        st["upkeep_balance"] = bal
        n += 1
    st["upkeep_paid"] = last
    return n


REPOSSESS_AFTER = 4                    # missed weekly upkeep payments before the plot is taken back


def repossess_due(st):
    return st.get("missed", 0) >= REPOSSESS_AFTER


def returned_items(st):
    """Item names that go back to a repossessed plot's owner: its furniture and the
    contents of its chests."""
    out = []
    for f in st.get("fixtures", []):
        out.append(f["item"])
        out += [i["name"] if isinstance(i, dict) else i[1] for i in f.get("items", [])]
    return out


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def plot_info(pid, plot, state, mine):
    """0x454 for plot pid (content) with its runtime state (owner, building, bought)."""
    owner = (state or {}).get("owner", "")
    built = bool((state or {}).get("building"))
    x, y, z = plot["loc"]
    data = struct.pack("<ii", pid, pid) + _w(plot.get("name", "")) + _w(owner) + _w("")
    data += struct.pack("<iBB", plot["cost"], int(mine), int(not owner))
    last = int((state or {}).get("upkeep_paid", (state or {}).get("bought", 0)))
    data += struct.pack("<iiiiI", (state or {}).get("upkeep_balance", 0), plot.get("upkeep", 0), last,
                        last + UPKEEP_PERIOD if state else 0, int((state or {}).get("bought", 0)))
    data += struct.pack("<fffi", x, y, z, (state or {}).get("missed", 0))
    data += struct.pack("<BBBBBBBB", int(mine), 0, int(mine), int(mine), int(mine), int(mine),
                        int(mine and not built), 0)
    data += struct.pack("<iBB", 0, 0, 0)
    opts = (plot.get("buildings", []) + [None] * 10)[:10]
    for o in opts:
        if o is None:
            data += struct.pack("<iiiii", 0, 0, 0, 0, 0) + _w("")
        else:
            data += struct.pack("<iiiii", o["type"], 0, 0, o.get("fixtures", 0), o.get("chests", 0)) + _w(o["name"])
    return _event(0x454, data)


def building_info(pid, plot, state, mine):
    b = next((o for o in plot.get("buildings", []) if o["type"] == state["building"]), {})
    x, y, z = plot["loc"]
    return _event(0x455, struct.pack("<i", pid) + _w(b.get("name", "")) + _w(state["owner"]) + _w("")
                  + struct.pack("<BBBB", int(mine), int(mine), 0, 0)
                  + struct.pack("<Ifffii", int(state.get("built", time.time())), x, y, z,
                                b.get("fixtures", 0), b.get("chests", 0)))


def chest_open(cid, capacity):
    return _event(0x199, struct.pack("<ii", cid, capacity))


def chest_clear():
    return _event(0x19F)


def chest_item(record, draw=False):
    return _event(0x19E if draw else 0x1A1, record)


def chest_refresh():
    return _event(0x1A0)


def chest_removed(handle):
    return _event(0x19C, struct.pack("<i", handle))


def chest_close():
    return _event(0x19A)


def upkeep_balance(copper):
    return _event(0x483, struct.pack("<i", copper))


def show():
    return _event(0x458)


def construction_rows(materials, added, resource_id=None):
    """[(resource id, name, added, needed)] for a building's materials {name: qty}. The
    resource id is the item's template id (item field 1; resource_id(name)), which the
    client's material picker matches against the bags."""
    rid = resource_id or (lambda name: 0)
    return [(rid(name), name, added.get(name, 0), qty) for name, qty in materials.items()]


def construction_percent(rows):
    need = sum(r[3] for r in rows)
    return 100 if need <= 0 else int(100 * sum(min(r[2], r[3]) for r in rows) / need)


def construction_done(rows):
    return all(r[2] >= r[3] for r in rows)


def construction_info(site_id, name, rows):
    """0x453 MsgConstructionInfoFull (FUN_00482ad0): {i32 site, i32 0, wstr project,
    i32 percent, 20 x (i32 resource id, wstr name, f32 needed, f32 added)}; opens the
    Building Construction window."""
    data = struct.pack("<ii", site_id, 0) + _w(name) + struct.pack("<i", construction_percent(rows))
    for n in range(20):
        rid, rname, a, b = rows[n] if n < len(rows) else (0, "", 0, 0)
        data += struct.pack("<i", rid) + _w(rname) + struct.pack("<ff", float(b), float(a))
    return _event(0x453, data)


def close_construction():
    return _event(0x477)


def parse_permission(data):
    """0x470 / 0x472 -> {plot, id, name, rank, flags, all_players, all_guild}."""
    plot, pid = struct.unpack_from("<ii", data, 0)
    end = 8
    while data[end:end + 2] != b"\0\0":
        end += 2
    name = data[8:end].decode("utf-16-le", "replace")
    rank, flags = struct.unpack_from("<iI", data, end + 2)
    allp, allg = data[end + 10], data[end + 11]
    return {"plot": plot, "id": pid, "name": name, "rank": rank, "flags": flags,
            "all_players": bool(allp), "all_guild": bool(allg)}


def permission_message(p):
    return _event(0x456, struct.pack("<ii", 0, p["id"]) + _w(p.get("name", ""))
                  + struct.pack("<iIBB", p.get("rank", 0), p.get("flags", 0), p.get("all_players", False),
                                p.get("all_guild", False)))


def friend_message(perm_id, row, name):
    return _event(0x46F, struct.pack("<ii", perm_id, row + 1) + _w(name))


def allowed(st, name, flag, guild_of=lambda n: None):
    """May the character `name` do `flag` (a permission mask) on this plot? The owner may do
    anything; others need a permission entry that covers them (all players, the owner's guild
    (rank at least the entry's), or its friend list) with the flag and without NoAccess."""
    if st is None:
        return False
    if st.get("owner", "").lower() == name.lower():
        return True
    owner_guild = guild_of(st.get("owner", ""))
    mine = guild_of(name)
    for p in st.get("permissions", []):
        covers = (p.get("all_players")
                  or name.lower() in [f.lower() for f in p.get("friends", [])]
                  or (p.get("all_guild") and owner_guild is not None and mine is owner_guild))
        if covers and p.get("flags", 0) & NO_ACCESS:
            return False
        if covers and p.get("flags", 0) & flag:
            return True
    return False


def has_construction(flag):
    return _event(0x479, struct.pack("<B", int(flag)))
