import json
import unittest
from pathlib import Path
from test_extract_blasting_bellow import effect_facts

ROOT = Path(__file__).resolve().parents[1]


class LullSilenceTests(unittest.TestCase):
    def test_reviewed_observations_preserve_unknowns(self):
        review = json.loads((ROOT / 'reviewed/BARD_LULL_SILENCE_SOURCE_REVIEW_ITERATION609.json').read_text())
        for row in review['rows']:
            with self.subTest(name=row['name']):
                facts = effect_facts(row['literal'])
                self.assertEqual(len(facts), 1)
                for key, value in row['observation'].items():
                    self.assertEqual(facts[0][key], value)
                for key in ('operative_values', 'target_level_limit', 'player_target_applicability'):
                    self.assertIsNone(facts[0][key])

    def test_unreviewed_semantics_withheld(self):
        literals = (
            'Lulls the target, preventing it from assisting nearby allies for 18 seconds.',
            'Silences your opponent, preventing the casting of most spells for 10 seconds.')
        for literal in literals:
            for altered in (literal.replace('18', '30').replace('10', '20'),
                            literal.replace('nearby allies', 'all allies').replace('most spells', 'all spells'),
                            literal + ' Unless resisted.'):
                self.assertEqual(effect_facts(altered), [])
