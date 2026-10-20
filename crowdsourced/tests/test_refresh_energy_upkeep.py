import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class RefreshEnergyUpkeepTests(unittest.TestCase):
    def rows(self):
        return json.loads(Path('reviewed/BARD_REFRESH_ENERGY_UPKEEP_SOURCE_REVIEW_ITERATION655.json').read_text())['rows']

    def test_reviewed_observations_preserve_unknowns(self):
        for row in self.rows():
            obs = row['observations'][0]
            facts = [f for f in effect_facts(obs['literal'])
                     if f['kind'] == 'refresh_energy_upkeep_tooltip_observation']
            self.assertEqual(len(facts), 1)
            for key, value in obs.items():
                if key not in ('literal', 'text_sha256', 'recognized_effect_facts'):
                    self.assertEqual(facts[0][key], value)

    def test_changed_values_targets_resources_and_conditions_fail_closed(self):
        for row in self.rows():
            literal = row['observations'][0]['literal']
            for changed in (literal + ' Only outdoors.',
                            literal.replace('8/sec', '9/sec').replace('2/sec', '3/sec'),
                            literal.replace('your group', 'your opponent').replace('allies', 'enemies'),
                            literal.replace('energy', 'health'),
                            literal.replace('20%', '21%').replace('all resistances', 'fire resistance')):
                self.assertFalse(any(f['kind'] == 'refresh_energy_upkeep_tooltip_observation'
                                     for f in effect_facts(changed)))
