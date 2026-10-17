"""Unit tests for the message builders and rules of the newer systems (no client needed)."""
import json
import os
import struct
import unittest
import unittest.mock

import assembly
import bugs
import combat
import encounter
import fishing
import forms
import grouploot
import housing
import mail
import market
import pets
import reactions
import songs
import titles
import travel
import shutil
import types
import vgmsg
import zone


def _w(text):
    return (text + "\0").encode("utf-16-le")


def payload(msg):
    """(event id, data) of a type-2 zone event."""
    _t, eid, n = struct.unpack_from("<HII", msg)
    return eid, msg[10:10 + n]


class MailTests(unittest.TestCase):
    def test_parse_send(self):
        data = (bytes(8) + _w("Justins") + _w("Hi") + _w("Body text")
                + struct.pack("<Bqi", 1, 120, 10011))
        self.assertEqual(mail.parse_send(data), ("Justins", "Hi", "Body text", True, 120, 10011))

    def test_message_layout(self):
        m = mail.new(7, "Ranger", "S", "B", coin=5, cod=0)
        eid, data = payload(mail.message(m))
        self.assertEqual(eid, 0x515)
        coin, cod, _x, mid = struct.unpack_from("<qqii", data)
        self.assertEqual((coin, cod, mid), (5, 0, 7))


class MarketTests(unittest.TestCase):
    def test_parse_search(self):
        data = bytes(12) + _w("Copper") + _w("") + struct.pack("<iihh", 0, 0, 5, 20)
        self.assertEqual(market.parse_search(data), ("Copper", "", 5, 20))

    def test_parse_rarity(self):
        tail = struct.pack("<iihhhhhhh", 0, 0, 5, 20, 0, 1, -1, 0xFF, 7) + struct.pack("<Bh", 0, -1)
        self.assertEqual(market.parse_rarity(bytes(12) + _w("Copper") + _w("") + tail), 7)
        tail = struct.pack("<iihhhhhhh", 0, 0, 0, 0, 0, 1, -1, 0xFF, 0xFF) + struct.pack("<Bh", 0, -1)
        self.assertIsNone(market.parse_rarity(bytes(12) + _w("") + _w("") + tail))

    def test_record_has_expiry(self):
        rec = market.record({"id": 9, "name": "X", "seller": "Y", "price": 40, "posted": 1000})
        self.assertIn(struct.pack("<I", 1000 + market.DURATION), rec)


class HousingTests(unittest.TestCase):
    def test_chest_permissions(self):
        st = {"owner": "Ranger"}
        chest = {"items": [], "perms": {"0": {"all_players": True}, "1": {"friends": ["Justins"]}}}
        self.assertTrue(housing.chest_allowed(st, chest, "ranger", housing.CHEST_WITHDRAW_SLOT))
        self.assertTrue(housing.chest_allowed(st, chest, "Anyone", housing.CHEST_VIEW))
        self.assertTrue(housing.chest_allowed(st, chest, "justins", housing.CHEST_DEPOSIT_SLOT))
        self.assertFalse(housing.chest_allowed(st, chest, "Anyone", housing.CHEST_DEPOSIT_SLOT))
        self.assertFalse(housing.chest_allowed(st, chest, "Justins", housing.CHEST_WITHDRAW_SLOT))
        msgs = housing.chest_permissions(77, chest)
        self.assertEqual([struct.unpack_from("<I", m, 2)[0] for m in msgs], [0x468, 0x469, 0x469, 0x46F])
        self.assertEqual(struct.unpack_from("<iii", msgs[1], 10), (77, 0, housing.CHEST_PERM_ID_BASE))
        # Captured 0x467 (All Players ticked, Accept): chest -1, slot 0, junk flags.
        data = bytes.fromhex("ffffffff000000000000000000000000b010d84f01000000")
        self.assertEqual(housing.parse_chest_permission(data), (-1, 0, {"rank": 0, "all_players": True, "all_guild": False}))

    def test_upkeep_charges_each_week(self):
        st = {"bought": 0, "upkeep_balance": 120}
        self.assertEqual(housing.charge_upkeep({"upkeep": 50}, st, 3 * housing.UPKEEP_PERIOD + 5), 3)
        self.assertEqual(st["upkeep_balance"], -30)
        self.assertEqual(st["missed"], 1)

    def test_construction_progress(self):
        rows = housing.construction_rows({"Rough Stone": 2, "Tattered Cloth": 2}, {"Rough Stone": 2}, len)
        self.assertEqual(rows, [(11, "Rough Stone", 2, 2), (14, "Tattered Cloth", 0, 2)])
        self.assertEqual(housing.construction_percent(rows), 50)
        self.assertFalse(housing.construction_done(rows))
        eid, data = payload(housing.construction_info(101, "Home", rows))
        self.assertEqual((eid, struct.unpack_from("<iiI", data)[:2]), (0x453, (101, 0)))

    def test_permissions(self):
        st = {"owner": "Ranger", "permissions": [
            {"id": 1, "flags": housing.PLACE_FIXTURE | housing.PICKUP_FIXTURE, "friends": ["Justins"]},
            {"id": 2, "flags": housing.NO_ACCESS, "friends": ["Griefer"]}]}
        self.assertTrue(housing.allowed(st, "ranger", housing.PAY_UPKEEP))           # owner
        self.assertTrue(housing.allowed(st, "Justins", housing.PLACE_FIXTURE))
        self.assertFalse(housing.allowed(st, "Justins", housing.PAY_UPKEEP))
        self.assertFalse(housing.allowed(st, "Griefer", housing.PLACE_FIXTURE))
        self.assertFalse(housing.allowed(st, "Stranger", housing.VIEW))

    def test_parse_permission(self):
        data = struct.pack("<ii", 101, 0) + _w("Friends") + struct.pack("<iIBB", 0, 0x0C, 0, 1)
        p = housing.parse_permission(data)
        self.assertEqual((p["plot"], p["name"], p["flags"], p["all_guild"]), (101, "Friends", 0x0C, True))
        self.assertEqual(payload(housing.permission_message(p))[0], 0x456)

    def test_repossession(self):
        st = {"bought": 0, "upkeep_balance": 0}
        housing.charge_upkeep({"upkeep": 50}, st, 4 * housing.UPKEEP_PERIOD + 1)
        self.assertTrue(housing.repossess_due(st))
        st = {"fixtures": [{"item": "Storage Chest", "items": [{"name": "Rough Stone"}]}]}
        self.assertEqual(housing.returned_items(st), ["Storage Chest", "Rough Stone"])

    def test_plot_info_starts_with_ids(self):
        plot = {"name": "P", "loc": [0, 0, 0], "cost": 1000, "buildings": []}
        eid, data = payload(housing.plot_info(101, plot, None, False))
        self.assertEqual(eid, 0x454)
        self.assertEqual(struct.unpack_from("<ii", data), (101, 101))


class AssemblyTests(unittest.TestCase):
    def test_categories_build_a_chain(self):
        msgs, ids = assembly.categories([("Jewelry", "Rings", "Copper", "All")])
        self.assertEqual(len(msgs), 5)                     # root + 4 levels
        self.assertEqual(payload(msgs[0])[0], 0x2AC)
        leaf = ids[("Jewelry", "Rings", "Copper", "All")]
        parent = ids[("Jewelry", "Rings", "Copper")]
        _eid, data = payload(msgs[-1])
        self.assertTrue(data.endswith(struct.pack("<ii", leaf, parent)))

    def test_trainer_list_is_count_prefixed(self):
        _start, lst = assembly.trainer_begin([("Ring", 1, 2, 3.0, "d")])
        self.assertEqual(struct.unpack_from("<i", payload(lst)[1])[0], 1)


class MiscTests(unittest.TestCase):
    def test_game_clock_in_range(self):
        _t, eid, _n = struct.unpack_from("<HII", titles.game_clock(titles.EPOCH + 3600))
        secs, day = struct.unpack_from("<ii", titles.game_clock(titles.EPOCH + 3600), 10)
        self.assertEqual(eid, titles.CLOCK_EVENT)
        self.assertTrue(0 <= secs < 86400 and day >= 0)

    def test_fishing_event_layout(self):
        eid, data = payload(fishing.event(5, fishing.PULL, 2))
        self.assertEqual((eid, struct.unpack("<Qii", data)), (0x59C, (5, 9, 2)))

    def test_pet_health_byte(self):
        class P:
            health, max_health = 150, 300
        self.assertEqual(payload(pets.health(P()))[1], bytes([127]))


class GroupLootTests(unittest.TestCase):
    class P:
        def __init__(self, name, cid):
            self.name, self.char_id, self.group = name, cid, None

    class G:
        def __init__(self, members):
            self.leader, self.members = members[0], members

    class N:
        def __init__(self, killer):
            self.killer = killer

    def group(self, mode):
        a, b, c = self.P("A", 1), self.P("B", 2), self.P("C", 3)
        g = self.G([a, b])
        a.group = b.group = g
        grouploot.settings(g)["mode"] = mode
        return a, b, c, g

    def test_mode_message_round_trips(self):
        a, b, c, g = self.group(grouploot.MASTER_LOOTER)
        eid, data = payload(grouploot.mode_message(g))
        self.assertEqual(eid, 0x6C8)
        self.assertEqual(grouploot.parse_set_mode(data), (1, 2, grouploot.DEFAULT_RARITY, False, False))

    def test_outsiders_and_master_looter(self):
        a, b, c, g = self.group(grouploot.MASTER_LOOTER)
        npc = self.N(b)
        self.assertEqual(grouploot.may_loot(c, npc), grouploot.NO_PERMISSION)
        self.assertIsNone(grouploot.may_loot(a, npc))                    # A is master looter
        self.assertEqual(grouploot.may_loot(b, npc), grouploot.NO_PERMISSION)
        npc.open_to_group = True
        self.assertIsNone(grouploot.may_loot(b, npc))

    def test_round_robin_turns(self):
        a, b, c, g = self.group(grouploot.ROUND_ROBIN)
        self.assertEqual([grouploot.next_turn(g).name for _ in range(3)], ["A", "B", "A"])

    def test_solo_kill_belongs_to_killer(self):
        c, d = self.P("C", 3), self.P("D", 4)
        self.assertIsNone(grouploot.may_loot(c, self.N(c)))
        self.assertEqual(grouploot.may_loot(d, self.N(c)), grouploot.NO_PERMISSION)

    def test_need_beats_greed(self):
        self.assertEqual(grouploot.resolve({"A": (False, 99), "B": (True, 3), "C": None}), ("B", True, 3))
        self.assertIsNone(grouploot.resolve({"A": None}))

    def test_coin_text_and_split(self):
        self.assertEqual(grouploot.coin_text(12345), "1 gold, 23 silver, 45 copper")
        self.assertEqual(grouploot.split_coin(10, 3), [4, 3, 3])

    def test_rarity_threshold(self):
        self.assertTrue(grouploot.qualifies(3, grouploot.DEFAULT_RARITY))      # Rare >= Uncommon
        self.assertFalse(grouploot.qualifies(grouploot.COMMON, grouploot.DEFAULT_RARITY))
        self.assertEqual(grouploot.rarity_index(None), 6)                       # mundane
        self.assertEqual([grouploot.rarity_wire(n) for n in ("mundane", "uncommon", "legendary")], [8, 6, 1])


class SteerTests(unittest.TestCase):
    def npc(self, blocked):
        n = combat.Npc(1, "Rat", 1, "x")
        n.location, n.blocked = (0.0, 0.0, 0.0), blocked
        return n

    def test_goes_around_a_rock(self):
        # A rock straight ahead on +x: the NPC turns away from it.
        n = self.npc(lambda x, y, z: 50 < x < 200 and abs(y) < 60)
        ux, uy = combat.steer(n, 1.0, 0.0, 20.0)
        self.assertNotAlmostEqual(uy, 0.0)

    def test_clear_way_is_straight(self):
        self.assertEqual(combat.steer(self.npc(lambda x, y, z: False), 1.0, 0.0, 20.0), (1.0, 0.0))

    def test_boxed_in_stops(self):
        n = self.npc(lambda x, y, z: (x, y) != (0.0, 0.0))
        self.assertEqual(combat.steer(n, 1.0, 0.0, 20.0), (None, None))


class ReactionTests(unittest.TestCase):
    def test_activate_on_dead_enemy(self):
        import login_stub, time
        sent = []
        npc = types.SimpleNamespace(alive=False)
        state = {"player": types.SimpleNamespace(abilities=[]), "send": sent.append,
                 "reactions": {7: {"ends": time.time() + 5, "target": npc, "ability": 1}}}
        login_stub.activate_reaction(state, None, 7)
        self.assertEqual(sent[0], reactions.result(reactions.TARGET_DEAD))
        self.assertEqual(sent[1], reactions.close_reaction(7))
        self.assertEqual(state["reactions"], {})

    CHAINS = {"Warrior": [{"opener": "A", "steps": ["B"], "finisher": "C", "window": 5}]}
    ABILITIES = [(1, 101, "A"), (2, 102, "B"), (3, 103, "C"), (4, 104, "D")]

    def chains(self):
        return reactions.class_chains(self.CHAINS, "Warrior", self.ABILITIES)

    def test_chain_flow(self):
        ch = self.chains()
        self.assertEqual(ch, [{"ids": [101, 102, 103], "window": 5}])
        self.assertEqual(reactions.next_step(ch, 101), (102, reactions.CHAIN_STEP, 5))
        self.assertEqual(reactions.next_step(ch, 102), (103, reactions.FINISHER, 5))
        self.assertIsNone(reactions.next_step(ch, 103))
        self.assertEqual([reactions.flags(ch, a) for a in (101, 102, 103, 104)], [3, 2, 2, 0])

    def test_define_layout(self):
        eid, data = payload(reactions.define(self.chains()[0]))
        self.assertEqual(eid, 0x268)
        self.assertEqual(struct.unpack("<14i", data),
                         (0, 0, 101, 101, 102, 102, -1, -1, -1, -1, -1, -1, 103, 103))

    def test_open_is_33_bytes(self):
        rid, msg = reactions.open_reaction(7, 102, 5.0)
        eid, data = payload(msg)
        self.assertEqual((eid, len(data)), (0x391, 33))
        self.assertEqual(struct.unpack_from("<Qii", data), (7, rid, 102))


class HateTests(unittest.TestCase):
    class P:
        def __init__(self, cid):
            self.char_id, self.health, self.name = cid, 100, str(cid)

    def test_switch_needs_ten_percent_more(self):
        npc, a, b = combat.Npc(1, "Rat", 1, "x"), self.P(1), self.P(2)
        combat.add_hate(npc, a, 100)
        combat.add_hate(npc, b, 105)
        self.assertIs(npc.aggro_on, a)
        combat.add_hate(npc, b, 10)
        self.assertIs(npc.aggro_on, b)

    def test_taunt_and_next_target(self):
        npc, a, b = combat.Npc(1, "Rat", 1, "x"), self.P(1), self.P(2)
        combat.add_hate(npc, a, 100)
        combat.taunt(npc, b)
        self.assertIs(npc.aggro_on, b)
        b.health = 0
        self.assertIs(combat.next_target(npc), a)


class EncounterTests(unittest.TestCase):
    class P:
        char_id, health, name, level_number, target = 7, 100, "P", 10, None

    def npc(self, eid):
        n = combat.Npc(eid, "Rat", 1, "x")
        n.level = 10
        return n

    def test_main_rows_and_removal(self):
        p, a, b = self.P(), self.npc(1), self.npc(2)
        npcs = {1: a, 2: b}
        enc = {}
        self.assertEqual(encounter.sync(enc, p, npcs), [])            # not fighting
        combat.add_hate(a, p, 5)
        combat.add_hate(b, p, 5)
        p.target = 1
        ids = [payload(m)[0] for m in encounter.sync(enc, p, npcs)]
        self.assertEqual(ids, [0x3A1, 0x491, 0x3B5])                   # main, its aggro, one row
        self.assertEqual(encounter.sync(enc, p, npcs), [])            # nothing changed
        b.health = 0
        ids = [payload(m)[0] for m in encounter.sync(enc, p, npcs)]
        self.assertEqual(ids, [0x3B6, 0x3B7])                          # "Dead!", row removed
        a.health = 50
        self.assertEqual([payload(m)[0] for m in encounter.sync(enc, p, npcs)], [0x3B9])

    def test_evade_clears_target_line_before_the_record(self):
        p, a = self.P(), self.npc(1)
        npcs, enc = {1: a}, {}
        combat.add_hate(a, p, 5)
        a.aggro_on, p.target = p, 1
        encounter.sync(enc, p, npcs)
        a.hate.clear()
        a.aggro_on = None                         # gave up (leash)
        ids = [payload(m)[0] for m in encounter.sync(enc, p, npcs)]
        self.assertEqual(ids, [0x3BA, 0x491, 0x3A2])   # target line, aggro, then the clear


class TravelJournalTests(unittest.TestCase):
    def test_login_messages(self):
        spawns = [({"mob": "m", "x": 1, "y": 2, "z": 3}, {"name": "Orin", "title": "Merchant", "merchant": "camp"}),
                  ({"mob": "w", "x": 0, "y": 0}, {"name": "Wolf"}),
                  ({"mob": "f", "x": 5, "y": 6, "z": 7}, {"name": "Forge", "station": True})]
        msgs = travel.login_messages(spawns, (-19, 12), house=("Home", [9, 9, 9], (-19, 12)))
        ids = [payload(m)[0] for m in msgs]
        self.assertEqual(ids, [0x2AE, 0x2AE, 0x382, 0x382, 0x382])
        self.assertIn("Orin".encode("utf-16-le"), msgs[2])
        self.assertEqual(struct.unpack_from("<i", msgs[-1], len(msgs[-1]) - 9)[0], travel.HOUSING)
        self.assertEqual(payload(travel.login_messages([], (0, 0))[0])[0], 0x2AE)   # built-ins still made
        known = {travel.ENTRY_ID_BASE + 2}
        ids = [payload(m)[0] for m in travel.login_messages(spawns, (-19, 12), known=known)]
        self.assertEqual(ids, [0x2AE, 0x382])                       # only the forge is known

    def test_discover(self):
        spawns = [({"mob": "m", "x": 1000, "y": 0}, {"name": "Orin", "merchant": "camp"}),
                  ({"mob": "f", "x": 5000, "y": 0}, {"name": "Forge", "station": True})]
        sites = travel.chunk_sites(spawns)
        self.assertEqual([s[3] for s in travel.discover(sites, set(), (0, 0))], ["Orin"])
        self.assertEqual(travel.discover(sites, {sites[0][0]}, (0, 0)), [])


class BugReportTests(unittest.TestCase):
    def test_parse_captured_submit(self):
        data = "Wolf".encode("utf-16-le") + bytes(2) + struct.pack("<iii", 11, 1, 0)
        self.assertEqual(bugs.parse(data), {"description": "Wolf", "category": "Gameplay: Combat",
                                            "severity": "Standard", "reproducibility": "Every time"})
        self.assertEqual(bugs.parse(bytes(2) + struct.pack("<iii", 99, -1, 7))["category"], "Unknown Category")

    def test_parse_captured_quest_feedback(self):
        data = bytes.fromhex("ffffffff46007500 6e0020007100 75006500 73007400 0000".replace(" ", "")) + struct.pack("<6i", 1, 1, 1, 1, 1, 0)
        r = bugs.parse_quest_feedback(data)
        self.assertEqual((r["quest_id"], r["comments"], r["challenge"], r["friends_needed"], r["fun"]),
                         (-1, "Fun quest", "Just right", "One", "A - Excellent"))


class SongTests(unittest.TestCase):
    PARTS = {"Valor": {"part": "melody", "stat": "strength", "bonus": 6, "energy": 2},
             "Charge": {"part": "verse", "bonus": 3, "energy": 1},
             "Rest": {"part": "rest", "energy": 1}}

    def test_compose_round_trip_and_rules(self):
        parts = songs.part_abilities(self.PARTS)
        ids = {aid for _, aid, _, _ in parts}
        melody, verse, rest = (aid for _, aid, _, _ in parts)
        song = {"name": "War Song", "description": "Loud", "melody": melody,
                "parts": {p: [-1] * 6 for p in songs.SLOT_PARTS}}
        song["parts"]["verse"][0] = verse
        song["parts"]["chorus"][1] = rest
        msg = songs.compose(1, song)
        self.assertEqual(payload(msg)[0], 0x573)
        # The client's 0x578 has the same layout as the server's 0x573.
        self.assertEqual(songs.parse_compose(msg[10:]), song)
        self.assertIsNone(songs.problem(song, ids))
        self.assertEqual(songs.problem(dict(song, melody=-1), ids), "Your song needs a melody.")
        self.assertEqual(songs.problem(dict(song, name=""), ids), "Your song needs a name.")
        fx = songs.effect(song, {aid: spec for _, aid, _, spec in parts})
        self.assertEqual((fx["stat"], fx["bonus"], fx["energy"]), ("strength", 9, 2))   # 2 + 1 - rest 1

    def test_energy_drain_and_regen(self):
        self.assertEqual(songs.energy_step(10, 100, 3), (7, True))
        self.assertEqual(songs.energy_step(2, 100, 3), (2, False))         # out of energy: the song stops
        self.assertEqual(songs.energy_step(99, 100, None), (100, False))   # not singing: regenerate


class FishingAchievementTests(unittest.TestCase):
    def test_records_and_messages(self):
        recs = {}
        fishing.add_catch(recs, "Sand Carp", 2.0, "Beach", "Grub")
        rec, best = fishing.add_catch(recs, "Sand Carp", 3.5, "Cove", "Grub")
        self.assertTrue(best)
        self.assertEqual((rec["caught"], rec["total"], rec["best"], rec["where"]), (2, 5.5, 3.5, "Cove"))
        self.assertFalse(fishing.add_catch(recs, "Sand Carp", 1.0, "X", None)[1])
        msgs = fishing.achievement_list(recs)
        self.assertEqual([payload(m)[0] for m in msgs], [0x5A1, 0x5A1, 0x5A1])
        self.assertIn("Grub".encode("utf-16-le"), msgs[1])
        # row id after the two strings and the type: -2 clears, -3 redraws
        self.assertEqual(struct.unpack_from("<ii", msgs[0], 10 + 4)[1], -2)

    def test_best_catches(self):
        a, b = {}, {}
        fishing.add_catch(a, "Sand Carp", 2.0, "Beach", None, "2026-10-12")
        fishing.add_catch(b, "Sand Carp", 3.0, "Cove", None, "2026-10-13")
        fishing.add_catch(b, "Sand Carp", 1.0, "Pier", None, "2026-10-13")
        chars = [("Ann", a), ("Bob", b), ("Cy", {})]
        self.assertEqual(fishing.leaderboard(chars, "Sand Carp"), [(3.0, "Bob", "Cove"), (2.0, "Ann", "Beach")])
        self.assertEqual(fishing.leaderboard(chars, "Sand Carp", "2026-10-13"), [(3.0, "Bob", "Cove")])
        msgs = fishing.best_messages(fishing.leaderboard(chars, "Sand Carp"))
        self.assertEqual(len(msgs), 4)
        self.assertEqual(struct.unpack_from("<iii", msgs[1], 10), (1, 1, 0))
        self.assertTrue(msgs[1].endswith(struct.pack("<if", 1, 3.0)))


class FormTests(unittest.TestCase):
    def test_form_list(self):
        fs = forms.class_forms({"Clarity": {"stat": "intelligence", "bonus": 12, "icon": 692}})
        msgs = forms.form_list(fs)
        self.assertEqual([payload(m)[0] for m in msgs], [0x38A, 0x38E])
        tail = msgs[1][-11:]
        self.assertEqual(struct.unpack("<iBiBB", tail), (1, 0, 692, 0, 1))
        self.assertIn("Increases Intelligence by 12.".encode("utf-16-le"), msgs[1])
        self.assertEqual(struct.unpack_from("<ii", forms.current(-1), 10), (-1, 0))


class UnstackTests(unittest.TestCase):
    def test_split(self):
        p = types.SimpleNamespace(items=[(5, "Wastes Grub", 443, 10, 0)], equipment=[])
        msgs = zone.split_stack(p, 5, 3)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(p.items[0][3], 7)
        self.assertEqual((p.items[1][3], p.items[1][4]), (3, 1))
        self.assertIsInstance(zone.split_stack(p, 5, 7), str)
        self.assertIsInstance(zone.split_stack(p, 99, 1), str)


class BagTests(unittest.TestCase):
    def test_bag_slots(self):
        import vgmsg
        s = vgmsg.bag_slot(10005, 3)
        self.assertEqual(vgmsg.split_slot(s), (10005, 3))
        self.assertEqual(vgmsg.split_slot(7), (-1, 7))
        rec = vgmsg.inventory_item(42, "X", s)
        self.assertEqual(rec, vgmsg.inventory_item(42, "X", 3, container=10005))

    def test_move_into_bag(self):
        items = [(2, "Wastes Grub", 443, 5, 1), (3, "Small Pouch", 442, 1, 2)]
        equipment = [(1, "Small Pouch", 442, 12)]
        target = zone.move_target(items, equipment, 2, 1, 0)
        self.assertEqual(target, 1000000 + 100 + 0)
        zone.move_item(items, 2, target)
        self.assertEqual([i[0] for i in zone.bag_items(items, 1)], [2])
        self.assertIsInstance(zone.move_target(items, equipment, 3, 1, 1), str)     # bag in a bag
        self.assertIsInstance(zone.move_target(items, equipment, 2, 1, 99), str)    # past capacity
        self.assertIsInstance(zone.move_target(items, equipment, 2, 3, 0), str)     # not equipped
        self.assertEqual(zone.move_target(items, equipment, 2, -1, 4), 4)

    def test_equip_bag(self):
        p = types.SimpleNamespace(items=[(1, "Small Pouch", 442, 1, 0), (2, "Small Pouch", 442, 1, 1)],
                                  equipment=[])
        self.assertIsInstance(zone.equip_item(p, 1), list)
        self.assertIsInstance(zone.equip_item(p, 2), list)
        self.assertEqual(sorted(e[3] for e in p.equipment), [12, 27])
        p.items.append((3, "Wastes Grub", 443, 1, 1000000 + 100))
        self.assertIsInstance(zone.unequip_item(p, 1), str)                  # not empty
        self.assertIsInstance(zone.unequip_item(p, 2), list)


class BrotherhoodBonusTests(unittest.TestCase):
    def test_bonus(self):
        import brotherhood
        self.assertEqual(brotherhood.xp_bonus(200, 0), 0)
        self.assertEqual(brotherhood.xp_bonus(200, 1), 10)
        self.assertEqual(brotherhood.xp_bonus(200, 9), 50)        # capped at 5 others
        rec = brotherhood.member_add({"id": 7, "name": "A", "exp": 1234})
        self.assertIn(struct.pack("<i", 1234), rec)


class ParleyRefreshTests(unittest.TestCase):
    def test_refresh(self):
        import diplomacy
        cards = {"1": {"name": "A", "push": 1, "refresh": 2}, "2": {"name": "B", "push": 1}}
        p = diplomacy.Parley({"npc_cards": []}, cards, [1, 2])
        p.play(1)
        self.assertEqual(p.check(1), diplomacy.ERR_REFRESHING)
        self.assertEqual(len(p.tick_refresh()), 1)       # end of the round it was played: 2 left
        self.assertEqual(p.check(1), diplomacy.ERR_REFRESHING)
        p.tick_refresh()
        p.tick_refresh()
        self.assertIsNone(p.check(1))
        self.assertIsNone(p.check(2))


class GiveLootTests(unittest.TestCase):
    def test_parse_and_match(self):
        data = struct.pack("<Q", 77) + "Justins\0".encode("utf-16-le") + "Tattered Cloth\0".encode("utf-16-le")
        self.assertEqual(grouploot.parse_give_loot(data), (77, "Justins", "Tattered Cloth"))
        loot = [(5, "Tattered Cloth", 1, 1), (6, "Widow Silk", 1, 2)]
        self.assertEqual(grouploot.match_loot(loot, "6")[1], "Widow Silk")
        self.assertEqual(grouploot.match_loot(loot, "widow silk")[0], 6)
        self.assertEqual(grouploot.match_loot(loot, "<item>Tattered Cloth</item>")[0], 5)
        self.assertIsNone(grouploot.match_loot(loot, "Sword"))


class FearTests(unittest.TestCase):
    def test_feared_npc_flees_and_holds(self):
        npc = combat.Npc(1, "Wolf", None, "x", max_health=100, location=(0.0, 0.0, 0.0))
        npc.aggro = True
        npc.feared_until = 100.0
        combat.chase_step(npc, (50.0, 0.0, 0.0), 0.5, now=10.0)
        self.assertLess(npc.location[0], 0.0)                  # ran away from x = 50
        p = types.SimpleNamespace(health=100, live_position=(1.0, 0.0, 0.0), npcs={1: npc})
        npc.aggro_on, npc.next_attack, npc.casting = p, 0, None
        self.assertEqual(combat.npc_turns(p, 10.0), [])         # no swing while feared


class FishComboTests(unittest.TestCase):
    def test_combo(self):
        c = fishing.combo_for("Sand Carp")
        self.assertEqual(len(c), 4)
        self.assertTrue(all(0 <= d <= 3 for d in c))
        self.assertEqual(fishing.combo_for("X", {"combo": [3, 2, 1, 0]}), [3, 2, 1, 0])
        rec = {"id": 1, "combo": [0, 1, 2, 3]}
        self.assertTrue(fishing.record("Sand Carp", rec).endswith(bytes([0, 1, 2, 3])))
        self.assertTrue(fishing.record("Sand Carp", {"id": 1}).endswith(bytes([0xFF] * 4)))


class DialogFlagTests(unittest.TestCase):
    def test_visible_responses(self):
        import login_stub
        node = {"responses": [{"text": "a"}, {"text": "b", "requires_flag": "x"}, {"text": "c"}]}
        p = types.SimpleNamespace(flags=[])
        self.assertEqual([r["text"] for r in login_stub.visible_responses(p, node)], ["a", "c"])
        p.flags = ["x"]
        self.assertEqual([r["text"] for r in login_stub.visible_responses(p, node)], ["a", "b", "c"])


class IgnoreRefusalTests(unittest.TestCase):
    def test_refused_only_when_ignored(self):
        import login_stub
        sent = []
        state = {"player": types.SimpleNamespace(name="Ranger"), "send": sent.append}
        target = types.SimpleNamespace(name="Justins", ignores=[])
        self.assertFalse(login_stub.refused_by_ignore(state, target))
        target.ignores = ["ranger"]
        self.assertTrue(login_stub.refused_by_ignore(state, target))
        self.assertIn("Justins is ignoring you.".encode("utf-16-le"), sent[-1])


class OpenSpaceTests(unittest.TestCase):
    def test_inside_a_built_house(self):
        import login_stub
        plots = {"101": {"chunk": "c", "loc": [1000.0, 1000.0, 0.0]}}
        args = types.SimpleNamespace(content=types.SimpleNamespace(plots=plots))
        p = types.SimpleNamespace(live_position=(1100.0, 1000.0, 0.0), spawned_at=None, level="c")
        with unittest.mock.patch.object(login_stub, "ARGS", args), \
                unittest.mock.patch.object(login_stub, "load_housing", return_value={"101": {"building": 3}}):
            self.assertTrue(login_stub.inside_a_house(p))
            p.live_position = (5000.0, 1000.0, 0.0)
            self.assertFalse(login_stub.inside_a_house(p))
        with unittest.mock.patch.object(login_stub, "ARGS", args), \
                unittest.mock.patch.object(login_stub, "load_housing", return_value={"101": {}}):
            p.live_position = (1100.0, 1000.0, 0.0)
            self.assertFalse(login_stub.inside_a_house(p))        # an empty plot is open ground


class TombstoneRegionTests(unittest.TestCase):
    def test_remove_from_the_tombstones_own_region(self):
        import login_stub
        far = login_stub.world.world_for("chunk_test_far")
        here = login_stub.world.world_for("chunk_test_here")
        player = types.SimpleNamespace(name="Ghost", char_id=77, tombstone={"level": "chunk_test_far", "loc": [0, 0, 0]})
        eid = login_stub.zone.tombstone_eid(player)
        far.npcs[eid] = object()
        state = {"world": here, "send": lambda m: None, "player": player}
        with unittest.mock.patch.object(login_stub, "save_character_field"), \
                unittest.mock.patch.object(login_stub, "tombstone_marker", return_value=[]):
            login_stub.remove_tombstone(state, player)
        self.assertNotIn(eid, far.npcs)
        self.assertIsNone(player.tombstone)


class ChunkArrivalTests(unittest.TestCase):
    def test_label_before_centre(self):
        import login_stub, tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "bin", "Resources", "Texts"))
            with open(os.path.join(d, "bin", "Resources", "Texts", "PoINames.txt"), "w", encoding="latin-1") as f:
                f.write('PoIName="Lomshir [10-20]" ChunkX=-15 ChunkY=-9 X=1 Y=2 Z=3 PoIRank=1\n'
                        'PoIName="Lomshir" ChunkX=-15 ChunkY=-9 X=19045 Y=-14894 Z=7428 PoIRank=1\n')
            saved = dict(login_stub._ARRIVALS)
            login_stub._ARRIVALS.clear()
            try:
                with unittest.mock.patch.object(login_stub, "ARGS", types.SimpleNamespace(client_dir=d)):
                    self.assertEqual(login_stub.chunk_arrival(-15, -9), (19045.0, -14894.0))   # the town label
                    self.assertEqual(login_stub.chunk_arrival(5, 5), (0.0, 0.0))
            finally:
                login_stub._ARRIVALS.clear()
                login_stub._ARRIVALS.update(saved)


class QuestWhereTests(unittest.TestCase):
    def test_turn_in_npc_place(self):
        import login_stub, tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "spawns"))
            with open(os.path.join(d, "spawns", "chunk_n19_12.json"), "w", encoding="utf-8") as f:
                json.dump({"spawns": [{"mob": "orin", "x": -31350, "y": -5450}]}, f)
            content_ = types.SimpleNamespace(directory=d, ground_z=lambda *a: 450.0)
            args = types.SimpleNamespace(content=content_, client_dir=None)
            with unittest.mock.patch.object(login_stub, "ARGS", args):
                self.assertEqual(login_stub.quest_where({"giver": "orin"}), (-19, 12, -31350, -5450, 450))
                self.assertIsNone(login_stub.quest_where({"giver": "nobody"}))


class DialogQuestTests(unittest.TestCase):
    def test_offer_progress_done(self):
        import login_stub
        q = {"id": 7, "name": "Q", "requires": ["first"], "steps": [{"talk": "x", "objective": "Talk"}]}
        sent = []
        player = types.SimpleNamespace(quests=types.SimpleNamespace(active={}, done={"first"}), items=[])
        state = {"player": player, "send": sent.append}
        args = types.SimpleNamespace(content=types.SimpleNamespace(quests={"q": q}))
        with unittest.mock.patch.object(login_stub, "ARGS", args):
            login_stub.dialog_quest(state, "q", 5)
            self.assertEqual(payload(sent[-1])[0], 0x2C0)          # the offer page
            self.assertIn("q", state["shared_quests"])              # Accept allowed here
            player.quests.active["q"] = login_stub.quest.new_progress()
            login_stub.dialog_quest(state, "q", 5)
            self.assertEqual(payload(sent[-1])[0], 0x2C0)          # progress page
            player.quests.done = set()                              # requirement not met
            del player.quests.active["q"]
            login_stub.dialog_quest(state, "q", 5)
            self.assertEqual(payload(sent[-1])[0], login_stub.quest.END_CONVERSATION)


class CrowdConvertTests(unittest.TestCase):
    def test_convert(self):
        import json, os, sys, tempfile
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "crowdsourced"))
        import convert
        src = [{"url": "https://example.org/1", "title": "Example source", "date": None}]
        recs = [{"type": "creature", "name": "Ashen Wolf", "level": 8, "health": 300, "creature_kind": "wolf", "aggressive": "yes",
                 "sources": src, "confidence": "medium"},
                {"type": "creature", "name": "Odd", "creature_kind": "zzz", "sources": src, "confidence": "high"},
                {"type": "creature", "name": "Unsure", "creature_kind": "bear", "sources": src, "confidence": "low"},
                {"type": "quest", "name": "Pelts", "giver": "Orin the Trader", "level": 5, "sources": src, "confidence": "high",
                 "steps": [{"kind": "kill", "target": "Ashen Wolf", "count": 2, "objective": "Hunt"}]}]
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "all.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(dict({"notes": ""}, **r)) for r in recs))
            b = convert.Batch(d)
            out = convert.convert(b, convert.creature_races())
        wolf = out["mobs.json"]["wastes_wolf"]                       # existing key for "Ashen Wolf"
        self.assertEqual((wolf["race"], wolf["level"]), (119, 8))
        self.assertEqual(out["quests.json"]["pelts"]["giver"], "camp_merchant")
        self.assertEqual(out["quests.json"]["pelts"]["steps"][0]["kill"], {"wastes_wolf": 2})
        self.assertTrue(any("Odd" in i for i in b.issues))
        self.assertTrue(any("low confidence" in i for i in b.issues))


class ChestMoveTests(unittest.TestCase):
    def items(self):
        return [[1, "Copper Ore", 487, 5, 0], [2, "Copper Ingot", 1, 1, 3]]

    def test_move_swap_split(self):
        items = self.items()
        self.assertEqual(housing.chest_move(items, 1, 5, 7, 20, 99), [[1, "Copper Ore", 487, 5, 7]])
        items = self.items()
        housing.chest_move(items, 1, -1, 3, 20, 99)               # whole stack onto another: swap
        self.assertEqual(sorted((i[0], i[4]) for i in items), [(1, 3), (2, 0)])
        items = self.items()
        housing.chest_move(items, 1, 2, 9, 20, 99)                # split 2 off to a free slot
        self.assertEqual(sorted((i[0], i[3], i[4]) for i in items), [(1, 3, 0), (2, 1, 3), (99, 2, 9)])

    def test_refused(self):
        for args in ((1, 2, 3), (1, 5, 20), (7, 1, 4), (1, 5, 0)):   # split onto used, bad slot, unknown, same slot
            items = self.items()
            self.assertEqual(housing.chest_move(items, *args, 20, 99), [])
            self.assertEqual(items, self.items())


class ItemLinkTests(unittest.TestCase):
    def test_link_names_an_item(self):
        tid = zone.template_id("Copper Ore")
        self.assertEqual(zone.item_link_name("<item=1:1::0:0:0:0:0:x>Copper Ore</link>"), "Copper Ore")
        self.assertEqual(zone.item_link_name(f"<item={tid}:1::0:0:0:0:0:x>Old Name</link>"), "Copper Ore")
        self.assertIsNone(zone.item_link_name("<item=1:1::0:0:0:0:0:x>No Such Thing</link>"))
        self.assertIsNone(zone.item_link_name("plain text"))


class PlayerReportTests(unittest.TestCase):
    def test_parse_live_capture(self):
        import bugs
        def w(s):
            return s.encode("utf-16-le") + b"\0\0"
        data = (struct.pack("<i", 2) + w("test") + w("Sorcha is not online.") + struct.pack("<iH", 4, 0)
                + w("<pcname>Ranger</pcname> waves") + struct.pack("<iH", 5, 0) + b"\xbb\x01\x00\x00junk")
        r = bugs.parse_player_report(data)
        self.assertEqual(r["reported"], "test")
        self.assertEqual([l["channel"] for l in r["chat"]], [4, 5])
        self.assertEqual(r["chat"][1]["text"], "<pcname>Ranger</pcname> waves")
        with self.assertRaises(struct.error):
            bugs.parse_player_report(struct.pack("<i", 1) + "abc".encode("utf-16-le"))


class CrowdConvertMoreTests(unittest.TestCase):
    def test_dialogue_faction_recipe_formula(self):
        import json, os, sys, tempfile
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "crowdsourced"))
        import convert
        src = [{"url": "https://example.org/1", "title": "Example source", "date": None}]
        recs = [
            {"type": "dialogue", "name": "Guard talk", "npc": "Thestran Guard", "sources": src, "confidence": "high",
             "conversation": [{"npc_says": "Halt.", "responses": [{"player_says": "Who are you?", "leads_to": "A guard."},
                                                                  {"player_says": "Bye", "leads_to": "end"}]},
                              {"npc_says": "A guard.", "responses": [{"player_says": "Ok", "leads_to": "end",
                                                                       "reward": "10 faction"}]}]},
            {"type": "faction", "name": "Wardens", "enemies": ["Raiders", "Nobody"], "sources": src, "confidence": "high"},
            {"type": "faction", "name": "Raiders", "sources": src, "confidence": "high"},
            {"type": "recipe", "name": "Copper Nail", "craft": "blacksmith", "sources": src, "confidence": "high",
             "ingredients": [{"item": "Copper Ingot", "count": 1}], "output": {"item": "Copper Nail", "count": 5}},
            {"type": "formula", "name": "XP table", "topic": "experience needed per level", "values": {"2": 1000},
             "sources": src, "confidence": "medium"},
            {"type": "spawn", "name": "Wolves", "what": "Ashen Wolf", "location": {"raw": "1, 2"}, "sources": src,
             "confidence": "high"},
        ]
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "all.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(dict({"notes": ""}, **r)) for r in recs))
            b = convert.Batch(d)
            out = convert.convert(b, convert.creature_races())
        dlg = out["dialogs.json"]["wastes_thestran_guard"]            # existing key for the guard
        self.assertEqual(dlg["nodes"]["n0"]["responses"][0]["goto"], "n1")
        self.assertNotIn("goto", dlg["nodes"]["n0"]["responses"][1])
        self.assertIn("_manual", dlg["nodes"]["n1"]["responses"][0])
        fw = next(f for f in out["factions.json"].values() if f["name"] == "Wardens")
        self.assertEqual(len(fw["enemies"]), 1)
        self.assertEqual(out["recipes.json"]["copper_nail"]["inputs"], {"Copper Ingot": 1})
        self.assertEqual(b.formulas[0]["_target"], "zone.xp_for_level")
        self.assertEqual(out["spawns_unplaced.json"][0]["what"], "Ashen Wolf")
        self.assertFalse(any("not converted automatically" in i for i in b.issues))


class ItemStatTests(unittest.TestCase):
    def test_mods_and_gear_bonus(self):
        import vgmsg
        rec = vgmsg.inventory_item(5, "Cloak", 0, mods=vgmsg.item_mods({"strength": 3}, {"Armor Class": 8}))
        plain = vgmsg.inventory_item(5, "Cloak", 0)
        self.assertEqual(len(rec) - len(plain), 2 * (5 * 4 + 1 + 4 * 4 + 4))   # two 41-byte records
        p = types.SimpleNamespace(equipment=[(1, "Forester's Cloak", 436, 7)], stats={"dexterity": 30, "wisdom": 20})
        self.assertEqual(sorted(zone.apply_gear_stats(p)), ["dexterity", "wisdom"])
        self.assertEqual(p.stats["dexterity"], 34)
        self.assertEqual(zone.apply_gear_stats(p), [])             # idempotent
        self.assertEqual(zone.stat_base(p, "dexterity"), 30)
        p.equipment = []
        zone.apply_gear_stats(p)
        self.assertEqual(p.stats["dexterity"], 30)
        self.assertEqual(p.armor_class, 0)
        p.equipment = [(1, "Forester's Cloak", 436, 7)]
        zone.apply_gear_stats(p)
        self.assertEqual(p.armor_class, 5 + 8)                      # cloak armor + Armor Class mod
        self.assertEqual(combat.mitigate(20, 25), 16)
        self.assertEqual(combat.mitigate(1, 500), 1)
        p.stats["strength"] = 60
        p.equipment = [(2, "Rusty Sword", 422, 28)]
        lo, hi = zone.ITEM_CONTENT.item("Rusty Sword")["damage"]
        self.assertEqual(combat.auto_attack_damage(p), (lo + 2, hi + 2))
        p.stats.update(constitution=40, hit_points=210)
        p.health = 210
        p.equipment = [(3, "Copper Ring", 444, 19)]                  # +2 Constitution
        zone.apply_gear_stats(p)
        self.assertEqual(p.stats["hit_points"], 210 + 2 * zone.CON_HP)
        p.level_number = 11
        zone.apply_gear_stats(p)
        self.assertEqual(p.stats["hit_points"], 210 + 2 * zone.CON_HP + 10 * zone.HP_PER_LEVEL)


class AvoidanceTests(unittest.TestCase):
    def test_outcomes(self):
        import random as _r
        import effects
        rng = _r.Random(7)
        seen = {combat.roll_outcome(rng, 10, 10, can_parry=True, can_block=True) for _ in range(2000)}
        self.assertEqual(seen, {effects.MISS, effects.DODGE, effects.PARRY, effects.BLOCK, effects.CRIT, effects.HIT})
        rng = _r.Random(7)
        no_def = [combat.roll_outcome(rng, 10, 10) for _ in range(2000)]
        self.assertNotIn(effects.PARRY, no_def)
        self.assertNotIn(effects.BLOCK, no_def)
        # a much higher-level defender is missed far more often
        rng = _r.Random(1)
        high = sum(combat.roll_outcome(rng, 1, 20) == effects.MISS for _ in range(2000))
        self.assertGreater(high, 600)
        p = types.SimpleNamespace(level_number=10)
        self.assertEqual(combat.kill_xp(p, types.SimpleNamespace(level=10)), combat.KILL_XP)
        self.assertGreater(combat.kill_xp(p, types.SimpleNamespace(level=12)), combat.KILL_XP)
        self.assertEqual(combat.kill_xp(p, types.SimpleNamespace(level=4)), 0)          # gray
        msg = effects.combat_text(1, 2, "", 0, kind=0, outcome=effects.DODGE)
        self.assertEqual(msg[10 + 8 + 8 + 4 + 1 + 1 + 4 + 4], effects.DODGE)


class ResourceTests(unittest.TestCase):
    def test_costs_and_pools(self):
        caster = types.SimpleNamespace(klass=25, stats={"energy": 100}, endurance=100)
        self.assertIsNone(combat.pay_cost(caster, 5.0))
        self.assertEqual((caster.energy, caster.endurance), (100 - combat.ABILITY_COST, 100))
        caster.energy = 1
        self.assertEqual(combat.pay_cost(caster, 5.0), combat.NOT_ENOUGH_ENERGY)
        fighter = types.SimpleNamespace(klass=28, stats={}, endurance=100)
        self.assertIsNone(combat.pay_cost(fighter, 5.0))
        self.assertEqual(fighter.endurance, 100 - combat.ABILITY_COST)
        self.assertIsNone(combat.pay_cost(fighter, 0))                 # instant openers are free
        p = types.SimpleNamespace(equipment=[], stats=dict(zone.DEFAULT_STATS, vitality=40, wisdom=25),
                                  endurance=100, energy=100)
        zone.apply_gear_stats(p)
        self.assertEqual(p.stats["endurance"], 100 + 10 * zone.POOL_PER_POINT)
        self.assertEqual(p.stats["energy"], 100 + 5 * zone.POOL_PER_POINT)


class PowerTests(unittest.TestCase):
    def test_power(self):
        lvl1 = types.SimpleNamespace(level_number=1, klass=28, stats={"strength": 40, "wisdom": 20})
        self.assertEqual(combat.scaled(lvl1, (10, 20)), (10, 20))
        lvl11 = types.SimpleNamespace(level_number=11, klass=28, stats={"strength": 50, "wisdom": 20})
        self.assertEqual(combat.scaled(lvl11, (10, 20)), (19, 38))          # 1 + 0.8 + 0.1
        caster = types.SimpleNamespace(level_number=1, klass=25, stats={"intelligence": 30, "wisdom": 25})
        self.assertEqual(combat.scaled(caster, (100, 100)), (110, 110))
        self.assertEqual(combat.scaled(caster, (100, 100), "heal"), (105, 105))


class ClassAttributeTests(unittest.TestCase):
    def test_innate(self):
        p = types.SimpleNamespace(klass=25, level_number=11, equipment=[], stats=dict(zone.DEFAULT_STATS))
        zone.apply_gear_stats(p)
        self.assertEqual(p.stats["intelligence"], 20 + 10 + 10)       # start bonus + 1 a level
        self.assertEqual(p.stats["wisdom"], 20 + 2 + 5)               # + 1 every 2 levels
        self.assertEqual(zone.stat_base(p, "intelligence"), 40)       # innate counts as base
        p.level_number = 12
        self.assertIn("intelligence", zone.apply_gear_stats(p))
        self.assertEqual(p.stats["intelligence"], 41)
        p.race = 4                                                    # High Elf: +4 Wisdom, +3 Intelligence
        zone.apply_gear_stats(p)
        self.assertEqual((p.stats["intelligence"], p.stats["wisdom"]), (44, 20 + 2 + 5 + 4))


class XpCurveTests(unittest.TestCase):
    def test_curve(self):
        self.assertEqual(zone.xp_for_level(1), 1000)
        self.assertGreater(zone.xp_for_level(20), zone.xp_for_level(10))
        self.assertEqual(zone.xp_for_level(2), 1120)


class LoginPoolTests(unittest.TestCase):
    def test_full_pools_at_login(self):
        p = types.SimpleNamespace(klass=25, level_number=10, equipment=[], stats=dict(zone.DEFAULT_STATS),
                                  skills=[], health=210, endurance=100)
        zone.stat_messages(p)
        self.assertGreater(p.stats["energy"], 100)
        self.assertEqual((p.health, p.endurance, p.energy),
                         (p.stats["hit_points"], p.stats["endurance"], p.stats["energy"]))
        p.health = 5
        zone.stat_messages(p)                 # a later resend (chunk handoff) does not heal
        self.assertEqual(p.health, 5)


class EveryRaceClassTests(unittest.TestCase):
    def test_login_messages_build(self):
        """Every playable race and adventuring class, at level 1 and 50, builds its zone-in
        messages (character sheet, stats, bags, abilities) with sane pools."""
        import races_classes
        import class_abilities
        for race in races_classes.RACES:
            for klass in races_classes.ADVENTURING_CLASSES:
                for level in (1, 50):
                    p = zone.Player("T", 1, race, klass, "chunk_n20_12")
                    p.level_number, p.xp = level, 0
                    p.abilities = class_abilities.starting_abilities("..", klass) or p.abilities
                    msgs = [zone.score_message(p)] + zone.stat_messages(p) + zone.inventory_messages(p) + zone.ability_messages(p)
                    self.assertTrue(all(isinstance(m, bytes) and m for m in msgs), (race, klass))
                    for k in ("hit_points", "endurance", "energy"):
                        self.assertGreater(p.stats[k], 0, (race, klass, level, k))
                    for k in ("strength", "dexterity", "constitution", "intelligence", "wisdom"):
                        self.assertGreater(p.stats[k], 0, (race, klass, level, k))
                    self.assertEqual(p.health, p.stats["hit_points"])


class ClearDebtTests(unittest.TestCase):
    def test_clear_debt(self):
        import login_stub
        sent = []
        p = zone.Player("Nobody", 1, 0x0E, 28, "chunk_n20_12")
        p.items, p.xp_debt, p.tombstone, p.level_number = [(7, "Experience Debt Clearance", 0, 1, 0)], 500, None, 5
        state = {"player": p, "send": sent.append}
        saved = login_stub.save_character_field
        login_stub.save_character_field = lambda *a: None
        try:
            p.tombstone = {"level": "x"}
            login_stub.clear_debt(state, 7)
            self.assertEqual(sent[-1][-4:], bytes([0x19, 0, 0, 0]))          # corpses first
            p.tombstone = None
            login_stub.clear_debt(state, 99)
            self.assertEqual(sent[-1][-4:], bytes([0x17, 0, 0, 0]))          # not that item
            login_stub.clear_debt(state, 7)
            self.assertEqual(p.xp_debt, 0)
            self.assertEqual(p.items, [])
            self.assertTrue(any(m[-4:] == bytes([0x16, 0, 0, 0]) for m in sent))
            p.items = [(8, "Experience Debt Clearance", 0, 1, 0)]
            login_stub.clear_debt(state, 8)
            self.assertEqual(sent[-1][-4:], bytes([0x18, 0, 0, 0]))          # no debt left
        finally:
            login_stub.save_character_field = saved


class GenderRaceChangeTests(unittest.TestCase):
    def test_gender_from_create_request(self):
        import login_stub
        self.assertEqual(login_stub.character_gender({"raw": "00000000e305000313"}), 0)
        self.assertEqual(login_stub.character_gender({"raw": "00000000e305010313"}), 1)
        self.assertEqual(login_stub.character_gender({"raw": "00000000e305000313", "gender": 1}), 1)
        self.assertEqual(login_stub.character_race_class({"raw": "00000000e305000313", "race": 14}), (14, 0x13))

    def test_change(self):
        import login_stub
        sent = []
        p = zone.Player("Nobody", 1, 3, 0x13, "chunk_n20_12")
        p.items = [(5, "Gender Change", 0, 1, 0), (6, "Race Change", 0, 1, 0)]
        state = {"player": p, "send": sent.append}
        saved, props = login_stub.save_character_field, login_stub.pawn_props_changed
        login_stub.save_character_field = lambda *a: None
        login_stub.pawn_props_changed = lambda *a: None
        try:
            login_stub.change_gender_race(state, login_stub.CHANGE_GENDER, 1, 6)     # wrong item
            self.assertEqual(sent[-1][-6:], bytes([0x10, 0, 0, 0, 0, 1]))
            login_stub.change_gender_race(state, login_stub.CHANGE_GENDER, 1, 5)
            self.assertEqual((p.gender, sent[-1][-6:]), (1, bytes([0x0C, 0, 0, 0, 0, 1])))
            login_stub.change_gender_race(state, login_stub.CHANGE_RACE, 14, 6)
            self.assertEqual((p.race, sent[-1][-6:]), (14, bytes([0x11, 0, 0, 0, 0, 14])))
            self.assertEqual(p.items, [])
        finally:
            login_stub.save_character_field, login_stub.pawn_props_changed = saved, props


class RenameTests(unittest.TestCase):
    def test_rename_refs(self):
        import login_stub
        data = {"boxes": {"orin": [{"from": "Orin", "to": "orin"}], "bob": []},
                "members": {"Orin": 10, "Justins": 1}, "owner": "Orin", "note": "Orin's house"}
        out = login_stub.rename_refs(data, "Orin", "Tamsin")
        self.assertEqual(out["boxes"]["tamsin"], [{"from": "Tamsin", "to": "tamsin"}])
        self.assertEqual(out["members"], {"Tamsin": 10, "Justins": 1})
        self.assertEqual((out["owner"], out["note"]), ("Tamsin", "Orin's house"))   # only whole names

    def test_validation(self):
        import login_stub
        self.assertTrue(login_stub.valid_first_name("Sorcha"))
        for bad in ("Al", "Sor cha", "S0rcha", "x" * 21):
            self.assertFalse(login_stub.valid_first_name(bad))


class ItemFlagTests(unittest.TestCase):
    def test_flags_and_restrictions(self):
        saved = dict(zone.ITEM_CONTENT.items)
        try:
            zone.ITEM_CONTENT.items["Test Relic"] = {"flags": ["no_trade", "quest"]}
            zone.ITEM_CONTENT.items["Test Ring"] = {"slot": "LEFTFINGER", "flags": ["bind_on_equip"]}
            self.assertEqual(zone.item_flags("Test Relic"), 0x21)
            self.assertEqual(zone.item_equip_fields("Test Ring", bound=True)["raw"][102], 0x88)
            p = zone.Player("Nobody", 1, 0x0E, 28, "chunk_n20_12")
            relic, ring = (1, "Test Relic", 0, 1, 0), (2, "Test Ring", 0, 1, 1)
            p.items, p.equipment, p.bound = [relic, ring], [], set()
            for action in ("trade", "mail", "market", "sell"):
                self.assertIsNotNone(zone.item_restriction(p, relic, action))
            self.assertIsNone(zone.item_restriction(p, ring, "trade"))
            self.assertIsInstance(zone.equip_item(p, 2), list)
            self.assertEqual(p.bound, {2})                                   # bound once worn
            self.assertIsNotNone(zone.item_restriction(p, ring, "trade"))
        finally:
            zone.ITEM_CONTENT.items.clear()
            zone.ITEM_CONTENT.items.update(saved)


class FormOnDeathTests(unittest.TestCase):
    def test_form_dropped_and_restored(self):
        import login_stub
        sent = []
        p = zone.Player("Nobody", 1, 0x0E, 14, "chunk_n20_12")
        p.forms = [(7, "Mindset of Clarity", {"stat": "intelligence", "bonus": 12, "icon": 692})]
        p.effects = []
        state = {"player": p, "send": sent.append}
        login_stub.apply_form(state, p.forms[0], 0)
        self.assertEqual(p.form, 7)
        login_stub.drop_form_on_death(state, p)
        self.assertEqual((p.form, p.lost_form), (-1, 7))
        self.assertTrue(all(e["ends"] == 0 for e in p.effects if e.get("form")))
        p.apply_form_on_death = False
        login_stub.restore_form_after_death(state, p)
        self.assertEqual(p.form, -1)
        p.lost_form, p.apply_form_on_death = 7, True
        login_stub.restore_form_after_death(state, p)
        self.assertEqual(p.form, 7)


class UnterminatedStringTests(unittest.TestCase):
    def test_no_hang_on_missing_terminator(self):
        """A UTF-16 string with no terminator used to spin forever in several readers
        (house permission friends, mail, market, songs, bug reports): one packet froze the server."""
        import tempfile
        import threading
        from unittest import mock
        import login_stub
        import housing
        p = zone.Player("Nobody", 1, 0x0E, 28, "chunk_n20_12")
        state = {"player": p, "send": lambda m: None}
        done = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(login_stub, "HOUSING_FILE", os.path.join(tmp.name, "housing.json"))
        patch.start()
        self.addCleanup(patch.stop)

        def run():
            for data in (b"", b"A\x00", b"A\x00B"):
                try:
                    login_stub.handle_housing_event(state, housing.PERM_ADD_FRIEND, data)
                except Exception:
                    pass
            done.append(1)
        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(5)
        self.assertTrue(done, "handler hung on an unterminated string")


class TinyPacketSizeTests(unittest.TestCase):
    def test_fragmenter_always_advances(self):
        import login_stub
        packets, seq = login_stub.build_reliable_fragments(0, bytes(100), 4)    # room would be <= 0
        self.assertEqual(seq, len(packets))
        self.assertGreater(len(packets), 0)


class FloodTests(unittest.TestCase):
    def test_flood_limits(self):
        from unittest import mock
        import login_stub
        sent = []
        state = {"send": sent.append}
        move = struct.pack("<HI", 1, 0)
        with mock.patch.object(login_stub.time, "time", return_value=1000.0):
            allowed = sum(login_stub.allow_message(state, move, None) for _ in range(700))
            self.assertEqual(allowed, int(login_stub.MSG_BURST))           # the burst, then drops
            state.clear()
            state["send"] = sent.append
            say = struct.pack("<HII", 2, 0x74, 4) + "hi".encode("utf-16-le")
            allowed = sum(login_stub.allow_message(state, say, None) for _ in range(20))
            self.assertEqual(allowed, int(login_stub.CHAT_BURST))
            self.assertEqual(len(sent), 1)                                  # one warning
        with mock.patch.object(login_stub.time, "time", return_value=1001.0):
            self.assertTrue(login_stub.allow_message(state, say, None))      # refilled after a second


class AuditTests(unittest.TestCase):
    def test_audit_lines(self):
        import tempfile
        from unittest import mock
        import login_stub
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "audit.log")
            with mock.patch.object(login_stub, "AUDIT_FILE", path):
                login_stub.audit("trade", giver="Ann", taker="Bo", items=[["Rock", 2]], coins=5)
                login_stub.audit("mail", sender="Bo", to="Ann", item=None, coins=1, cod=0)
            lines = [json.loads(x) for x in open(path, encoding="utf-8")]
        self.assertEqual([x["kind"] for x in lines], ["trade", "mail"])
        self.assertEqual(lines[0]["items"], [["Rock", 2]])
        with mock.patch.object(login_stub, "AUDIT_FILE", None):
            login_stub.audit("trade")                                   # no file: nothing written


class ConsoleTests(unittest.TestCase):
    def test_operator_commands(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        import login_stub
        sent = []
        p = zone.Player("Ann", 1, 0x0E, 28, "chunk_n20_12")
        s = {"player": p, "send": sent.append}
        out = io.StringIO()
        with mock.patch.dict(login_stub.ONLINE, {"ann": s}, clear=True), \
                mock.patch.object(login_stub, "close_session") as close, redirect_stdout(out):
            self.assertIsNone(login_stub.console_command("who", {}, None))
            login_stub.console_command("announce Restart in 5 minutes", {}, None)
            login_stub.console_command("kick ann", {}, None)
            self.assertEqual(login_stub.console_command("stop", {}, None), "stop")
        self.assertIn("1 online: Ann", out.getvalue())
        self.assertIn("Server: Restart in 5 minutes".encode("utf-16-le"), sent[0])
        close.assert_called_once_with(s, None)


class SecondLoginTests(unittest.TestCase):
    def test_second_login_closes_the_first(self):
        from unittest import mock
        import login_stub
        p_old, p_new = zone.Player("Twice", 1, 0x0E, 28, "chunk_n20_12"), zone.Player("Twice", 1, 0x0E, 28, "chunk_n20_12")
        ended = []
        old = {"player": p_old, "session": "a", "terminate": lambda: ended.append(1)}
        new = {"player": p_new, "session": "b"}
        handoff = {"player": p_new, "session": "a"}
        with mock.patch.dict(login_stub.ONLINE, {"twice": old}, clear=True), \
                mock.patch.object(login_stub, "leave_world") as leave:
            login_stub.kick_other_session(handoff, None)        # same session: a chunk handoff
            self.assertFalse(old.get("closed"))
            login_stub.kick_other_session(new, None)
            self.assertTrue(old["closed"])
            self.assertEqual(ended, [1])
            leave.assert_called_once_with(old, None)


class ResendTests(unittest.TestCase):
    """Reliable packets are kept until acknowledged and sent again when they are not."""

    class Sock:
        def __init__(self):
            self.sent = []

        def sendto(self, pkt, addr):
            self.sent.append(pkt)

    def test_acks_and_resends(self):
        import struct
        import login_stub
        sock = self.Sock()
        state = {"out_seq": 65530, "max_raw": 512}
        for _ in range(10):                                   # seqs 65530..65539 (u16 wraps at 6)
            login_stub.send_message(sock, ("h", 1), state, b"\x02\x00hello")
        self.assertEqual(len(state["unacked"]), 10)
        self.assertEqual(login_stub.full_seq(state, 2), 65538)
        login_stub.handle_acks(state, struct.pack(">BBH", 0, 0x15, 1))     # AckAll up to 65537
        self.assertEqual(list(state["unacked"]), [65538, 65539])
        multi = bytes([0, 3, 4]) + struct.pack(">BBH", 0, 0x11, 3)         # Ack1 inside Multi
        login_stub.handle_acks(state, multi)
        self.assertEqual(list(state["unacked"]), [65538])
        before = len(sock.sent)
        login_stub.resend_tick({"k": state}, state["unacked"][65538][1] + 0.1)
        self.assertEqual(len(sock.sent), before)                          # not overdue yet
        login_stub.resend_tick({"k": state}, state["unacked"][65538][1] + login_stub.RESEND_SECONDS + 0.01)
        self.assertEqual(sock.sent[-1][2:4], struct.pack(">H", 65538 & 0xFFFF))
        self.assertEqual(state["resent"], 1)


class SequenceWrapTests(unittest.TestCase):
    def test_in_order_delivery_survives_wrap(self):
        import struct
        import login_stub

        class Sock:
            def __init__(self):
                self.sent = []

            def sendto(self, pkt, addr):
                self.sent.append(pkt)
        sock, state = Sock(), {"in_expect": 65534}
        recv = lambda seq, payload, kind=0x09: login_stub.receive_reliable(
            sock, None, state, kind, seq & 0xFFFF, payload, quiet=True)
        self.assertEqual(recv(65534, b"\x02\x00a"), [b"\x02\x00a"])
        self.assertEqual(recv(0, b"\x02\x00c"), [])                # 65535 is missing: held
        self.assertEqual(sock.sent[-2], struct.pack(">BBH", 0, 0x11, 0))    # Ack1 for the early one
        self.assertEqual(sock.sent[-1], struct.pack(">BBH", 0, 0x15, 65534))
        self.assertEqual(recv(65535, b"\x02\x00b"), [b"\x02\x00b", b"\x02\x00c"])
        self.assertEqual(recv(65535, b"\x02\x00b"), [])           # a resend: only acknowledged again
        self.assertEqual(sock.sent[-1], struct.pack(">BBH", 0, 0x15, 0))
        message = b"\x02\x00" + bytes(range(256)) * 3              # 770 bytes: three fragments
        parts = [struct.pack(">I", len(message)) + message[:300], message[300:600], message[600:]]
        self.assertEqual(recv(3, parts[2], 0x0D), [])
        self.assertEqual(recv(1, parts[0], 0x0D), [])
        self.assertEqual(recv(2, parts[1], 0x0D), [message])
        self.assertEqual(login_stub.build_reliable(65537, b"x")[2:4], bytes([0, 1]))    # outgoing seq wraps too
        packets, _ = login_stub.build_reliable_fragments(65535, bytes(1000), 512)
        self.assertEqual([p[2:4] for p in packets[:2]], [bytes([0xFF, 0xFF]), bytes([0, 0])])


class ChannelSequenceTests(unittest.TestCase):
    def test_wrap_aware(self):
        import ue2net
        self.assertEqual(ue2net.seq_diff(0, 4095, 4096), 1)          # after the wrap: newer
        self.assertEqual(ue2net.seq_diff(4095, 0, 4096), -1)
        self.assertEqual(ue2net.seq_diff(5, 5, 4096), 0)              # a resend
        self.assertLess(ue2net.seq_diff(10, 20, 4096), 0)


class HealTargetTests(unittest.TestCase):
    def test_defensive_target_first(self):
        import login_stub
        me = zone.Player("Healer", 1, 0x0E, 5, "chunk_n20_12")
        friend = zone.Player("Friend", 2, 0x0E, 28, "chunk_n20_12")
        w = types.SimpleNamespace(members={})
        state = {"player": me, "world": w}
        fs = {"player": friend}
        w.members = {1: state, 2: fs}
        me.target = None
        self.assertIs(login_stub.heal_target(state), state)          # nobody targeted: yourself
        state["def_target"] = 2
        self.assertIs(login_stub.heal_target(state), fs)             # the defensive target
        friend.health = 0
        self.assertIs(login_stub.heal_target(state), state)          # not a dead one


class HarvestItemRequestTests(unittest.TestCase):
    def test_parse_and_answer(self):
        import harvest
        data = struct.pack("<iii", 2, 7, 9)
        self.assertEqual(harvest.parse_item_request(data), [7, 9])
        self.assertEqual(harvest.parse_item_request(struct.pack("<ii", 5, 1)), [])   # count too big
        self.assertEqual(harvest.parse_item_request(b""), [])
        msgs = harvest.item_records([b"r1", b"r2"])
        self.assertEqual([struct.unpack_from("<I", m, 2)[0] for m in msgs], [0x2E2, 0x2E2, 0x2E3])


class RandomResultTests(unittest.TestCase):
    def test_layout(self):
        import social
        m = social.random_result(0x1336F1A, 1, 100, 42)
        self.assertEqual(struct.unpack("<HIIQiii", m), (2, 0x31A, 20, 0x1336F1A, 1, 100, 42))


class CombatInfoTests(unittest.TestCase):
    def test_sheet_percentages(self):
        p = types.SimpleNamespace(equipment=[], stats={"dexterity": 50})
        m = combat.combat_info(p)
        self.assertEqual(struct.unpack_from("<I", m, 2)[0], 0x11E)
        dodge, parry, block, _, _ = struct.unpack_from("<ffffi", m, 10)
        self.assertAlmostEqual(dodge, 6.0, places=4)          # 4% + 0.1% x 20 Dexterity above 30
        self.assertEqual((parry, block), (0.0, 0.0))          # no weapon, no shield


class OwnershipTests(unittest.TestCase):
    def test_layout(self):
        npc = types.SimpleNamespace(entity_id=0x2000008)
        m = combat.ownership(npc, 0x1336F1A)
        self.assertEqual(struct.unpack("<HIIQQB", m), (2, 0x567, 17, 0x2000008, 0x1336F1A, 0))


class InCombatTests(unittest.TestCase):
    def test_in_combat(self):
        p = types.SimpleNamespace(auto_attack=False, npcs={})
        self.assertFalse(combat.in_combat(p))
        p.auto_attack = True
        self.assertTrue(combat.in_combat(p))
        p.auto_attack = False
        p.npcs = {1: types.SimpleNamespace(alive=True, aggro=True, aggro_on=p)}
        self.assertTrue(combat.in_combat(p))
        p.npcs[1].alive = False
        self.assertFalse(combat.in_combat(p))


class AutoAttackTargetTests(unittest.TestCase):
    def test_service_npcs_refused(self):
        forge = combat.Npc(1, "Camp Forge", None, "x.SGONPCPawn")
        forge.station = True
        p = types.SimpleNamespace(auto_attack=False, target=1, npcs={1: forge}, health=100)
        self.assertEqual(combat.toggle_auto_attack(p), [(combat.AUTO_TARGET_INVALID, "autofail")])
        self.assertFalse(p.auto_attack)
        wolf = combat.Npc(2, "Wolf", None, "x.SGONPCPawn")
        p.target, p.npcs = 2, {2: wolf}
        self.assertEqual(combat.toggle_auto_attack(p), [])
        self.assertTrue(p.auto_attack)


class AccountTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        import accounts
        self.accounts = accounts
        self.dir = tempfile.TemporaryDirectory()
        self.old = accounts.ACCOUNTS_FILE
        accounts.ACCOUNTS_FILE = os.path.join(self.dir.name, "accounts.json")

    def tearDown(self):
        self.accounts.ACCOUNTS_FILE = self.old
        self.dir.cleanup()

    def test_password_and_token_login(self):
        a = self.accounts
        self.assertIsNone(a.create("Alice", "correct horse"))
        self.assertEqual(a.create("alice", "another one"), "That username is taken.")
        self.assertIsNotNone(a.create("x", "longenough"))                # name too short
        self.assertIsNotNone(a.create("Bob", "short"))                   # password too short
        self.assertEqual(a.login("Alice", "correct horse"), "alice")
        self.assertEqual(a.login("ALICE", "correct horse"), "alice")     # usernames ignore case
        self.assertIsNone(a.login("Alice", "wrong password"))
        self.assertIsNone(a.login("Nobody", "correct horse"))
        self.assertIsNone(a.login(a.LAUNCHER_LOGIN, "12345678"))
        self.assertIsNone(a.set_token("alice", "12345678"))
        self.assertEqual(a.login(a.LAUNCHER_LOGIN, "12345678"), "alice")
        import storage
        data = storage.read_json(a.ACCOUNTS_FILE)
        self.assertNotIn("correct horse", json.dumps(data))             # only the hash is stored
        self.assertIsNone(a.set_password("alice", "new secret"))
        self.assertIsNone(a.login("Alice", "correct horse"))
        self.assertEqual(a.login("Alice", "new secret"), "alice")
        a.FAILURES.clear()
        for _ in range(a.MAX_FAILURES):
            self.assertFalse(a.throttled("10.0.0.9"))
            a.record_failure("10.0.0.9")
        self.assertTrue(a.throttled("10.0.0.9"))
        self.assertFalse(a.throttled("10.0.0.9", now=a.time.time() + a.FAILURE_WINDOW + 1))
        a.FAILURES.clear()

    def test_sessions_and_dev_account(self):
        a = self.accounts
        key = a.new_session("alice")
        self.assertEqual(a.session_account(key), "alice")
        self.assertIsNone(a.session_account("made up"))
        password = a.ensure_dev_account()
        self.assertTrue(password)
        self.assertEqual(a.login(a.DEV_ACCOUNT, password), a.DEV_ACCOUNT)
        self.assertEqual(a.login(a.LAUNCHER_LOGIN, "22222222"), a.DEV_ACCOUNT)
        self.assertIsNone(a.ensure_dev_account())                        # only on a fresh install
        self.assertFalse(a.is_suspended(a.DEV_ACCOUNT))
        self.assertIsNone(a.set_suspended(a.DEV_ACCOUNT, True))
        self.assertTrue(a.is_suspended(a.DEV_ACCOUNT))

class StorageTests(unittest.TestCase):
    def test_database_imports_and_updates(self):
        import tempfile
        import storage
        with tempfile.TemporaryDirectory() as d:
            chars = os.path.join(d, "characters.json")
            guilds = os.path.join(d, "guilds.json")
            storage.write_json_atomic(chars, [{"first": "Ann", "level": 1}, {"first": "Bo", "level": 2}])
            storage.write_json_atomic(guilds, {"g": {"members": ["Ann"]}})
            self.assertEqual([c["first"] for c in storage.read_characters(chars)], ["Ann", "Bo"])
            self.assertFalse(os.path.exists(chars))                       # imported, kept as a backup
            self.assertTrue(os.path.exists(chars + ".imported"))
            self.assertTrue(storage.update_character(chars, "Bo", {"level": 3}))
            self.assertFalse(storage.update_character(chars, "Nobody", {"level": 3}))
            storage.update_character(chars, "Ann", lambda c: c.update(level=c["level"] + 10))
            self.assertEqual([c["level"] for c in storage.read_characters(chars)], [11, 3])
            storage.write_characters(chars, storage.read_characters(chars) + [{"first": "Cy"}])
            self.assertEqual([c["first"] for c in storage.read_characters(chars)], ["Ann", "Bo", "Cy"])
            storage.update_character(chars, "Bo", {"account": "acc1"})
            storage.update_character(chars, "Cy", {"account": "acc1"})
            self.assertEqual([c["first"] for c in storage.read_characters(chars, "acc1")], ["Bo", "Cy"])
            self.assertEqual(storage.read_characters(chars, "nobody"), [])
            self.assertEqual(storage.read_character(chars, "bo", ignore_case=True)["first"], "Bo")
            self.assertIsNone(storage.read_character(chars, "bo"))
            self.assertEqual(storage.read_json(guilds), {"g": {"members": ["Ann"]}})
            self.assertEqual(storage.read_json(os.path.join(d, "mail.json"), {"x": 1}), {"x": 1})
            storage.write_json(guilds, {})
            self.assertEqual(storage.read_json(guilds), {})
            out = os.path.join(d, "out")
            self.assertIn("characters.json", storage.export(d, out))
            self.assertEqual(len(json.load(open(os.path.join(out, "characters.json"), encoding="utf-8"))), 3)
            storage.write_json_atomic(os.path.join(out, "guilds.json"), {"h": 1})
            storage.import_file(os.path.join(out, "guilds.json"), d)
            b = storage.backup(d, keep=1)
            storage.backup(d, keep=1)
            self.assertEqual(len(os.listdir(os.path.join(d, "backups"))), 1)
            import sqlite3
            con = sqlite3.connect(b if os.path.exists(b) else os.path.join(d, "backups", os.listdir(os.path.join(d, "backups"))[0]))
            self.assertEqual(con.execute("SELECT count(*) FROM characters").fetchone()[0], 3)
            con.close()
            self.assertEqual(storage.read_json(guilds), {"h": 1})



if __name__ == "__main__":
    unittest.main()


class AATests(unittest.TestCase):
    A = {"id": 1001, "list": "general", "title": "Hardiness", "max_rank": 2, "cost": [1, 3], "level": 10,
         "stats": {"constitution": 2}}
    B = {"id": 1005, "list": "archetype", "title": "Next", "max_rank": 1, "cost": 2, "level": 10,
         "requires": {"1001": 2}}

    def test_add_layout(self):
        import aa
        eid, data = payload(aa.ability_add(self.A, 1, {1001: 1}, {1001: self.A}))
        self.assertEqual(eid, 0x85F)
        self.assertEqual(struct.unpack_from("<ii", data), (1001, 0))
        rest = data[8 + len("Hardiness\0".encode("utf-16-le")) + 2:]
        self.assertEqual(struct.unpack_from("<iiiifB", rest), (1, 2, 3, 10, 0.0, 1))
        msgs = aa.list_messages([self.A], {})
        self.assertEqual([payload(m)[0] for m in msgs], [0x85D, 0x85F, 0x85E])

    def test_training_rules(self):
        import aa
        self.assertIsNone(aa.train_error(self.A, 0, {}, 1, 0, 10))
        self.assertIn("level 10", aa.train_error(self.A, 0, {}, 1, 0, 9))
        self.assertIn("enough AA points", aa.train_error(self.A, 1, {1001: 1}, 2, 1, 10))
        self.assertIn("highest rank", aa.train_error(self.A, 2, {1001: 2}, 9, 4, 10))
        self.assertIn("spend 100", aa.train_error(self.B, 0, {1001: 2}, 9, 4, 10))
        self.assertIn("requirements", aa.train_error(self.B, 0, {1001: 1}, 9, 100, 10))
        self.assertEqual(aa.cost(self.A, 2), -1)
        self.assertEqual(aa.stat_bonus([self.A], {1001: 2}), {"constitution": 4})

    def test_gain(self):
        import aa
        self.assertEqual(aa.gain(0, 0, 0, 1000, aa.MIN_LEVEL - 1), (0, 0, 0))
        self.assertEqual(aa.gain(0, 900, 2, 1000, aa.MIN_LEVEL), (150, 3, 1))


class LootButtonTests(unittest.TestCase):
    def test_buttons_per_mode(self):
        g = types.SimpleNamespace(leader=types.SimpleNamespace(char_id=1))
        npc = types.SimpleNamespace()
        for mode, want in ((grouploot.FREE_FOR_ALL, (0, 0)), (grouploot.MASTER_LOOTER, (1, 0)),
                           (grouploot.ROUND_ROBIN, (1, 0)), (grouploot.RANDOM_FOR_MAGICAL, (0, 1))):
            grouploot.settings(g)["mode"] = mode
            got = [payload(m) for m in grouploot.loot_buttons(g, npc)]
            self.assertEqual(got, [(0x6CA, bytes([want[0]])), (0x6C9, bytes([want[1]]))])
        npc.open_to_group = True
        grouploot.settings(g)["mode"] = grouploot.MASTER_LOOTER
        self.assertEqual(payload(grouploot.loot_buttons(g, npc)[0]), (0x6CA, b"\0"))
        self.assertEqual(payload(grouploot.loot_buttons(None, npc)[0]), (0x6CA, b"\0"))


class AttributePointTests(unittest.TestCase):
    def test_pool_cap_and_codes(self):
        import attributes as at
        alloc = {}
        self.assertEqual(at.pool(1, alloc), 0)
        self.assertEqual(at.allocate("strength", at.ONE, 1, alloc), (0, at.NO_POINTS))
        self.assertEqual(at.pool(5, alloc), 8)
        self.assertEqual(at.allocate("strength", at.ONE, 5, alloc), (1, 0))
        self.assertEqual(at.allocate("wisdom", at.MAX, 5, alloc), (5, 4))         # capped at level 5
        self.assertEqual(at.allocate("wisdom", at.ONE, 5, alloc), (0, 6 + 4))     # can't raise wisdom
        self.assertEqual(at.pool(5, alloc), 2)
        self.assertEqual(at.allocate("hit_points", at.ONE, 5, alloc), (0, at.NOT_ALLOWED))
        eid, data = payload(at.result(0, 3, 51, 2))
        self.assertEqual((eid, struct.unpack("<iiiii", data)), (0x2D9, (0, 3, 0, 51, 2)))
        self.assertEqual(payload(at.set_pool(7)), (0x2DA, struct.pack("<ii", 7, 0)))


class CraftAttributeTests(unittest.TestCase):
    def test_codes_and_level_grant(self):
        import attributes as at
        alloc = {}
        self.assertEqual(at.allocate("reasoning", at.ONE, 2, alloc, at.CRAFTING), (1, 28))
        self.assertEqual(at.allocate("finesse", at.MAX, 2, alloc, at.CRAFTING), (1, 29))
        self.assertEqual(at.allocate("ingenuity", at.ONE, 2, alloc, at.CRAFTING), (0, at.NO_POINTS))
        self.assertEqual(at.allocate("strength", at.ONE, 9, alloc, at.CRAFTING), (0, at.NOT_ALLOWED))
        p = types.SimpleNamespace(spheres={"1": [1, 990]}, craft_alloc={})
        msgs = zone.gain_sphere_xp(p, zone.CRAFTING, 20)
        self.assertEqual([payload(m)[0] for m in msgs], [0x713, 0x2DA, 0x2DB])
        self.assertEqual(payload(msgs[1])[1], struct.pack("<ii", 2, 1))


class HarvestTabTests(unittest.TestCase):
    def test_category3_records_and_updates(self):
        p = types.SimpleNamespace(skills=[(0x0F, 7, 0x15), (0x4B, 3, 0x15), (0x16, 25, 0)])
        self.assertEqual(zone.harvest_skills(p), {0x0F: 7, 0x4B: 3, zone.HARVESTING_STAT: 7})
        msgs = zone.harvest_updates(p)
        self.assertEqual(payload(msgs[0]), (0x2E0, struct.pack("<ii", 0x0F, 0x4B)))
        eid, data = payload(msgs[1])
        self.assertEqual(eid, 0x2D4)
        self.assertEqual(struct.unpack_from("<iB", data), (zone.HARVEST_INSTANCE + 0x0F, 3))   # instance, category
        self.assertEqual(len(zone.harvest_records(p)), 3)


class SkillPoolTests(unittest.TestCase):
    def test_caps_per_group(self):
        p = types.SimpleNamespace(skills=[(1, 25, 0), (2, 30, 0), (3, 10, 4), (4, 1, 0x15)])
        eid, data = payload(zone.skill_pool_caps(p))
        caps = struct.unpack("<12i", data)
        self.assertEqual((eid, caps[0], caps[2], sum(caps)), (0x2D6, 100, 50, 150))


class CraftSkillTabTests(unittest.TestCase):
    def test_records_and_trade_caps(self):
        import attributes as at
        recs = at.craft_skill_records(2)
        self.assertEqual(len(recs), len(at.CRAFT_SKILLS))
        p = types.SimpleNamespace(skills=[], craft_trade=0)                  # blacksmith
        caps = struct.unpack("<12i", payload(zone.skill_pool_caps(p))[1])
        self.assertEqual(caps[6:10], (2 * 50, 1 * 50, 6 * 50, 1 * 50))       # finishing, special, refining, general
        p.craft_trade = 0xFF
        self.assertEqual(struct.unpack("<12i", payload(zone.skill_pool_caps(p))[1])[6:10], (0, 0, 0, 0))


class SkillDirectionTests(unittest.TestCase):
    def test_update_carries_direction(self):
        import attributes as at
        eid, data = payload(at.craft_skill_update(40, 2, 1))
        self.assertEqual(eid, 0x2D4)
        self.assertIn(bytes([1]), data)
        recs = at.craft_skill_records(2, {40: 2})
        self.assertEqual(len(recs), len(at.CRAFT_SKILLS))


class ContentFormsRiftwaysTests(unittest.TestCase):
    def test_bad_forms_and_riftways_are_reported(self):
        import content, shutil, tempfile
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, "content")
            shutil.copytree(os.path.join(os.path.dirname(os.path.abspath(__file__)), "content"), c)
            self.assertEqual(content.validate(c), [])
            forms = json.load(open(os.path.join(c, "forms.json"), encoding="utf-8"))
            forms["Wizard"] = {"X": {"stat": "luck", "bonus": "lots"}}
            json.dump(forms, open(os.path.join(c, "forms.json"), "w", encoding="utf-8"))
            rifts = json.load(open(os.path.join(c, "riftways.json"), encoding="utf-8"))
            rifts["NEWPLACE"] = {"name": "New", "color": "pink", "chunk": "chunk_n19_12", "x": None, "y": None}
            json.dump(rifts, open(os.path.join(c, "riftways.json"), "w", encoding="utf-8"))
            ab = json.load(open(os.path.join(c, "abilities.json"), encoding="utf-8"))
            ab["Bad Spell"] = {"kind": "explode", "refresh": "soon", "damage": [5]}
            json.dump(ab, open(os.path.join(c, "abilities.json"), "w", encoding="utf-8"))
            for fname, key, val in (("outposts.json", "nowhere", {"name": "X"}), ("hints.json", "bad", {"title": 1})):
                doc = json.load(open(os.path.join(c, fname), encoding="utf-8"))
                doc[key] = val
                json.dump(doc, open(os.path.join(c, fname), "w", encoding="utf-8"))
            problems = " | ".join(content.validate(c))
            for text in ("forms Wizard: not a class", "stat must be", "bonus must be", "color must be", "needs x and y",
                         "kind must be", "refresh must be a number", "damage must be [min, max]",
                         "outpost nowhere", "hint bad"):
                self.assertIn(text, problems)


class EditorTests(unittest.TestCase):
    def test_check_and_save(self):
        import shutil, sys, tempfile
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, "content")
            shutil.copytree(os.path.join(os.path.dirname(os.path.abspath(__file__)), "content"), c)
            self.assertIn("spawns/chunk_n19_12.json", editor.content_files(c))
            self.assertTrue(editor.check(c, "mobs.json", "{bad"))
            with self.assertRaises(ValueError):
                editor.safe_path(c, "../x.json")
            name = "spawns/chunk_n19_12.json"
            doc = json.load(open(os.path.join(c, "spawns", "chunk_n19_12.json"), encoding="utf-8"))
            doc["spawns"].append({"mob": "no_such_mob", "x": 0, "y": 0})
            self.assertTrue(editor.save(c, name, json.dumps(doc), os.path.join(d, "bk")))   # refused
            doc["spawns"][-1]["mob"] = doc["spawns"][0]["mob"]
            self.assertEqual(editor.save(c, name, json.dumps(doc), os.path.join(d, "bk")), [])
            self.assertEqual(len(os.listdir(os.path.join(d, "bk"))), 1)                      # backup kept
            self.assertTrue(editor.png(2, 1, [[0, 255]]).startswith(b"\x89PNG"))

    def test_save_keeps_key_order(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        old = {"_comment": "c", "1002": {"name": "b", "start": 0}, "1001": {"start": 1, "name": "a"}}
        browser = {"1001": {"name": "a", "start": 1}, "1002": {"name": "B", "start": 0}, "_comment": "c", "1003": {}}
        kept = editor.keep_order(browser, old)
        self.assertEqual(list(kept), ["_comment", "1002", "1001", "1003"])
        self.assertEqual(list(kept["1001"]), ["start", "name"])
        self.assertEqual(kept["1002"]["name"], "B")


EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


@unittest.skipUnless(os.path.exists(EDGE), "needs Microsoft Edge for a headless page check")
class EditorPageTests(unittest.TestCase):
    def test_forms_round_trip(self):
        """The editor page's #selftest: every quest and mob goes through its form unchanged."""
        import subprocess, sys, tempfile, threading
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        httpd = editor.http.server.ThreadingHTTPServer(("127.0.0.1", 0), editor.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as prof:
                dom = subprocess.run([EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}",
                                      "--virtual-time-budget=8000", "--dump-dom",
                                      f"http://127.0.0.1:{httpd.server_address[1]}/#selftest"],
                                     capture_output=True, text=True, timeout=90).stdout
        finally:
            httpd.shutdown()
        self.assertIn("SELFTEST OK", dom, dom[dom.find("SELFTEST"):][:2000])


@unittest.skipUnless(os.path.exists(EDGE) and shutil.which("node"), "needs Microsoft Edge and Node for a page check")
class EditorSaveTests(unittest.TestCase):
    def test_tab_saves_change_only_the_edited_lines(self):
        """Edit one field in the Factions and Recipes tabs, click Save: each file on disk differs
        from before only in that value (and keeps its key order)."""
        import subprocess, sys, tempfile, threading
        tools = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
        sys.path.insert(0, tools)
        import editor
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, "content")
            shutil.copytree(os.path.join(os.path.dirname(os.path.abspath(__file__)), "content"), c)
            before = {f: open(os.path.join(c, f), encoding="utf-8").read() for f in ("factions.json", "recipes.json")}
            handler = type("H", (editor.Handler,), {"directory": c, "backups_dir": os.path.join(d, "bk")})
            httpd = editor.http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}/"
            cases = [("#factions", [
                "(() => { const tr=[...document.querySelectorAll('#facTable tr')].find(t=>t.cells[0]&&t.cells[0].textContent==='1003');"
                " const k=tr.querySelector('[data-k=kill]'); k.value='-12'; k.dispatchEvent(new Event('change')); return 1; })()",
                "document.getElementById('saveFactions').click(), 1", 1500,
                "document.getElementById('problems').innerText"]),
                ("#recipes=copper_ingot", [
                "(() => { const i=document.querySelector('#recBody [data-f=xp]'); i.value='121'; i.dispatchEvent(new Event('input')); return 1; })()",
                "document.getElementById('saveRecipes').click(), 1", 1500,
                "document.getElementById('problems').innerText"])]
            try:
                for hash_, steps in cases:
                    sf = os.path.join(d, "steps.json")
                    with open(sf, "w", encoding="utf-8") as f:
                        json.dump(steps, f)
                    out = subprocess.run(["node", os.path.join(tools, "editor_e2e.mjs"), base + hash_, sf],
                                         capture_output=True, text=True, timeout=90)
                    self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
                    self.assertIn("Saved", out.stdout.strip().splitlines()[-1])
            finally:
                httpd.shutdown()
            for f, old_value, new_value in (("factions.json", '"kill": -10', '"kill": -12'), ("recipes.json", '"xp": 120', '"xp": 121')):
                after = open(os.path.join(c, f), encoding="utf-8").read()
                changed = [(a, b) for a, b in zip(before[f].splitlines(), after.splitlines()) if a != b]
                self.assertEqual(len(changed), 1, changed)
                self.assertIn(old_value, changed[0][0])
                self.assertIn(new_value, changed[0][1])


class ImportZoneTests(unittest.TestCase):
    def test_plan_and_apply_never_overwrite(self):
        import sys, tempfile
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        with tempfile.TemporaryDirectory() as d:
            names = os.path.join(d, "ChunkNames.txt")
            with open(names, "w", encoding="latin-1") as f:
                f.write('SHORTNAME="Khal" DISPLAYNAME="Khal" X=-13 Y=-9\nSHORTNAME="X" DISPLAYNAME="Inst" X=3000 Y=3000\n')
            chunks = import_zone.zone_chunks(names)
            self.assertEqual(chunks, {"Khal": (-13, -9)})                 # instances (1000+) left out
            raw = os.path.join(d, "raw", "b1")
            os.makedirs(raw)
            with open(os.path.join(raw, "npc.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"name": "Afshin Budjiri", "zone": "Khal", "continent": "Qalia", "level": 40,
                                    "services": ["trainer", "quest giver"],
                                    "location": {"raw": "-9686, -35413, 1540"},
                                    "sources": [{"url": "https://example.org/a"}]}) + "\n")
                f.write(json.dumps({"name": "Nowhere Man", "zone": "Khal"}) + "\n")       # no position
            level, mobs, spawns = import_zone.plan("Khal", import_zone.archive_npcs(os.path.join(d, "raw")), chunks)
            self.assertEqual(level, "chunk_n13_n9")
            self.assertEqual([{k: v for k, v in sp.items() if k != "yaw"} for sp in spawns],
                             [{"mob": "arch_afshin_budjiri", "x": -9686, "y": -35413, "z": 1540}])
            t = mobs["arch_afshin_budjiri"]
            self.assertEqual((t["race"], t["level"], t["title"], t["_source"]), (13, 40, "Trainer", "https://example.org/a"))
            content = os.path.join(d, "content")
            os.makedirs(os.path.join(content, "spawns"))
            with open(os.path.join(content, "mobs.json"), "w", encoding="utf-8") as f:
                json.dump({"arch_afshin_budjiri": {"name": "Edited by a builder"}}, f)
            self.assertEqual(import_zone.apply(level, mobs, spawns, content), (0, 1))     # template kept, spawn added
            self.assertEqual(import_zone.apply(level, mobs, spawns, content), (0, 0))     # a second run adds nothing
            kept = json.load(open(os.path.join(content, "mobs.json"), encoding="utf-8"))
            self.assertEqual(kept["arch_afshin_budjiri"]["name"], "Edited by a builder")
            self.assertEqual(kept["arch_afshin_budjiri"]["level"], 40)                 # missing fields added

    def test_quest_givers_from_quest_locations(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        quests = {
            "A": {"name": "A", "zone": "Khal", "giver": "Wadj Peheb", "level": 5,
                  "archive_fields": {"location": ["33289, -95029, 2936 in Khal (-13, -9)"]},
                  "referenced_entities": [{"name": "Wadj Peheb", "url": "https://vgsoharchive.com/mobs/wadj-peheb"}]},
            "B": {"name": "B", "zone": "Khal", "giver": "Kurake , Kurake Wamani",
                  "archive_fields": {"location": ["1, 2, 3 in Khal (-13, -9)"]}},
            "C": {"name": "C", "zone": "Khal", "giver": "Far Away",
                  "archive_fields": {"location": ["1, 2, 3 in Elsewhere (-14, -9)"]}}}
        spots = import_zone.quest_giver_spots("Khal", quests, (-13, -9))
        self.assertEqual(list(spots), ["Wadj Peheb"])        # several names and other chunks are skipped
        level, mobs, spawns = import_zone.plan("Khal", {}, {"Khal": (-13, -9)}, quests, "Qalia")
        self.assertEqual([{k: v for k, v in sp.items() if k != "yaw"} for sp in spawns],
                         [{"mob": "arch_wadj_peheb", "x": 33289, "y": -95029, "z": 2936}])
        self.assertEqual((mobs["arch_wadj_peheb"]["level"], mobs["arch_wadj_peheb"]["race"]), (5, 13))

    def test_npcs_face_their_neighbour(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        a, b, c = {"mob": "a", "x": 0, "y": 0}, {"mob": "b", "x": 100, "y": 0}, {"mob": "c", "x": 0, "y": 5000}
        import_zone.face([a, b, c])
        self.assertEqual((a["yaw"], b["yaw"]), (0, 32768))           # a looks east at b, b west at a
        self.assertTrue(0 <= c["yaw"] < 65536)                        # alone: a fixed direction

    def test_npc_race_from_archive(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        race = lambda r: import_zone.npc_race({"continent": "Qalia", "archive_fields": {"race": [r]} if r else {}})
        self.assertEqual([race(r) for r in ("Dwarf", "Kojani Human", "Half-Elf", "Gnome *")], [2, 12, 8, 6])
        self.assertEqual([race(r) for r in ("Human", "Jharru", None)], [13, 13, 13])   # the continent's

    def test_camps_from_zone_map(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        zone = {"map_places": [{"name": "Hill Cats", "location": {"raw": "6515, -40766"}},
                               {"name": "Hillshadow", "location": {"raw": "7730, -59516"}},      # one name: may be a person
                               {"name": "Injured Soldiers", "location": {"raw": "1, 2"}},
                               {"name": "Bank", "location": {"raw": "3, 4"}}]}
        cr = {n: {"name": n, "zone": "Halgarad", "level": 1} for n in ("Hill Cat", "Hillshadow", "Injured Soldier")}
        out = import_zone.camps("Halgarad", zone, cr, "Thestra")
        self.assertEqual([(k, len(c)) for k, _, c in out], [("arch_hill_cat", 3)])
        self.assertTrue(all("z" not in s and abs(s["x"] - 6515) <= 250 for s in out[0][2]))   # the server finds the ground

    def test_people_from_zone_map(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        zone = {"map_places": [{"name": "Sorcerer Instructor", "location": {"raw": "-34897, -20831"}, "entities": ["Fila Azadi"]},
                               {"name": "Heavyfighter Instructor", "location": {"raw": "100, 100"}, "entities": ["A B", "C D"]},
                               {"name": "Camp", "location": {"raw": "5000, 5000"}, "entities": ["Boiling Cauldrons"]},
                               {"name": "Dock", "location": {"raw": "-10000, -24000"}, "entities": ["Ju Mai"]}]}
        placed = [{"mob": "arch_x", "x": -34143, "y": -19537, "z": 1820}]
        out = {k: (t, sp) for k, t, sp in import_zone.map_people("Ahgram", zone, {}, "Qalia", placed)}
        self.assertEqual(sorted(out), ["arch_a_b", "arch_c_d", "arch_fila_azadi"])     # no objects, no round guesses
        t, sp = out["arch_fila_azadi"]
        self.assertEqual((t["title"], t["trainer_classes"], sp["z"]), ("Sorcerer Instructor", ["Sorcerer"], 1820))
        self.assertEqual(out["arch_a_b"][0]["trainer_classes"], ["Warrior", "Paladin", "Dread Knight"])
        self.assertNotIn("z", out["arch_a_b"][1])                                       # no neighbour: the terrain

    def test_altars_and_mailboxes_from_zone_map(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        zone = {"map_places": [{"name": "Bindstone", "location": {"raw": "100, 100"}},
                               {"name": "Resurection Altar", "location": {"raw": "1100, 100"}},    # too close to the first
                               {"name": "Altar", "location": {"raw": "-9000, 100"}},
                               {"name": "Mailbox", "location": {"raw": "5, 5"}}]}
        existing = [{"mob": "camp_altar", "x": -9500, "y": 0}]
        out = import_zone.service_props(zone, [{"mob": "a", "x": 0, "y": 0, "z": 77}], existing)
        self.assertEqual([(s["mob"], s["x"], s.get("z")) for s in out], [("camp_altar", 100, 77), ("camp_mailbox", 5, 77)])

    def test_off_terrain_city_heights(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        city = [{"mob": f"arch_{i}", "x": i * 100, "y": 0, "z": 87000} for i in range(6)]     # below the mountain
        near, far = {"mob": "arch_p", "x": 700, "y": 0}, {"mob": "arch_q", "x": 50000, "y": 0}
        import_zone.off_terrain_heights("chunk_x", city, [near, far], ground=lambda x, y: 95000)
        self.assertEqual((near.get("z"), far.get("z")), (87000, None))
        on_ground = {"mob": "arch_r", "x": 700, "y": 0}
        import_zone.off_terrain_heights("chunk_x", city, [on_ground], ground=lambda x, y: 87050)
        self.assertNotIn("z", on_ground)                         # the city stands on the terrain: keep it

    def test_people_at_map_labels(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        labels = {(-13, -9): {"zaraj arena": (100.0, 200.0, 300.0), "khal": (0.0, 0.0, 0.0)}}
        npcs = {"Arena Enforcer": {"name": "Arena Enforcer", "zone": "Khal", "archive_fields": {"locations seen": ["Zaraj Arena"]}},
                "A Beggar": {"name": "A Beggar", "zone": "Khal", "archive_fields": {"locations seen": ["Khal"]}}}
        out = import_zone.poi_people("Khal", (-13, -9), npcs, "Qalia", [], labels)
        self.assertEqual([(k, sp["x"], sp["z"]) for k, _, sp in out], [("arch_arena_enforcer", 100, 300)])  # not the hub

    def test_female_titles(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        self.assertEqual(import_zone.template({"name": "Priestess Aludan"}).get("gender"), 1)
        self.assertIsNone(import_zone.template({"name": "Ladyslayer Brom"}).get("gender"))   # whole words only
        self.assertIsNone(import_zone.template({"name": "Kooshin Vahdaat"}).get("gender"))

    def test_zone_race(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        recs = {n: {"name": n, "zone": "Mekalia", "archive_fields": {"race": [r]}}
                for n, r in (("a", "Gnome"), ("b", "Gnome"), ("c", "Gnome *"), ("d", "Qaliathari"))}
        self.assertIsNone(import_zone.zone_race("Mekalia", recs))          # 3 of 4 is not enough
        del recs["d"]
        self.assertEqual(import_zone.zone_race("Mekalia", recs), 6)
        import_zone.ZONE_RACE["Mekalia"] = 6
        try:
            self.assertEqual(import_zone.npc_race({"zone": "Mekalia", "continent": "Qalia"}), 6)
        finally:
            import_zone.ZONE_RACE.pop("Mekalia")

    def test_mislabelled_objects_and_zone_case(self):
        import sys, tempfile, json as _json
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        self.assertTrue(import_zone.is_object({"archive_fields": {"type": ["Object"]}}))
        self.assertFalse(import_zone.is_object({"archive_fields": {"type": ["Object"], "role": ["Merchant - Crafting Equipment"]}}))
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "b1"))
            with open(os.path.join(d, "b1", "npc.jsonl"), "w", encoding="utf-8") as f:
                f.write(_json.dumps({"name": "Fenton Orde", "zone": "Wardship Of The Sleeping Moon"}) + "\n")
            with unittest.mock.patch.object(import_zone, "zone_chunks", return_value={"Wardship of the Sleeping Moon": (-23, 27)}):
                recs = import_zone.archive_npcs(d)
        self.assertEqual(recs["Fenton Orde"]["zone"], "Wardship of the Sleeping Moon")
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "b1"))
            with open(os.path.join(d, "b1", "quest.jsonl"), "w", encoding="utf-8") as f:
                f.write(_json.dumps({"name": "Ceremony", "zone": "Nerail Tharazen",
                                     "archive_fields": {"location": ["-80422, 84409, 17146 in Lomshir (-15, -9)"]}}) + "\n")
            with unittest.mock.patch.object(import_zone, "zone_chunks", return_value={"Lomshir": (-15, -9)}):
                recs = import_zone.archive_npcs(d, kind="quest")
        self.assertEqual(recs["Ceremony"]["zone"], "Lomshir")             # from the location's chunk
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "b1"))
            with open(os.path.join(d, "b1", "npc.jsonl"), "w", encoding="utf-8") as f:
                f.write(_json.dumps({"name": "Moor Man", "zone": "Vursog Moor"}) + "\n")
            with unittest.mock.patch.object(import_zone, "zone_chunks", return_value={"Vsurog Moor": (-30, 24)}), \
                    unittest.mock.patch.object(import_zone, "poi_labels", return_value={}):
                recs = import_zone.archive_npcs(d)
        self.assertEqual(recs["Moor Man"]["zone"], "Vsurog Moor")         # ZONE_ALIASES
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "b1"))
            with open(os.path.join(d, "b1", "npc.jsonl"), "w", encoding="utf-8") as f:
                f.write(_json.dumps({"name": "Cave Man", "zone": "Oathbreaker Caves"}) + "\n")
            with open(os.path.join(d, "b1", "zone.jsonl"), "w", encoding="utf-8") as f:
                f.write(_json.dumps({"name": "Oathbreaker Caves", "archive_fields": {"chunk": ["Bordinars Cleft"]}}) + "\n")
            with unittest.mock.patch.object(import_zone, "zone_chunks", return_value={"Bordinar's Cleft": (-28, 26)}), \
                    unittest.mock.patch.object(import_zone, "poi_labels", return_value={}):
                recs = import_zone.archive_npcs(d)
        self.assertEqual(recs["Cave Man"]["zone"], "Bordinar's Cleft")    # a sub-area page's parent

    def test_absurd_heights_dropped(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        npcs = {"Nirrin": {"name": "Nirrin", "zone": "Z", "location": {"raw": "-1483, -1717, 223739"}}}
        with unittest.mock.patch.object(import_zone, "existing_spawns", return_value=[]):
            level, mobs, spawns = import_zone.plan("Z", npcs, {"Z": (-11, -10)})
        self.assertEqual([("z" in sp, sp["x"]) for sp in spawns], [(False, -1483)])

    def test_role_titles_cleaned(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        self.assertEqual(import_zone.clean_role("Light Armor Vendor (east city walls outside Tavern)"), "Light Armor Vendor")
        self.assertEqual(import_zone.clean_role("(Peacebearer of Gloriann)"), "(Peacebearer of Gloriann)")
        self.assertIsNone(import_zone.clean_role("Up on the wall - to the north from stairs"))

    def test_quest_giver_not_doubled(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        npcs = {"Ardalan Awji": {"name": "Ardalan Awji", "zone": "Khal", "location": {"raw": "100, 200, 300"}}}
        quests = {"Q": {"name": "Q", "zone": "Khal", "giver": "Ardalan",
                        "archive_fields": {"location": ["110, 190, 300 in Khal (-13, -9)"]}}}
        level, mobs, spawns = import_zone.plan("Khal", npcs, {"Khal": (-13, -9)}, quests, "Qalia")
        self.assertEqual([s["mob"] for s in spawns], ["arch_ardalan_awji"])      # "Ardalan" is the same person

    def test_located_creatures(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        cr = {"Blackheart": {"name": "Blackheart", "zone": "Lomshir", "level": 9,
                             "archive_fields": {"location": ["39719, -61690, -2349"], "behaviour": ["Aggressive"],
                                                "difficulty": ["4 dots"], "respawn": ["20"]}},
              "A Crate": {"name": "A Crate", "zone": "Lomshir", "archive_fields": {"location": ["1, 2, 3"], "type": ["Object"]}},
              "Elsewhere": {"name": "Elsewhere", "zone": "Lomshir", "archive_fields": {"location": ["1, 2, 3 in X (5, 5)"]}}}
        level, mobs, spawns = import_zone.plan("Lomshir", {}, {"Lomshir": (-15, -9)}, {}, "Qalia", cr)
        self.assertEqual([{k: v for k, v in sp.items() if k != "yaw"} for sp in spawns],
                         [{"mob": "arch_blackheart", "x": 39719, "y": -61690, "z": -2349, "respawn": 1200}])
        t = mobs["arch_blackheart"]
        self.assertEqual((t["level"], t["aggro_radius"], t["health"]), (9, 600, (100 + 40 * 9) * 4 // 2))

    def test_parley_types(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        rec = {"archive_fields": {"parley types": ["[[[ Gossip ]]], , , [[[ Convice ]]], [[[ Interview ]]]"],
                                  "presence": ["700"]}}
        self.assertEqual(import_zone.parley_types(rec), ["gossip", "convince", "interview"])
        t = import_zone.template(dict(rec, name="X", level=10))
        self.assertEqual(t["parley"], ["archive_gossip_700", "archive_convince_700", "archive_interview_700"])
        self.assertEqual(import_zone.parley_types({"archive_fields": {"parley types": [", ,"]}}), [])

    def test_several_parley_offers(self):
        import diplomacy
        m = diplomacy.parley_offer(5, [{"type": "gossip"}, {"type": "convince", "presence": 3}])
        _t, eid, n = struct.unpack_from("<HII", m)
        body = m[10:10 + n]
        self.assertEqual(struct.unpack_from("<Qi", body), (5, 2))
        second = body.index("Let's talk business.\0".encode("utf-16-le"), 12 + 1) + len("Let's talk business.\0".encode("utf-16-le"))
        self.assertEqual(struct.unpack_from("<iiiiBBB", body, second),
                         (diplomacy.PARLEY_OPTION_ID + 1, 3, 0, 0, 0, 0, diplomacy.PARLEY_TYPES["convince"]))

    def test_trainer_classes(self):
        import login_stub
        npc = types.SimpleNamespace(trainer=True, trainer_classes=["Ranger"])
        self.assertTrue(login_stub.trains(npc, types.SimpleNamespace(klass=19)))      # Ranger
        self.assertFalse(login_stub.trains(npc, types.SimpleNamespace(klass=28)))     # Warrior
        npc.trainer_classes = []
        self.assertTrue(login_stub.trains(npc, types.SimpleNamespace(klass=28)))


class ArchiveSearchTests(unittest.TestCase):
    def test_newest_record_and_ranking(self):
        import sys, tempfile
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        with tempfile.TemporaryDirectory() as d:
            for folder, lvl, when in (("a", 5, "2026-01-01"), ("b", 9, "2026-02-01")):
                os.makedirs(os.path.join(d, folder))
                with open(os.path.join(d, folder, "creature.jsonl"), "w", encoding="utf-8") as f:
                    f.write(json.dumps({"type": "creature", "name": "Grey Wolf", "level": lvl, "collected_at": when}) + "\n")
                    f.write(json.dumps({"type": "creature", "name": "Wolf", "level": 1, "collected_at": when}) + "\nnot json\n")
            saved = list(editor._ARCHIVE)
            editor._ARCHIVE.clear()
            try:
                editor.archive_index(d)
                hits = editor.archive_search("wolf", "creature")
                self.assertEqual([h["name"] for h in hits], ["Wolf", "Grey Wolf"])          # exact match first
                self.assertEqual(hits[1]["level"], 9)                                          # newest record wins
                self.assertEqual(editor.archive_search("w"), [])
            finally:
                editor._ARCHIVE[:] = saved


class ArchiveDraftTests(unittest.TestCase):
    def test_loot_draft(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        rec = {"name": "X", "source": "Grim Thing", "drops": [
            {"item": "Copper Ore", "chance": "33.3%", "quantity": None, "observed_sample": "33.3% 1/3"},
            {"item": "Mystery Thing", "chance": None}]}
        d = editor.loot_draft(rec, "u", lambda n: n.lower().replace(" ", "_"))
        self.assertEqual(d["key"], "grim_thing_drops")
        self.assertEqual(d["value"][0]["chance"], 0.333)
        self.assertIn("icon", d["value"][0])                       # Copper Ore is in items.json
        self.assertNotIn("chance", d["value"][1])
        self.assertEqual(len(d["needs"]), 3)                       # small sample, unknown item, no chance

    def test_quest_draft_maps_known_names(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        rec = {"name": "Wolf Trouble", "level": 12, "giver": "Orin the Trader", "turn_in": "Nobody Here",
               "chain_previous": "Wanderer Trouble",
               "candidate_steps": [{"objective": "Ashen Wolf Slain (3)", "kind": "kill", "target": "Ashen Wolf", "count": 3},
                                   {"objective": "Pelts (2)", "kind": "collect", "target": "Wolf Pelt", "count": 2},
                                   {"objective": "Shadow Slain (1)", "kind": "kill", "target": None, "count": 1}],
               "rewards": {"xp": 300, "coin_copper": 75, "items": None, "choice": ["A", "B"]}}
        d = editor.quest_draft(rec, "https://example.org/q", lambda n: n.lower().replace(" ", "_"))
        q = d["value"]
        self.assertEqual((d["file"], d["key"]), ("quests.json", "wolf_trouble"))
        self.assertEqual((q["giver"], q["_turn_in_name"], q["requires"]), ("camp_merchant", "Nobody Here", ["wanderer_trouble"]))
        self.assertEqual(q["steps"][0]["kill"], {"wastes_wolf": 3})
        self.assertEqual(q["steps"][1]["collect"], {"Wolf Pelt": 2})
        self.assertEqual(q["steps"][2]["_count"], 1)
        self.assertEqual(q["reward"], {"xp": 300, "coin": 75, "choice": ["A", "B"]})
        self.assertTrue(any("turn_in" in n for n in q["_needs"]) and any("Shadow" in n for n in q["_needs"]))

    def test_drafts_copy_only_known_values(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        src = [{"url": "https://example.org/x", "title": "X", "date": None}]
        recs = {("creature", "Grey Wolf"): {"type": "creature", "name": "Grey Wolf", "level": 7, "creature_kind": "wolf",
                                            "sources": src},
                ("item", "Iron Cap"): {"type": "item", "name": "Iron Cap", "item_type": "armor", "slot": "head",
                                       "armor": 5, "sources": src, "confidence": "low", "notes": ""}}
        saved = list(editor._ARCHIVE)
        editor._ARCHIVE[:] = [recs]
        try:
            d = editor.draft("creature", "Grey Wolf")
            self.assertEqual((d["file"], d["value"]["race"], d["value"]["level"]), ("mobs.json", 119, 7))
            self.assertEqual(d["value"]["_needs"], ["health", "damage"])                  # nothing invented
            i = editor.draft("item", "Iron Cap")["value"]
            self.assertEqual((i["type"], i["slot"], i["armor"], i["_source"]), ("armor", "HEAD", 5, src[0]["url"]))
            self.assertIsNone(editor.draft("item", "Nope"))
        finally:
            editor._ARCHIVE[:] = saved


@unittest.skipUnless(os.path.isdir(os.path.join("..", "VGUIAssets")), "needs the client's icon sheets")
class IconTests(unittest.TestCase):
    def test_icon_png(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        self.assertGreater(len(editor.icon_index()), 1000)
        data = editor.icon_png(436)
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertEqual(struct.unpack(">II", data[16:24]), (40, 40))
        self.assertIsNone(editor.icon_png(999999999))


@unittest.skipUnless(os.path.isdir(os.path.join("..", "Assets", "Characters", "Meshes")), "needs the client's item meshes")
class MeshListTests(unittest.TestCase):
    def test_existing_gear_models_are_listed(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        mobs = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "content", "mobs.json"), encoding="utf-8"))
        for key, m in mobs.items():
            for t, n, _slot in (m.get("gear") or []) if isinstance(m, dict) else []:
                self.assertIn(n, editor.mesh_numbers(t), f"{key}: gear ({t}, {n}) not in the client")


@unittest.skipUnless(os.path.isdir(os.path.join("..", "Assets", "Maps")), "needs the client's maps")
class SpawnWarningTests(unittest.TestCase):
    def test_spawn_inside_rock_is_warned(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        import obstacles
        name = "spawns/chunk_n19_12.json"
        text = open(os.path.join(editor.CONTENT, "spawns", "chunk_n19_12.json"), encoding="utf-8").read()
        # The hand-made camp is clean; archive NPCs whose recorded height puts them on a mesh are
        # flagged _uncertain in the file (B-008) and may still draw the hint.
        uncertain = {m["name"] for s in json.loads(text)["spawns"] if s.get("_uncertain")
                     for m in [json.load(open(os.path.join(editor.CONTENT, "mobs.json"), encoding="utf-8"))[s["mob"]]]}
        warns = editor.spawn_warnings(editor.CONTENT, name, text)
        self.assertEqual([w for w in warns if not any(f"({n})" in w for n in uncertain)], [])
        rock = next(o for o in obstacles.obstacles("chunk_n19_12") if o[2] > 200)
        doc = json.loads(text)
        doc["spawns"].append({"mob": "wastes_wolf", "x": round(rock[0]), "y": round(rock[1])})
        warn = editor.spawn_warnings(editor.CONTENT, name, json.dumps(doc))
        self.assertTrue(any("inside an obstacle" in w for w in warn), warn)


class EditorAccountsTests(unittest.TestCase):
    def test_contributor_proposes_admin_approves(self):
        import http.client, shutil, sys, tempfile, threading
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import accounts
        import editor
        with tempfile.TemporaryDirectory() as d:
            content = os.path.join(d, "content")
            shutil.copytree(os.path.join(os.path.dirname(os.path.abspath(__file__)), "content"), content)
            saved_file = accounts.ACCOUNTS_FILE
            accounts.ACCOUNTS_FILE = os.path.join(d, "accounts.json")
            accounts.FAILURES.clear()
            handler = type("H", (editor.Handler,), {"directory": content, "login_required": True,
                                                    "proposals_dir": os.path.join(d, "proposals"),
                                                    "backups_dir": os.path.join(d, "bk"), "sessions": {}})
            httpd = editor.http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            port = httpd.server_address[1]

            def call(method, path, body=None, cookie=None, editor_header=True):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
                h = {"X-Editor": "1"} if editor_header else {}
                if cookie:
                    h["Cookie"] = cookie
                c.request(method, path, body=body, headers=h)
                r = c.getresponse()
                out = (r.status, json.loads(r.read() or b"{}"), r.getheader("Set-Cookie"))
                c.close()
                return out
            try:
                self.assertIsNone(accounts.create("helper", "secret1"))
                self.assertIsNone(accounts.create("boss", "secret2"))
                self.assertIsNone(accounts.set_editor_role("boss", "admin"))
                self.assertEqual(call("GET", "/api/files")[0], 401)                        # must log in
                self.assertEqual(call("POST", "/api/login", json.dumps({"username": "helper", "password": "bad"}))[0], 403)
                st, body, cookie = call("POST", "/api/login", json.dumps({"username": "helper", "password": "secret1"}))
                self.assertEqual((st, body["role"]), (200, "contributor"))
                helper = cookie.split(";")[0]
                text = open(os.path.join(content, "hints.json"), encoding="utf-8").read().replace("Welcome to Telon", "Welcome!")
                self.assertEqual(call("PUT", "/api/file?name=hints.json", text, helper)[0], 403)   # can't save directly
                self.assertEqual(call("PUT", "/api/propose?name=hints.json", text, helper, editor_header=False)[0], 403)
                st, body, _ = call("PUT", "/api/propose?name=hints.json&note=nicer", text, helper)
                pid = body["proposal"]
                self.assertEqual(call("POST", f"/api/review?id={pid}&action=approve", None, helper)[0], 403)
                boss = call("POST", "/api/login", json.dumps({"username": "boss", "password": "secret2"}))[2].split(";")[0]
                st, diff, _ = call("GET", f"/api/proposal?id={pid}", None, boss)
                self.assertIn("+", diff["diff"])
                self.assertEqual(call("POST", f"/api/review?id={pid}&action=approve", None, boss)[0], 200)
                self.assertIn("Welcome!", open(os.path.join(content, "hints.json"), encoding="utf-8").read())
                self.assertEqual(call("GET", "/api/proposals", None, helper)[1][0]["status"], "approved")
            finally:
                httpd.shutdown()
                accounts.ACCOUNTS_FILE = saved_file


class AbilityArchiveTests(unittest.TestCase):
    def test_ability_from_archive(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import editor
        rec = {"type": "ability", "name": "Kick I", "icon_name": "Icon516.png", "tooltip": "Kicks.",
               "cast_time_seconds": None, "refresh_seconds": 12, "sources": [{"url": "https://example.org/kick"}]}
        saved_a, saved_i = list(editor._ARCHIVE), dict(editor._ICON_INDEX)
        editor._ARCHIVE[:] = [{("ability", "Kick I"): rec}]
        editor._ICON_INDEX.clear()
        editor._ICON_INDEX[516] = ("x.tga", 0, 0, 40, 40)
        try:
            self.assertEqual(editor.ability_from_archive("Kick I"),
                             {"icon": 516, "description": "Kicks.", "refresh": 12.0, "_source": "https://example.org/kick"})
            self.assertEqual(editor.ability_from_archive("Nope"), {})
        finally:
            editor._ARCHIVE[:] = saved_a
            editor._ICON_INDEX.clear()
            editor._ICON_INDEX.update(saved_i)


class JournalRecipeTests(unittest.TestCase):
    def test_details_and_missing_steps(self):
        import craft
        r = {"id": 5001, "name": "Test", "stages": [{"name": "S", "steps": [{"name": "A", "tool": "Tongs"}, {"name": "B"}]}]}
        eid, data = payload(craft.journal_recipe(r))
        self.assertEqual(eid, 0x2F2)
        self.assertEqual(payload(craft.journal_missing([7, 9])), (0x309, struct.pack("<iii", 2, 7, 9)))
        self.assertEqual(len(craft.missing_steps(r, set())), 1)
        self.assertEqual(craft.missing_steps(r, {"Tongs"}), [])


class QuestReadinessTests(unittest.TestCase):
    """tools/quest_readiness.py: which archive quests can be done with what is placed."""

    def setUp(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import quest_readiness
        self.qr = quest_readiness
        self.world = {"chunk_n25_26": ({"ranger shyath": "arch_ranger_shyath", "timber wolf": "arch_timber_wolf"},
                                       {"wolf pelt": ("Wolf Pelt", 442)})}
        self.chunks = {"Leth Nurae": (-25, 26)}

    def quest(self, *objectives, giver="Ranger Shyath"):
        return {"name": "Q", "zone": "Leth Nurae", "giver": giver,
                "candidate_steps": [{"objective": o, "kind": k, "count": n} for o, k, n in objectives]}

    def test_objective_names(self):
        self.assertEqual(self.qr.objective_target("- Loamite Sludgemongers Slain (7/10)"), "loamite sludgemongers")
        self.assertIn("timber wolf", self.qr.singulars("timber wolves"))
        self.assertEqual([self.qr.coin_copper(t) for t in ("1s 40c", "55 c", "17", "0")], [140, 55, None, None])

    def test_steps(self):
        status, steps = self.qr.plan_steps(self.quest(("Timber Wolves Slain (12)", "kill", 12),
                                                      ("Wolf Pelt (0/3)", None, 3)), self.world, self.chunks)
        self.assertEqual(status, "ready")
        self.assertEqual(steps, [{"objective": "Timber Wolves Slain", "kill": {"arch_timber_wolf": 12}},
                                 {"objective": "Wolf Pelt", "collect": {"Wolf Pelt": 3}}])
        self.assertEqual(self.qr.readiness(self.quest(("Bear Claws (0/2)", "collect", 2)), self.world, self.chunks), "giver")
        self.assertEqual(self.qr.readiness(self.quest(("Wolf Pelt (1)", "collect", 1), giver="Nobody"),
                                           self.world, self.chunks), "no giver")
        r = self.qr.report({"a": self.quest(("Wolf Pelt (1)", "collect", 1)), "b": self.quest(("Bear Claws (0/2)", "collect", 2))},
                           self.world, self.chunks)
        self.assertEqual(r["totals"], {"ready": 1, "giver": 1})
        self.assertEqual(r["zones"][0]["blocked"][0]["objectives"], [["Bear Claws (0/2)", "no placed creature in the zone drops it"]])
        # A kill target the archive knows but doesn't locate gets an invented camp near the giver,
        # marked _placeholder, on dry ground.
        creatures = {"Bear": {"name": "Bear", "zone": "Leth Nurae", "level": 5}}
        q = {"bear": self.quest(("Bears Slain (3)", "kill", 3))}
        with unittest.mock.patch.object(self.qr.z, "existing_spawns",
                                        return_value=[{"mob": "arch_ranger_shyath", "x": 0, "y": 0, "z": 100}]),                 unittest.mock.patch.object(self.qr, "_wet", side_effect=lambda lvl, x, y, h=None: x > 0),                 unittest.mock.patch.object(self.qr, "_ground", return_value=90):
            camps = self.qr.placeholder_camps(q, self.world, self.chunks, creatures)
        (key, t, camp), = camps["chunk_n25_26"]
        self.assertEqual((key, len(camp), t["level"]), ("arch_bear", 3, 5))
        self.assertTrue(all(sp["x"] <= 0 and sp["_placeholder"] and "z" not in sp for sp in camp))
        import tempfile, json as _json
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "quests.json"), "w", encoding="utf-8") as f:
                _json.dump({"arch_a": {"name": "A"}, "arch_b": {"name": "B"}, "arch_c": {"name": "C", "requires": ["arch_b"]}}, f)
            archive = {"A": {"chain_previous": None}, "B": {"chain_previous": "C"}, "C": {"chain_previous": "A"}}
            # B follows C, but C already requires B: no loop; A has no previous quest.
            self.assertEqual(self.qr.link_chains(archive, d), 0)
            archive["B"]["chain_previous"] = "A"
            self.assertEqual(self.qr.link_chains(archive, d), 1)
            with open(os.path.join(d, "quests.json"), encoding="utf-8") as f:
                self.assertEqual(_json.load(f)["arch_b"]["requires"], ["arch_a"])
        # The giver as the objective ("read the book") is an interaction we can't do.
        self.assertEqual(self.qr.readiness(self.quest(("Ranger Shyath (1/1)", None, 1)), self.world, self.chunks), "giver")


class ArchiveMerchantTests(unittest.TestCase):
    """Role stocks for imported merchants and placeholder icons (tools/import_zone.py)."""

    def setUp(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        self.z = import_zone

    def test_role_stock(self):
        self.assertEqual(self.z.role_stock_key("Merchant - Heavy Armor Vendor"), "archive_heavy_armor")
        self.assertEqual(self.z.role_stock_key("Ranged Weapon Vendor"), "archive_ranged")
        self.assertIsNone(self.z.role_stock_key("Merchant - General Goods"))
        rec = lambda name, lvl, rarity="common": {"name": name, "level_required": lvl, "rarity": rarity, "slot": "chest",
                                                  "archive_fields": {"type": ["Heavy Armor"]}}
        recs = {r["name"]: r for r in (rec("Plate Vest", 5), rec("Iron Helm", 1), rec("Steel Greaves", 10),
                                       rec("Basnaret's Robe", 50), rec("Glowing Mail", 20, "rare"))}
        stock = self.z.build_role_stock("heavy_armor", recs)
        self.assertEqual([(r["name"], p) for r, p in stock], [("Iron Helm", 25), ("Plate Vest", 125), ("Steel Greaves", 250)])
        del recs["Steel Greaves"]
        self.assertEqual(self.z.build_role_stock("heavy_armor", recs), [])     # too few: keep general goods

    def test_icons(self):
        self.assertEqual(self.z.slot_icon({}, "CHEST"), 436)
        self.assertEqual(self.z.slot_icon({}, "TWOHANDS", "Ardent Greatmaul"), 425)
        self.assertEqual(self.z.slot_icon({}, None), 442)
        import content
        c = content.Content.__new__(content.Content)
        c.loot, c.items = {"t": [{"name": "Known"}, {"name": "Unknown"}, {"name": "Set", "icon": 7}]}, {"Known": {"icon": 436}}
        self.assertEqual([icon for _, icon, _ in c.roll_loot("t")], [436, 442, 7])


class ObstacleLoadTests(unittest.TestCase):
    def test_obstacles_build_in_the_background(self):
        import threading
        gate = threading.Event()
        def slow(level):
            gate.wait(5)
            return ["obs"]
        import obstacles
        import time
        with unittest.mock.patch.object(obstacles, "obstacles", side_effect=slow), \
                unittest.mock.patch.object(zone, "obstacles_blocked", return_value=True):
            zone._obstacles.pop("chunk_test", None)
            self.assertFalse(zone.npc_blocked("chunk_test", 0, 0, 0))     # loading: not blocked, no wait
            self.assertFalse(zone.npc_blocked("chunk_test", 0, 0, 0))
            gate.set()
            for _ in range(50):
                if zone._obstacles.get("chunk_test") == ["obs"]:
                    break
                time.sleep(0.02)
            self.assertTrue(zone.npc_blocked("chunk_test", 0, 0, 0))
        zone._obstacles.pop("chunk_test", None)


class PresenceTests(unittest.TestCase):
    def test_presence_rows(self):
        p = types.SimpleNamespace(presence={"noble": 120})
        recs = zone.presence_records(p)
        self.assertEqual(len(recs), 8)
        ups = zone.presence_updates(p)
        noble = [u for u in ups if struct.unpack_from("<i", u, len(u) - 4)[0] == 0x22][0]
        self.assertEqual(struct.unpack_from("<I", noble, 2)[0], 0x2D4)
        self.assertEqual(struct.unpack_from("<ib", noble, 10), (zone.PRESENCE_INSTANCE + 0x22, zone.DIPLOMACY_CATEGORY))
        self.assertEqual(zone.presence_values(types.SimpleNamespace())[0x25], zone.PRESENCE_START)


class ProvenanceTests(unittest.TestCase):
    def test_classify(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import provenance
        self.assertEqual(provenance.classify({"_source": "https://x", "_placeholder_steps": "delivery"}), "placeholder")
        self.assertEqual(provenance.classify({"_source": "https://x"}), "sourced")
        self.assertEqual(provenance.classify({"name": "Orin"}), "unmarked")
        rows = provenance.report()
        self.assertGreater(rows["quests.json"]["placeholder"], 0)
        self.assertGreater(rows["spawns/*.json"]["sourced"], 0)


class StartAreaTests(unittest.TestCase):
    """B-017: new characters start where the create request asks (start_areas.py)."""

    @staticmethod
    def raw(race, x, y):
        return bytes(7) + bytes([race, 0x1C]) + struct.pack("<ii", x, y) + bytes(64)

    def test_requested_chunk_and_racial_value(self):
        import start_areas as sa
        self.assertEqual(sa.start_chunk(self.raw(14, -26, 1)), sa.ISLE_OF_DAWN)
        self.assertEqual(sa.start_chunk(self.raw(14, -65535, -65535)), sa.TURSH)
        self.assertEqual(sa.start_chunk(self.raw(12, -65535, -65535)), sa.SHANG)
        self.assertEqual(sa.start_chunk(self.raw(13, -65535, -65535)), sa.KARIBASA)
        self.assertIsNone(sa.start_chunk(self.raw(14, 5, 5)))          # not a starting area
        self.assertIsNone(sa.start_chunk(bytes(10)))                 # too short

    def test_every_race_has_a_starting_area(self):
        import races_classes
        import start_areas as sa
        self.assertEqual(set(races_classes.RACES), set(sa.RACE_START))

    def test_anchor_prefers_the_named_npc_then_the_village(self):
        import start_areas as sa
        far = [({"x": 90000, "y": 90000}, {"name": "Lone Wolf"})]
        village = [({"x": 100 * i, "y": 0}, {"name": f"Villager {i}"}) for i in range(5)]
        rahlsu = [({"x": -7545, "y": -2270}, {"name": "Master Rahlsu"})]
        self.assertEqual(sa.anchor(far + village + rahlsu, sa.SHANG), (-7545, -2270))
        self.assertIn(sa.anchor(far + village, sa.TURSH), [(100 * i, 0) for i in range(5)])
        pack = [({"x": 50000 + i, "y": 0}, {"name": "Crawler", "damage": [1, 2]}) for i in range(9)]
        self.assertIn(sa.anchor(pack + village, sa.TURSH), [(100 * i, 0) for i in range(5)])  # not by the pack
        self.assertIsNone(sa.anchor(pack, sa.TURSH))
        self.assertIsNone(sa.anchor([], sa.TURSH))

    def test_new_character_placed_beside_the_anchor(self):
        import login_stub
        import start_areas as sa
        from unittest import mock
        content = mock.Mock()
        content.spawns.return_value = [({"x": 1000, "y": 2000}, {"name": "Master Rahlsu"})]
        content.ground_z.return_value = 500.0
        args = mock.Mock(content=content, client_dir=None)
        char = {"first": "Newbie"}
        with mock.patch.object(login_stub, "ARGS", args), \
                mock.patch.object(login_stub, "chunk_exists", lambda x, y: True):
            login_stub.place_new_character(char, self.raw(12, -65535, -65535))
        self.assertEqual(char["chunk"], list(sa.SHANG))
        self.assertEqual(char["position_chunk"], list(sa.SHANG))
        self.assertEqual(char["position"], [1000 + sa.BESIDE, 2000, 500.0 + login_stub.zone.SPAWN_Z_LIFT])
        other = {"first": "Default"}
        with mock.patch.object(login_stub, "ARGS", args):
            login_stub.place_new_character(other, self.raw(14, 5, 5))
        self.assertNotIn("chunk", other)                               # stays at the camp


class StartSpotTests(unittest.TestCase):
    """B-017: a map's PlayerStart is used only when it looks placed for players."""

    def test_player_start_rule(self):
        import start_areas as sa
        npcs = [({"x": 0, "y": 0}, {"name": "Elder"})]
        flat = lambda x, y: 100.0
        self.assertEqual(sa.usable_player_start([(500, 0, 290)], npcs, flat), (500, 0))      # 190 up, near
        self.assertIsNone(sa.usable_player_start([(500, 0, 24000)], npcs, flat))           # hangs in the air
        self.assertIsNone(sa.usable_player_start([(50000, 0, 290)], npcs, flat))           # far from everyone
        self.assertIsNone(sa.usable_player_start([None, (500, 0, 50)], npcs, flat))        # below the ground

    def test_start_position_order(self):
        import start_areas as sa
        from unittest import mock
        content = mock.Mock()
        content.ground_z.return_value = 100.0
        content.spawns.return_value = [({"x": 0, "y": 0}, {"name": "Elder"})]
        # a usable PlayerStart wins over the village cluster
        self.assertEqual(sa.start_position(content, sa.ISLE_OF_DAWN, "x", None, 90, starts=[(500, 0, 290)]),
                         [500, 0, 190.0])
        # no usable one: beside the cluster
        self.assertEqual(sa.start_position(content, sa.ISLE_OF_DAWN, "x", None, 90, starts=[]),
                         [sa.BESIDE, 0, 190.0])
        # the NPC the intro names wins over the PlayerStart
        content.spawns.return_value = [({"x": 7, "y": 7}, {"name": "Master Rahlsu"})]
        self.assertEqual(sa.start_position(content, sa.SHANG, "x", None, 90, starts=[(10, 7, 290)]),
                         [7 + sa.BESIDE, 7, 190.0])


class DisabledQuestTests(unittest.TestCase):
    """B-007: a quest marked "disabled" is not offered, but one already in a log still works."""

    def test_icon_and_offer(self):
        import types
        import quest
        quests = {"off": {"id": 1, "name": "Off", "giver": "orin", "turn_in": "smith", "level": 1,
                          "steps": [{"talk": "smith"}], "disabled": True}}
        log = types.SimpleNamespace(active={}, done=[])
        have = lambda name: 0
        self.assertIsNone(quest.npc_icon(quests, "orin", log, have, 1))          # no "!" over the giver
        self.assertFalse(quest.offerable(quests["off"]))
        log.active["off"] = quest.new_progress()                                 # taken before it was disabled
        self.assertEqual(quest.npc_icon(quests, "orin", log, have, 1), quest.ICON_IN_PROGRESS)

    def test_accept_refused(self):
        import login_stub
        import quest
        import zone
        from unittest import mock
        q = {"id": 4242, "name": "Off", "giver": "orin", "turn_in": "orin", "level": 1,
             "steps": [{"talk": "orin"}], "disabled": True}
        npc = mock.Mock(template_id="orin", entity_id=7)
        player = zone.Player(name="Ann", char_id=1, level="chunk_n19_12")
        sent = []
        state = {"player": player, "send": sent.append}
        args = mock.Mock()
        args.content.quests = {"off": q}
        with mock.patch.object(login_stub, "ARGS", args), \
                mock.patch.object(login_stub, "save_character_field", lambda *a: None):
            login_stub.dialog_quest(state, "off", 7)
        self.assertNotIn("off", player.quests.active)
        self.assertNotIn("off", state.get("shared_quests", set()))             # no offer page

    def test_content_split(self):
        import json
        q = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "content", "quests.json"),
                           encoding="utf-8"))
        placeholders = [v for v in q.values() if isinstance(v, dict) and v.get("_placeholder_steps")]
        kept = [v for v in placeholders if not v.get("disabled")]
        self.assertTrue(all(v.get("_delivery_evidence") for v in kept))       # only with evidence
        self.assertTrue(all(v.get("_disabled") for v in placeholders if v.get("disabled")))


class QuestCheckTests(unittest.TestCase):
    """tools/quest_check.py: every quest a player can be offered can be finished."""

    @staticmethod
    def tool():
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import quest_check
        return quest_check

    def test_finds_what_is_missing(self):
        import json
        import tempfile
        qc = self.tool()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "spawns"))
            mobs = {"giver": {"name": "Giver"}, "wolf": {"name": "Wolf", "loot": "wolf_drops"},
                    "ghost": {"name": "Ghost"}, "vein": {"name": "Vein", "harvest": {"item": "Ore"}}}
            files = {"mobs.json": mobs, "loot.json": {"wolf_drops": [{"name": "Pelt"}]}, "merchants.json": {},
                     "quests.json": {
                         "ok": {"name": "Ok", "giver": "giver",
                                "steps": [{"kill": {"wolf": 1}}, {"collect": {"Pelt": 1, "Ore": 1}}]},
                         "bad": {"name": "Bad", "giver": "giver",
                                 "steps": [{"kill": {"ghost": 1}}, {"collect": {"Gold Bar": 1}}]},
                         "off": {"name": "Off", "giver": "ghost", "disabled": True}}}
            for name, data in files.items():
                with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                    json.dump(data, f)
            with open(os.path.join(d, "spawns", "c.json"), "w", encoding="utf-8") as f:
                json.dump({"spawns": [{"mob": m} for m in ("giver", "wolf", "vein")]}, f)
            rows = {k: probs for k, _q, probs in qc.check(d)}
        self.assertEqual(rows["ok"], [])
        self.assertTrue(any("'Ghost' is not spawned" in p for p in rows["bad"]))
        self.assertTrue(any("'Gold Bar'" in p for p in rows["bad"]))
        self.assertNotIn("off", rows)                                    # disabled quests are skipped

    def test_real_content_is_finishable(self):
        bad = [(k, probs) for k, _q, probs in self.tool().check() if probs]
        self.assertEqual(bad, [])


@unittest.skipUnless(os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Assets", "Maps",
                                                 "chunk_n20_13.vgr")), "needs the client's maps")
class ChunkAuditTests(unittest.TestCase):
    """tools/chunk_audit.py: no archive spawn sits in a chunk whose terrain contradicts its
    recorded height while a neighbour's terrain matches it (Tracker Nok was out at sea)."""

    def test_no_spawn_in_the_wrong_chunk(self):
        import sys
        import content
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import chunk_audit
        rows = chunk_audit.candidates(content.Content())
        self.assertEqual([(r[2]["mob"], r[3], r[5]) for r in rows], [])


class MovedSpawnImportTests(unittest.TestCase):
    """B-020: the archive import must not put back a spawn tools/chunk_audit.py moved to another
    chunk (it did: a refresh re-added 27 moved NPCs to their mislabelled chunks)."""

    def test_moved_spawn_not_reimported(self):
        import json
        import sys
        import tempfile
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "spawns"))
            with open(os.path.join(d, "mobs.json"), "w", encoding="utf-8") as f:
                json.dump({"arch_nok": {"name": "Tracker Nok"}}, f)
            with open(os.path.join(d, "spawns", "chunk_b.json"), "w", encoding="utf-8") as f:
                json.dump({"spawns": [{"mob": "arch_nok", "x": 1, "y": 2,
                                       "_moved_from": "chunk_a: recorded z ..."}]}, f)
            added = import_zone.apply("chunk_a", {"arch_nok": {"name": "Tracker Nok"}},
                                      [{"mob": "arch_nok", "x": 1, "y": 2}], content=d)
            self.assertEqual(added, (0, 0))
            self.assertFalse(os.path.exists(os.path.join(d, "spawns", "chunk_a.json")))
            added = import_zone.apply("chunk_c", {"arch_new": {"name": "New"}},
                                      [{"mob": "arch_new", "x": 3, "y": 4}], content=d)
            self.assertEqual(added, (1, 1))                                  # others still import
            with open(os.path.join(d, "spawns", "chunk_d.json"), "w", encoding="utf-8") as f:
                json.dump({"spawns": [{"mob": "arch_naji", "x": 5, "y": 5}]}, f)
            added = import_zone.apply("chunk_d", {"arch_naji_sevenblade": {"name": "Naji Sevenblade"}},
                                      [{"mob": "arch_naji_sevenblade", "x": 5, "y": 5}], content=d)
            self.assertEqual(added[1], 0)                                    # same spot, another name: same person


class QuestGiverNameTests(unittest.TestCase):
    """Archive quest givers that are parsing leftovers ("Varies", "Then") are not placed as people."""

    def test_rules(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
        import import_zone
        page = {"giver": "Naji Sevenblade",
                "referenced_entities": [{"name": "Naji Sevenblade", "url": "https://vgsoharchive.com/mobs/naji-sevenblade"}]}
        word = {"giver": "Then", "referenced_entities": [{"name": "Khal", "url": "https://vgsoharchive.com/zones/khal"}]}
        self.assertTrue(import_zone.has_npc_page(page))
        self.assertFalse(import_zone.has_npc_page(word))
        quests = {"a": {"name": "A", "zone": "Khal", "giver": "Varies",
                        "archive_fields": {"location": ["1, 2, 3 in Khal (-13, -9)"]}}}
        self.assertEqual(import_zone.quest_giver_spots("Khal", quests, (-13, -9)), {})


class DeadPlayerTests(unittest.TestCase):
    """A dead character can't bind at an altar (or, live-checked, hail an NPC): notice 112."""

    def test_altar_refuses_the_dead(self):
        import struct
        import login_stub
        import zone
        from unittest import mock
        player = zone.Player(name="Ann", char_id=1, level="chunk_n13_n9")
        sent = []
        state = {"player": player, "send": sent.append}
        altar = mock.Mock(altar=True)
        with mock.patch.object(login_stub, "player_distance", lambda p, n: 0), \
                mock.patch.object(login_stub, "bind_here", lambda s, n: sent.append("bound")):
            player.health = 0
            login_stub.handle_altar_use(state, altar)
            self.assertNotIn("bound", sent)
            self.assertEqual(struct.unpack_from("<h", sent[0], 10)[0], login_stub.NOT_WHILE_DEAD)
            sent.clear()
            player.health = 50
            login_stub.handle_altar_use(state, altar)
            self.assertIn("bound", sent)

    def test_world_actions_refused_while_dead(self):
        import struct
        import login_stub
        import quest
        import zone
        from unittest import mock
        player = zone.Player(name="Ann", char_id=1, level="chunk_n13_n9")
        player.health = 0
        sent = []
        state = {"player": player, "send": sent.append}
        q = {"id": 4243, "name": "Q", "giver": "orin", "steps": [{"talk": "orin"}]}
        args = mock.Mock()
        args.content.quests = {"q": q}
        notice = lambda m: isinstance(m, bytes) and struct.unpack_from("<h", m, 10)[0] == login_stub.NOT_WHILE_DEAD
        with mock.patch.object(login_stub, "ARGS", args),                 mock.patch.object(login_stub, "save_character_field", lambda *a: None):
            login_stub.handle_quest_event(state, quest.ACCEPT, struct.pack("<HIIi", 2, quest.ACCEPT, 4, 4243))
            self.assertNotIn("q", player.quests.active)
            self.assertTrue(any(notice(m) for m in sent))
            self.assertEqual(login_stub.open_loot(state, mock.Mock()), [])          # no looting
            sent.clear()
            player.quests.active["q"] = quest.new_progress()
            login_stub.handle_quest_event(state, quest.ABANDON, struct.pack("<HIIi", 2, quest.ABANDON, 4, 4243))
            self.assertNotIn("q", player.quests.active)                           # abandoning still works


class InventoryResendTests(unittest.TestCase):
    """B-024: after a chunk hand-off the client still holds the items, and a 0x197 for an id it has
    does not refill the grid that 0x195 cleared (bags looked empty after every riftway). A resend
    removes each item (0x1a5) first."""

    def test_resend_removes_first(self):
        import struct
        import zone
        player = zone.Player(name="Ann", char_id=1, level="chunk_n19_12")
        player.items = [[10001, "Travel Rations", 442, 1, 3]]
        player.equipment = [[2001, "Rusty Sword", 422, 28]]
        ids = lambda msgs: [struct.unpack_from("<I", m, 2)[0] for m in msgs]
        first = zone.inventory_messages(player)
        self.assertNotIn(0x1A5, ids(first))
        self.assertEqual(ids(first)[0], 0x195)
        again = zone.inventory_messages(player, resend=True)
        self.assertEqual(ids(again)[:3], [0x1A5, 0x1A5, 0x195])           # each item and equipped piece, then reset
        removed = {struct.unpack_from("<i", m, 10)[0] for m in again if struct.unpack_from("<I", m, 2)[0] == 0x1A5}
        self.assertEqual(removed, {10001, 2001})

    def test_equipped_items_created_in_their_equip_slot(self):
        """B-025: equipped pieces are created with field 7 = their equip slot, not parked in a bag
        slot first (with full bags, six bag items vanished from view)."""
        import zone
        import vgmsg
        player = zone.Player(name="Ann", char_id=1, level="chunk_n19_12")
        player.items = []
        player.equipment = [[2001, "Rusty Sword", 422, 28]]
        msg = [m for m in zone.inventory_messages(player) if m[2:6] == (0x197).to_bytes(4, "little")][0]
        kw = zone.item_equip_fields("Rusty Sword", 100, False)
        want = zone.zone_event(0x197, vgmsg.inventory_item(2001, "Rusty Sword", 49, zone.item_icon("Rusty Sword", 422),
                                                           equip_slot=28, **kw))
        parked = zone.zone_event(0x197, vgmsg.inventory_item(2001, "Rusty Sword", 49, zone.item_icon("Rusty Sword", 422),
                                                             **kw))
        self.assertNotEqual(want, parked)
        self.assertEqual(msg, want)
