import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class SpeedDamageObservationTests(unittest.TestCase):
    def test_reviewed_speed_damage_and_unknown_mechanics(self):
        review = json.loads(Path('reviewed/BARD_NONNUMERIC_SPEED_DAMAGE_SOURCE_REVIEW_ITERATION683.json').read_text())
        for row in review['rows']:
            for observation in row['observations']:
                fact, = effect_facts(observation['literal'])
                self.assertEqual(fact['kind'], 'speed_damage_tooltip_observation')
                for key, value in observation['candidate_observation'].items():
                    self.assertEqual(fact[key], value)
                for key in ('stacking_rules', 'magnitude', 'tick_interval_seconds', 'duration_seconds', 'operative_values'):
                    self.assertIsNone(fact[key])

    def test_changed_scope_and_conditions_withheld(self):
        review = json.loads(Path('reviewed/BARD_NONNUMERIC_SPEED_DAMAGE_SOURCE_REVIEW_ITERATION683.json').read_text())
        for row in review['rows']:
            literal = row['observations'][0]['literal']
            for changed in ('Does not: ' + literal, literal + ' Only outdoors.', literal.replace('movement', 'attack').replace('all attacks', 'melee attacks'), literal.replace('your', 'their').replace('you', 'them')):
                self.assertFalse(any(f['kind'] == 'speed_damage_tooltip_observation' for f in effect_facts(changed)))
