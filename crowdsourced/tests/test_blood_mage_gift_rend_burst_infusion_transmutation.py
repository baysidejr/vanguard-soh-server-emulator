import json
from pathlib import Path
import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_gift_rend_burst_infusion_transmutation_observation'

class BloodMageGiftRendBurstInfusionTransmutationTests(unittest.TestCase):
    def test_reviewed_observations_and_unknowns(self):
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_GIFT_REND_BURST_INFUSION_TRANSMUTATION_SOURCE_REVIEW_ITERATION732.json').read_text())
        for row in review['rows']:
            for o in row['observations']:
                with self.subTest(name=row['name']):
                    fact, = [f for f in effect_facts(o['literal']) if f['kind'] == KIND]
                    for key, value in o['candidate_observation'].items():
                        self.assertEqual(fact[key], value)
                    self.assertIsNone(fact['operative_values'])
                    self.assertIsNone(fact['historical_authentication'])

    def test_changed_amount_or_recipient_is_withheld(self):
        literal = 'You use your blood to heal an ally, other than yourself, for 2869. Heals for an extra 2% per level of Blood Union.'
        for changed in (literal.replace('2869', '2870'), literal.replace('other than yourself', 'including yourself'), literal + ' Only against undead.'):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
