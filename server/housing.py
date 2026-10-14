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
# Building Inventory tab: "Move Fixture to me" (move_tome_fixture_button, FUN_00476020) sends
# 0x465 {i32 fixture id} (the selected row; "Pickup Fixture" sends 0x462 the same way).
MOVE_TO_ME = 0x465
# The fixture's "Send To Owner" option (mo_fixture_option_send_to_owner, FUN_00476120) sends
# 0x463 {i32 fixture id}. Only trophies (placed by someone else) go back; the answers are notice
# 358 NoPermissionToSendFixture and 359 CantSendNotTrophy. No item here is a trophy.
SEND_TO_OWNER, NO_PERMISSION_TO_SEND, CANT_SEND_NOT_TROPHY = 0x463, 358, 359
SEND_TROPHIES = 0x8000                  # permission bit 15
# House chests (client chest dispatcher FUN_004733d0): 0x151 {chest id} open, 0x152 close,
# 0x155 {chest, bag item handle, count, slot} deposit, 0x157 {chest, chest item, count, container, slot}
# withdraw, 0x153 move inside. Server: 0x199 {chest id, capacity} opens "House Chest",
# 0x19f clear, 0x1a1 item (silent), 0x19e item (drawn), 0x1a0 refresh, 0x19c {item} removed, 0x19a close.
CHEST_OPEN, CHEST_CLOSE, CHEST_DEPOSIT, CHEST_WITHDRAW = 0x151, 0x152, 0x155, 0x157
# 0x153 {chest, chest item, count (the whole stack, or the split amount), slot}: an item dragged
# to another slot inside the chest (FUN_00471d00, from the drop handler FUN_00687a80).
CHEST_MOVE = 0x153
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
# Chest permissions (Manage Chest): 0x466 {chest id} opens it -> 0x468 reset, 0x469 per slot,
# 0x46b {chest id, wstr display name, wstr item name}. Each slot (0 View, 1 Deposit, 2 Withdrawal;
# VGUIBuildingInformationWnd.xml "Edit ... Permission") is its own permission: all players, all
# guild members (guild rank), a name list. "Edit Chest Permission" > Accept sends 0x467 {i32 chest
# id (-1 in practice: use the chest being managed), i32 slot, i32 permission id (0 = new),
# i32 guild rank, u32 (junk), bool8 all players, bool8 all guild, wstr ""}.
CHEST_MANAGE, CHEST_PERMISSION = 0x466, 0x467
CHEST_VIEW, CHEST_DEPOSIT_SLOT, CHEST_WITHDRAW_SLOT = 0, 1, 2
CLIENT_EVENTS = (INSPECT, BUY, BUILD, TEAR_DOWN, SELL, PICK_UP, NUDGE, CHEST_OPEN, CHEST_CLOSE, CHEST_DEPOSIT,
                 CHEST_WITHDRAW, UPKEEP_DEPOSIT, VIEW_CONSTRUCTION, ADD_MATERIAL, COMPLETE_CONSTRUCTION,
                 ABANDON_CONSTRUCTION, CHEST_MANAGE, CHEST_PERMISSION) + PERMISSION_EVENTS
# /transferplot <name>, then /transferplotconfirm accept: 0x5c6 {wstr name}. The plot (house,
# fixtures and chests included) goes to that player.
TRANSFER = 0x5C6
CLIENT_EVENTS = CLIENT_EVENTS + (TRANSFER, CHEST_MOVE)
# The client's own furniture placement: the bag menu's Place Fixture (FUN_00480b30, only inside a
# house) sends 0x461 {i32 item handle}; the server answers 0x459 MsgStringAndFloat {wstr prefab,
# f32} (FUN_0047d250), which spawns a local ghost of the prefab under the cursor. A left click
# sends 0x46d MsgSpawnFixture {i32 item handle, i32 building id, f32 x, y, z, i32 yaw, pitch,
# roll} (FUN_0047da50; fields registered by FUN_00473be0) with the ghost's pose.
PLACE_REQUEST, SPAWN_FIXTURE, PLACEMENT_PREVIEW = 0x461, 0x46D, 0x459
CLIENT_EVENTS = CLIENT_EVENTS + (PLACE_REQUEST, SPAWN_FIXTURE)
# Selecting a building on the plot window's Buildings tab (plot_selected_building_details,
# FUN_00476ce0) sends 0x474 {i32 building type}; the answer 0x474 has the 0x453 layout and lists
# the materials it needs as "%s ( %d )" (FUN_0047ed10).
BUILDING_DETAILS = 0x474
# Guild buildings (Admin tab). 0x47a {plot} toggles "guild usable" (toggle_building_guild_usable,
# FUN_00476a00) -> 0x47a {bool8} and notice 383 / 382. 0x47b {plot} (the accept button of
# BuildingGuildHeadquartersConfirm or ...RelinquishConfirm, FUN_00476a80 / FUN_00476b30) makes the
# plot the owner's guild headquarters, or clears it. The guild leader confirms: S->C 0x47c
# {i32 a, i32 b, wstr owner, bool8} opens BuildingGuildLeaderHeadquartersConfirm; the leader's
# Accept / Decline sends 0x47c {i32 a, i32 b, wstr "", bool8 accept} (FUN_0047d830 /
# FUN_0047d940) with a and b echoed. Here a is the plot id and b the guild id. 0x47b {i32 guild,
# bool8 hq} updates the window, 0x47d {i32, wstr guild name} names the HQ (strGuildHQName).
# The client's own tooltips give the rules (VGClient.int BuildingGuildHeadQuarters /
# BuildingGuildHeadQuartersRemove): the owner must be in a guild, the guild leader must be at the
# plot to confirm, one HQ per guild, existing permissions are replaced by guild access, the leader
# becomes co-owner, and only the leader can clear it (permissions are deleted again).
GUILD_USABLE, GUILD_HQ, HQ_LEADER_RESPONSE, HQ_NAME = 0x47A, 0x47B, 0x47C, 0x47D
NOW_GUILD_USABLE, NO_LONGER_GUILD_USABLE, HQ_ADDED, HQ_REMOVED, NO_GUILD = 383, 382, 28, 27, 26
CLIENT_EVENTS = CLIENT_EVENTS + (BUILDING_DETAILS, GUILD_USABLE, GUILD_HQ, HQ_LEADER_RESPONSE, MOVE_TO_ME,
                                 SEND_TO_OWNER)
VIEW_FIXTURE_LIST = 0x4000              # permission bit 14


def fixture_list(fixtures):
    """The Building Inventory list: 0x45a clear, 0x45c MsgBuildingFixtureInfo {i32 fixture id,
    bool8 chest, bool8, wstr name} per fixture (FUN_00483a90; the first bool is what the client
    counts for "Chests: (n of m)", FUN_00479e00; the second is copied to the row, meaning
    unknown), 0x45b rebuild the rows and the counts. The id is the fixture's object id, which
    Pickup Fixture (0x462) and Move Fixture to me (0x465) send back."""
    out = [_event(0x45A)]
    for f in fixtures:
        out.append(_event(0x45C, struct.pack("<iBB", FIXTURE_ID_BASE + f["id"], int("items" in f), 0) + _w(f["item"])))
    out.append(_event(0x45B))
    return out


def guild_usable(flag):
    return _event(GUILD_USABLE, struct.pack("<B", int(flag)))


def hq_state(guild_id, is_hq):
    return _event(GUILD_HQ, struct.pack("<iB", guild_id, int(is_hq)))


def hq_leader_confirm(pid, guild_id, owner):
    return _event(HQ_LEADER_RESPONSE, struct.pack("<ii", pid, guild_id) + _w(owner) + b"\0")


def parse_hq_response(data):
    """(plot id, guild id, accepted) from the leader's 0x47c, or None if malformed."""
    if len(data) < 11:
        return None
    a, b = struct.unpack_from("<ii", data)
    end = 8
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
        end += 2
    if end + 2 >= len(data):
        return None
    return a, b, bool(data[end + 2])


def hq_name(guild_name):
    return _event(HQ_NAME, struct.pack("<i", 0) + _w(guild_name))


def hq_guild_permission():
    """The permission an HQ starts with: guild members may enter (OpenDoor)."""
    return {"id": 1, "name": "Guild", "rank": 0, "flags": OPEN_DOOR, "all_players": False, "all_guild": True,
            "friends": []}


def placement_preview(prefab, scale=1.0):
    return _event(PLACEMENT_PREVIEW, _w(prefab) + struct.pack("<f", scale))


def parse_spawn_fixture(data):
    """(item handle, building id, (x, y, z), yaw) from a 0x46d payload, or None if short."""
    if len(data) < 32:
        return None
    handle, building, x, y, z, yaw = struct.unpack_from("<iifffi", data)
    return handle, building, (x, y, z), yaw


def chest_move(items, handle, count, slot, capacity, new_handle):
    """Move (or split off `count` of) a chest item [id, name, icon, qty, slot] to `slot`.
    A whole stack dropped on another item swaps the two. Returns the changed items, or []
    when nothing can move (unknown item, bad slot, a split onto a used slot)."""
    it = next((x for x in items if x[0] == handle), None)
    if it is None or not 0 <= slot < capacity or slot == it[4]:
        return []
    other = next((x for x in items if x[4] == slot), None)
    if 0 < count < it[3]:
        if other is not None:
            return []
        it[3] -= count
        new = [new_handle, it[1], it[2], count, slot]
        items.append(new)
        return [it, new]
    if other is not None:
        other[4] = it[4]
    it[4] = slot
    return [it] + ([other] if other is not None else [])
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
                        int(mine and not built), int(bool((state or {}).get("guild_usable"))))
    hq = (state or {}).get("hq_guild")
    data += struct.pack("<iBB", hq or 0, int(hq is not None), 0)
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


def construction_info(site_id, name, rows, event=0x453):
    """0x453 MsgConstructionInfoFull (FUN_00482ad0): {i32 site, i32 0, wstr project,
    i32 percent, 20 x (i32 resource id, wstr name, f32 needed, f32 added)}; opens the
    Building Construction window. With event BUILDING_DETAILS it is the Buildings tab preview."""
    data = struct.pack("<ii", site_id, 0) + _w(name) + struct.pack("<i", construction_percent(rows))
    for n in range(20):
        rid, rname, a, b = rows[n] if n < len(rows) else (0, "", 0, 0)
        data += struct.pack("<i", rid) + _w(rname) + struct.pack("<ff", float(b), float(a))
    return _event(event, data)


def close_construction():
    return _event(0x477)


def parse_permission(data):
    """0x470 / 0x472 -> {plot, id, name, rank, flags, all_players, all_guild}."""
    plot, pid = struct.unpack_from("<ii", data, 0)
    end = 8
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
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


CHEST_SLOT_NAMES = ("View", "Deposit", "Withdrawal")
# A chest slot's permission id: kept apart from building permission ids (1..10) because Add
# Player sends the same 0x46f {wstr name, i32 permission id, i32 0} for both; the name list is
# filled with 0x46f {permission id, friend id (row + 1), wstr name} (0x46a does not redraw it); 0x46e {permission id,
# friend id} removes one.
CHEST_PERM_ID_BASE = 1001


def chest_slot_of(perm_id):
    slot = perm_id - CHEST_PERM_ID_BASE
    return slot if 0 <= slot < len(CHEST_SLOT_NAMES) else None


def chest_friend(perm_id, row, name):
    return _event(0x46F, struct.pack("<ii", perm_id, row + 1) + _w(name))


def parse_chest_permission(data):
    """0x467 -> (chest id, slot, {rank, all_players, all_guild})."""
    cid, slot, _pid, rank = struct.unpack_from("<iiii", data, 0)
    return cid, slot, {"rank": rank, "all_players": bool(data[20]), "all_guild": bool(data[21])}


def chest_permissions(cid, chest, st=None):
    """0x468 reset, then 0x469 {chest id, slot, permission id, guild rank, u32 flags, bool8 all
    players, bool8 all guild, wstr name} and its 0x46a names for each slot that has a permission."""
    out = [_event(0x468)]
    for slot, p in sorted((chest.get("perms") or {}).items()):
        if not isinstance(p, dict):
            continue
        perm_id = CHEST_PERM_ID_BASE + int(slot)
        out.append(_event(0x469, struct.pack("<iiiiIBB", cid, int(slot), perm_id, p.get("rank", 0), 0,
                                             p.get("all_players", False), p.get("all_guild", False))
                          + _w(CHEST_SLOT_NAMES[int(slot)])))
        out += [chest_friend(perm_id, row, name) for row, name in enumerate(p.get("friends", []))]
    return out


def chest_info(cid, display_name, item_name):
    return _event(0x46B, struct.pack("<i", cid) + _w(display_name) + _w(item_name))


def _covers(p, name, owner_guild, mine):
    return bool(p.get("all_players")
                or name.lower() in [f.lower() for f in p.get("friends", [])]
                or (p.get("all_guild") and owner_guild is not None and mine is owner_guild))


def chest_allowed(st, chest, name, slot, guild_of=lambda n: None):
    """May `name` view (0), deposit into (1) or withdraw from (2) this chest? The plot owner
    always may; others need that slot's permission to cover them."""
    if st is None:
        return False
    if st.get("owner", "").lower() == name.lower():
        return True
    p = (chest.get("perms") or {}).get(str(slot))
    return isinstance(p, dict) and _covers(p, name, guild_of(st.get("owner", "")), guild_of(name))


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
    if is_hq_leader(st, name, mine):
        return True
    for p in st.get("permissions", []):
        covers = _covers(p, name, owner_guild, mine)
        if covers and p.get("flags", 0) & NO_ACCESS:
            return False
        if covers and p.get("flags", 0) & flag:
            return True
    return False


def is_hq_leader(st, name, guild):
    """Is `name` the leader of the guild whose headquarters this plot is (a co-owner)?"""
    if st is None or st.get("hq_guild") is None or guild is None or guild.get("id") != st["hq_guild"]:
        return False
    return any(m.lower() == name.lower() and r == HQ_LEADER_RANK for m, r in guild.get("members", {}).items())


HQ_LEADER_RANK = 10                    # guild.LEADER


def has_construction(flag):
    return _event(0x479, struct.pack("<B", int(flag)))
