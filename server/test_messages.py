"""Regression tests for message builders whose layouts were verified against the
live client. Run: python -m unittest test_messages (from server/)."""
import random
import struct
import unittest

import combat
import ue2net
import vgmsg
import zone


def header(msg):
    """(event id, payload) of a zone event message (u16 2, u32 id, u32 len)."""
    kind, event, length = struct.unpack_from("<HII", msg)
    assert kind == 2 and length == len(msg) - 10, (kind, length, len(msg))
    return event, msg[10:]


class Player:
    def __init__(self):
        self.char_id = 0x1336F1A
        self.health = 210
        self.endurance = 100
        self.stats = {"hit_points": 210, "endurance": 100}
        self.npcs = {}
        self.target = None
        self.pending_displays = []
        self.pending_rewards = []
        self.auto_attack = False
        self.last_combat = 0.0
        self.items = []
        self.equipment = []


class CombatMessages(unittest.TestCase):
    def test_target_health(self):
        npc = combat.Npc(0x2000003, "Guide West", 6, "x.SGONPCPawn")
        npc.health = 50
        event, data = header(combat.target_health(npc))
        self.assertEqual(event, 0x3E1)
        self.assertEqual(struct.unpack("<QB", data), (0x2000003, 128))

    def test_targets(self):
        npc = combat.Npc(7, "a", 3, "x.y")
        event, data = header(combat.targets(npc))
        self.assertEqual(event, 0x3E0)
        self.assertEqual(len(data), 27)
        self.assertEqual(struct.unpack_from("<QB", data), (7, 255))

    def test_display_ability_is_57_bytes(self):
        event, data = header(combat.display_ability(1, combat.NO_ENTITY, 570001))
        self.assertEqual(event, 0x3D1)
        self.assertEqual(len(data), 57)
        self.assertEqual(struct.unpack_from("<QQi", data), (1, combat.NO_ENTITY, 570001))

    def test_experience_reward(self):
        event, data = header(combat.experience_reward(150, 9))
        self.assertEqual(event, 0x3D5)
        self.assertEqual(struct.unpack("<iiBBBQBB", data), (150, 0, 0, 0, 0, 9, 0, 0))

    def test_kill_and_loot(self):
        player = Player()
        npc = combat.Npc(5, "Rat", 3, "x.y", max_health=1)
        player.npcs[5], player.target = npc, 5
        lines, hit = combat.use_ability(player, (1, 570001, "Strike", 553, "", 0.0),
                                        rng=random.Random(1))
        self.assertIs(hit, npc)
        self.assertFalse(npc.alive)
        self.assertEqual(player.pending_rewards, [combat.KILL_XP])
        events = [header(m)[0] for m in combat.loot_messages(npc)]
        self.assertEqual(events, [0x1ED, 0x1E8] + [0x1F2] * len(combat.LOOT_TABLE) + [0x1EF])
        out = combat.take_loot(player, npc, -1)
        self.assertEqual(len(player.items), len(combat.LOOT_TABLE))
        self.assertEqual(len({i[0] for i in player.items}), len(player.items))   # unique ids
        self.assertEqual(header(out[-1])[0], 0x1ED)

    def test_chase_step_moves_toward_target(self):
        npc = combat.Npc(5, "Rat", 3, "x.y", location=(0.0, 0.0, 0.0))
        npc.aggro = True
        values = combat.chase_step(npc, (1000.0, 0.0, 0.0), 0.25)
        self.assertAlmostEqual(npc.location[0], combat.NPC_SPEED * 0.25)
        self.assertEqual(values["Rotation"], (0, 0, 0))


class ZoneMessages(unittest.TestCase):
    def test_teleport(self):
        event, data = header(zone.player_teleport((1.0, 2.0, 3.0)))
        self.assertEqual(event, 0x3E5)
        self.assertEqual(struct.unpack("<fffiiii", data), (1.0, 2.0, 3.0, 0, 0, 0, 0))

    def test_hotkey_record(self):
        rec = vgmsg.hotkey(3, 610004)
        self.assertTrue(rec.startswith("m_wb\0".encode("utf-16-le")))
        self.assertEqual(struct.unpack_from("<iii", rec, 10), (3, 610004, -1))


class BitWriterTests(unittest.TestCase):
    def test_rotator_compression(self):
        w = ue2net.BitWriter()
        w.rotator((0, 32768, 0))
        data, nbits = w.packed()
        self.assertEqual(nbits, 1 + 1 + 8 + 1)     # flag, flag + byte, flag


class NetFieldTests(unittest.TestCase):
    def test_integer_location_is_a_vector(self):
        # Regression: an all-int Location was once written as a Rotator.
        import netcache
        import rpc
        f = netcache.NetField("Location", "StructProperty")
        w = ue2net.BitWriter()
        f.writer((-31000, -5500, 442))(w)
        data, nbits = w.packed()
        self.assertEqual(rpc.read_vector(rpc.BitReader(data, nbits)), (-31000, -5500, 442))

    def test_rotation_is_a_rotator(self):
        import netcache
        f = netcache.NetField("Rotation", "StructProperty")
        w = ue2net.BitWriter()
        f.writer((0, 32768, 0))(w)
        self.assertEqual(w.packed()[1], 11)


if __name__ == "__main__":
    unittest.main()
