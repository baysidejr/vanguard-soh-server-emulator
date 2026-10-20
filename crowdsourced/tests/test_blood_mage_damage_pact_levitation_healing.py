import unittest
from archive_extract import effect_facts


CASES = {'Bonds you with your allies, allowing you to split incoming damage amongst each other. The ally who is hit takes 70% of the incoming damage; the rest of the group splits 200% of the remaining damage.': {'effect_reported': 'group_incoming_damage_sharing',
                                                                                                                                                                                                            'hit_ally_damage_percent': 70,
                                                                                                                                                                                                            'group_percent_of_remaining_damage': 200,
                                                                                                                                                                                                            'group_distribution_rule': None,
                                                                                                                                                                                                            'rounding_rules': None,
                                                                                                                                                                                                            'damage_transfer_order': None,
                                                                                                                                                                                                            'duration_seconds': None,
                                                                                                                                                                                                            'tick_interval_seconds': None,
                                                                                                                                                                                                            'stacking_rules': None,
                                                                                                                                                                                                            'operative_values': None,
                                                                                                                                                                                                            'historical_authentication': None},
 'Causes the flesh of your opponent to split and tear, dealing 557 to 588 damage. Increases Blood Union by 3.': {'effect_reported': 'damage_blood_union_gain',
                                                                                                                 'recipient_reported': 'your '
                                                                                                                                       'opponent',
                                                                                                                 'damage_min': 557,
                                                                                                                 'damage_max': 588,
                                                                                                                 'blood_union_increase': 3,
                                                                                                                 'damage_type': None,
                                                                                                                 'duration_seconds': None,
                                                                                                                 'tick_interval_seconds': None,
                                                                                                                 'stacking_rules': None,
                                                                                                                 'operative_values': None,
                                                                                                                 'historical_authentication': None},
 'Attaches a hollow symbiote to a targets group, allowing them to float off of the ground for 1 hour. Expends 1 Hollow Symbiote. Only 1 Symbiote allowed on a target at a time.': {'effect_reported': 'group_levitation_symbiote',
                                                                                                                                                                                   'recipient_reported': 'a '
                                                                                                                                                                                                         'targets '
                                                                                                                                                                                                         'group',
                                                                                                                                                                                   'duration_seconds': 3600,
                                                                                                                                                                                   'consumed_component_reported': 'Hollow '
                                                                                                                                                                                                                  'Symbiote',
                                                                                                                                                                                   'component_quantity': 1,
                                                                                                                                                                                   'maximum_symbiotes_per_target': 1,
                                                                                                                                                                                   'canonical_component_id': None,
                                                                                                                                                                                   'tick_interval_seconds': None,
                                                                                                                                                                                   'stacking_rules': None,
                                                                                                                                                                                   'operative_values': None,
                                                                                                                                                                                   'historical_authentication': None},
 'Releases a burst of life, healing all allies within 10m by 791. Heals for an extra 2% per level of Blood Union.': {'effect_reported': 'area_healing_with_blood_union_bonus',
                                                                                                                     'recipient_reported': 'all '
                                                                                                                                           'allies '
                                                                                                                                           'within '
                                                                                                                                           '10m',
                                                                                                                     'radius_meters': 10,
                                                                                                                     'health_amount': 791,
                                                                                                                     'healing_bonus_percent_per_blood_union_level': 2,
                                                                                                                     'bonus_basis': None,
                                                                                                                     'duration_seconds': None,
                                                                                                                     'tick_interval_seconds': None,
                                                                                                                     'stacking_rules': None,
                                                                                                                     'operative_values': None,
                                                                                                                     'historical_authentication': None},
 'Heals for 635 health over 16 seconds.': {'effect_reported': 'periodic_healing',
                                           'health_amount_total': 635,
                                           'duration_seconds': 16,
                                           'healing_per_tick': None,
                                           'recipient_reported': None,
                                           'tick_interval_seconds': None,
                                           'stacking_rules': None,
                                           'operative_values': None,
                                           'historical_authentication': None}}


class BloodMageDamagePactLevitationHealingTests(unittest.TestCase):
    def test_reviewed_observations_preserve_unknowns(self):
        for literal, expected in CASES.items():
            with self.subTest(literal=literal):
                fact, = [f for f in effect_facts(literal)
                         if f['kind'] == 'blood_mage_damage_pact_levitation_healing_observation']
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
                    self.assertFalse(any(f['kind'] == 'blood_mage_damage_pact_levitation_healing_observation'
                                         for f in effect_facts(changed)))
