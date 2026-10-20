from test_extract_blasting_bellow import effect_facts
import unittest


class NeedleTests(unittest.TestCase):
    literal = "A fast piercing attack that deals 50% of weapon damage and lowers your opponent's damage by 15 for 30 sec."

    def test_compound_observation_preserves_unknown_units(self):
        self.assertEqual(effect_facts(self.literal), [dict(
            kind='weapon_damage_and_opponent_reduction_observation',
            weapon_damage_percent_recorded=50, opponent_damage_reduction_recorded=15,
            reduction_duration_seconds_recorded=30, damage_reduction_unit=None,
            weapon_damage_basis=None, damage_school=None, target_recorded='opponent',
            stacking=None, conditions_unparsed=True)])

    def test_unreviewed_units_and_conditions_withheld(self):
        for altered in [self.literal.replace('by 15', 'by 15%'),
                        self.literal.replace('30 sec', '0 sec'),
                        self.literal.replace('50%', '0%'),
                        self.literal + ' While singing.',
                        self.literal.replace('weapon damage', 'base weapon damage')]:
            self.assertEqual(effect_facts(altered), [])
