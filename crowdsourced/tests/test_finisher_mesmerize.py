import unittest
from archive_extract import effect_facts


class FinisherMesmerizeTests(unittest.TestCase):
    def test_reviewed_observations_keep_unknown_mechanics(self):
        damage = effect_facts('Deals 400% of normal damage. This ability is only available when a target is below 20% health.')
        fact = next(f for f in damage if f['kind'] == 'normal_damage_health_availability_tooltip_observation')
        self.assertEqual(fact['damage_percent_of_normal_recorded'], 400)
        self.assertEqual(fact['availability_condition_recorded']['comparison'], 'strictly_less_than')
        self.assertEqual(fact['availability_condition_recorded']['target_health_percent'], 20)
        for key in ('normal_damage_definition', 'damage_type', 'health_denominator', 'condition_evaluation_timing', 'operative_values'):
            self.assertIsNone(fact[key])
        fact = next(f for f in effect_facts('Single target mesmerize (28 sec)') if f['kind'] == 'single_target_mesmerize_tooltip_observation')
        self.assertEqual(fact['duration_recorded'], dict(amount=28, unit_literal='sec'))
        self.assertEqual(fact['target_phrase_recorded'], 'Single target')
        self.assertIsNone(fact['mesmerize_break_conditions'])
        self.assertIsNone(fact['immunity_rules'])
        self.assertIsNone(fact['operative_values'])

    def test_unreviewed_variants_do_not_receive_reviewed_facts(self):
        variants = ['Deals 400% of normal damage. This ability is only available when a target is at or below 20% health.',
                    'Deals 400% of normal damage.', 'Single target mesmerize (28)',
                    'Single target mesmerize (28 sec) unless immune']
        kinds = {'normal_damage_health_availability_tooltip_observation', 'single_target_mesmerize_tooltip_observation'}
        for literal in variants:
            with self.subTest(literal=literal):
                self.assertFalse(kinds.intersection(f['kind'] for f in effect_facts(literal)))
