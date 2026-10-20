import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class ReactiveDamageTests(unittest.TestCase):
    def test_reviewed_values_and_unknowns(self):
        rows = json.loads(Path('reviewed/BARD_REACTIVE_DAMAGE_SOURCE_REVIEW_ITERATION622.json').read_text())['rows']
        for row in rows:
            with self.subTest(name=row['name']):
                fact, = effect_facts(row['literal'])
                self.assertEqual(fact['kind'], 'reactive_damage_tooltip_observation')
                for key, value in row['observation'].items():
                    self.assertEqual(fact[key], value)
                for key in ('operative_values', 'attack_eligibility', 'per_hit_behavior',
                            'damage_type', 'trigger_probability', 'mitigation', 'scaling', 'radius'):
                    self.assertIsNone(fact[key])
                self.assertTrue(fact['conditions_unparsed'])

    def test_unreviewed_changes_fail_closed(self):
        base = 'Attacks against you resonate sharply, dealing 15 damage to your attackers.'
        for prose in (base + ' Only outdoors.', base.replace('15', '16'),
                      base.replace('damage', 'physical damage'),
                      base.replace('against you', 'against your group')):
            self.assertFalse(any(f['kind'] == 'reactive_damage_tooltip_observation'
                                 for f in effect_facts(prose)))
