import json
from pathlib import Path
import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_transmutation_symbiote_thief_tribute_vein_observation'

class BloodMageTransmutationSymbioteThiefTributeVeinTests(unittest.TestCase):
    def test_reviewed_observations_and_unknowns(self):
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_TRANSMUTATION_SYMBIOTE_THIEF_TRIBUTE_VEIN_SOURCE_REVIEW_ITERATION734.json').read_text())
        for row in review['rows']:
            for o in row['observations']:
                with self.subTest(name=row['name']):
                    fact, = [f for f in effect_facts(o['literal']) if f['kind'] == KIND]
                    for key, value in o['candidate_observation'].items():
                        self.assertEqual(fact[key], value)
                    self.assertIsNone(fact['operative_values'])
                    self.assertIsNone(fact['historical_authentication'])

    def test_changed_amount_or_recipient_is_withheld(self):
        literal = 'Steals 360 to 381 health from all opponents within 10m and returns 50% of it to you. Increases the returned portion by 10% per level of Blood Union.'
        for changed in (literal.replace('360', '361'), literal.replace('to you', 'to your ally'), literal + ' Only against undead.'):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
