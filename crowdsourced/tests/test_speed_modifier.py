import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class SpeedModifierTests(unittest.TestCase):
    def test_reviewed_values_and_unknowns(self):
        rows = json.loads(Path('reviewed/BARD_SPEED_MODIFIER_SOURCE_REVIEW_ITERATION637.json').read_text())['rows']
        for row in rows:
            for obs in row['observations']:
                facts = [f for f in effect_facts(obs['literal'])
                         if f['kind'] == 'speed_modifier_tooltip_observation']
                self.assertEqual(len(facts), 1)
                for key, value in obs.items():
                    if key not in ('literal', 'text_sha256', 'recognized_effect_facts'):
                        self.assertEqual(facts[0][key], value)

    def test_unreviewed_conditions_targets_and_values_fail_closed(self):
        rows = json.loads(Path('reviewed/BARD_SPEED_MODIFIER_SOURCE_REVIEW_ITERATION637.json').read_text())['rows']
        for row in rows:
            base = row['observations'][0]['literal']
            for prose in (base + ' Only outdoors.', base.replace('your', 'their'),
                          base.replace('5%', '6%').replace('3%', '4%'),
                          base.replace('speed', 'interval')):
                self.assertFalse(any(f['kind'] == 'speed_modifier_tooltip_observation'
                                     for f in effect_facts(prose)))
