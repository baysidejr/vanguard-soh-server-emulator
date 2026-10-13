"""Smoke test: every per-login hook runs for a fresh character before its pawn exists
(no position, no Unreal channel), against temporary data files."""
import os
import tempfile
import unittest
from unittest import mock

import content
import login_stub
import zone


class LoginHookTests(unittest.TestCase):
    def test_login_hooks_with_no_pawn_yet(self):
        sent = []
        player = zone.Player(name="Tester", char_id=0x1234, level="chunk_n19_12")
        state = {"player": player, "send": sent.append, "session": "s1"}
        args = mock.Mock()
        args.content = content.Content()
        args.client_dir = None
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(login_stub, "ARGS", args, create=True), \
                mock.patch.object(login_stub, "save_character_field"), \
                mock.patch.object(login_stub, "world_send"), \
                mock.patch.object(login_stub, "load_characters", return_value=[]):
            for attr, name in (("GUILDS_FILE", "g.json"), ("BROTHERHOODS_FILE", "b.json"),
                               ("MAIL_FILE", "m.json"), ("CARAVANS_FILE", "c.json"),
                               ("HOUSING_FILE", "h.json"), ("MARKET_FILE", "k.json")):
                if hasattr(login_stub, attr):
                    mock.patch.object(login_stub, attr, os.path.join(d, name)).start()
            login_stub.save_caravans([{"leader": "Tester", "members": ["Tester", "Other"]}])
            try:
                for hook in ("social_login", "guild_login", "brotherhood_login", "faction_login",
                             "workorder_login", "mail_login", "title_login", "caravan_login"):
                    getattr(login_stub, hook)(state)
            finally:
                mock.patch.stopall()
        self.assertTrue(sent)


class FallTests(unittest.TestCase):
    def run_fall(self, zs, x=0.0):
        fs, out = {}, []
        for z in zs:
            out.append(login_stub.fall_drop(fs, (x, 0.0, z)))
        return [d for d in out if d is not None]

    def test_spawn_drop_is_not_a_fall(self):
        self.assertEqual(self.run_fall([2000, 1800, 1400, 900, 400, 400]), [])

    def test_fall_after_standing_counts(self):
        self.assertEqual(self.run_fall([1000, 1000, 900, 600, 300, 300]), [700])

    def test_teleport_disarms(self):
        self.assertEqual(self.run_fall([100, 100, 3000, 2800, 2000, 1500, 1500]), [])


class MovementCheckTests(unittest.TestCase):
    def run_moves(self, moves, teleport_at=None):
        ms = {} if teleport_at is None else {"teleport_at": teleport_at}
        return [w for t, x in moves for w in [login_stub.movement_warning(ms, (x, 0.0, 0.0), t)] if w]

    def test_walking_is_fine(self):
        self.assertEqual(self.run_moves([(t * 0.5, t * 0.5 * 340) for t in range(12)]), [])

    def test_too_fast(self):
        out = self.run_moves([(t * 0.5, t * 0.5 * 1500) for t in range(12)])
        self.assertTrue(out and "units/s" in out[0])

    def test_jump_without_teleport(self):
        self.assertIn("jumped", self.run_moves([(0, 0), (0.5, 100), (1.0, 9000)])[0])

    def test_server_teleport_is_excused(self):
        self.assertEqual(self.run_moves([(10, 0), (10.5, 100), (11.0, 9000)], teleport_at=9.0), [])


if __name__ == "__main__":
    unittest.main()
