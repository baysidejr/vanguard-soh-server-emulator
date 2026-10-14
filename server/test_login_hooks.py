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
                             "workorder_login", "mail_login", "title_login", "caravan_login",
                             "assembly_login", "journal_login", "songs_login", "fishing_login", "forms_login"):
                    getattr(login_stub, hook)(state)
            finally:
                mock.patch.stopall()
        self.assertTrue(sent)


class LoginHookListTests(unittest.TestCase):
    def test_every_zone_login_hook_is_covered(self):
        """The zone login calls <name>_login(state) hooks; the smoke test above must run each."""
        import inspect
        import re
        src = inspect.getsource(login_stub)
        called = set(re.findall(r"^\s+(\w+_login)\(state\)$", src, re.M))
        tested = set(re.findall(r'"(\w+_login)"', inspect.getsource(LoginHookTests)))
        self.assertTrue(called)
        self.assertEqual(called - tested, set())


class CharacterRoundTripTests(unittest.TestCase):
    CHAR = {
        "first": "Tester", "last": "Two", "world": "Stub World", "raw": "00000000e305010313",
        "adventure_level": 12, "adventure_xp": 345, "coins": 777, "bank_coins": 55,
        "items": [[10, "Copper Ore", 487, 3, 0]], "bank": [[11, "Copper Ingot", 1, 2, 0]],
        "equipment": [[12, "Copper Ring", 1225, 15]], "durability": {"12": 80},
        "skills": {"88": 40}, "learned_abilities": [123], "hotbar": {"1": [1, 2]},
        "friends": ["Ann"], "ignores": ["Bob"], "parleys_won": ["guard"], "factions": {"1004": 250},
        "work_order": {"id": 1}, "xp_debt": 90, "tombstone": {"level": "chunk_n19_12", "loc": [1, 2, 3]},
        "bind": {"level": "chunk_n19_12", "loc": [4, 5, 6]}, "dialog_rewards": ["r1"], "played": 3600,
        "titles": [2], "songs": [{"name": "s"}], "fish_records": {"Mud Eel": 3.5}, "discovered": ["Mailbox"],
        "flags": ["orin_trust"], "assembly_known": ["buckle"], "title_prefix": 1, "title_suffix": 2,
        "show_title": False, "known_recipes": ["copper_ingot"], "diplomacy_deck": [1, 2, 3],
        "diplomacy_slots": [1, None], "spheres": {"crafting": [3, 40]}, "active_toolbelt": 68,
        "bound": [12], "deck_presets": {"1": [1, 2]}, "apply_form_on_death": True, "access_level": 5,
        "gender": 1, "race": 14, "quests": {}, "pawn_prefs": {"m_bHideHood": 1, "m_WearPreference": 2},
    }
    LOADED = {   # characters.json field -> Player attribute, compared after normalising
        "adventure_level": "level_number", "adventure_xp": "xp", "coins": "coins", "bank_coins": "bank_coins",
        "learned_abilities": "learned", "hotbar": "hotbar", "friends": "friends", "ignores": "ignores",
        "parleys_won": "parleys_won", "factions": "factions", "work_order": "work_order", "xp_debt": "xp_debt",
        "tombstone": "tombstone", "bind": "bind", "dialog_rewards": "dialog_rewards", "played": "played",
        "titles": "titles", "songs": "songs", "fish_records": "fish_records", "discovered": "discovered",
        "flags": "flags", "assembly_known": "assembly_known", "title_prefix": "title_prefix",
        "title_suffix": "title_suffix", "show_title": "show_title", "known_recipes": "known_recipes",
        "diplomacy_deck": "diplomacy_deck", "diplomacy_slots": "diplomacy_slots", "spheres": "spheres",
        "active_toolbelt": "active_toolbelt", "deck_presets": "deck_presets",
        "apply_form_on_death": "apply_form_on_death", "access_level": "access_level", "gender": "gender",
        "race": "race", "durability": "durability", "pawn_prefs": "pawn_prefs",
    }

    def test_every_saved_value_comes_back(self):
        args = mock.Mock()
        args.content = content.Content()
        args.client_dir = ".."
        args.zone_level = None
        p = login_stub.player_from_character(dict(self.CHAR), "Tester", args)
        for field, attr in self.LOADED.items():
            got = getattr(p, attr)
            want = self.CHAR[field]
            if isinstance(got, set):
                got = sorted(got)
            self.assertEqual(got, want, field)
        self.assertEqual([list(i) for i in p.items], self.CHAR["items"])
        self.assertEqual([list(i) for i in p.bank], self.CHAR["bank"])
        self.assertEqual([list(e) for e in p.equipment], self.CHAR["equipment"])
        self.assertEqual(dict((sid, v) for sid, v, _ in p.skills).get(88), 40)
        self.assertEqual(sorted(p.bound), [12])

    def test_pawn_prefs_replicate(self):
        """Saved appearance settings go on the pawn; each is a real SGOPCPawn property."""
        import types
        args = mock.Mock()
        args.content = content.Content()
        args.client_dir = ".."
        args.zone_level = None
        p = login_stub.player_from_character(dict(self.CHAR, pawn_prefs={
            "m_bHideHood": 1, "m_bHideHelm": 1, "m_bHideCloak": 1, "m_WearPreference": 3,
            "m_WieldPreference": 2, "bogus": 1}), "Tester", args)
        self.assertNotIn("bogus", p.pawn_prefs)
        p.movement_mode = 1
        values = zone.player_pawn_values(p, (0.0, 0.0, 0.0))
        self.assertEqual(values["m_WearPreference"], 3)
        self.assertTrue(values["bIsWalking"])
        pm = zone.package_map(types.SimpleNamespace(client_dir="..", package_maps={}), "chunk_n19_12")
        names = {f.name for f in pm.net_cache.class_cache("SGOPCPawn")["all"]}
        for prop, _, _ in login_stub.PAWN_PREFS.values():
            self.assertIn(prop, names)
        self.assertIn("bIsWalking", names)

    def test_every_saved_field_is_read(self):
        """Each field the server saves (save_character_field / progress) is read back somewhere."""
        import inspect
        import re
        src = inspect.getsource(login_stub)
        saved = set(re.findall(r'save_character_field\([^,]+, "(\w+)"', src))
        read = set(re.findall(r'char(?:acter)?\.get\("(\w+)"', src)) | set(re.findall(r'char\["(\w+)"\]', src))
        self.assertTrue(saved)
        self.assertEqual(saved - read, set())


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


class BreathTests(unittest.TestCase):
    def test_runs_out_then_drowns(self):
        b, drowning = zone.BREATH_MAX, False
        for _ in range(zone.BREATH_MAX):
            b, drowning = login_stub.breath_step(b, True)
        self.assertEqual((b, drowning), (0, False))
        self.assertEqual(login_stub.breath_step(b, True), (0, True))

    def test_refills_above_water(self):
        self.assertEqual(login_stub.breath_step(55, False), (zone.BREATH_MAX, False))


if __name__ == "__main__":
    unittest.main()
