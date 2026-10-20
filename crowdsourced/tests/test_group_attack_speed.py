import unittest

from archive_extract import effect_facts


class GroupAttackSpeedTests(unittest.TestCase):
    def test_reviewed_qualifiers_and_range_remain_distinct(self):
        cases = [
            ('Increases the melee attack speed for your gruop by 12%',
             'melee attack speed', 'your gruop', 12, None),
            ('Increases the attack speed of your group by 12%',
             'attack speed', 'your group', 12, None),
            ('This voice melody increases the attack speed of you and your allies by 8 to 10%',
             'attack speed', 'you and your allies', 8, 10),
        ]
        for prose, phrase, target, low, high in cases:
            with self.subTest(prose=prose):
                fact, = effect_facts(prose)
                self.assertEqual(fact['attack_speed_phrase_recorded'], phrase)
                self.assertEqual(fact['target_phrase_recorded'], target)
                self.assertEqual(fact['increase_percent_min_recorded' if high else
                                      'increase_percent_recorded'], low)
                if high:
                    self.assertEqual(fact['increase_percent_max_recorded'], high)
                    self.assertNotIn('increase_percent_recorded', fact)
                for key in ('stacking', 'scaling', 'base_attack_interval',
                            'attack_interval_formula', 'range_dependency',
                            'duration_seconds', 'operative_values'):
                    self.assertIsNone(fact[key])

    def test_unreviewed_conditions_targets_and_values_fail_closed(self):
        base = 'Increases the attack speed of your group by 12%'
        for prose in [base + ' while in combat', base + ' unless stunned',
                      base.replace('your group', 'your enemy'),
                      base.replace('12%', '0%'), base.replace('12%', '24%'),
                      base.replace('attack speed', 'ranged attack speed')]:
            with self.subTest(prose=prose):
                self.assertFalse(any(f['kind'] == 'group_attack_speed_tooltip_observation'
                                     for f in effect_facts(prose)))
