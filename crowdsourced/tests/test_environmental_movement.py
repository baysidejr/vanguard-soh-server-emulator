import unittest
from archive_extract import effect_facts


class EnvironmentalMovementTests(unittest.TestCase):
    def test_duration_and_upkeep_remain_distinct(self):
        fact, = effect_facts('Whistling this little tune will cause you and your nearby group mates to levitate for 60 minutes.')
        self.assertEqual(fact['duration_minutes_recorded'], 60)
        self.assertIsNone(fact['height'])
        self.assertIsNone(fact['nearby_radius'])
        for prose, action, upkeep in [
            ('Enables your group to breathe underwater. Costs 7/sec energy.', 'breathe underwater', 7),
            ('Levitates your group off of the ground. Costs 6/sec energy.', 'Levitates', 6),
        ]:
            fact, = effect_facts(prose)
            self.assertEqual(fact['action_recorded'], action)
            self.assertEqual(fact['energy_per_second_recorded'], upkeep)
            self.assertNotIn('duration_minutes_recorded', fact)
            self.assertIsNone(fact['upkeep_timing'])
            self.assertIsNone(fact['operative_values'])

    def test_unreviewed_conditions_targets_and_numbers_fail_closed(self):
        base = 'Levitates your group off of the ground. Costs 6/sec energy.'
        for prose in [base + ' Only outdoors.', base.replace('your group', 'you'),
                      base.replace('6/sec', '7/sec'), base.replace('energy', 'health')]:
            self.assertFalse(any(f['kind'] == 'environmental_movement_tooltip_observation'
                                 for f in effect_facts(prose)))
