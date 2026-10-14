"""Regression checks for crowdsourced conversion; all scratch data stays here.

Run from the repository root:
    python -B -m unittest discover -s crowdsourced/tests -v
"""
import importlib.util
import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("crowdsourced_converter", HERE / "convert.py")
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


def record(kind, name, **fields):
    return dict(type=kind, name=name,
                sources=[dict(url="https://example.org/record", title=name, date=None)],
                confidence="medium", notes="Synthetic test fixture.", **fields)


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="test-", dir=HERE / "tests")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.batch_dir = self.root / "raw" / "fixture"
        self.batch_dir.mkdir(parents=True)

    def batch(self, records):
        (self.batch_dir / "records.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return converter.Batch(str(self.batch_dir))

    def test_percentages_below_or_equal_one(self):
        for chance, expected in [("1%", 0.01), ("0.5%", 0.005), (1, 0.01), (0.5, 0.005)]:
            with self.subTest(chance=chance):
                batch = self.batch([record("loot", "Fixture", drops=[
                    dict(item="Fixture Item", chance=chance, quantity=[1, 1])])])
                result = converter.convert(batch, {})
                self.assertEqual(result["loot.json"]["fixture"][0]["chance"], expected)

    def test_qualitative_chance_is_not_invented(self):
        batch = self.batch([record("loot", "Fixture", drops=[
            dict(item="Fixture Item", chance="rare", quantity=[1, 1])])])
        result = converter.convert(batch, {})
        self.assertFalse(result["loot.json"].get("fixture"))
        self.assertTrue(batch.issues)

    def test_unsupported_quest_is_not_exported_partially(self):
        batch = self.batch([record("quest", "Fixture Quest", level=1, giver="Fixture NPC",
            steps=[dict(kind="talk", target="Fixture NPC", objective="Talk"),
                   dict(kind="use", target="Fixture Device", objective="Use device")])])
        result = converter.convert(batch, {})
        self.assertNotIn("fixture_quest", result["quests.json"])
        self.assertTrue(batch.issues)

    def test_non_object_json_is_reported_and_valid_records_survive(self):
        batch = self.batch([[], None, 42, record("item", "Fixture Item", item_type="armor")])
        self.assertEqual(len(batch.of("item")), 1)
        self.assertEqual(len(batch.issues), 3)

    def test_malformed_sources_are_rejected(self):
        records = []
        for sources in [[{}], ["invalid"], "invalid"]:
            r = record("item", "Fixture Item", item_type="armor")
            r["sources"] = sources
            records.append(r)
        batch = self.batch(records)
        self.assertFalse(batch.of("item"))
        self.assertEqual(len(batch.issues), 3)

    def test_missing_confidence_is_rejected(self):
        r = record("item", "Fixture Item", item_type="armor")
        del r["confidence"]
        batch = self.batch([r])
        self.assertFalse(batch.of("item"))
        self.assertTrue(batch.issues)

    def test_rerun_does_not_retain_stale_items(self):
        self.batch([record("item", "Fixture Item", item_type="armor")])
        with patch.object(converter, "HERE", str(self.root)), patch.object(converter, "creature_races", return_value={}):
            converter.main([str(self.batch_dir)])
            items = self.root / "reviewed" / "fixture" / "proposed" / "items.json"
            self.assertTrue(items.exists())
            self.batch([])
            converter.main([str(self.batch_dir)])
            self.assertTrue(not items.exists() or json.loads(items.read_text(encoding="utf-8")) == {})

    def test_unsourced_and_low_confidence_records_are_skipped(self):
        unsourced = record("item", "Unsourced")
        unsourced["sources"] = []
        low = record("item", "Low")
        low["confidence"] = "low"
        batch = self.batch([unsourced, low, record("item", "Accepted", item_type="armor")])
        self.assertEqual([r["name"] for r in batch.of("item")], ["Accepted"])
        self.assertEqual(len(batch.issues), 2)

    def test_invalid_chances_are_reported(self):
        for chance in [-1, 101, True, "..%", "about 5%", "5", float("inf")]:
            with self.subTest(chance=chance):
                batch = self.batch([record("loot", "Fixture", drops=[
                    dict(item="Fixture Item", chance=chance, quantity=[1, 1])])])
                result = converter.convert(batch, {})
                self.assertFalse(result["loot.json"].get("fixture"))
                self.assertTrue(batch.issues)

    def test_explicit_percentages_preserve_precision(self):
        for chance, expected in [("0.01%", 0.0001), ("100%", 1), ("0%", 0), (25, 0.25)]:
            with self.subTest(chance=chance):
                batch = self.batch([record("loot", "Fixture", drops=[
                    dict(item="Fixture Item", chance=chance, quantity=[1, 1])])])
                self.assertEqual(converter.convert(batch, {})["loot.json"]["fixture"][0]["chance"], expected)

    def test_quest_ids_avoid_live_and_previous_batch_collisions(self):
        live = self.root / "server" / "content"
        live.mkdir(parents=True)
        (live / "quests.json").write_text(json.dumps({"live": {"id": 6000}}), encoding="utf-8")
        previous = self.root / "reviewed" / "previous" / "proposed"
        previous.mkdir(parents=True)
        (previous / "quests.json").write_text(json.dumps({"previous": {"id": 6001}}), encoding="utf-8")
        batch = self.batch([record("quest", "New Quest", level=1, giver="Fixture NPC",
            steps=[dict(kind="talk", target="Fixture NPC", objective="Talk")]),
            record("quest", "Previous", level=1, giver="Fixture NPC",
            steps=[dict(kind="talk", target="Fixture NPC", objective="Talk")])])
        with patch.object(converter, "ROOT", str(self.root)), patch.object(converter, "HERE", str(self.root)):
            quests = converter.convert(batch, {})["quests.json"]
        self.assertEqual(quests["new_quest"]["id"], 6002)
        self.assertEqual(quests["previous"]["id"], 6001)

    def test_corrupt_json_does_not_discard_valid_following_record(self):
        (self.batch_dir / "records.jsonl").write_text(
            "{broken\n" + json.dumps(record("item", "Accepted", item_type="armor")) + "\n",
            encoding="utf-8")
        batch = converter.Batch(str(self.batch_dir))
        self.assertEqual([r["name"] for r in batch.of("item")], ["Accepted"])
        self.assertEqual(len(batch.issues), 1)

    def test_include_low_requires_opt_in(self):
        r = record("item", "Low", item_type="armor")
        r["confidence"] = "low"
        self.batch([r])
        self.assertEqual(len(converter.Batch(str(self.batch_dir), include_low=True).of("item")), 1)

    def test_duplicate_records_are_all_withheld(self):
        batch = self.batch([record("item", "Same", armor=10), record("item", "Same", armor=20)])
        self.assertFalse(batch.of("item"))
        self.assertTrue(any("duplicate" in issue for issue in batch.issues))

    def test_slug_collisions_are_all_withheld(self):
        batch = self.batch([record("quest", "A-B"), record("quest", "A B")])
        self.assertFalse(batch.of("quest"))
        self.assertTrue(any("collision" in issue for issue in batch.issues))

    def test_npc_creature_output_collision_is_withheld(self):
        batch = self.batch([record("npc", "Same"), record("creature", "Same")])
        self.assertFalse(batch.of("npc"))
        self.assertFalse(batch.of("creature"))

    def test_malformed_nested_values_are_rejected_without_crash(self):
        malformed = [record("item", "Stats", stats=[]), record("loot", "Drops", drops=[42]),
            record("merchant", "Sales", sells="invalid"), record("quest", "Steps", steps=[None]),
            record("quest", "Rewards", rewards=[]), record("item", "Damage", damage=[1]),
            record("npc", "Race", race=42), record("quest", "Count", steps=[dict(count="3")])]
        batch = self.batch(malformed + [record("item", "Accepted", item_type="armor")])
        self.assertEqual([r["name"] for r in batch.of("item")], ["Accepted"])
        self.assertGreaterEqual(len(batch.issues), len(malformed))

    def test_unknown_npc_values_do_not_become_defaults(self):
        batch = self.batch([record("npc", "Unknown NPC", level=None, race=None)])
        self.assertFalse(converter.convert(batch, {})["mobs.json"])
        self.assertTrue(batch.issues)

    def test_known_npc_preserves_health_without_invented_damage(self):
        batch = self.batch([record("npc", "Known NPC", level=20, race="Human", health=123)])
        mob = converter.convert(batch, {"human": 14})["mobs.json"]["known_npc"]
        self.assertEqual(mob["health"], 123)
        self.assertNotIn("damage", mob)

    def test_npc_with_unknown_required_health_is_withheld(self):
        batch = self.batch([record("npc", "Known NPC", level=20, race="Human")])
        self.assertFalse(converter.convert(batch, {"human": 14})["mobs.json"])

    def test_creature_name_is_not_used_to_guess_model(self):
        batch = self.batch([record("creature", "Wolf", level=10, creature_kind=None)])
        self.assertFalse(converter.convert(batch, {"wolf": 1})["mobs.json"])
        self.assertIsNone(converter.find_race({"direwolf": 1}, "wolf"))

    def test_unknown_aggro_range_is_not_invented(self):
        batch = self.batch([record("creature", "Fixture Wolf", level=10, health=100, creature_kind="wolf", aggressive="yes")])
        mob = converter.convert(batch, {"wolf": 1})["mobs.json"]["fixture_wolf"]
        self.assertNotIn("aggro_radius", mob)
        self.assertTrue(batch.issues)

    def test_bag_capacity_and_weapon_delay_are_not_invented(self):
        batch = self.batch([record("item", "Bag", item_type="container", slot="bag"),
                            record("item", "Sword", item_type="weapon", damage=[1, 3])])
        items = converter.convert(batch, {})["items.json"]
        self.assertNotIn("bag", items["Bag"])
        self.assertNotIn("delay", items["Sword"])
        self.assertEqual(len(batch.issues), 2)

    def test_partial_loot_tables_are_not_exported(self):
        batch = self.batch([record("loot", "Fixture", drops=[
            dict(item="Known", chance=50, quantity=[1, 1]),
            dict(item="Unknown", chance="rare", quantity=[1, 1])])])
        self.assertNotIn("fixture", converter.convert(batch, {})["loot.json"])

    def test_unknown_loot_quantity_is_not_invented(self):
        batch = self.batch([record("loot", "Fixture", drops=[dict(item="Known", chance=50, quantity=None)])])
        self.assertNotIn("fixture", converter.convert(batch, {})["loot.json"])

    def test_unknown_merchant_prices_withhold_inventory(self):
        batch = self.batch([record("merchant", "Vendor", npc="Vendor", sells=[dict(item="Item", price_copper=None)])])
        self.assertNotIn("vendor", converter.convert(batch, {})["merchants.json"])

    def test_explicit_zero_price_is_preserved(self):
        batch = self.batch([record("merchant", "Vendor", npc="Vendor", sells=[dict(item="Item", price_copper=0)])])
        self.assertEqual(converter.convert(batch, {})["merchants.json"]["vendor"][0]["price"], 0)

    def test_unknown_quest_count_withholds_quest(self):
        batch = self.batch([record("quest", "Quest", level=1, giver="NPC", steps=[
            dict(kind="collect", target="Item", count=None)])])
        self.assertFalse(converter.convert(batch, {})["quests.json"])

    def test_zero_rewards_are_preserved(self):
        batch = self.batch([record("quest", "Quest", level=1, giver="NPC",
            steps=[dict(kind="talk", target="NPC")], rewards=dict(xp=0, coin_copper=0))])
        with patch.object(converter, "ROOT", str(self.root)), patch.object(converter, "HERE", str(self.root)):
            rewards = converter.convert(batch, {})["quests.json"]["quest"]["reward"]
        self.assertEqual(rewards, dict(xp=0, coin=0))

    def test_item_restrictions_are_preserved_for_manual_mapping(self):
        batch = self.batch([record("item", "Item", item_type="quest", quest_item=True,
            class_restrictions=["Warrior"], stats=dict(unknown_stat=7))])
        metadata = converter.convert(batch, {})["items.json"]["Item"]["_unsupported"]
        self.assertEqual(metadata["item_type"], "quest")
        self.assertEqual(metadata["class_restrictions"], ["Warrior"])
        self.assertEqual(metadata["stats"], dict(unknown_stat=7))

    def test_unresolved_references_are_reported(self):
        batch = self.batch([record("quest", "Quest", level=1, giver="Missing NPC",
            steps=[dict(kind="collect", target="Missing Item", count=2)])])
        with patch.object(converter, "ROOT", str(self.root)), patch.object(converter, "HERE", str(self.root)):
            issues = converter.reference_issues(converter.convert(batch, {}))
        self.assertEqual(len(issues), 2)
        self.assertTrue(any("missing_npc" in i for i in issues))
        self.assertTrue(any("Missing Item" in i for i in issues))

    def test_provenance_keeps_all_sources_and_confidence(self):
        r = record("item", "Item", item_type="armor")
        r["sources"].append(dict(url="https://example.org/other", title="Other", date=None))
        self.batch([r])
        with patch.object(converter, "HERE", str(self.root)), patch.object(converter, "creature_races", return_value={}):
            converter.main([str(self.batch_dir)])
        provenance = json.loads((self.root / "reviewed" / "fixture" / "proposed" / "PROVENANCE.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["item"]["Item"]["sources"], r["sources"])
        self.assertEqual(provenance["item"]["Item"]["confidence"], "medium")

    def validator(self):
        spec = importlib.util.spec_from_file_location("batch_validator", HERE / "validate.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"convert": converter}):
            spec.loader.exec_module(module)
        return module

    def test_validator_requires_delivery_files(self):
        self.batch([record("item", "Item")])
        _, issues = self.validator().validate(self.batch_dir)
        self.assertIn("missing REPORT.md", issues)
        self.assertIn("missing gaps.jsonl", issues)

    def test_validator_accepts_complete_delivery_with_low_confidence(self):
        r = record("item", "Item")
        r["confidence"] = "low"
        self.batch([r])
        (self.batch_dir / "REPORT.md").write_text("Fixture report\n", encoding="utf-8")
        (self.batch_dir / "gaps.jsonl").write_text("", encoding="utf-8")
        batch, issues = self.validator().validate(self.batch_dir)
        self.assertEqual(issues, [])
        self.assertEqual(len(batch.of("item")), 1)

    def test_validator_reports_malformed_gap_records(self):
        self.batch([record("item", "Item")])
        (self.batch_dir / "REPORT.md").write_text("Fixture report\n", encoding="utf-8")
        (self.batch_dir / "gaps.jsonl").write_text("[]\n{broken\n", encoding="utf-8")
        _, issues = self.validator().validate(self.batch_dir)
        self.assertEqual(len(issues), 2)


if __name__ == "__main__":
    unittest.main()
