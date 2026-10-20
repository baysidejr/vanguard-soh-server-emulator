import json
from pathlib import Path
import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_final_numeric_observation'

class BloodMageFinalNumericTests(unittest.TestCase):
    def test_reviewed_observations_and_unknowns(self):
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_FINAL_NUMERIC_SOURCE_REVIEW_ITERATION738.json').read_text())
        for row in review['rows']:
            for o in row['observations']:
                with self.subTest(name=row['name']):
                    fact, = [f for f in effect_facts(o['literal']) if f['kind'] == KIND]
                    for key, value in o['candidate_observation'].items():
                        self.assertEqual(fact[key], value)
                    self.assertIsNone(fact['operative_values'])
                    self.assertIsNone(fact['historical_authentication'])

    def test_changed_amount_or_recipient_is_withheld(self):
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_FINAL_NUMERIC_SOURCE_REVIEW_ITERATION738.json').read_text())
        for row in review['rows']:
            literal = row['observations'][0]['literal']
            for changed in (literal.replace(next(c for c in literal if c.isdigit()), '9', 1), literal + ' Only against undead.', literal.replace('your', 'their')):
                if changed != literal:
                    self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
