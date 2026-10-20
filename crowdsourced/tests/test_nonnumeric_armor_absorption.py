import json
import unittest
from pathlib import Path
from archive_extract import effect_facts

class ArmorAbsorptionTests(unittest.TestCase):
    def test_reviewed_modifiers_and_unknown_absorption(self):
        review = json.loads(Path('reviewed/BARD_NONNUMERIC_ARMOR_ABSORPTION_SOURCE_REVIEW_ITERATION679.json').read_text())
        for row in review['rows']:
            for observation in row['observations']:
                fact, = effect_facts(observation['literal'])
                self.assertEqual(fact['kind'], 'armor_absorption_tooltip_observation')
                for key, value in observation['candidate_observation'].items():
                    self.assertEqual(fact[key], value)
                self.assertIsNone(fact['absorption_amount'])
                self.assertIsNone(fact['operative_values'])

    def test_changed_scope_negation_and_conditions_withheld(self):
        literal = "This string chorus causes a curtain of sound to protect you and your allies that increases armor class, block skill and absorbs damage each pulse."
        for changed in ('Does not: ' + literal, literal + ' Only outdoors.', literal.replace('allies', 'opponents'), literal.replace('each pulse', 'once')):
            self.assertFalse(any(f['kind'] == 'armor_absorption_tooltip_observation' for f in effect_facts(changed)))
