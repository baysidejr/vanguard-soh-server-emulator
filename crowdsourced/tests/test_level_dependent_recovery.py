import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class LevelDependentRecoveryTests(unittest.TestCase):
    def reviewed(self):
        return json.loads(Path('reviewed/BARD_PERIODIC_RECOVERY_SOURCE_REVIEW_ITERATION643.json').read_text())['rows']

    def test_reviewed_observations_preserve_level_dependency_and_unknowns(self):
        for row in self.reviewed():
            obs = row['observations'][0]
            facts = [f for f in effect_facts(obs['literal'])
                     if f['kind'] == 'level_dependent_periodic_recovery_tooltip_observation']
            self.assertEqual(len(facts), 1)
            for key, value in obs.items():
                if key not in ('literal', 'text_sha256', 'recognized_effect_facts'):
                    self.assertEqual(facts[0][key], value)

    def test_unreviewed_values_targets_and_conditions_fail_closed(self):
        for row in self.reviewed():
            literal = row['observations'][0]['literal']
            for changed in (literal + ' Only outdoors.', literal.replace('your', 'their'),
                            literal.replace('4 seconds', '5 seconds'),
                            literal.replace('4/sec', '5/sec'),
                            literal.replace('depending on your level, ', ''),
                            literal.replace('7-9', '8-10').replace('6 energy', '8 energy')):
                self.assertFalse(any(f['kind'] == 'level_dependent_periodic_recovery_tooltip_observation'
                                     for f in effect_facts(changed)))
