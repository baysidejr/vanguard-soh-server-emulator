import json
import unittest
from pathlib import Path
from archive_extract import effect_facts

class ResistanceDebuffTests(unittest.TestCase):
    def test_reviewed_schools_and_unknown_magnitude(self):
        review = json.loads(Path('reviewed/BARD_NONNUMERIC_RESISTANCE_SOURCE_REVIEW_ITERATION675.json').read_text())
        for row in review['rows']:
            for observation in row['observations']:
                fact, = effect_facts(observation['literal'])
                self.assertEqual(fact['kind'], 'resistance_debuff_tooltip_observation')
                for key, value in observation['candidate_observation'].items():
                    self.assertEqual(fact[key], value)
                self.assertIsNone(fact['magnitude'])
                self.assertIsNone(fact['operative_values'])

    def test_changed_scope_negation_and_conditions_withheld(self):
        literal = "This brass embellishment lowers your opponent's arcane resistance."
        for changed in ('Does not: ' + literal, literal + ' Only outdoors.', literal.replace('opponent', 'ally'), literal.replace('arcane', 'all')):
            self.assertFalse(any(f['kind'] == 'resistance_debuff_tooltip_observation' for f in effect_facts(changed)))
