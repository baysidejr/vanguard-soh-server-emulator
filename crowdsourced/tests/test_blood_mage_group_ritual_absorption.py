import unittest
from archive_extract import effect_facts


CASES = {"Fills your defensive target's party with life, granting them 40 additional vitality.": {'effect_reported': 'party_vitality_buff',
                                                                                          'recipient_reported': 'your '
                                                                                                                'defensive '
                                                                                                                "target's "
                                                                                                                'party',
                                                                                          'vitality_increase': 40,
                                                                                          'duration_seconds': None,
                                                                                          'tick_interval_seconds': None,
                                                                                          'stacking_rules': None,
                                                                                          'operative_values': None,
                                                                                          'historical_authentication': None},
 'Fills your targets group with power.\r\n+56 Constitution\r\n+28 Vitality\r\n+64 Intelligence\r\n+44 Wisdom\r\n+600 Hit Points\r\n+6 Hit Point Regeneration\r\n+160 Physical Resistance\r\nStacks Best Buff Only': {'effect_reported': 'group_stat_buff',
                                                                                                                                                                                                                     'recipient_reported': 'your '
                                                                                                                                                                                                                                           'targets '
                                                                                                                                                                                                                                           'group',
                                                                                                                                                                                                                     'constitution_increase': 56,
                                                                                                                                                                                                                     'vitality_increase': 28,
                                                                                                                                                                                                                     'intelligence_increase': 64,
                                                                                                                                                                                                                     'wisdom_increase': 44,
                                                                                                                                                                                                                     'hit_points_increase': 600,
                                                                                                                                                                                                                     'hit_point_regeneration_increase': 6,
                                                                                                                                                                                                                     'physical_resistance_increase': 160,
                                                                                                                                                                                                                     'regeneration_interval_seconds': None,
                                                                                                                                                                                                                     'stacking_reported': 'Stacks '
                                                                                                                                                                                                                                          'Best '
                                                                                                                                                                                                                                          'Buff '
                                                                                                                                                                                                                                          'Only',
                                                                                                                                                                                                                     'duration_seconds': None,
                                                                                                                                                                                                                     'tick_interval_seconds': None,
                                                                                                                                                                                                                     'stacking_rules': None,
                                                                                                                                                                                                                     'operative_values': None,
                                                                                                                                                                                                                     'historical_authentication': None},
 'This ritual heals an ally, other than yourself, for 2112 health over 20 seconds. Reduces Blood Union by 3. Only usable from Blood Union 3 or greater.': {'effect_reported': 'periodic_ally_heal_blood_union_consumption',
                                                                                                                                                           'recipient_reported': 'an '
                                                                                                                                                                                 'ally, '
                                                                                                                                                                                 'other '
                                                                                                                                                                                 'than '
                                                                                                                                                                                 'yourself',
                                                                                                                                                           'healing_total': 2112,
                                                                                                                                                           'duration_seconds': 20,
                                                                                                                                                           'blood_union_reduction': 3,
                                                                                                                                                           'minimum_blood_union': 3,
                                                                                                                                                           'healing_per_tick': None,
                                                                                                                                                           'tick_interval_seconds': None,
                                                                                                                                                           'stacking_rules': None,
                                                                                                                                                           'operative_values': None,
                                                                                                                                                           'historical_authentication': None},
 'Covers you in a husk of energy, absorbing all incoming damage for 7 seconds. Consumes a vial of blood.': {'effect_reported': 'self_damage_absorption',
                                                                                                            'recipient_reported': 'you',
                                                                                                            'damage_absorption_reported': 'all '
                                                                                                                                          'incoming '
                                                                                                                                          'damage',
                                                                                                            'duration_seconds': 7,
                                                                                                            'consumed_component_reported': 'a '
                                                                                                                                           'vial '
                                                                                                                                           'of '
                                                                                                                                           'blood',
                                                                                                            'component_quantity': None,
                                                                                                            'canonical_component_id': None,
                                                                                                            'absorption_cap': None,
                                                                                                            'tick_interval_seconds': None,
                                                                                                            'stacking_rules': None,
                                                                                                            'operative_values': None,
                                                                                                            'historical_authentication': None},
 'You use your blood to heal an ally, other than yourself, for 1357. Heals for an extra 2% per level of Blood Union.': {'effect_reported': 'ally_heal_blood_union_scaling',
                                                                                                                        'recipient_reported': 'an '
                                                                                                                                              'ally, '
                                                                                                                                              'other '
                                                                                                                                              'than '
                                                                                                                                              'yourself',
                                                                                                                        'healing_base': 1357,
                                                                                                                        'extra_healing_percent_per_blood_union_level': 2,
                                                                                                                        'health_cost': None,
                                                                                                                        'scaling_base': None,
                                                                                                                        'duration_seconds': None,
                                                                                                                        'tick_interval_seconds': None,
                                                                                                                        'stacking_rules': None,
                                                                                                                        'operative_values': None,
                                                                                                                        'historical_authentication': None}}


class BloodMageGroupRitualAbsorptionTests(unittest.TestCase):
    def test_reviewed_observations_preserve_unknowns(self):
        for literal, expected in CASES.items():
            with self.subTest(literal=literal):
                fact, = [f for f in effect_facts(literal)
                         if f['kind'] == 'blood_mage_group_ritual_absorption_observation']
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
                    self.assertFalse(any(f['kind'] == 'blood_mage_group_ritual_absorption_observation'
                                         for f in effect_facts(changed)))
