import json
from pathlib import Path
import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_qualitative_support_observation'

class BloodMageQualitativeSupportTests(unittest.TestCase):
    def test_reviewed_observations_and_unknowns(self):
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_NONNUMERIC_SOURCE_REVIEW_ITERATION744.json').read_text())
        for row in review['rows']:
            if row['name'] not in {"Serak's Mantle II", "Serak's Mantle I", 'Strip Enchantment IV', 'Regeneration I', 'Mental Infusion I', 'Mortal Calling', "Serak's Augmentation I", 'Strip Enchantment III', "Serak's Mantle III", 'Grim Harvest', 'Strip Enchantment II', 'Strip Enchantment I', 'Call of the Warehouse', 'Ritual of Shielding', "Serak's Mantle IV", 'Health Graft II'}:
                continue
            for o in row['observations']:
                if o['candidate_observation'] is None:
                    continue
                with self.subTest(name=row['name']):
                    fact, = [f for f in effect_facts(o['literal']) if f['kind'] == KIND]
                    for key, value in o['candidate_observation'].items():
                        self.assertEqual(fact[key], value)
                    self.assertIsNone(fact['duration_seconds'])
                    self.assertIsNone(fact['operative_values'])
                    self.assertIsNone(fact['historical_authentication'])

    def test_changed_amount_or_recipient_is_withheld(self):
        review = json.loads((Path(__file__).resolve().parents[1] / 'reviewed/BLOOD_MAGE_NONNUMERIC_SOURCE_REVIEW_ITERATION744.json').read_text())
        for row in review['rows']:
            if row['name'] not in {"Serak's Mantle II", "Serak's Mantle I", 'Strip Enchantment IV', 'Regeneration I', 'Mental Infusion I', 'Mortal Calling', "Serak's Augmentation I", 'Strip Enchantment III', "Serak's Mantle III", 'Grim Harvest', 'Strip Enchantment II', 'Strip Enchantment I', 'Call of the Warehouse', 'Ritual of Shielding', "Serak's Mantle IV", 'Health Graft II'}:
                continue
            literal = next(o['literal'] for o in row['observations'] if o['candidate_observation'])
            for changed in (literal + ' Lasts 30 seconds.', literal + ' Only against undead.', literal.replace('your', 'their')):
                if changed != literal:
                    self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
