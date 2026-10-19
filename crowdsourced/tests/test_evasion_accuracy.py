import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class ReviewedEvasionAccuracyTests(unittest.TestCase):
    def rows(self):
        return json.loads(Path('reviewed/BARD_EVASION_ACCURACY_SPELL_COST_SOURCE_REVIEW_ITERATION649.json').read_text())['rows']

    def test_reviewed_observations_preserve_unknowns(self):
        for row in self.rows():
            obs = row['observations'][0]
            facts = [f for f in effect_facts(obs['literal']) if f['kind'] == 'evasion_accuracy_spell_cost_tooltip_observation']
            self.assertEqual(len(facts), 1)
            for key, value in obs.items():
                if key not in ('literal', 'text_sha256', 'recognized_effect_facts'):
                    self.assertEqual(facts[0][key], value)

    def test_changed_values_targets_and_duration_fail_closed(self):
        for row in self.rows():
            literal = row['observations'][0]['literal']
            for changed in (literal + ' Only outdoors.', literal.replace('2%', '3%').replace('20%', '21%'), literal.replace('allies', 'enemies').replace('opponent', 'ally'), literal.replace('dodge', 'block').replace('45 sec.', '60 sec.')):
                self.assertFalse(any(f['kind'] == 'evasion_accuracy_spell_cost_tooltip_observation' for f in effect_facts(changed)))
