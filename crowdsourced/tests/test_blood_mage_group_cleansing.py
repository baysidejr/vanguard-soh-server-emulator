import unittest
from archive_extract import effect_facts


CASES = {'Fills your targets group with power.\r\n+14 Constitution\r\n+7 Vitality\r\n+16 Intelligence\r\n+11 Wisdom\r\n+150 Hit Points\r\n+2 Hit Point Regeneration\r\n+40 Physical Resistance': {'effect_reported': 'group_attribute_buff',
                                                                                                                                                                                          'recipient_reported': 'your '
                                                                                                                                                                                                                'targets '
                                                                                                                                                                                                                'group',
                                                                                                                                                                                          'constitution_bonus': 14,
                                                                                                                                                                                          'vitality_bonus': 7,
                                                                                                                                                                                          'intelligence_bonus': 16,
                                                                                                                                                                                          'wisdom_bonus': 11,
                                                                                                                                                                                          'hit_points_bonus': 150,
                                                                                                                                                                                          'hit_point_regeneration_bonus': 2,
                                                                                                                                                                                          'physical_resistance_bonus': 40,
                                                                                                                                                                                          'regeneration_time_basis': None,
                                                                                                                                                                                          'duration_seconds': None,
                                                                                                                                                                                          'tick_interval_seconds': None,
                                                                                                                                                                                          'stacking_rules': None,
                                                                                                                                                                                          'operative_values': None,
                                                                                                                                                                                          'historical_authentication': None},
 'Fills your targets group with power.\r\n+28 Constitution\r\n+14 Vitality\r\n+32 Intelligence\r\n+22 Wisdom\r\n+300 Hit Points\r\n+3 Hit Point Regeneration\r\n+80 Physical Resistance': {'effect_reported': 'group_attribute_buff',
                                                                                                                                                                                           'recipient_reported': 'your '
                                                                                                                                                                                                                 'targets '
                                                                                                                                                                                                                 'group',
                                                                                                                                                                                           'constitution_bonus': 28,
                                                                                                                                                                                           'vitality_bonus': 14,
                                                                                                                                                                                           'intelligence_bonus': 32,
                                                                                                                                                                                           'wisdom_bonus': 22,
                                                                                                                                                                                           'hit_points_bonus': 300,
                                                                                                                                                                                           'hit_point_regeneration_bonus': 3,
                                                                                                                                                                                           'physical_resistance_bonus': 80,
                                                                                                                                                                                           'regeneration_time_basis': None,
                                                                                                                                                                                           'duration_seconds': None,
                                                                                                                                                                                           'tick_interval_seconds': None,
                                                                                                                                                                                           'stacking_rules': None,
                                                                                                                                                                                           'operative_values': None,
                                                                                                                                                                                           'historical_authentication': None},
 'Diffuses incoming light making you invisible. Lasts 5 minutes, but has a chance to break early.': {'effect_reported': 'invisibility_with_early_break_chance',
                                                                                                     'duration_seconds': 300,
                                                                                                     'early_break_probability': None,
                                                                                                     'early_break_triggers': None,
                                                                                                     'tick_interval_seconds': None,
                                                                                                     'stacking_rules': None,
                                                                                                     'operative_values': None,
                                                                                                     'historical_authentication': None},
 'You use your blood to heal an ally, other than yourself, for 914. Heals for an extra 2% per level of Blood Union.': {'effect_reported': 'healing_with_blood_union_bonus',
                                                                                                                       'health_amount': 914,
                                                                                                                       'recipient_reported': 'an '
                                                                                                                                             'ally, '
                                                                                                                                             'other '
                                                                                                                                             'than '
                                                                                                                                             'yourself',
                                                                                                                       'healing_bonus_percent_per_blood_union_level': 2,
                                                                                                                       'bonus_basis': None,
                                                                                                                       'health_cost': None,
                                                                                                                       'duration_seconds': None,
                                                                                                                       'tick_interval_seconds': None,
                                                                                                                       'stacking_rules': None,
                                                                                                                       'operative_values': None,
                                                                                                                       'historical_authentication': None},
 'Attaches a leech to an ally, removing 8 poison and disease counters every 2 seconds for 10 seconds. Expends 1 Cleansing Leech.': {'effect_reported': 'periodic_poison_disease_counter_removal',
                                                                                                                                    'counters_removed_reported': 8,
                                                                                                                                    'counter_types_reported': ['poison',
                                                                                                                                                               'disease'],
                                                                                                                                    'tick_interval_seconds': 2,
                                                                                                                                    'duration_seconds': 10,
                                                                                                                                    'consumed_component_reported': 'Cleansing '
                                                                                                                                                                   'Leech',
                                                                                                                                    'consumed_component_quantity': 1,
                                                                                                                                    'counters_shared_or_per_type': None,
                                                                                                                                    'total_counters_removed': None,
                                                                                                                                    'canonical_component_id': None,
                                                                                                                                    'stacking_rules': None,
                                                                                                                                    'operative_values': None,
                                                                                                                                    'historical_authentication': None}}


class BloodMageGroupCleansingTests(unittest.TestCase):
    def test_reviewed_observations_preserve_unknowns(self):
        for literal, expected in CASES.items():
            with self.subTest(literal=literal):
                fact, = [f for f in effect_facts(literal)
                         if f['kind'] == 'blood_mage_group_cleansing_observation']
                for key, value in expected.items():
                    self.assertEqual(fact[key], value)
                self.assertTrue(fact['conditions_unparsed'])
                self.assertEqual(fact['effect_phrase_recorded'], literal)

    def test_changed_quantities_or_scope_are_withheld(self):
        for literal in CASES:
            for changed in (literal + ' Except against undead.',
                            literal.replace('group', 'raid').replace('5 minutes', '6 minutes')
                            .replace('914', '915').replace('8 poison', '9 poison')):
                with self.subTest(changed=changed):
                    self.assertNotEqual(changed, literal)
                    self.assertFalse(any(f['kind'] == 'blood_mage_group_cleansing_observation'
                                         for f in effect_facts(changed)))
