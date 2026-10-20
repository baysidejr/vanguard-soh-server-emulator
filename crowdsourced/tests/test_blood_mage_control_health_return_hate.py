import unittest
from archive_extract import effect_facts


CASES = {'Attaches a controlling symbiote to an opponent forcing them to obey your commands for 30 sec. Repeated symbiote uses will be ignored completely. Draconic, undead, construct and elemental targets are immune to suggestion. Expends 1 Controlling Symbiote. Only 1 Symbiote allowed on a target at a time.': {'effect_reported': 'target_control',
                                                                                                                                                                                                                                                                                                                 'recipient_reported': 'an '
                                                                                                                                                                                                                                                                                                                                       'opponent',
                                                                                                                                                                                                                                                                                                                 'duration_seconds': 30,
                                                                                                                                                                                                                                                                                                                 'repeated_use_reported': 'ignored '
                                                                                                                                                                                                                                                                                                                                          'completely',
                                                                                                                                                                                                                                                                                                                 'immune_target_types_reported': ['draconic',
                                                                                                                                                                                                                                                                                                                                                  'undead',
                                                                                                                                                                                                                                                                                                                                                  'construct',
                                                                                                                                                                                                                                                                                                                                                  'elemental'],
                                                                                                                                                                                                                                                                                                                 'consumed_component_reported': 'Controlling '
                                                                                                                                                                                                                                                                                                                                                'Symbiote',
                                                                                                                                                                                                                                                                                                                 'component_quantity': 1,
                                                                                                                                                                                                                                                                                                                 'maximum_symbiotes_per_target': 1,
                                                                                                                                                                                                                                                                                                                 'canonical_component_id': None,
                                                                                                                                                                                                                                                                                                                 'control_break_rules': None,
                                                                                                                                                                                                                                                                                                                 'tick_interval_seconds': None,
                                                                                                                                                                                                                                                                                                                 'stacking_rules': None,
                                                                                                                                                                                                                                                                                                                 'operative_values': None,
                                                                                                                                                                                                                                                                                                                 'historical_authentication': None},
 'Allows you to gain health equal to 10% of the damage all allies deal within 50m.': {'effect_reported': 'ally_damage_health_gain',
                                                                                      'recipient_reported': 'you',
                                                                                      'health_gain_percent_of_ally_damage': 10,
                                                                                      'radius_meters': 50,
                                                                                      'damage_eligibility': None,
                                                                                      'duration_seconds': None,
                                                                                      'tick_interval_seconds': None,
                                                                                      'stacking_rules': None,
                                                                                      'operative_values': None,
                                                                                      'historical_authentication': None},
 'Steals 303 to 322 health from your opponent and returns 100% of it to allies within 10m of the caster. Increases the returned portion by 10% per level of Blood Union. Increases Blood Union by 2.': {'effect_reported': 'health_steal_area_return',
                                                                                                                                                                                                        'health_steal_min': 303,
                                                                                                                                                                                                        'health_steal_max': 322,
                                                                                                                                                                                                        'returned_health_percent': 100,
                                                                                                                                                                                                        'recipient_reported': 'allies '
                                                                                                                                                                                                                              'within '
                                                                                                                                                                                                                              '10m '
                                                                                                                                                                                                                              'of '
                                                                                                                                                                                                                              'the '
                                                                                                                                                                                                                              'caster',
                                                                                                                                                                                                        'radius_meters': 10,
                                                                                                                                                                                                        'returned_portion_bonus_percent_per_blood_union_level': 10,
                                                                                                                                                                                                        'blood_union_gain': 2,
                                                                                                                                                                                                        'bonus_basis': None,
                                                                                                                                                                                                        'return_allocation': None,
                                                                                                                                                                                                        'duration_seconds': None,
                                                                                                                                                                                                        'tick_interval_seconds': None,
                                                                                                                                                                                                        'stacking_rules': None,
                                                                                                                                                                                                        'operative_values': None,
                                                                                                                                                                                                        'historical_authentication': None},
 'Steals 170 to 182 health from your opponent and returns 130% of it to your defensive target. Increases the returned portion by 10% per level of Blood Union. Increases your Blood Union by 1.': {'effect_reported': 'health_steal_defensive_target_return',
                                                                                                                                                                                                   'health_steal_min': 170,
                                                                                                                                                                                                   'health_steal_max': 182,
                                                                                                                                                                                                   'returned_health_percent': 130,
                                                                                                                                                                                                   'recipient_reported': 'your '
                                                                                                                                                                                                                         'defensive '
                                                                                                                                                                                                                         'target',
                                                                                                                                                                                                   'returned_portion_bonus_percent_per_blood_union_level': 10,
                                                                                                                                                                                                   'blood_union_gain': 1,
                                                                                                                                                                                                   'bonus_basis': None,
                                                                                                                                                                                                   'duration_seconds': None,
                                                                                                                                                                                                   'tick_interval_seconds': None,
                                                                                                                                                                                                   'stacking_rules': None,
                                                                                                                                                                                                   'operative_values': None,
                                                                                                                                                                                                   'historical_authentication': None},
 "Numbs your opponent's mind, lowering your hate by 1914.": {'effect_reported': 'hate_reduction',
                                                             'recipient_reported': 'your opponent',
                                                             'hate_reduction_amount': 1914,
                                                             'hate_unit': None,
                                                             'duration_seconds': None,
                                                             'tick_interval_seconds': None,
                                                             'stacking_rules': None,
                                                             'operative_values': None,
                                                             'historical_authentication': None}}


class BloodMageControlHealthReturnHateTests(unittest.TestCase):
    def test_reviewed_observations_preserve_unknowns(self):
        for literal, expected in CASES.items():
            with self.subTest(literal=literal):
                fact, = [f for f in effect_facts(literal)
                         if f['kind'] == 'blood_mage_control_health_return_hate_observation']
                for key, value in expected.items():
                    self.assertEqual(fact[key], value)
                self.assertTrue(fact['conditions_unparsed'])
                self.assertEqual(fact['effect_phrase_recorded'], literal)

    def test_changed_quantities_or_scope_are_withheld(self):
        for literal in CASES:
            for changed in (literal + ' Except against undead.',
                            __import__('re').sub(r'\d+', lambda match: str(int(match.group())+1), literal, count=1)):
                with self.subTest(changed=changed):
                    self.assertNotEqual(changed, literal)
                    self.assertFalse(any(f['kind'] == 'blood_mage_control_health_return_hate_observation'
                                         for f in effect_facts(changed)))
