import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class ReviewedReductionTests(unittest.TestCase):
    def rows(self):
        return json.loads(Path('reviewed/BARD_AC_STRENGTH_HEALING_POTENCY_SOURCE_REVIEW_ITERATION652.json').read_text())['rows']

    def test_reviewed_observations_preserve_unknowns(self):
        for row in self.rows():
            obs = row['observations'][0]
            facts = [f for f in effect_facts(obs['literal'])
                     if f['kind'] == 'ac_strength_healing_potency_tooltip_observation']
            self.assertEqual(len(facts), 1)
            for key, value in obs.items():
                if key not in ('literal', 'text_sha256', 'recognized_effect_facts'):
                    self.assertEqual(facts[0][key], value)

    def test_changed_ranges_attributes_targets_and_conditions_fail_closed(self):
        for row in self.rows():
            literal = row['observations'][0]['literal']
            for changed in (literal + ' Only outdoors.',
                            literal.replace('25-95', '25-96').replace('10%', '11%'),
                            literal.replace('opponent', 'ally'),
                            literal.replace('strengthe', 'strength').replace('heals', 'damage')):
                self.assertFalse(any(f['kind'] == 'ac_strength_healing_potency_tooltip_observation'
                                     for f in effect_facts(changed)))
