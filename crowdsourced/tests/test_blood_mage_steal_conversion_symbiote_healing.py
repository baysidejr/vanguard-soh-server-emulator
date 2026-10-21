import unittest
from archive_extract import effect_facts

KIND = 'blood_mage_steal_damage_conversion_symbiote_healing_observation'

class BloodMageStealConversionSymbioteHealingTests(unittest.TestCase):
    def test_exact_health_return_keeps_scaling_unknown(self):
        literal = 'Steals 234 to 247 health from your opponent and returns 130% of it to you. Increases the returned portion by 25% per level of Blood Union. Increases your Blood Union by 1.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['health_stolen_min'], fact['health_stolen_max']), (234, 247))
        self.assertEqual(fact['health_return_percent'], 130)
        self.assertEqual(fact['returned_portion_increase_percent_per_blood_union_level'], 25)
        for key in ('return_scaling_base', 'duration_seconds', 'operative_values', 'historical_authentication'):
            self.assertIsNone(fact[key])

    def test_unreviewed_conversion_amount_and_condition_withheld(self):
        import json
        from pathlib import Path
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_STEAL_DAMAGE_CONVERSION_SYMBIOTE_HEALING_SOURCE_REVIEW_ITERATION712.json').read_text())
        row, = [r for r in review['rows'] if r['name'] == 'Mental Transmutation III']
        literal = row['observations'][0]['literal']
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['health_expended'], fact['energy_returned']), (400, 480))
        for changed in (literal.replace('480', '481'), literal + ' Only against undead.'):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
