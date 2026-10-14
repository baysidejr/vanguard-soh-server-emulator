"""Unit tests for the message builders and rules of the newer systems (no client needed)."""
import struct
import unittest

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
import types
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


class CrowdConvertTests(unittest.TestCase):
    def test_convert(self):
        import json, os, sys, tempfile
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "crowdsourced"))
        import convert
        src = [{"url": "https://example.org/1"}]
        recs = [{"type": "creature", "name": "Ashen Wolf", "level": 8, "creature_kind": "wolf", "aggressive": "yes",
                 "sources": src, "confidence": "medium"},
                {"type": "creature", "name": "Odd", "creature_kind": "zzz", "sources": src, "confidence": "high"},
                {"type": "creature", "name": "Unsure", "creature_kind": "bear", "sources": src, "confidence": "low"},
                {"type": "quest", "name": "Pelts", "giver": "Orin the Trader", "sources": src, "confidence": "high",
                 "steps": [{"kind": "kill", "target": "Ashen Wolf", "count": 2, "objective": "Hunt"}]}]
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "all.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(r) for r in recs))
            b = convert.Batch(d)
            out = convert.convert(b, convert.creature_races())
        wolf = out["mobs.json"]["wastes_wolf"]                       # existing key for "Ashen Wolf"
        self.assertEqual((wolf["race"], wolf["level"]), (119, 8))
        self.assertEqual(out["quests.json"]["pelts"]["giver"], "camp_merchant")
        self.assertEqual(out["quests.json"]["pelts"]["steps"][0]["kill"], {"wastes_wolf": 2})
        self.assertTrue(any("Odd" in i for i in b.issues))
        self.assertTrue(any("low confidence" in i for i in b.issues))


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
        self.assertEqual(combat.pay_cost(caster, 5.0), "You do not have enough energy.")
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
        import threading
        import login_stub
        import housing
        p = zone.Player("Nobody", 1, 0x0E, 28, "chunk_n20_12")
        state = {"player": p, "send": lambda m: None}
        done = []

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


if __name__ == "__main__":
    unittest.main()
