import json
import unittest
from pathlib import Path
from test_extract_blasting_bellow import effect_facts

ROOT = Path(__file__).resolve().parents[1]

class MesmerizeTests(unittest.TestCase):
    def test_reviewed_pages_and_duration_collision(self):
        review = json.loads((ROOT / 'reviewed/BARD_MESMERIZE_SOURCE_REVIEW_ITERATION607.json').read_text())
        for row in review['rows']:
            with self.subTest(name=row['name']):
                facts = effect_facts(row['literal'])
                self.assertEqual(len(facts), 1)
                for key, value in row['observation'].items():
                    self.assertEqual(facts[0][key], value)
                self.assertIsNone(facts[0]['operative_duration_seconds'])

    def test_unreviewed_conditions_are_withheld(self):
        literal = ('Mesmerizes your opponent, preventing any actions and movement for 18 seconds or 1 hit. '
                   'Mesmerized targets begin to regenerate after 4 sec. Only one target can be mesmerized at once.')
        for altered in (literal.replace('18 seconds', '0 seconds'), literal.replace('18 seconds', '30 seconds'),
                        literal.replace('or 1 hit', 'and 1 hit'), literal.replace('4 sec', '8 sec'),
                        literal.replace('one target', 'two targets'), literal + ' Unless resisted.'):
            self.assertFalse(any(f['kind'] == 'mesmerize_tooltip_observation' for f in effect_facts(altered)))
