import unittest
from archive_extract import effect_facts


CASES = {'Covers you in a husk of energy, absorbing all incoming damage for 6 seconds. Consumes a vial of blood.': {'effect_reported': 'incoming_damage_absorption',
                                                                                                            'recipient_reported': 'you',
                                                                                                            'damage_scope_reported': 'all '
                                                                                                                                     'incoming '
                                                                                                                                     'damage',
                                                                                                            'duration_seconds': 6,
                                                                                                            'consumed_component_reported': 'vial '
                                                                                                                                           'of '
                                                                                                                                           'blood',
                                                                                                            'canonical_component_id': None,
                                                                                                            'absorption_limit': None,
                                                                                                            'tick_interval_seconds': None,
                                                                                                            'stacking_rules': None,
                                                                                                            'operative_values': None,
                                                                                                            'historical_authentication': None},
 'Releases a burst of life, healing all allies within 10m by 533. Heals for an extra 2% per level of Blood Union.': {'effect_reported': 'area_healing_with_blood_union_bonus',
                                                                                                                     'recipient_reported': 'all '
                                                                                                                                           'allies '
                                                                                                                                           'within '
                                                                                                                                           '10m',
                                                                                                                     'radius_meters': 10,
                                                                                                                     'health_amount': 533,
                                                                                                                     'healing_bonus_percent_per_blood_union_level': 2,
                                                                                                                     'bonus_basis': None,
                                                                                                                     'duration_seconds': None,
                                                                                                                     'tick_interval_seconds': None,
                                                                                                                     'stacking_rules': None,
                                                                                                                     'operative_values': None,
                                                                                                                     'historical_authentication': None},
 'Bonds you with a single ally, allowing you to split incoming damage amongst each other. The ally who is hit takes 85% of the incoming damage; you take 125% of the remaining damage. Only 1 Pact may be active at a time.': {'effect_reported': 'incoming_damage_sharing',
                                                                                                                                                                                                                               'recipient_reported': 'a '
                                                                                                                                                                                                                                                     'single '
                                                                                                                                                                                                                                                     'ally',
                                                                                                                                                                                                                               'hit_ally_damage_percent': 85,
                                                                                                                                                                                                                               'caster_percent_of_remaining_damage': 125,
                                                                                                                                                                                                                               'maximum_active_pacts': 1,
                                                                                                                                                                                                                               'rounding_rules': None,
                                                                                                                                                                                                                               'damage_transfer_order': None,
                                                                                                                                                                                                                               'duration_seconds': None,
                                                                                                                                                                                                                               'tick_interval_seconds': None,
                                                                                                                                                                                                                               'stacking_rules': None,
                                                                                                                                                                                                                               'operative_values': None,
                                                                                                                                                                                                                               'historical_authentication': None},
 'Severs all pacts you have made that link you to other allies. Ends all Blood Pacts within 500m of you; ends all Scarring Pacts within 500m of you.': {'effect_reported': 'pact_removal',
                                                                                                                                                        'pact_types_reported': ['Blood '
                                                                                                                                                                                'Pacts',
                                                                                                                                                                                'Scarring '
                                                                                                                                                                                'Pacts'],
                                                                                                                                                        'radius_meters': 500,
                                                                                                                                                        'recipient_reported': 'all '
                                                                                                                                                                              'pacts '
                                                                                                                                                                              'you '
                                                                                                                                                                              'have '
                                                                                                                                                                              'made '
                                                                                                                                                                              'that '
                                                                                                                                                                              'link '
                                                                                                                                                                              'you '
                                                                                                                                                                              'to '
                                                                                                                                                                              'other '
                                                                                                                                                                              'allies',
                                                                                                                                                        'canonical_ability_ids': None,
                                                                                                                                                        'duration_seconds': None,
                                                                                                                                                        'tick_interval_seconds': None,
                                                                                                                                                        'stacking_rules': None,
                                                                                                                                                        'operative_values': None,
                                                                                                                                                        'historical_authentication': None},
 'Infuses 545 health into your defensive target. Heals for an extra 2% per level of Blood Union.': {'effect_reported': 'healing_with_blood_union_bonus',
                                                                                                    'recipient_reported': 'your '
                                                                                                                          'defensive '
                                                                                                                          'target',
                                                                                                    'health_amount': 545,
                                                                                                    'healing_bonus_percent_per_blood_union_level': 2,
                                                                                                    'bonus_basis': None,
                                                                                                    'duration_seconds': None,
                                                                                                    'tick_interval_seconds': None,
                                                                                                    'stacking_rules': None,
                                                                                                    'operative_values': None,
                                                                                                    'historical_authentication': None}}


class BloodMageAbsorptionSharingHealingTests(unittest.TestCase):
    def test_reviewed_observations_preserve_unknowns(self):
        for literal, expected in CASES.items():
            with self.subTest(literal=literal):
                fact, = [f for f in effect_facts(literal)
                         if f['kind'] == 'blood_mage_absorption_sharing_healing_observation']
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
                    self.assertFalse(any(f['kind'] == 'blood_mage_absorption_sharing_healing_observation'
                                         for f in effect_facts(changed)))
