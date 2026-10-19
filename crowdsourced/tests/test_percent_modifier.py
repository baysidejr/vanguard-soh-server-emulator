import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class PercentModifierTests(unittest.TestCase):
    def reviewed(self):
        return json.loads(Path('reviewed/BARD_PERCENT_MODIFIER_SOURCE_REVIEW_ITERATION646.json').read_text())['rows']

    def test_reviewed_modifiers_and_unknowns(self):
        for row in self.reviewed():
            obs = row['observations'][0]
            facts = [f for f in effect_facts(obs['literal'])
                     if f['kind'] == 'percent_modifier_tooltip_observation']
            self.assertEqual(len(facts), 1)
            for key, value in obs.items():
                if key not in ('literal', 'text_sha256', 'recognized_effect_facts'):
                    self.assertEqual(facts[0][key], value)

    def test_unreviewed_percentages_targets_and_restrictions_fail_closed(self):
        for row in self.reviewed():
            literal = row['observations'][0]['literal']
            for changed in (literal + ' Only outdoors.', literal.replace('3%', '4%').replace('15%', '16%'),
                            literal.replace('spell', 'melee').replace('opponent', 'ally'),
                            literal.split('. ')[0] + '.'):
                self.assertFalse(any(f['kind'] == 'percent_modifier_tooltip_observation'
                                     for f in effect_facts(changed)))
