import re
import unittest
from archive_extract import effect_facts

CASES = {'Forms a strong union with your opponent, dealing 291 to 309 damage over 24 sec. Increases Blood Union by 2.': {'effect_reported': 'periodic_damage_with_blood_union_gain',
                                                                                                                 'damage_min': 291,
                                                                                                                 'damage_max': 309,
                                                                                                                 'duration_seconds': 24,
                                                                                                                 'blood_union_gain_points': 2,
                                                                                                                 'damage_school': None,
                                                                                                                 'tick_interval_seconds': None,
                                                                                                                 'stacking_rules': None,
                                                                                                                 'operative_values': None,
                                                                                                                 'historical_authentication': None},
 'Steals 120 to 130 health from your opponent and returns 130% of it to your defensive target. Increases the returned portion by 10% per level of Blood Union. Increases your Blood Union by 1.': {'effect_reported': 'health_steal_and_return',
                                                                                                                                                                                                   'health_stolen_min': 120,
                                                                                                                                                                                                   'health_stolen_max': 130,
                                                                                                                                                                                                   'return_percent': 130,
                                                                                                                                                                                                   'recipient_reported': 'your '
                                                                                                                                                                                                                         'defensive '
                                                                                                                                                                                                                         'target',
                                                                                                                                                                                                   'returned_portion_bonus_percent_per_blood_union_level': 10,
                                                                                                                                                                                                   'blood_union_gain_points': 1,
                                                                                                                                                                                                   'bonus_basis': None,
                                                                                                                                                                                                   'duration_seconds': None,
                                                                                                                                                                                                   'tick_interval_seconds': None,
                                                                                                                                                                                                   'stacking_rules': None,
                                                                                                                                                                                                   'operative_values': None,
                                                                                                                                                                                                   'historical_authentication': None},
 'Steals 218 to 232 health from your opponent and returns 100% of it to allies within 10m of the caster. Increases the returned portion by 10% per level of Blood Union. Increases Blood Union by 2.': {'effect_reported': 'health_steal_and_return',
                                                                                                                                                                                                        'health_stolen_min': 218,
                                                                                                                                                                                                        'health_stolen_max': 232,
                                                                                                                                                                                                        'return_percent': 100,
                                                                                                                                                                                                        'recipient_reported': 'allies '
                                                                                                                                                                                                                              'within '
                                                                                                                                                                                                                              '10m '
                                                                                                                                                                                                                              'of '
                                                                                                                                                                                                                              'the '
                                                                                                                                                                                                                              'caster',
                                                                                                                                                                                                        'recipient_radius_meters': 10,
                                                                                                                                                                                                        'returned_portion_bonus_percent_per_blood_union_level': 10,
                                                                                                                                                                                                        'blood_union_gain_points': 2,
                                                                                                                                                                                                        'bonus_basis': None,
                                                                                                                                                                                                        'duration_seconds': None,
                                                                                                                                                                                                        'tick_interval_seconds': None,
                                                                                                                                                                                                        'stacking_rules': None,
                                                                                                                                                                                                        'operative_values': None,
                                                                                                                                                                                                        'historical_authentication': None},
 'This ritual heals an ally, other than yourself, for 1224 health over 20 seconds. Reduces Blood Union by 3. Only usable from Blood Union 3 or greater.': {'effect_reported': 'periodic_healing_with_blood_union_cost',
                                                                                                                                                           'health_amount': 1224,
                                                                                                                                                           'duration_seconds': 20,
                                                                                                                                                           'recipient_reported': 'an '
                                                                                                                                                                                 'ally, '
                                                                                                                                                                                 'other '
                                                                                                                                                                                 'than '
                                                                                                                                                                                 'yourself',
                                                                                                                                                           'blood_union_reduction_points': 3,
                                                                                                                                                           'minimum_blood_union_reported': 3,
                                                                                                                                                           'tick_interval_seconds': None,
                                                                                                                                                           'stacking_rules': None,
                                                                                                                                                           'operative_values': None,
                                                                                                                                                           'historical_authentication': None},
 'Causes your blood to rise to the surface of your skin so that you may take a vial of it. This process is painful and dangerous, lowering your health by 25%.': {'effect_reported': 'health_loss_for_blood_vial',
                                                                                                                                                                  'health_loss_percent': 25,
                                                                                                                                                                  'health_loss_basis': None,
                                                                                                                                                                  'vial_quantity': None,
                                                                                                                                                                  'duration_seconds': None,
                                                                                                                                                                  'tick_interval_seconds': None,
                                                                                                                                                                  'stacking_rules': None,
                                                                                                                                                                  'operative_values': None,
                                                                                                                                                                  'historical_authentication': None}}

class BloodMageTransferObservations(unittest.TestCase):
    def test_source_values_and_unknowns(self):
        for literal, expected in CASES.items():
            with self.subTest(literal=literal):
                fact, = [f for f in effect_facts(literal) if f['kind'] == 'blood_mage_transfer_ritual_observation']
                for key, value in expected.items():
                    self.assertEqual(fact[key], value)
                self.assertTrue(fact['conditions_unparsed'])

    def test_altered_conditions_and_numbers_are_withheld(self):
        for literal in CASES:
            altered_number = re.sub(r'\d+', lambda m: str(int(m[0])+1), literal)
            for changed in (literal+' Only while resting.', altered_number):
                self.assertNotEqual(changed, literal)
                self.assertFalse(any(f['kind'] == 'blood_mage_transfer_ritual_observation' for f in effect_facts(changed)))
