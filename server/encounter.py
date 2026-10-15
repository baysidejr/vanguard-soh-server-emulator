"""The encounter display: the enemies a player is fighting, with their health and whom
they are attacking (docs/CREATURES.md "Encounter display"; client dispatcher FUN_004b4210).

The client keeps one main record for the player's current target (Target Display) and a list
of the other enemies in the fight (Encounter Display, "AntiGroupCombatInfo"). It does not
de-duplicate, so the server remembers what each client shows (state["encounter"]) and sends
only differences:
  0x3a1 main / 0x3b5 row add {eid64 entity, i32 state 0, wstr name, u8 hp%, eid64 its target,
        i32 ferocity 0}; 0x3a2 clears the main record; 0x3b7 {eid64} removes a row;
  0x3b9 {eid64, u8 hp%} health; 0x3ba {eid64, eid64 target or -1} target of target;
  0x3b6 {eid64, i32 1 "Dead!" / 2 "Lost!"} row text; 0x3c0 clears all rows;
  0x491 {eid64, i32 aggro (1 on you, 2 on someone else, 0 neutral), i32 con 0..7} the main
        target's aggro colour (only applied to the current offensive target)."""
import struct

NO_TARGET = 0xFFFFFFFFFFFFFFFF
DEAD, LOST = 1, 2


def _event(event_id, data=b""):
    return struct.pack("<HII", 2, event_id, len(data)) + data


def _w(text):
    return (text + "\0").encode("utf-16-le")


def hp_pct(npc):
    return max(0, min(100, npc.health * 100 // max(1, npc.max_health)))


def target_eid(npc):
    t = npc.aggro_on
    return t.char_id if t is not None else NO_TARGET


def add(npc, main):
    return _event(0x3A1 if main else 0x3B5, struct.pack("<Qi", npc.entity_id, 0) + _w(npc.name)
                  + struct.pack("<BQi", hp_pct(npc), target_eid(npc), 0))


def remove_row(eid):
    return _event(0x3B7, struct.pack("<Q", eid))


def clear_main():
    return _event(0x3A2)


def clear_rows():
    return _event(0x3C0)


def health(npc):
    return _event(0x3B9, struct.pack("<QB", npc.entity_id, hp_pct(npc)))


def target_of_target(npc):
    return _event(0x3BA, struct.pack("<QQ", npc.entity_id, target_eid(npc)))


def row_text(eid, code):
    return _event(0x3B6, struct.pack("<Qi", eid, code))


def aggro(npc, player, con):
    on = 1 if npc.aggro_on is player else (2 if npc.aggro_on is not None else 0)
    return _event(0x491, struct.pack("<Qii", npc.entity_id, on, con))


def con_of(player, npc):
    diff = npc.level - player.level_number
    return 4 if diff == 0 else max(0, min(7, 4 + (diff // 2 if diff > 0 else -((-diff + 1) // 2))))


def engaged(player, npcs):
    """The living NPCs fighting this player (it is on their hate list)."""
    return [n for n in npcs if n.alive and player.char_id in getattr(n, "hate", {})]


def sync(enc, player, npcs_by_eid):
    """Messages that bring the client's encounter display up to date. enc is the per-player
    memory {"main": eid or None, "rows": {eid: (hp, target)}, "main_seen": (hp, target)}."""
    out = []
    fighting = {n.entity_id: n for n in engaged(player, npcs_by_eid.values())}
    want_main = player.target if player.target in fighting else None
    rows = enc.setdefault("rows", {})
    # Main record.
    if enc.get("main") != want_main:
        if enc.get("main") is not None:
            old = npcs_by_eid.get(enc["main"])
            if old is not None and old.alive and old.aggro_on is None:
                # It stopped fighting (evaded): 0x3a2 leaves the target-of-target line and the
                # red name, so clear those first, while the record still exists (seen live 2026-10-15).
                out.append(target_of_target(old))
                out.append(aggro(old, player, con_of(player, old)))
            out.append(clear_main())
        if want_main is not None:
            if want_main in rows:
                out.append(remove_row(want_main))
                rows.pop(want_main)
            npc = fighting[want_main]
            out.append(add(npc, True))
            out.append(aggro(npc, player, con_of(player, npc)))
            enc["main_seen"] = (hp_pct(npc), target_eid(npc))
        enc["main"] = want_main
    elif want_main is not None:
        npc = fighting[want_main]
        seen = enc.get("main_seen", (None, None))
        if hp_pct(npc) != seen[0]:
            out.append(health(npc))
        if target_eid(npc) != seen[1]:
            out.append(target_of_target(npc))
            out.append(aggro(npc, player, con_of(player, npc)))
        enc["main_seen"] = (hp_pct(npc), target_eid(npc))
    # Rows: the other enemies.
    for eid in [e for e in rows if e not in fighting or e == want_main]:
        if eid not in fighting:
            npc = npcs_by_eid.get(eid)
            out.append(row_text(eid, DEAD if npc is None or not npc.alive else LOST))
        out.append(remove_row(eid))
        rows.pop(eid)
    for eid, npc in fighting.items():
        if eid == want_main:
            continue
        if eid not in rows:
            out.append(add(npc, False))
        else:
            hp, tgt = rows[eid]
            if hp != hp_pct(npc):
                out.append(health(npc))
            if tgt != target_eid(npc):
                out.append(target_of_target(npc))
        rows[eid] = (hp_pct(npc), target_eid(npc))
    return out
