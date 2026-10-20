import json
from pathlib import Path
import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_conditional_cyst_observation'

class BloodMageConditionalCystTests(unittest.TestCase):
    def test_reviewed_observations_and_unknowns(self):
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_PREEXISTING_NUMERIC_COMPLETENESS_ITERATION741.json').read_text())
        for row in review['rows']:
            if 'Cyst' not in row['name']:
                continue
            for o in row['observations']:
                with self.subTest(name=row['name']):
                    fact, = [f for f in effect_facts(o['literal']) if f['kind'] == KIND]
                    for key, value in o['candidate_observation'].items():
                        self.assertEqual(fact[key], value)
                    self.assertEqual(fact['additional_damage_minimum_blood_union'], 3)
                    self.assertEqual(fact['additional_damage_duration_seconds'], 12)
                    self.assertIsNone(fact['damage_type'])
                    self.assertIsNone(fact['tick_interval_seconds'])
                    self.assertIsNone(fact['operative_values'])
                    self.assertIsNone(fact['historical_authentication'])

    def test_changed_amount_or_recipient_is_withheld(self):
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_PREEXISTING_NUMERIC_COMPLETENESS_ITERATION741.json').read_text())
        for row in review['rows']:
            if 'Cyst' not in row['name']:
                continue
            literal = row['observations'][0]['literal']
            for changed in (literal.replace(next(c for c in literal if c.isdigit()), '9', 1), literal + ' Only against undead.', literal.replace('your', 'their')):
                if changed != literal:
                    self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
