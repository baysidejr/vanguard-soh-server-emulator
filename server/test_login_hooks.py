"""Smoke test: every per-login hook runs for a fresh character before its pawn exists
(no position, no Unreal channel), against temporary data files."""
import os
import struct
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
                             "assembly_login", "journal_login", "songs_login", "fishing_login", "forms_login",
                             "house_npcs_login", "combat_sheet_login", "wounds_login"):
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

    def test_send_to_owner(self):
        import struct
        self.db["101"]["fixtures"] = [{"id": 3, "item": "Oak Table"}]
        oid = struct.pack("<i", self.housing.FIXTURE_ID_BASE + 3)
        with mock.patch.object(login_stub, "load_housing", lambda: self.db):
            owner, stranger = self.login("Owner"), self.login("Stranger")
            self.event(owner, self.housing.SEND_TO_OWNER, oid)
            self.event(stranger, self.housing.SEND_TO_OWNER, oid)
        self.assertEqual(self.notices("Owner"), [self.housing.CANT_SEND_NOT_TROPHY])
        self.assertEqual(self.notices("Stranger"), [self.housing.NO_PERMISSION_TO_SEND])

    def test_building_preview(self):
        import struct
        owner = self.login("Owner")
        owner["plot_window"] = "101"
        self.event(owner, self.housing.BUILDING_DETAILS, struct.pack("<i", 2))
        self.assertEqual(self.sent["Owner"], [self.housing.construction_info(
            101, "Home", [(77, "Rough Stone", 0, 2)], self.housing.BUILDING_DETAILS)])


class JournalRemoveTests(unittest.TestCase):
    def test_removed_location_stays_gone(self):
        import travel
        sent, saved = [], {}
        player = zone.Player(name="Tester", char_id=1, level="chunk_n19_12")
        player.discovered = ["chunk_n19_12:7", "chunk_n19_12:8"]
        state = {"player": player, "send": sent.append, "journal_sites": ("chunk_n19_12", [], {7, 8})}
        with mock.patch.object(login_stub, "save_character_field", lambda n, k, v: saved.__setitem__(k, v)):
            login_stub.journal_remove(state, 7)
            login_stub.journal_remove(state, travel.HOUSE_ENTRY_ID)
        self.assertEqual(sent, [travel.remove(7), travel.remove(travel.HOUSE_ENTRY_ID)])
        self.assertEqual(saved["journal_removed"], ["chunk_n19_12:7", f"*:{travel.HOUSE_ENTRY_ID}"])
        self.assertEqual(login_stub.journal_removed(player), {7, travel.HOUSE_ENTRY_ID})
        player.level = "chunk_n18_12"
        self.assertEqual(login_stub.journal_removed(player), {travel.HOUSE_ENTRY_ID})


class CallPcTests(unittest.TestCase):
    def test_offer_accept_decline(self):
        import struct
        caller_sent, target_sent, placed = [], [], []
        caller = {"player": zone.Player(name="Caller", char_id=11, level="c1"), "send": caller_sent.append,
                  "position": (10.0, 20.0, 30.0)}
        target = {"player": zone.Player(name="Target", char_id=12, level="c1"), "send": target_sent.append}
        online = {"caller": caller, "target": target}
        with mock.patch.object(login_stub, "ONLINE", online), \
                mock.patch.object(login_stub, "place_player", lambda s, a, loc, chunk: placed.append((s, loc))):
            login_stub.call_offer(caller, target)
            self.assertEqual(target_sent[-1], zone.zone_event(0x270, "Caller\0".encode("utf-16-le")))
            login_stub.call_answer(target, None, b"\0")             # decline
            self.assertEqual(placed, [])
            login_stub.call_answer(target, None, b"\1")             # nothing pending any more
            self.assertEqual(placed, [])
            login_stub.call_offer(caller, target)
            login_stub.call_answer(target, None, b"\1")
        self.assertEqual(placed, [(target, (110.0, 20.0, 80.0))])
        self.assertEqual(struct.unpack_from("<h", target_sent[-1], 10)[0], login_stub.YOU_HAVE_BEEN_SUMMONED)


class HouseNpcTests(unittest.TestCase):
    """Manage NPCs: lists (0x5cc / 0x5cd), place (0x5ce), remove (0x5cf), and reload at login."""
    def test_place_remove_reload(self):
        import struct
        import housing
        import world
        args = mock.Mock()
        args.content = content.Content()
        args.client_dir = None
        pid = "101"
        plot = args.content.plots[pid]
        db = {pid: {"owner": "Owner", "building": plot["buildings"][0]["type"]}}
        sent = []
        player = zone.Player(name="Owner", char_id=1, level=plot["chunk"])
        player.live_position = tuple(plot["loc"])
        w = world.World(plot["chunk"])
        state = {"player": player, "send": sent.append, "plot_window": pid, "world": w}
        w.members[1] = state
        with mock.patch.object(login_stub, "ARGS", args), \
                mock.patch.object(login_stub, "load_housing", lambda: db), \
                mock.patch.object(login_stub, "save_housing", lambda d: None), \
                mock.patch.object(login_stub.zone, "open_npc", lambda s, a, npc: ("open", npc.entity_id)), \
                mock.patch.object(login_stub.zone, "close_actor", lambda s, eid: ("close", eid)), \
                mock.patch.object(login_stub, "build_system_text", lambda text, channel=0: text):
            login_stub.handle_housing_event(state, 0x5D1, b"")
            avail = [m for m in sent if isinstance(m, bytes) and struct.unpack_from("<I", m, 2)[0] == 0x5CC]
            self.assertEqual(len(avail), 3)                     # clear, the banker, end of batch
            self.assertEqual(struct.unpack_from("<i", avail[1], 10)[0], 1)
            x, y, z = plot["loc"]
            sent.clear()
            login_stub.handle_housing_event(state, housing.SPAWN_NPC, struct.pack("<iffff", 1, 16384.0, x + 50, y, z))
            self.assertEqual(db[pid]["npcs"], [{"id": 1, "mob": "camp_banker", "loc": [x + 50, y, z], "yaw": 16384}])
            eid = housing.NPC_EID_BASE + 101 * 64 + 1
            self.assertIn(eid, w.npcs)
            self.assertTrue(w.npcs[eid].banker)
            self.assertIn(("open", eid), sent)
            # a fresh world loads it at login
            w2 = world.World(plot["chunk"])
            login_stub.house_npcs_login({"player": player, "send": sent.append, "world": w2})
            self.assertIn(eid, w2.npcs)
            sent.clear()
            login_stub.handle_housing_event(state, housing.REMOVE_NPC, struct.pack("<i", 1))
            self.assertEqual(db[pid]["npcs"], [])
            self.assertNotIn(eid, w.npcs)
            self.assertIn(("close", eid), sent)
            # someone else's window: nothing
            db[pid]["owner"] = "Other"
            sent.clear()
            login_stub.handle_housing_event(state, 0x5D1, b"")
            self.assertEqual(sent, [])


class FactionInfoRequestTests(unittest.TestCase):
    def test_known_and_unknown_ids(self):
        import faction
        sent = []
        args = mock.Mock()
        args.content.factions = {"2001": {"name": "Camp Guards"}}
        player = zone.Player(name="T", char_id=1, level="c1")
        with mock.patch.object(login_stub, "ARGS", args):
            login_stub.faction_info_request({"player": player, "send": sent.append}, 2001)
            login_stub.faction_info_request({"player": player, "send": sent.append}, 9999)
            expected = [faction.info(2001, "Camp Guards", login_stub.faction_value(player, "2001")), faction.publish()]
        self.assertEqual(sent, expected)


class EffectQueryTests(unittest.TestCase):
    def test_gone_running_and_untimed(self):
        import effects
        sent = []
        player = zone.Player(name="T", char_id=1, level="c1")
        player.effects = [{"kind": "buff", "id": 5, "ends": 110.0, "duration": 30},
                          {"kind": "incoming", "id": 6}]
        state = {"player": player, "send": sent.append}
        login_stub.effect_query(state, 9, 100.0)              # not active: remove it
        login_stub.effect_query(state, 5, 100.0)              # still running: its timer
        login_stub.effect_query(state, 6, 100.0)              # no timer: nothing
        self.assertEqual(sent, [effects.effect_remove(9), effects.effect_timer(5, 10.0, 30)])


class GmSummonGroupTests(unittest.TestCase):
    def test_whole_group_comes(self):
        gm = {"player": zone.Player(name="Gm", char_id=1, level="c1"), "send": [].append, "position": (0.0, 0.0, 0.0)}
        a = {"player": zone.Player(name="A", char_id=2, level="c1"), "send": [].append}
        b = {"player": zone.Player(name="B", char_id=3, level="c1"), "send": [].append}
        moved = []
        args = mock.Mock(dev_commands=True)
        with mock.patch.object(login_stub, "ONLINE", {"gm": gm, "a": a, "b": b}), \
                mock.patch.object(login_stub, "group_states", lambda p: [a, b]), \
                mock.patch.object(login_stub, "place_player", lambda s, ar, loc, ch: moved.append((s["player"].name, loc))):
            login_stub.gm_command(gm, args, login_stub.GM_SUMMON_GROUP, "A\0".encode("utf-16-le"))
        self.assertEqual(moved, [("A", (100.0, 0.0, 50.0)), ("B", (160.0, 0.0, 50.0))])


class SongCrowdControlTests(unittest.TestCase):
    def test_no_song_while_feared_or_stunned(self):
        import struct
        import time
        import effects
        for kind, expect in (("fear", ("notice", 483)), ("stun", ("fail", effects.STUNNED))):
            sent = []
            player = zone.Player(name="Bard", char_id=1, level="c1")
            player.cc = {"kind": kind, "until": time.time() + 10}
            player.song_parts = []
            login_stub.play_song({"player": player, "send": sent.append}, {"name": "Tune"})
            self.assertEqual(len(sent), 1)
            mid = struct.unpack_from("<I", sent[0], 2)[0]
            if expect[0] == "notice":
                self.assertEqual((mid, struct.unpack_from("<h", sent[0], 10)[0]), (0x0E, 483))
            else:
                self.assertEqual(sent[0], effects.ability_failed(expect[1]))
            self.assertFalse(getattr(player, "playing_song", None))


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
        "titles": [2], "songs": [{"name": "s"}], "fish_records": {"Mud Eel": 3.5}, "discovered": ["Mailbox"], "journal_removed": ["chunk_n19_12:5"], "auto_def_target_me": True,
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
        "titles": "titles", "songs": "songs", "fish_records": "fish_records", "discovered": "discovered", "journal_removed": "journal_removed", "auto_def_target_me": "auto_def_target_me",
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

    @unittest.skipUnless(os.path.isdir(os.path.join("..", "UnrealScript")), "needs the game client's files")
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
        self.assertEqual(login_stub.next_wield_preference(p), 3)
        p.pawn_prefs["m_WieldPreference"] = 3
        self.assertEqual(login_stub.next_wield_preference(p), 0)
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

    def test_flying_descent_is_not_a_fall(self):
        sent = []
        player = zone.Player(name="T", char_id=7, level="c")
        player.health, player.flying = 500, True
        player.stats = dict(player.stats, hit_points=500)
        state = {"player": player, "send": sent.append}
        with mock.patch.object(login_stub, "in_water", return_value=False),                 mock.patch.object(login_stub, "build_system_text", lambda t, c=0: t):
            for z in (3000, 3000, 2600, 2000, 1400, 800):
                login_stub.check_fall(state, (0.0, 0.0, float(z)))
            player.flying = False                        # landed: walking from here
            for z in (800, 800):
                login_stub.check_fall(state, (0.0, 0.0, float(z)))
        self.assertEqual(player.health, 500)
        self.assertFalse(any("fall" in str(m) for m in sent))


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


class GeneralAbilityTests(unittest.TestCase):
    def test_general_page_abilities(self):
        names = [a[2] for a in login_stub.general_abilities(content.Content())]
        self.assertEqual(names, ["Sprint", "Recall", "Recall to House"])

    def test_sprint_speeds_up_then_ends(self):
        sent = []
        player = zone.Player(name="Tester", char_id=1, level="chunk_n19_12")
        state = {"player": player, "send": sent.append}
        spec = content.Content().abilities["Sprint"]
        with mock.patch.object(login_stub.zone, "player_pawn_update", return_value=b"u"):
            self.assertTrue(login_stub.general_ability(state, mock.Mock(), player, spec))
            self.assertAlmostEqual(login_stub.ground_speed(player), login_stub.BASE_GROUND_SPEED * 1.25)
            login_stub.sprint_tick(state, mock.Mock(), player.sprint_until + 1)
        self.assertEqual(login_stub.ground_speed(player), login_stub.BASE_GROUND_SPEED)

    def test_recall_needs_a_bind_point(self):
        player = zone.Player(name="Tester", char_id=1, level="chunk_n19_12")
        player.bind = None
        state = {"player": player, "send": [].append}
        self.assertFalse(login_stub.general_ability(state, mock.Mock(), player, {"kind": "recall"}))


class LootSparkleTests(unittest.TestCase):
    def test_sparkle_stops_when_emptied(self):
        npc = mock.Mock(prop=False, merchant=False, tombstone_of=None, loot=[(1, "Tattered Cloth", 1, 1)],
                        coin_left=0, entity_id=0x2000008, sparkle_off=False)
        sent = []
        state = {"send": sent.append}
        self.assertTrue(login_stub.corpse_lootable(npc))
        login_stub.corpse_emptied(state, npc)
        self.assertEqual(sent, [])
        npc.loot = []
        login_stub.corpse_emptied(state, npc)
        login_stub.corpse_emptied(state, npc)
        self.assertEqual(sent, [login_stub.combat.loot_sparkle(npc, False)])
        self.assertEqual(struct.unpack_from("<I", sent[0], 2)[0], 0x565)

    def test_unlock_lines(self):
        self.assertEqual(login_stub.grouploot.unlock_result()[10:], b"\x01\x00\x00\x00")
        m = login_stub.grouploot.unlocked_to_you("Ranger", "Canyon Widow")
        self.assertEqual(struct.unpack_from("<I", m, 2)[0], 0x685)
        # The corpse comes first on the wire (the client prints the second string as the looter).
        self.assertEqual(m[10:], ("Canyon Widow\0Ranger\0").encode("utf-16-le"))

    def test_props_never_sparkle(self):
        self.assertFalse(login_stub.corpse_lootable(mock.Mock(prop=True)))


class EscrowTests(unittest.TestCase):
    def test_full_bags_go_to_escrow_then_a_banker_hands_it_over(self):
        sent = []
        player = zone.Player(name="Tester", char_id=1, level="chunk_n19_12")
        banker = mock.Mock(banker=True)
        player.npcs, player.target = {7: banker}, 7
        state = {"player": player, "send": sent.append}
        with mock.patch.object(login_stub, "save_character_field"),                 mock.patch.object(login_stub, "player_distance", return_value=10),                 mock.patch.object(login_stub, "quest_items_changed"):
            with mock.patch.object(login_stub.zone, "free_bag_slot", return_value=None):
                self.assertTrue(login_stub.give_item(state, "Tattered Cloth", 2))
                self.assertFalse(login_stub.give_item(state, "Rough Stone", escrow=False))
            self.assertEqual([e[0] for e in player.escrow], ["Tattered Cloth"])
            sent.clear()
            login_stub.handle_escrow_event(state, login_stub.merchant.REQ_ESCROW_OPEN, b"")
            ids = [struct.unpack_from("<I", m, 2)[0] for m in sent if isinstance(m, bytes)]
            self.assertEqual(ids[-3:], [0x28D, 0x295, 0x294])
            login_stub.handle_escrow_event(state, login_stub.merchant.REQ_ESCROW_TAKE,
                                           struct.pack("<i", login_stub.merchant.ESCROW_HANDLE_BASE))
        self.assertEqual(player.escrow, [])
        self.assertEqual([i[1] for i in player.items][-1:], ["Tattered Cloth"])


class LearnActionTests(unittest.TestCase):
    def test_only_new_actions_are_announced(self):
        r = {"id": 5, "name": "Test", "stages": [["Prep", [{"action": 11, "name": "Hammer"}, {"action": 12, "name": "Cut"}]]]}
        sent = []
        with mock.patch.object(login_stub.craft, "stages", return_value=r["stages"]):
            login_stub.learn_recipe_actions(sent.append, r, {11})
        ids = [struct.unpack_from("<I", m, 2)[0] for m in sent]
        self.assertEqual(ids, [0x2E8, 0x2E5])


class GreetTests(unittest.TestCase):
    def test_greet_kinds(self):
        npc = mock.Mock(merchant=None, trainer=None, recipe_trainer=None, assembly_trainer=[])
        q = login_stub.quest
        self.assertEqual(login_stub.greet_kind(npc, []), login_stub.GREET_GENERAL)
        self.assertEqual(login_stub.greet_kind(npc, [("Wolf Pelts", 1, q.OPTION_AVAILABLE)]), login_stub.GREET_QUESTER)
        self.assertEqual(login_stub.greet_kind(npc, [("Wolf Pelts (in progress)", 1, q.OPTION_PROGRESS)]), login_stub.GREET_PROGRESS)
        npc.merchant = "camp"
        self.assertEqual(login_stub.greet_kind(npc, []), login_stub.GREET_MERCHANT)


class ChatterTests(unittest.TestCase):
    def test_chatter_reaches_only_nearby_players(self):
        near, far = [], []
        p_near = mock.Mock(live_position=(100.0, 0.0, 0.0), spawned_at=None)
        p_far = mock.Mock(live_position=(9000.0, 0.0, 0.0), spawned_at=None)
        npc = mock.Mock(chatter=["Keep your blade sharp."], chatter_every=60.0, alive=True, aggro=False,
                        location=(0.0, 0.0, 0.0), next_chatter=None)
        npc.name = "Thestran Guard"
        w = mock.Mock(npcs={1: npc}, members={1: {"player": p_near, "send": near.append},
                                             2: {"player": p_far, "send": far.append}})
        login_stub.npc_chatter_tick(w, 1000.0)
        self.assertEqual(near, [])                 # first a random wait
        login_stub.npc_chatter_tick(w, 1000.0 + 61)
        self.assertEqual(len(near), 1)
        self.assertIn("Keep your blade sharp.".encode("utf-16-le"), near[0])
        self.assertEqual(far, [])

    def test_npcs_without_chatter_fields(self):
        w = mock.Mock(npcs={1: object()}, members={})
        login_stub.npc_chatter_tick(w, 1.0)          # tombstones and pets have no "chatter"


class QuestNodeTests(unittest.TestCase):
    def test_nodes_light_up_while_the_quest_needs_their_item(self):
        node = mock.Mock(harvest={"item": "Copper Ore"}, entity_id=0x1234, depleted_until=0)
        player = mock.Mock(npcs={0x1234: node})
        player.quests.active = {"forge_supplies": {"step": 1}}
        args = mock.Mock()
        args.content.quests = {"forge_supplies": {"steps": [{"kill": {"w": 1}}, {"collect": {"Copper Ore": 2}}]}}
        sent = []
        state = {"player": player, "send": sent.append}
        with mock.patch.object(login_stub, "ARGS", args, create=True):
            login_stub.refresh_quest_nodes(state, lambda name: 0)
            login_stub.refresh_quest_nodes(state, lambda name: 0)
            login_stub.refresh_quest_nodes(state, lambda name: 2)
        self.assertEqual([struct.unpack_from("<I", m, 2)[0] for m in sent], [0x56A, 0x56B])


class ConversionTests(unittest.TestCase):
    def test_convert_four_ore_into_an_ingot(self):
        sent = []
        player = zone.Player(name="Tester", char_id=1, level="chunk_n19_12")
        player.items = [(7, "Copper Ore", 443, 6, 0)]
        state = {"player": player, "send": sent.append}
        args = mock.Mock()
        args.content = content.Content()
        with mock.patch.object(login_stub, "ARGS", args, create=True), \
                mock.patch.object(login_stub, "save_character_field"), \
                mock.patch.object(login_stub, "quest_items_changed"):
            ui = login_stub.conversion_ui(player.items[0], args.content.item("Copper Ore")["convert"])
            self.assertEqual(struct.unpack_from("<I", ui, 2)[0], 0x1C2)
            login_stub.handle_conversion(state, struct.pack("<ii", 7, 1))
        self.assertEqual(sorted((i[1], i[3]) for i in player.items), [("Copper Ingot", 1), ("Copper Ore", 2)])


class DeconstructTests(unittest.TestCase):
    def test_salvage_and_dust(self):
        sent = []
        player = zone.Player(name="Tester", char_id=1, level="chunk_n19_12")
        player.items = [(1, "Hunter's Shortsword", 422, 1, 0), (2, "Salvage Kit", 495, 2, 1), (3, "Rusted Dagger", 429, 1, 2)]
        state = {"player": player, "send": sent.append}
        args = mock.Mock()
        args.content = content.Content()
        with mock.patch.object(login_stub, "ARGS", args, create=True), \
                mock.patch.object(login_stub, "save_character_field"), \
                mock.patch.object(login_stub, "quest_items_changed"):
            login_stub.handle_deconstruct(state, login_stub.DECONSTRUCT_ITEMS, struct.pack("<ii", 1, 2))
            login_stub.handle_deconstruct(state, login_stub.DECONSTRUCT_DUST, struct.pack("<ii", 3, 2))
        self.assertEqual(sorted(i[1] for i in player.items), ["Copper Buckle", "Copper Ingot", "Shimmering Dust"])


class ObjectUseTests(unittest.TestCase):
    def test_refusals(self):
        p = mock.Mock(flying=False, resting=False)
        self.assertEqual(login_stub.object_use_refusal({"player": p}), 0)
        self.assertEqual(login_stub.object_use_refusal({"player": p, "craft": {"begun": True}}), login_stub.USE_BUSY)
        p.resting = True
        self.assertEqual(login_stub.object_use_refusal({"player": p}), login_stub.USE_RESTING)
        p.flying = True
        self.assertEqual(login_stub.object_use_refusal({"player": p}), login_stub.USE_FLYING)


class WoundTests(unittest.TestCase):
    def test_crit_wounds_and_rest_heals(self):
        rng = mock.Mock(random=mock.Mock(return_value=0.0), randrange=mock.Mock(return_value=0))
        player = zone.Player(name="Tester", char_id=1, level="chunk_n19_12")
        login_stub.combat.wound(player, rng)
        login_stub.combat.wound(player, rng)
        self.assertEqual(player.wounds, [2, 0, 0, 0, 0])
        sent = []
        state = {"player": player, "send": sent.append}
        player.resting, player.health = True, 10
        with mock.patch.object(login_stub, "save_character_field"), \
                mock.patch.object(login_stub.combat, "in_combat", return_value=False):
            login_stub.wounds_tick(state, 100.0)          # sends the wound, starts the timer
            login_stub.wounds_tick(state, 100.0 + login_stub.WOUND_HEAL_SECONDS)
        self.assertEqual(player.wounds, [1, 0, 0, 0, 0])
        self.assertEqual([m[10:] for m in sent], [bytes([2, 0, 0, 0, 0]), bytes([1, 0, 0, 0, 0])])


class PrestigeFactionTests(unittest.TestCase):
    def test_first_gain_unlocks(self):
        sent = []
        player = zone.Player(name="Tester", char_id=1, level="chunk_n19_12")
        player.factions = {}
        state = {"player": player, "send": sent.append}
        args = mock.Mock()
        args.content = content.Content()
        with mock.patch.object(login_stub, "ARGS", args, create=True), \
                mock.patch.object(login_stub, "save_character_field"):
            login_stub.faction_login(state)
            self.assertFalse(any("Riftwatch".encode("utf-16-le") in m for m in sent))
            sent.clear()
            login_stub.adjust_faction(state, 1005, 250)
        self.assertEqual(struct.unpack_from("<I", sent[0], 2)[0], 0x35D)
        self.assertEqual(player.factions["1005"], 250)


class BuilderTests(unittest.TestCase):
    def test_spawn_then_despawn_restores_the_file(self):
        import json, shutil
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(os.path.join(os.path.dirname(os.path.abspath(login_stub.__file__)), "content"),
                            os.path.join(d, "content"))
            path = os.path.join(d, "content", "spawns", "chunk_n19_12.json")
            before = open(path, encoding="utf-8").read()
            args = mock.Mock(client_dir=None)
            args.content = content.Content(os.path.join(d, "content"))
            args.content.ground_z = lambda *a: 450.0
            w = mock.Mock(npcs={})
            player = zone.Player(name="Tester", char_id=1, level="chunk_n19_12")
            sent = []
            state = {"player": player, "send": sent.append, "world": w, "position": (-30500.0, -6000.0, 450.0)}
            npc = mock.Mock(template_id="forest_bear", home=(-30500.0, -6000.0, 450.0), wander=0.0, respawn=60, path=[])
            npc.name = "Thornback Bear"
            with mock.patch.object(login_stub.zone, "npc_from_template", side_effect=lambda w_, a, eid, *r: setattr(npc, "entity_id", eid) or npc):
                login_stub.build_spawn(state, args, "forest_bear")
            self.assertIn('"forest_bear"', open(path, encoding="utf-8").read())
            player.npcs, player.target = {npc.entity_id: npc}, npc.entity_id
            login_stub.build_edit(state, args, "wander", 250)
            login_stub.build_edit(state, args, "path add")
            entry = json.loads(open(path, encoding="utf-8").read())["spawns"][-1]
            self.assertEqual((entry["wander"], entry["path"]), (250, [[-30500, -6000]]))
            login_stub.build_despawn(state, args)
            self.assertEqual(json.loads(open(path, encoding="utf-8").read()), json.loads(before))
            self.assertEqual(w.npcs, {})
            with mock.patch.object(login_stub.zone, "npc_from_template", side_effect=lambda w_, a, eid, *r: npc):
                login_stub.build_undo(state)              # the removal comes back
            self.assertIn(npc.entity_id, w.npcs)
            self.assertIn('"forest_bear"', open(path, encoding="utf-8").read())
            for _ in range(3):
                login_stub.build_undo(state)              # path add, wander, then the spawn itself
            self.assertEqual(open(path, encoding="utf-8").read(), before)
            self.assertEqual(w.npcs, {})


class BuilderAccessTests(unittest.TestCase):
    def test_gms_may_build_without_dev_commands(self):
        args = mock.Mock(dev_commands=False)
        gm, player = mock.Mock(access_level=1), mock.Mock(access_level=0)
        self.assertTrue(login_stub.dev_allowed(args, gm, "!spawn wastes_bear"))
        self.assertFalse(login_stub.dev_allowed(args, gm, "!kill"))
        self.assertFalse(login_stub.dev_allowed(args, player, "!spawn wastes_bear"))
        self.assertTrue(login_stub.dev_allowed(mock.Mock(dev_commands=True), player, "!kill"))


class SpawnReloadTests(unittest.TestCase):
    def test_refresh_replaces_spawned_npcs_only(self):
        base = login_stub.zone.SPAWN_EID_BASE
        tomb = mock.Mock()
        w = mock.Mock(level="chunk_n19_12", npcs={base: mock.Mock(), base + 1: mock.Mock(), 0x3000001: tomb})
        args = mock.Mock()
        args.content.directory = "nowhere"

        def populate(w_, a):
            w_.npcs[base] = mock.Mock()
        with mock.patch.object(login_stub.zone, "populate_world", side_effect=populate):
            login_stub.refresh_world_spawns(w, args)
        self.assertEqual(sorted(w.npcs), [base, 0x3000001])
        self.assertIs(w.npcs[0x3000001], tomb)          # tombstones and pets stay


class FormRestrictionTests(unittest.TestCase):
    def test_fields_and_refusal(self):
        import forms
        fl = [(1, "Mindset of Clarity", {"abilities": ["Mind Blast"]}), (2, "Mindset of Focus", {})]
        self.assertEqual(forms.allowed_forms(fl, "Mind Blast"), [1])
        self.assertEqual(forms.form_fields([1]), {61 + n: 1 for n in range(8)})
        self.assertEqual(forms.form_fields([]), {})
        sent = []
        player = zone.Player(name="T", char_id=1, level="c")
        player.forms, player.form, player.cooldowns = fl, 2, {}
        args = mock.Mock()
        args.content.abilities = {}
        with mock.patch.object(login_stub, "stunned", side_effect=AssertionError("not reached")):
            login_stub.use_ability({"player": player, "send": sent.append}, args, player,
                                   (5, 1234, "Mind Blast", 443, "", 0.0))
        self.assertIn("can only be used in Mindset of Clarity".encode("utf-16-le"), sent[0])


class SmallFeatureTests(unittest.TestCase):
    """Messages of 2026-10-15 features that were checked live; these pin their layouts."""

    def test_spyglass_toggles_the_zoom(self):
        sent = []
        state = {"send": sent.append}
        login_stub.use_spyglass(state, {"fov": 20, "seconds": 1})
        login_stub.use_spyglass(state, {"fov": 20, "seconds": 1})
        self.assertEqual([struct.unpack_from("<I", m, 2)[0] for m in sent], [0x5C7, 0x5C7])
        self.assertEqual(struct.unpack_from("<fff", sent[0], 10), (90.0, 20.0, 1.0))
        self.assertEqual(struct.unpack_from("<fff", sent[1], 10), (20.0, 90.0, 1.0))

    def test_fireworks_play_and_use_one(self):
        sent = []
        player = zone.Player(name="T", char_id=7, level="c")
        player.items = [(1, "Blue Rocket", 444, 2, 0)]
        state = {"player": player, "send": sent.append}
        with mock.patch.object(login_stub, "save_character_field"):
            login_stub.set_off_fireworks(state, player.items[0], 60002)
        self.assertEqual(struct.unpack_from("<I", sent[0], 2)[0], login_stub.combat.DISPLAY_EVENT)
        self.assertEqual(struct.unpack_from("<i", sent[0], 10 + 16)[0], 60002)
        self.assertEqual(player.items[0][3], 1)
        sent.clear()
        state["position"] = (10.0, 20.0, 500.0)
        with mock.patch.object(login_stub, "save_character_field"):
            login_stub.set_off_fireworks(state, player.items[0], 60022, "FXspells.FXspells_FireworksCastSparklerARed_P001fx")
        self.assertEqual(struct.unpack_from("<I", sent[1], 2)[0], login_stub.SPAWN_CLIENT_ACTOR)
        self.assertEqual(struct.unpack_from("<fff", sent[1], len(sent[1]) - 12), (10.0, 20.0, 440.0))

    def test_visit_finds_an_npc_spawn(self):
        import tempfile, json as _json
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "spawns"))
            with open(os.path.join(d, "spawns", "chunk_n14_n11.json"), "w", encoding="utf-8") as f:
                _json.dump({"spawns": [{"mob": "a", "x": 1, "y": 2, "z": 3}, {"mob": "b", "x": 4, "y": 5}]}, f)
            content = mock.Mock(directory=d, mobs={"a": {"name": "Ghobad Houri"}, "b": {"name": "Ghob"}})
            self.assertEqual(login_stub.find_npc_spawn(content, "ghob"), ("chunk_n14_n11", "Ghob", 4.0, 5.0, None))
            self.assertEqual(login_stub.find_npc_spawn(content, "houri")[1], "Ghobad Houri")
            self.assertIsNone(login_stub.find_npc_spawn(content, "nobody"))
            content.mobs["b"]["name"] = "Hive-King Ghob"
            self.assertEqual(login_stub.find_npc_spawn(content, "hive king")[1], "Hive-King Ghob")   # punctuation ignored

    def test_corpse_summon_moves_the_tombstone(self):
        sent = []
        player = zone.Player(name="T", char_id=7, level="c")
        player.tombstone = {"level": "c", "loc": [0.0, 0.0, 0.0]}
        npc = mock.Mock(corpse_summoner=True)
        npc.name = "Veyla Brightsteel"
        player.npcs, player.target = {5: npc}, 5
        state = {"player": player, "send": sent.append, "position": (100.0, 200.0, 300.0)}
        with mock.patch.object(login_stub, "player_distance", return_value=50), \
                mock.patch.object(login_stub, "place_tombstone") as place:
            login_stub.summon_corpse(state, mock.Mock())
        place.assert_called_once()
        self.assertEqual(player.died_at, (180.0, 200.0, 300.0))

    def test_direction_answer_and_banner_layouts(self):
        import attributes, craft
        m = attributes.direction_result(0, 231, 1, 2)
        self.assertEqual((struct.unpack_from("<I", m, 2)[0], struct.unpack_from("<iiii", m, 10)), (0x2D8, (0, 231, 1, 2)))
        b = craft.banner("Preparation complete. Next: Smelting")
        self.assertEqual(struct.unpack_from("<I", b, 2)[0], 0x307)
        self.assertIn("Next: Smelting".encode("utf-16-le"), b)


class ConsoleReloadTests(unittest.TestCase):
    def test_reload_forces_a_content_reload(self):
        args = mock.Mock()
        fresh = mock.Mock(directory="d")
        with mock.patch.object(login_stub.content, "validate", return_value=[]), \
                mock.patch.object(login_stub.content, "Content", return_value=fresh) as make, \
                mock.patch.object(login_stub.zone, "ITEM_CONTENT", login_stub.zone.ITEM_CONTENT), \
                mock.patch.object(login_stub.world, "all_worlds", return_value=[]), \
                mock.patch.object(login_stub, "npc_files_stamp", return_value=1.0):
            login_stub.console_command("reload", {}, args)
        make.assert_called_once()
        self.assertIs(args.content, fresh)


class MobCritTests(unittest.TestCase):
    def test_crit_overrides_the_formula(self):
        rng = mock.Mock(random=mock.Mock(return_value=0.99))
        self.assertEqual(login_stub.combat.roll_outcome(rng, 10, 10, crit=1.0), login_stub.effects.CRIT)
        rng.random.return_value = 0.0001
        self.assertNotEqual(login_stub.combat.roll_outcome(rng, 10, 10, crit=0.0), login_stub.effects.CRIT)


class LeashTests(unittest.TestCase):
    def test_leashed_npc_does_not_reaggro(self):
        c = login_stub.combat
        npc = c.Npc(1, "Ashen Wolf", None, "x", location=(0.0, 0.0, 0.0))
        npc.aggro_radius = 800
        p = mock.Mock(live_position=(100.0, 0.0, 0.0), spawned_at=None, health=10, char_id=5)
        npc.location = (c.LEASH + 500.0, 0.0, 0.0)
        p.live_position = (c.LEASH + 600.0, 0.0, 0.0)
        self.assertIsNone(c.proximity_aggro(npc, [p]))
        npc.location = (0.0, 0.0, 0.0)
        p.live_position = (100.0, 0.0, 0.0)
        self.assertIs(c.proximity_aggro(npc, [p]), p)

    def test_evading_npc_inside_the_leash_does_not_reaggro(self):
        # Seen live 2026-10-15: wolves that chased a griffon rider past the leash gave up, took one
        # step home (back inside the leash), noticed the player again and gave up again, forever.
        c = login_stub.combat
        npc = c.Npc(1, "Ashen Wolf", None, "x", location=(0.0, 0.0, 0.0))
        npc.aggro_radius = 800
        npc.location = (c.LEASH - 10.0, 0.0, 0.0)
        c.give_up(npc)
        p = mock.Mock(live_position=(c.LEASH + 100.0, 0.0, 0.0), spawned_at=None, health=10, char_id=5)
        self.assertIsNone(c.proximity_aggro(npc, [p]))
        npc.evading = False                                    # home again
        self.assertIs(c.proximity_aggro(npc, [p]), p)

    def test_leash_forgets_and_heals_at_home(self):
        c = login_stub.combat
        npc = c.Npc(1, "Ashen Wolf", None, "x", max_health=100, location=(0.0, 0.0, 0.0))
        npc.blocked = None
        p = mock.Mock(char_id=5, health=10)
        npc.health, npc.aggro, npc.aggro_on = 40, True, p
        npc.hate = {5: (p, 30)}
        npc.location = (c.LEASH + 10.0, 0.0, 0.0)
        c.chase_step(npc, (c.LEASH + 400.0, 0.0, 0.0), 0.5)
        self.assertEqual((npc.aggro, npc.hate), (False, {}))
        out = None
        for _ in range(100):
            out = c.chase_step(npc, None, 0.5) or out
            if npc.health == 100:
                break
        self.assertEqual(npc.health, 100)
        self.assertEqual(out.get("Health"), 100)


class PetDefaultTests(unittest.TestCase):
    def test_toggle_ids(self):
        # The client flips its flag before sending: 0x86 = now the default, 0x87 = not (winbreak).
        self.assertEqual((login_stub.pets.DEFAULT_ON, login_stub.pets.DEFAULT_OFF), (0x86, 0x87))


class GiveUpTests(unittest.TestCase):
    def test_give_up_forgets_and_heads_home(self):
        c = login_stub.combat
        npc = c.Npc(1, "Canyon Widow", None, "x", location=(50.0, 0.0, 0.0))
        npc.home = (0.0, 0.0, 0.0)
        npc.aggro, npc.aggro_on, npc.hate = True, mock.Mock(), {5: (None, 3)}
        c.give_up(npc)
        self.assertEqual((npc.aggro, npc.aggro_on, npc.hate, npc.wander_goal, npc.evading),
                         (False, None, {}, (0.0, 0.0, 0.0), True))


class AfterPetTests(unittest.TestCase):
    def test_turns_on_owner_or_gives_up(self):
        c = login_stub.combat
        owner = mock.Mock(health=50)
        npc = c.Npc(1, "Dust Bear", None, "x", location=(0.0, 0.0, 0.0))
        npc.hate = {5: (owner, 10)}
        npc.fighting_pet_until = 100.0
        c.after_pet(npc, 99.0)
        self.assertFalse(npc.aggro)                       # the pet still holds it
        c.after_pet(npc, 101.0)
        self.assertEqual((npc.aggro, npc.aggro_on), (True, owner))
        npc2 = c.Npc(2, "Dust Bear", None, "x", location=(0.0, 0.0, 0.0))
        npc2.hate = {5: (mock.Mock(health=0), 10)}
        npc2.fighting_pet_until = 100.0
        c.after_pet(npc2, 101.0)
        self.assertTrue(npc2.evading)                     # owner dead: walks home


class FleeTests(unittest.TestCase):
    def test_flees_once_below_the_share(self):
        c = login_stub.combat
        npc = c.Npc(1, "Ashen Wolf", None, "x", max_health=100, location=(0.0, 0.0, 0.0))
        npc.flee_at = 0.2
        npc.health = 50
        self.assertFalse(c.maybe_flee(npc, 10.0))
        npc.health = 15
        self.assertTrue(c.maybe_flee(npc, 10.0))
        self.assertEqual(npc.feared_until, 10.0 + c.FLEE_SECONDS)
        npc.aggro_on = mock.Mock(char_id=5)
        friend = c.Npc(2, "Ashen Wolf", None, "x", max_health=100, location=(100.0, 0.0, 0.0))
        friend.template_id = npc.template_id
        self.assertEqual(c.social_assist(npc, [npc, friend]), [friend])     # calls for help as it runs
        self.assertFalse(c.maybe_flee(npc, 11.0))        # once per fight


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


class GroupReferralTests(unittest.TestCase):
    def test_member_invite_goes_to_leader(self):
        import struct
        import group
        sent = {"lead": [], "mem": [], "out": []}
        st = {k: {"player": zone.Player(name=k.title(), char_id=i, level="c1"), "send": sent[k].append}
              for i, k in enumerate(("lead", "mem", "out"), 1)}
        g = group.Group(st["lead"]["player"])
        g.members.append(st["mem"]["player"])
        st["lead"]["player"].group = st["mem"]["player"].group = g
        with mock.patch.object(login_stub, "ONLINE", st):
            login_stub.handle_group_event(st["mem"], group.INVITE, b"\0" * 10 + "Out\0".encode("utf-16-le"))
        self.assertEqual(sent["out"], [])                       # no invite popup from a non-leader
        self.assertIn("Mem would like to invite Out to the group.\0".encode("utf-16-le"), sent["lead"][-1])
        self.assertIn(struct.pack("<QQ", 2, 3), sent["lead"][-1])


class GuildInviteTimeoutTests(unittest.TestCase):
    def test_expired_invite_closes_popup_and_tells_inviter(self):
        sent = {"a": [], "b": []}
        a = {"player": zone.Player(name="A", char_id=1, level="c1"), "send": sent["a"].append}
        b = {"player": zone.Player(name="B", char_id=2, level="c1"), "send": sent["b"].append,
             "guild_invite": (5, "A"), "guild_invite_at": (0.0, "Night Watch")}
        with mock.patch.object(login_stub, "ONLINE", {"a": a, "b": b}):
            login_stub.group_tick()
        self.assertNotIn("guild_invite", b)
        self.assertIn(zone.zone_event(0x4E8, "Night Watch\0".encode("utf-16-le") + bytes(4)), sent["b"])
        self.assertTrue(any("invitation to B has expired".encode("utf-16-le") in m for m in sent["a"]))


class BardingTests(unittest.TestCase):
    def test_barding_only_on_modular_mounts_while_owned(self):
        args = mock.Mock()
        args.content.item = lambda name: {"Plate Barding": {"barding": 205}}.get(name, {})
        p = zone.Player(name="R", char_id=1, level="c1")
        p.items = [(7, "Plate Barding", 1225, 1, 0)]
        p.barding_item = "Plate Barding"
        p.mount = 1000
        self.assertEqual(login_stub.mount_barding(args, p), 205)
        p.barding = 205
        self.assertIn((500, 205, 45), zone.gear_attachments(p))
        p.mount = 5001                                      # a full-mesh mount takes no barding
        self.assertIsNone(login_stub.mount_barding(args, p))
        p.mount, p.items = 1000, []                         # the item is gone
        self.assertIsNone(login_stub.mount_barding(args, p))


class UseItemTests(unittest.TestCase):
    def test_heal_cooldown_and_refusal(self):
        import struct
        sent = []
        p = zone.Player(name="R", char_id=1, level="c1")
        p.stats = {"hit_points": 100, "energy": 50}
        p.health, p.energy = 30, 10
        p.items = [(7, "Snack", 442, 2, 0)]
        state = {"player": p, "send": sent.append}
        args = mock.Mock()
        args.content.item = lambda name: {"use": {"heal": 40}, "cooldown": 30}
        with mock.patch.object(login_stub, "save_character_field", lambda *a: None), \
                mock.patch.object(zone, "cooldown_group", lambda name: 9):
            login_stub.use_item(state, args, p.items[0])
            self.assertEqual((p.health, p.items), (70, [(7, "Snack", 442, 1, 0)]))
            self.assertIn(zone.zone_event(0x1E5, struct.pack("<qii", 30, 9, 30)), sent)
            login_stub.use_item(state, args, p.items[0])
        self.assertEqual(sent[-1], zone.zone_event(0x1C5, bytes([7])))
        self.assertEqual((p.health, len(p.items)), (70, 1))


class HintTests(unittest.TestCase):
    def test_once_per_character_and_off(self):
        import hints
        args = mock.Mock()
        args.content.hints = {"welcome": {"title": "Hi", "text": "Move"}, "death": {"title": "D", "text": "x"}}
        p = zone.Player(name="R", char_id=1, level="c1")
        with mock.patch.object(login_stub, "ARGS", args), \
                mock.patch.object(login_stub, "save_character_field", lambda *a: None):
            m = login_stub.hint(p, "welcome")
            self.assertEqual(m, hints.show(2, "Hi", "Move"))
            self.assertIsNone(login_stub.hint(p, "welcome"))         # once
            self.assertIsNone(login_stub.hint(p, "level"))           # no such hint
            login_stub.handle_hint_event({"player": p, "send": [].append}, hints.CLOSED_NO_MORE)
            self.assertIsNone(login_stub.hint(p, "death"))           # turned off
            login_stub.handle_hint_event({"player": p, "send": [].append}, hints.RESET)
            self.assertIsNotNone(login_stub.hint(p, "welcome"))


class GroupCastTests(unittest.TestCase):
    def test_cast_shown_then_cleared(self):
        import group
        sent = []
        a = {"player": zone.Player(name="A", char_id=1, level="c1"), "send": [].append}
        b = {"player": zone.Player(name="B", char_id=2, level="c1"), "send": sent.append}
        ability = (5, 600, "Regrowth I", 553, "", 0.0)
        a["casting"] = {"ability": ability, "ends": 102.0, "pos": None}
        with mock.patch.object(login_stub, "group_states", lambda p: [a, b]):
            login_stub.group_cast_sync(a, a["player"], 100.0)
            login_stub.group_cast_sync(a, a["player"], 101.0)        # still casting: nothing new
            a.pop("casting")
            login_stub.group_cast_sync(a, a["player"], 102.0)
        self.assertEqual(sent, [group.member_casting(a["player"], 553, "Regrowth I", 2.0),
                                group.member_cast_over(a["player"], 553)])


class OutpostTests(unittest.TestCase):
    def test_flag_follows_position(self):
        sent = []
        args = mock.Mock()
        args.content.outposts = {"camp": {"chunk": "c1", "loc": [0, 0], "radius": 100}}
        p = zone.Player(name="R", char_id=1, level="c1")
        state = {"player": p, "send": sent.append, "ue": object(), "position": (500.0, 0.0, 0.0),
                 "outpost_after": 0}
        with mock.patch.object(login_stub, "ARGS", args):
            login_stub.outpost_sync(state)                 # outside at first: on, then off
            self.assertEqual(sent, [zone.zone_event(0x552, bytes([1])), zone.zone_event(0x552, bytes([0]))])
            login_stub.outpost_sync(state)
            self.assertEqual(len(sent), 2)                 # no change, nothing sent
            state["position"] = (10.0, 0.0, 0.0)
            login_stub.outpost_sync(state)
            self.assertEqual(sent[-1], zone.zone_event(0x552, bytes([1])))


class DefTargetPanelTests(unittest.TestCase):
    def test_health_sent_on_change(self):
        sent = []
        other = zone.Player(name="B", char_id=9, level="c1")
        other.stats, other.health = {"hit_points": 200}, 100
        w = mock.Mock()
        w.members = {9: {"player": other}}
        state = {"player": zone.Player(name="A", char_id=1, level="c1"), "send": sent.append,
                 "world": w, "def_target": 9}
        login_stub.def_target_sync(state)
        login_stub.def_target_sync(state)                    # unchanged: nothing more
        other.health = 0
        login_stub.def_target_sync(state)
        self.assertEqual(sent, [zone.zone_event(0x3E2, struct.pack("<QB", 9, 128)),
                                zone.zone_event(0x3E2, struct.pack("<QB", 9, 0))])


class AbilityContentTests(unittest.TestCase):
    def test_overrides_icon_description_refresh(self):
        a = (3, 570001, "Brutal Strike I", 553, "Brutal Strike I.", 5.0)
        self.assertEqual(login_stub.ability_content(a, {}), a)
        b = login_stub.ability_content(a, {"Brutal Strike I": {"icon": 516, "description": "A powerful attack.", "refresh": 0}})
        self.assertEqual(b, (3, 570001, "Brutal Strike I", 516, "A powerful attack.", 0.0))


class ArchiveQuestPlayTests(unittest.TestCase):
    """Every archive quest in quests.json (arch_*, added by tools/quest_readiness.py) can be played
    through the server's own quest code: its kills count, its items are handed over, and turning
    it in pays out and closes it."""

    def test_archive_quests_play_through(self):
        import content
        import quest
        c = content.Content()
        keys = [k for k in c.quests if k.startswith("arch_")]
        self.assertTrue(keys)
        args = mock.Mock(content=c, quest_feedback=False)
        for key in keys:
            q = c.quests[key]
            with self.subTest(quest=key):
                sent = []
                player = zone.Player(name="T", char_id=7, level="c")
                player.items, player.coins = [], 0
                player.quests.active[key] = {"step": 0, "count": 0}
                state = {"player": player, "send": sent.append}
                with mock.patch.object(login_stub, "ARGS", args, create=True), \
                        mock.patch.object(login_stub, "save_character_field"), \
                        mock.patch.object(login_stub, "award_xp", return_value=[]), \
                        mock.patch.object(login_stub, "give_item"):
                    for n, step in enumerate(quest.steps(q)):
                        for mob, need in step.get("kill", {}).items():
                            npc = mock.Mock(template_id=mob, entity_id=99)
                            for _ in range(need):
                                login_stub.quest_kill(state, npc)
                        for name, need in step.get("collect", {}).items():
                            player.items.append((100 + n, name, 442, need, n))
                            login_stub.quest_advance(state, key, q, 0)
                    have = login_stub.have_items(player)
                    self.assertTrue(quest.ready(q, player.quests.active[key], have), player.quests.active[key])
                    login_stub.finish_quest(state, key, q)
                self.assertIn(key, player.quests.done)
                self.assertFalse(any(i[1] in {nm for s in quest.steps(q) for nm in s.get("collect", {})} for i in player.items))


class ParleyLevelTests(unittest.TestCase):
    def test_archive_parley_xp_scales_with_level(self):
        sent, xp = [], []
        player = zone.Player(name="T", char_id=7, level="c")
        player.parleys_won = ["arch_x"]
        args = mock.Mock()
        args.content.mobs = {"arch_x": {"parley_level": 40}, "orin": {"parley_level": 40}}
        state = {"player": player, "send": sent.append}
        npc = mock.Mock(template_id="arch_x", entity_id=5)
        npc.name = "X"
        generic = mock.Mock(npc=npc, config={"reward": {"xp": 100}, "_archive_placeholder": True})
        with mock.patch.object(login_stub, "ARGS", args, create=True), \
                mock.patch.object(login_stub, "sphere_xp", lambda s, sphere, n: xp.append(n)), \
                mock.patch.object(login_stub, "faction_reward"):
            login_stub.finish_parley(state, generic, "won")
            npc.template_id = "orin"
            player.parleys_won = ["orin"]
            login_stub.finish_parley(state, mock.Mock(npc=npc, config={"reward": {"xp": 150}}), "won")
        self.assertEqual(xp, [400, 150])          # hand-made parleys keep their reward

    def test_won_parley_raises_presence(self):
        sent = []
        player = zone.Player(name="T", char_id=7, level="c")
        player.parleys_won, player.presence = ["n"], {"noble": 30}
        args = mock.Mock()
        args.content.mobs = {"n": {"presence_station": "noble"}}
        npc = mock.Mock(template_id="n", entity_id=5)
        npc.name = "N"
        with mock.patch.object(login_stub, "ARGS", args, create=True),                 mock.patch.object(login_stub, "save_character_field") as save,                 mock.patch.object(login_stub, "sphere_xp"), mock.patch.object(login_stub, "faction_reward"):
            login_stub.finish_parley({"player": player, "send": sent.append}, mock.Mock(npc=npc, config={"reward": {}}), "won")
        self.assertEqual(player.presence["noble"], 30 + login_stub.PRESENCE_GAIN)
        save.assert_any_call("T", "presence", player.presence)
        ids = [struct.unpack_from("<I", m, 2)[0] for m in sent]
        self.assertLess(ids.index(0x2D3), ids.index(0x2D4))      # re-create the stat, then update it
