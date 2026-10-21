import unittest
from archive_extract import effect_facts

KIND = "blood_mage_symbiote_hate_ritual_union_observation"

class BloodMageSymbioteHateRitualUnionTests(unittest.TestCase):
    def test_hate_amount_has_no_invented_duration(self):
        fact, = [f for f in effect_facts("Numbs your opponent's mind, lowering your hate by 2729.") if f['kind'] == KIND]
        self.assertEqual(fact['hate_reduction'], 2729)
        for key in ('duration_seconds', 'tick_interval_seconds', 'operative_values', 'historical_authentication'):
            self.assertIsNone(fact[key])

    def test_unreviewed_quantity_and_condition_are_withheld(self):
        for literal in ("Numbs your opponent's mind, lowering your hate by 2730.",
                        "Numbs your opponent's mind, lowering your hate by 2729. Only against undead."):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(literal)))
