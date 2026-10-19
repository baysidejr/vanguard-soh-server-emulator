import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class ResistanceDamageShieldTests(unittest.TestCase):
    def test_reviewed_values_and_unknowns(self):
        rows = json.loads(Path('reviewed/BARD_RESISTANCE_DAMAGE_SHIELD_SOURCE_REVIEW_ITERATION640.json').read_text())['rows']
        for row in rows:
            for obs in row['observations']:
                facts = [f for f in effect_facts(obs['literal'])
                         if f['kind'] == 'resistance_damage_shield_tooltip_observation']
                self.assertEqual(len(facts), 1)
                for key, value in obs.items():
                    if key not in ('literal', 'text_sha256', 'recognized_effect_facts'):
                        self.assertEqual(facts[0][key], value)

    def test_unreviewed_conditions_targets_and_values_fail_closed(self):
        rows = json.loads(Path('reviewed/BARD_RESISTANCE_DAMAGE_SHIELD_SOURCE_REVIEW_ITERATION640.json').read_text())['rows']
        for row in rows:
            base = row['observations'][0]['literal']
            for prose in (base + ' Only outdoors.', base.replace('your', 'their'),
                          base.replace('8', '9').replace('2 point', '3 point'),
                          base.replace('cold', 'arcane').replace('fire', 'arcane')):
                self.assertFalse(any(f['kind'] == 'resistance_damage_shield_tooltip_observation'
                                     for f in effect_facts(prose)))
