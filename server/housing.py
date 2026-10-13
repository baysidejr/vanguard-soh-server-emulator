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
CLIENT_EVENTS = (INSPECT, BUY, BUILD, TEAR_DOWN, SELL, PICK_UP, NUDGE, CHEST_OPEN, CHEST_CLOSE, CHEST_DEPOSIT,
                 CHEST_WITHDRAW)
HOUSE_RADIUS = 900                     # "inside the house": this close to the plot centre
FIXTURE_ID_BASE = 0x5100000
PURCHASED, SOLD, BUILT, REMOVED, SELL_BUILDINGS_FIRST, ONE_PLOT = 0x170, 0x173, 0x192, 0x1A7, 0x172, 0x16D
SIGN_PREFAB = "Ra1_P1_C1_Markers_ForSaleSign"


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
    data += struct.pack("<iiiiI", plot.get("upkeep_balance", 0), plot.get("upkeep", 0), 0, 0,
                        int((state or {}).get("bought", 0)))
    data += struct.pack("<fffi", x, y, z, 0)
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


def show():
    return _event(0x458)


def has_construction(flag):
    return _event(0x479, struct.pack("<B", int(flag)))
