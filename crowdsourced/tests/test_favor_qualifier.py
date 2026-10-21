import unittest
from archive_extract import effect_facts


class FavorQualifierTests(unittest.TestCase):
    def test_at_55_preserves_literal_without_inventing_level(self):
        literal = "Fills your targets group with power.\n+141 Constitution\n+70 Vitality\n+160 Intelligence\n+110 Wisdom\n+1500 Hit Points\n+15 Hit Point Regeneration\n+400 Physical Resistance\n+2.27% Flurry Resist @55\n+2.27% Rampage Resist @55\nStacks Best Buff Only"
        for ending in ("\n", "\r\n", "\r"):
            with self.subTest(ending=repr(ending)):
                fact = effect_facts(literal.replace("\n", ending))[0]
                for kind in ("flurry", "rampage"):
                    self.assertEqual(fact[kind + "_resist_percent_reported"], 2.27)
                    self.assertEqual(fact[kind + "_resist_qualifier_reported"], "@55")
                    self.assertIsNone(fact[kind + "_resist_qualifier_meaning"])
                    self.assertNotIn(kind + "_resist_percent_at_level_55", fact)
                self.assertIsNone(fact["operative_values"])
                self.assertIsNone(fact["historical_authentication"])
