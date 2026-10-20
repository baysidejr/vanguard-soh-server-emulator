import json
import unittest
from pathlib import Path
from archive_extract import effect_facts

class ResistanceBuffTests(unittest.TestCase):
    def test_reviewed_schools_and_unknown_magnitude(self):
        review = json.loads(Path('reviewed/BARD_NONNUMERIC_RESISTANCE_BUFF_SOURCE_REVIEW_ITERATION677.json').read_text())
        for row in review['rows']:
            for observation in row['observations']:
                fact, = effect_facts(observation['literal'])
                self.assertEqual(fact['kind'], 'resistance_buff_tooltip_observation')
                for key, value in observation['candidate_observation'].items():
                    self.assertEqual(fact[key], value)
                self.assertIsNone(fact['magnitude'])
                self.assertIsNone(fact['operative_values'])

    def test_changed_scope_negation_and_conditions_withheld(self):
        literal = "Increases all resistances of you and your allies."
        for changed in ('Does not: ' + literal, literal + ' Only outdoors.', literal.replace('allies', 'opponents'), literal.replace('all resistances', 'fire resistance')):
            self.assertFalse(any(f['kind'] == 'resistance_buff_tooltip_observation' for f in effect_facts(changed)))
