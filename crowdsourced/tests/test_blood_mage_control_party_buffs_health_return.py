import unittest
from archive_extract import effect_facts


CASES = {'Constricts the movement of your opponent, rooting them in place for 45 seconds. Has a 60% chance to break on hit.': {'effect_reported': 'root_with_break_chance',
                                                                                                                       'recipient_reported': 'your '
                                                                                                                                             'opponent',
                                                                                                                       'duration_seconds': 45,
                                                                                                                       'break_on_hit_percent': 60,
                                                                                                                       'break_roll_rules': None,
                                                                                                                       'tick_interval_seconds': None,
                                                                                                                       'stacking_rules': None,
                                                                                                                       'operative_values': None,
                                                                                                                       'historical_authentication': None},
 "Grafts blood and flesh onto your defensive target's party, granting them an additional 290 health for 1 hour.": {'effect_reported': 'party_health_buff',
                                                                                                                   'recipient_reported': 'your '
                                                                                                                                         'defensive '
                                                                                                                                         "target's "
                                                                                                                                         'party',
                                                                                                                   'health_increase': 290,
                                                                                                                   'duration_seconds': 3600,
                                                                                                                   'tick_interval_seconds': None,
                                                                                                                   'stacking_rules': None,
                                                                                                                   'operative_values': None,
                                                                                                                   'historical_authentication': None},
 'Infuses 785 health into your defensive target. Heals for an extra 2% per level of Blood Union.': {'effect_reported': 'target_heal_blood_union_scaling',
                                                                                                    'recipient_reported': 'your '
                                                                                                                          'defensive '
                                                                                                                          'target',
                                                                                                    'health_amount': 785,
                                                                                                    'extra_healing_percent_per_blood_union_level': 2,
                                                                                                    'scaling_base': None,
                                                                                                    'duration_seconds': None,
                                                                                                    'tick_interval_seconds': None,
                                                                                                    'stacking_rules': None,
                                                                                                    'operative_values': None,
                                                                                                    'historical_authentication': None},
 "Augments the skin of your defensive target's party, granting them 51 constitution and 145 physical resistance.": {'effect_reported': 'party_constitution_resistance_buff',
                                                                                                                    'recipient_reported': 'your '
                                                                                                                                          'defensive '
                                                                                                                                          "target's "
                                                                                                                                          'party',
                                                                                                                    'constitution_increase': 51,
                                                                                                                    'physical_resistance_increase': 145,
                                                                                                                    'duration_seconds': None,
                                                                                                                    'tick_interval_seconds': None,
                                                                                                                    'stacking_rules': None,
                                                                                                                    'operative_values': None,
                                                                                                                    'historical_authentication': None},
 'Steals 392 to 414 health from your opponent and returns 100% of it to allies within 10m of the caster. Increases the returned portion by 10% per level of Blood Union. Increases Blood Union by 2.': {'effect_reported': 'area_health_steal_return_blood_union_gain',
                                                                                                                                                                                                        'recipient_reported': 'allies '
                                                                                                                                                                                                                              'within '
                                                                                                                                                                                                                              '10m '
                                                                                                                                                                                                                              'of '
                                                                                                                                                                                                                              'the '
                                                                                                                                                                                                                              'caster',
                                                                                                                                                                                                        'health_stolen_min': 392,
                                                                                                                                                                                                        'health_stolen_max': 414,
                                                                                                                                                                                                        'health_return_percent': 100,
                                                                                                                                                                                                        'radius_meters': 10,
                                                                                                                                                                                                        'returned_portion_increase_percent_per_blood_union_level': 10,
                                                                                                                                                                                                        'blood_union_increase': 2,
                                                                                                                                                                                                        'return_scaling_base': None,
                                                                                                                                                                                                        'distribution_rule': None,
                                                                                                                                                                                                        'duration_seconds': None,
                                                                                                                                                                                                        'tick_interval_seconds': None,
                                                                                                                                                                                                        'stacking_rules': None,
                                                                                                                                                                                                        'operative_values': None,
                                                                                                                                                                                                        'historical_authentication': None}}


class BloodMageControlPartyBuffsHealthReturnTests(unittest.TestCase):
    def test_reviewed_observations_preserve_unknowns(self):
        for literal, expected in CASES.items():
            with self.subTest(literal=literal):
                fact, = [f for f in effect_facts(literal)
                         if f['kind'] == 'blood_mage_control_party_buffs_health_return_observation']
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
                    self.assertFalse(any(f['kind'] == 'blood_mage_control_party_buffs_health_return_observation'
                                         for f in effect_facts(changed)))
