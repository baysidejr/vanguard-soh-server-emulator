import unittest

from archive_extract import effect_facts


class GroupMovementTests(unittest.TestCase):
    def test_printed_terminology_and_unknown_mechanics(self):
        for term, percent in [('movement speed', 29), ('movement rate', 3),
                              ('movement rate', 2)]:
            with self.subTest(term=term, percent=percent):
                facts = effect_facts(f'Increases the {term} of your group by {percent}%.')
                self.assertEqual(len(facts), 1)
                fact = facts[0]
                self.assertEqual(fact['kind'], 'group_movement_tooltip_observation')
                self.assertEqual(fact['movement_word_recorded'], term)
                self.assertEqual(fact['increase_percent_recorded'], percent)
                for key in ('stacking', 'scaling', 'base_movement_speed',
                            'percent_interpretation', 'combat_applicability',
                            'duration_seconds', 'operative_values'):
                    self.assertIsNone(fact[key])

    def test_conditional_or_different_target_prose_is_not_simplified(self):
        prefix = 'Increases the movement speed of your group by '
        for value in [prefix+'29% while outdoors.', prefix+'29% unless in combat.',
                      prefix+'0%.', prefix+'-3%.', prefix+'29.',
                      'Increases the movement speed of your target by 29%.']:
            with self.subTest(value=value):
                self.assertFalse(any(f['kind'] == 'group_movement_tooltip_observation'
                                     for f in effect_facts(value)))
