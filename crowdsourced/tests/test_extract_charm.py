from test_extract_blasting_bellow import effect_facts
import unittest


class CharmTests(unittest.TestCase):
    def test_reviewed_duration_and_level_pairs(self):
        for duration, level in ((18, 35), (18, 50), (22, 50)):
            literal = (f'Charms your opponent, forcing it to fight for you for {duration} seconds. '
                       f'Effective on targets level {level} and lower.')
            self.assertEqual(effect_facts(literal), [dict(
                kind='charm_duration_target_level_observation',
                charm_duration_seconds_recorded=duration,
                maximum_target_level_recorded=level, target_recorded='opponent',
                resist_check=None, break_conditions=None,
                player_target_applicability=None, stacking=None,
                conditions_unparsed=True)])

    def test_unreviewed_conditions_and_invalid_values_withheld(self):
        literal = ('Charms your opponent, forcing it to fight for you for 18 seconds. '
                   'Effective on targets level 35 and lower.')
        for altered in (literal + ' Breaks on damage.',
                        literal.replace('18 seconds', '0 seconds'),
                        literal.replace('level 35', 'level 0'),
                        literal.replace('and lower', 'and higher'),
                        literal.replace('18 seconds', 'up to 18 seconds'),
                        literal.replace('opponent', 'player')):
            self.assertEqual(effect_facts(altered), [])
