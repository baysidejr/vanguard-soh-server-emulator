from test_extract_blasting_bellow import effect_facts
import unittest


class ExpiatingEchoTests(unittest.TestCase):
    def test_reviewed_compound_observations(self):
        for minimum, maximum in ((144, 153), (210, 222), (282, 298), (336, 355)):
            literal = (f'You shout after a successful parry, dealing {minimum} to {maximum} damage '
                       'and restoring 50 of your endurance. Only usable after you parry.')
            self.assertEqual(effect_facts(literal), [dict(
                kind='parry_damage_endurance_observation',
                damage_minimum_recorded=minimum, damage_maximum_recorded=maximum,
                endurance_restored_recorded=50, prerequisite_recorded='successful parry',
                damage_school=None, damage_target=None, activation_window_seconds=None,
                scaling=None, conditions_unparsed=True)])

    def test_invalid_ranges_and_unreviewed_conditions_withheld(self):
        literal = ('You shout after a successful parry, dealing 144 to 153 damage '
                   'and restoring 50 of your endurance. Only usable after you parry.')
        for altered in (literal.replace('144 to 153', '153 to 144'),
                        literal.replace('144 to 153', '0 to 153'),
                        literal.replace('restoring 50', 'restoring 0'),
                        literal.replace('endurance', 'energy'),
                        literal.replace('parry', 'dodge'),
                        literal + ' Only against undead.',
                        literal.replace('Only usable after you parry.', '')):
            self.assertEqual(effect_facts(altered), [])
