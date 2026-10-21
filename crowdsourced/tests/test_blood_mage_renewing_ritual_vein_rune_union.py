import json
from pathlib import Path
import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_renewing_ritual_vein_rune_union_observation'

class BloodMageRenewingRitualVeinRuneUnionTests(unittest.TestCase):
    def test_reviewed_observations_and_unknowns(self):
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_RENEWING_RITUAL_VEIN_RUNE_UNION_SOURCE_REVIEW_ITERATION736.json').read_text())
        for row in review['rows']:
            for o in row['observations']:
                with self.subTest(name=row['name']):
                    fact, = [f for f in effect_facts(o['literal']) if f['kind'] == KIND]
                    for key, value in o['candidate_observation'].items():
                        self.assertEqual(fact[key], value)
                    self.assertIsNone(fact['operative_values'])
                    self.assertIsNone(fact['historical_authentication'])

    def test_changed_amount_or_recipient_is_withheld(self):
        literal = 'Steals 240 to 254 health from your opponent and returns 130% of it to your defensive target. Increases the returned portion by 10% per level of Blood Union. Increases your Blood Union by 1.'
        for changed in (literal.replace('240', '241'), literal.replace('defensive target', 'offensive target'), literal + ' Only against undead.'):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
