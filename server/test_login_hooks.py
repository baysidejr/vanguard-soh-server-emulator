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


class ParleyStrategyTests(unittest.TestCase):
    def run_event(self, event, data, in_parley):
        import struct
        import diplomacy
        sent = []
        player = mock.Mock(diplomacy_deck=[40001, 40002], diplomacy_slots=[None, None, None, None])
        state = {"player": player, "send": sent.append}
        if in_parley:
            state["parley"] = mock.Mock()
        args = mock.Mock()
        args.content.diplomacy = {"cards": {}, "slots": 4}
        with mock.patch.object(login_stub, "ARGS", args), \
                mock.patch.object(login_stub, "diplomacy_deck", lambda p: ([40001, 40002], [None] * 4)), \
                mock.patch.object(login_stub, "save_character_field", lambda *a: None):
            login_stub.handle_parley_event(state, event, data)
        codes = [struct.unpack_from("<i", m, 10)[0] for m in sent if struct.unpack_from("<I", m, 2)[0] == 0x330]
        return codes, sent

    def test_no_strategy_changes_in_a_parley(self):
        import struct
        import diplomacy
        for event, data in ((diplomacy.SLOT, struct.pack("<ii", 40001, 0)), (diplomacy.UNSLOT, struct.pack("<iB", 40001, 0)),
                            (diplomacy.DECK_LOAD, struct.pack("<i", 1)), (diplomacy.DECK_CLEAR, b"")):
            codes, _ = self.run_event(event, data, True)
            self.assertEqual(codes, [diplomacy.ERR_IN_PARLEY], hex(event))

    def test_invalid_slot(self):
        import struct
        import diplomacy
        codes, _ = self.run_event(diplomacy.SLOT, struct.pack("<ii", 40001, 9), False)
        self.assertEqual(codes, [diplomacy.ERR_INVALID_SLOT])
        codes, sent = self.run_event(diplomacy.SLOT, struct.pack("<ii", 40001, 1), False)
        self.assertEqual(codes, [])
        self.assertTrue(sent)


class FixturePlacementTests(unittest.TestCase):
    """The client's own placement: 0x461 -> 0x459 ghost preview -> 0x46d with the clicked pose."""
    def run_events(self, events, pos=(1000.0, 2000.0, 300.0)):
        import struct
        import housing
        sent, placed = [], []
        player = zone.Player(name="Owner", char_id=1, level="chunk_n19_12")
        player.items = [[7, "Oak Table", 1, 1, 1], [8, "Rations", 1, 1, 2]]
        player.live_position = pos
        state = {"player": player, "send": sent.append}
        args = mock.Mock()
        args.content.plots = {"101": {"chunk": "chunk_n19_12", "loc": [1000.0, 2000.0, 0.0],
                                      "buildings": [{"type": 5, "fixtures": 20}]}}
        args.content.item = lambda name: {"fixture": "Table01"} if name == "Oak Table" else {}
        db = {"101": {"owner": "Owner", "building": 5}}
        with mock.patch.object(login_stub, "ARGS", args), \
                mock.patch.object(login_stub, "load_housing", lambda: db), \
                mock.patch.object(login_stub, "save_housing", lambda d: None), \
                mock.patch.object(login_stub, "take_items", lambda *a: placed.append(a[1])), \
                mock.patch.object(login_stub, "broadcast_object", lambda s, o, close=False: None), \
                mock.patch.object(login_stub, "build_system_text", lambda text, channel=0: text):
            for event, data in events:
                login_stub.handle_housing_event(state, event, data)
        return sent, db["101"].get("fixtures", []), placed, struct, housing

    def spawn(self, handle, x, y, z, yaw):
        import struct
        return struct.pack("<iifffiii", handle, 0, x, y, z, yaw, 0, 0)

    def test_preview_then_place_at_clicked_pose(self):
        import struct
        import housing
        sent, fixtures, placed, _, _ = self.run_events([
            (housing.PLACE_REQUEST, struct.pack("<i", 7)),
            (housing.SPAWN_FIXTURE, self.spawn(7, 1100.0, 2050.0, 120.0, 0x4000))])
        self.assertEqual(sent[0], housing.placement_preview("Table01"))
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0]["loc"], [1100.0, 2050.0, 120.0])
        self.assertEqual(fixtures[0]["yaw"], 0x4000)
        self.assertEqual(placed, ["Oak Table"])

    def test_refusals(self):
        import struct
        import housing
        # not a fixture item: no preview
        sent, fixtures, _, _, _ = self.run_events([(housing.PLACE_REQUEST, struct.pack("<i", 8))])
        self.assertEqual((sent, fixtures), ([], []))
        # outside the house
        sent, fixtures, _, _, _ = self.run_events([(housing.PLACE_REQUEST, struct.pack("<i", 7))], pos=(9000.0, 0.0, 0.0))
        self.assertEqual(sent, ["You can only place items when in your house."])
        # a click with no preview pending, or outside the house
        _, fixtures, _, _, _ = self.run_events([(housing.SPAWN_FIXTURE, self.spawn(7, 1100.0, 2050.0, 120.0, 0))])
        self.assertEqual(fixtures, [])
        sent, fixtures, _, _, _ = self.run_events([
            (housing.PLACE_REQUEST, struct.pack("<i", 7)),
            (housing.SPAWN_FIXTURE, self.spawn(7, 5000.0, 2050.0, 120.0, 0))])
        self.assertEqual(fixtures, [])
        self.assertEqual(sent[-1], "You can only place items when in your house.")


class GuildBuildingTests(unittest.TestCase):
    """Guild usable (0x47a), guild headquarters (0x47b / 0x47c) and the building preview (0x474)."""
    def setUp(self):
        import housing
        self.db = {"101": {"owner": "Owner", "building": 1,
                           "permissions": [{"id": 3, "name": "Friends", "flags": 1, "friends": ["Bob"]}]}}
        self.guilds = {"5": {"id": 5, "name": "Night Watch", "members": {"Owner": 1, "Boss": 10}},
                       "6": {"id": 6, "name": "Others", "members": {"Stranger": 10}}}
        self.args = mock.Mock()
        self.args.content.plots = {"101": {"name": "Plot", "chunk": "c1", "loc": [0.0, 0.0, 0.0], "cost": 1, "upkeep": 0,
                                           "buildings": [{"type": 1, "name": "Cottage", "fixtures": 5, "chests": 1},
                                                         {"type": 2, "name": "Home",
                                                          "materials": {"Rough Stone": 2}}]}}
        self.online = {}
        self.sent = {}
        self.patches = [mock.patch.object(login_stub, "ARGS", self.args),
                        mock.patch.object(login_stub, "ONLINE", self.online),
                        mock.patch.object(login_stub, "load_housing", lambda: self.db),
                        mock.patch.object(login_stub, "save_housing", lambda d: None),
                        mock.patch.object(login_stub, "load_guilds", lambda: self.guilds),
                        mock.patch.object(login_stub, "build_system_text", lambda text, channel=0: text),
                        mock.patch.object(login_stub.zone, "template_id", lambda name: 77)]
        for p in self.patches:
            p.start()
        self.housing = housing

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def login(self, name, pos=(100.0, 0.0, 0.0), chunk="c1"):
        player = zone.Player(name=name, char_id=len(self.online) + 1, level=chunk)
        player.live_position = pos
        self.sent[name] = []
        s = {"player": player, "send": self.sent[name].append}
        self.online[name.lower()] = s
        return s

    def event(self, s, event, data):
        login_stub.handle_housing_event(s, event, data)

    def notices(self, name):
        import struct
        return [struct.unpack_from("<h", m, 10)[0] for m in self.sent[name]
                if not isinstance(m, str) and struct.unpack_from("<I", m, 2)[0] == 0x0E]

    def test_guild_usable_toggle(self):
        import struct
        owner = self.login("Owner")
        self.event(owner, self.housing.GUILD_USABLE, struct.pack("<i", 101))
        self.assertTrue(self.db["101"]["guild_usable"])
        self.assertIn(self.housing.guild_usable(True), self.sent["Owner"])
        self.assertEqual(self.notices("Owner"), [self.housing.NOW_GUILD_USABLE])
        self.event(owner, self.housing.GUILD_USABLE, struct.pack("<i", 101))
        self.assertFalse(self.db["101"]["guild_usable"])
        # not the owner: nothing
        other = self.login("Boss")
        self.event(other, self.housing.GUILD_USABLE, struct.pack("<i", 101))
        self.assertFalse(self.db["101"]["guild_usable"])

    def test_hq_confirmed_by_leader_then_cleared(self):
        import struct
        owner, boss = self.login("Owner"), self.login("Boss")
        self.event(owner, self.housing.GUILD_HQ, struct.pack("<i", 101))
        self.assertIn(self.housing.hq_leader_confirm(101, 5, "Owner"), self.sent["Boss"])
        self.assertNotIn("hq_guild", self.db["101"])
        accept = struct.pack("<ii", 101, 5) + b"\0\0" + b"\1"
        self.event(boss, self.housing.HQ_LEADER_RESPONSE, accept)
        self.assertEqual(self.db["101"]["hq_guild"], 5)
        self.assertEqual(self.db["101"]["permissions"], [self.housing.hq_guild_permission()])
        self.assertIn(self.housing.HQ_ADDED, self.notices("Owner"))
        self.assertIn(self.housing.HQ_ADDED, self.notices("Boss"))
        self.assertTrue(self.housing.allowed(self.db["101"], "Boss", self.housing.PAY_UPKEEP, login_stub.guild_of))
        # the same answer again does nothing (offer used up)
        self.event(boss, self.housing.HQ_LEADER_RESPONSE, accept)
        # the owner can't clear it, the leader can
        self.event(owner, self.housing.GUILD_HQ, struct.pack("<i", 101))
        self.assertEqual(self.db["101"]["hq_guild"], 5)
        self.event(boss, self.housing.GUILD_HQ, struct.pack("<i", 101))
        self.assertNotIn("hq_guild", self.db["101"])
        self.assertEqual(self.db["101"]["permissions"], [])
        self.assertIn(self.housing.HQ_REMOVED, self.notices("Owner"))

    def test_hq_refusals(self):
        import struct
        owner = self.login("Owner")
        # leader offline / away from the plot
        self.event(owner, self.housing.GUILD_HQ, struct.pack("<i", 101))
        self.assertEqual(self.sent["Owner"][-1], "The Guild Leader must be present at the plot to confirm the action.")
        boss = self.login("Boss", pos=(9000.0, 0.0, 0.0))
        self.event(owner, self.housing.GUILD_HQ, struct.pack("<i", 101))
        self.assertEqual(self.sent["Boss"], [])
        # declined
        boss["player"].live_position = (50.0, 0.0, 0.0)
        self.event(owner, self.housing.GUILD_HQ, struct.pack("<i", 101))
        self.event(boss, self.housing.HQ_LEADER_RESPONSE, struct.pack("<ii", 101, 5) + b"\0\0\0")
        self.assertNotIn("hq_guild", self.db["101"])
        self.assertIn("Boss declined", self.sent["Owner"][-1])
        # an answer nobody asked for
        stranger = self.login("Stranger")
        self.event(stranger, self.housing.HQ_LEADER_RESPONSE, struct.pack("<ii", 101, 6) + b"\0\0\1")
        self.assertNotIn("hq_guild", self.db["101"])
        # not in a guild
        del self.guilds["5"]["members"]["Owner"]
        self.event(owner, self.housing.GUILD_HQ, struct.pack("<i", 101))
        self.assertEqual(self.notices("Owner")[-1], self.housing.NO_GUILD)

    def test_fixture_list(self):
        import struct
        msgs = self.housing.fixture_list([{"id": 2, "item": "Storage Chest", "items": []}, {"id": 3, "item": "Oak Table"}])
        ids = [struct.unpack_from("<I", m, 2)[0] for m in msgs]
        self.assertEqual(ids, [0x45A, 0x45C, 0x45C, 0x45B])
        self.assertEqual(struct.unpack_from("<iBB", msgs[1], 10), (self.housing.FIXTURE_ID_BASE + 2, 1, 0))
        self.assertEqual(msgs[2][16:].decode("utf-16-le"), "Oak Table\0")
        # the owner sees it in the plot window
        owner = self.login("Owner")
        self.db["101"]["fixtures"] = [{"id": 3, "item": "Oak Table"}]
        login_stub.send_plot_window(owner, "101")
        self.assertIn(self.housing.fixture_list([{"id": 3, "item": "Oak Table"}])[1], self.sent["Owner"])
        stranger = self.login("Stranger")
        login_stub.send_plot_window(stranger, "101")
        self.assertNotIn(self.housing.fixture_list([{"id": 3, "item": "Oak Table"}])[1], self.sent["Stranger"])

    def test_building_preview(self):
        import struct
        owner = self.login("Owner")
        owner["plot_window"] = "101"
        self.event(owner, self.housing.BUILDING_DETAILS, struct.pack("<i", 2))
        self.assertEqual(self.sent["Owner"], [self.housing.construction_info(
            101, "Home", [(77, "Rough Stone", 0, 2)], self.housing.BUILDING_DETAILS)])


class CityStatusTests(unittest.TestCase):
    def run_status(self, parleys, saved):
        import json
        import struct
        args = mock.Mock()
        args.content.diplomacy = {"parleys": parleys}
        sent = []
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "civic.json")
            if saved is not None:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(saved, f)
            with mock.patch.object(login_stub, "ARGS", args), mock.patch.object(login_stub, "CIVIC_FILE", path):
                login_stub.city_status({"send": sent.append})
        return sent, struct

    def test_no_stats_is_the_clients_popup(self):
        sent, struct = self.run_status({"p": {"reward": {"xp": 1}}}, None)
        self.assertEqual(len(sent), 1)
        self.assertEqual(struct.unpack_from("<HIIii", sent[0]), (2, 0x330, 8, 16, 0))

    def test_stats_from_content_and_save(self):
        parleys = {"a": {"reward": {"civic": {"stat": "Camp Prosperity", "delta": 5, "start": 50}}},
                   "b": {"reward": {"civic": {"stat": "Camp Safety", "delta": 1}}}}
        with mock.patch.object(login_stub, "build_system_text", lambda text, channel=0: text):
            sent, _ = self.run_status(parleys, {"Camp Prosperity": 65})
        self.assertEqual(sent, ["Camp Prosperity: 65", "Camp Safety: 50"])


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
        "app_gear_visible": True,
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
        "race": "race", "durability": "durability", "pawn_prefs": "pawn_prefs", "app_gear_visible": "app_gear_visible",
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
