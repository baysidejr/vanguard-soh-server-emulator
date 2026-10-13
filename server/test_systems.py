"""Unit tests for the message builders and rules of the newer systems (no client needed)."""
import struct
import unittest

import assembly
import combat
import fishing
import grouploot
import housing
import mail
import market
import pets
import titles


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

    def test_record_has_expiry(self):
        rec = market.record({"id": 9, "name": "X", "seller": "Y", "price": 40, "posted": 1000})
        self.assertIn(struct.pack("<I", 1000 + market.DURATION), rec)


class HousingTests(unittest.TestCase):
    def test_upkeep_charges_each_week(self):
        st = {"bought": 0, "upkeep_balance": 120}
        self.assertEqual(housing.charge_upkeep({"upkeep": 50}, st, 3 * housing.UPKEEP_PERIOD + 5), 3)
        self.assertEqual(st["upkeep_balance"], -30)
        self.assertEqual(st["missed"], 1)

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

    def test_rarity_threshold(self):
        self.assertTrue(grouploot.qualifies(3, grouploot.DEFAULT_RARITY))      # Rare >= Uncommon
        self.assertFalse(grouploot.qualifies(grouploot.COMMON, grouploot.DEFAULT_RARITY))


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


if __name__ == "__main__":
    unittest.main()
