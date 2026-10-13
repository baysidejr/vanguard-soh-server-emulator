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


if __name__ == "__main__":
    unittest.main()
