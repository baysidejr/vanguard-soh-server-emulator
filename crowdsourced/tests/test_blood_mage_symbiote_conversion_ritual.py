import unittest
from archive_extract import effect_facts


CASES = {'Attaches a symbiote to an ally, cleansing their body of poison and disease over 15 minutes. Energy Cost: 1 Cleansing Symbiote Cast Time: 1.0 Refresh: None Range: 25 Controlling Symbiote': {'effect_reported': 'poison_disease_cleansing',
                                                                                                                                                                                               'recipient_reported': 'an '
                                                                                                                                                                                                                     'ally',
                                                                                                                                                                                               'duration_minutes_reported': 15,
                                                                                                                                                                                               'cleansing_frequency': None,
                                                                                                                                                                                               'conditions_removed_per_tick': None,
                                                                                                                                                                                               'component_quantity': None,
                                                                                                                                                                                               'cast_time_seconds': None,
                                                                                                                                                                                               'range_meters': None,
                                                                                                                                                                                               'source_anomaly': 'Effect '
                                                                                                                                                                                                                 'block '
                                                                                                                                                                                                                 'includes '
                                                                                                                                                                                                                 'Energy '
                                                                                                                                                                                                                 'Cost, '
                                                                                                                                                                                                                 'Cast '
                                                                                                                                                                                                                 'Time, '
                                                                                                                                                                                                                 'Refresh, '
                                                                                                                                                                                                                 'Range '
                                                                                                                                                                                                                 'and '
                                                                                                                                                                                                                 'trailing '
                                                                                                                                                                                                                 'Controlling '
                                                                                                                                                                                                                 'Symbiote '
                                                                                                                                                                                                                 'labels; '
                                                                                                                                                                                                                 'those '
                                                                                                                                                                                                                 'values '
                                                                                                                                                                                                                 'are '
                                                                                                                                                                                                                 'withheld '
                                                                                                                                                                                                                 'pending '
                                                                                                                                                                                                                 'structural '
                                                                                                                                                                                                                 'review.',
                                                                                                                                                                                               'duration_seconds': None,
                                                                                                                                                                                               'tick_interval_seconds': None,
                                                                                                                                                                                               'stacking_rules': None,
                                                                                                                                                                                               'operative_values': None,
                                                                                                                                                                                               'historical_authentication': None},
 'Transmutes 268 health into 294 energy.': {'effect_reported': 'health_to_energy_conversion',
                                            'health_consumed': 268,
                                            'energy_restored': 294,
                                            'duration_seconds': None,
                                            'tick_interval_seconds': None,
                                            'stacking_rules': None,
                                            'operative_values': None,
                                            'historical_authentication': None},
 'Attaches a plated symbiote to an ally, transforming their skin into spiky plates that return 29 damage upon their attackers and increases armor class by 54 for 1 hour. Expends 1 Plated Symbiote. Only 1 Symbiote allowed on a target at a time.': {'effect_reported': 'retaliatory_damage_armor_buff',
                                                                                                                                                                                                                                                       'recipient_reported': 'an '
                                                                                                                                                                                                                                                                             'ally',
                                                                                                                                                                                                                                                       'returned_damage': 29,
                                                                                                                                                                                                                                                       'armor_class_increase': 54,
                                                                                                                                                                                                                                                       'duration_hours_reported': 1,
                                                                                                                                                                                                                                                       'consumed_component_reported': 'Plated '
                                                                                                                                                                                                                                                                                      'Symbiote',
                                                                                                                                                                                                                                                       'component_quantity': 1,
                                                                                                                                                                                                                                                       'maximum_symbiotes_per_target': 1,
                                                                                                                                                                                                                                                       'canonical_component_id': None,
                                                                                                                                                                                                                                                       'damage_type': None,
                                                                                                                                                                                                                                                       'trigger_frequency': None,
                                                                                                                                                                                                                                                       'duration_seconds': None,
                                                                                                                                                                                                                                                       'tick_interval_seconds': None,
                                                                                                                                                                                                                                                       'stacking_rules': None,
                                                                                                                                                                                                                                                       'operative_values': None,
                                                                                                                                                                                                                                                       'historical_authentication': None},
 'This ritual uses positive energy harnessed from your blood union to heal an ally for 15% of their total life. The amount healed increases for each level of your Blood Union. Removes all Blood Union when used.': {'effect_reported': 'blood_union_healing_ritual',
                                                                                                                                                                                                                      'recipient_reported': 'an '
                                                                                                                                                                                                                                            'ally',
                                                                                                                                                                                                                      'healing_percent_of_total_life': 15,
                                                                                                                                                                                                                      'blood_union_scaling_reported': 'amount '
                                                                                                                                                                                                                                                      'healed '
                                                                                                                                                                                                                                                      'increases '
                                                                                                                                                                                                                                                      'for '
                                                                                                                                                                                                                                                      'each '
                                                                                                                                                                                                                                                      'level',
                                                                                                                                                                                                                      'blood_union_removed_reported': 'all',
                                                                                                                                                                                                                      'scaling_per_level': None,
                                                                                                                                                                                                                      'duration_seconds': None,
                                                                                                                                                                                                                      'tick_interval_seconds': None,
                                                                                                                                                                                                                      'stacking_rules': None,
                                                                                                                                                                                                                      'operative_values': None,
                                                                                                                                                                                                                      'historical_authentication': None},
 'Forms a strong union with your opponent, dealing 423 to 447 damage over 24 sec. Increases Blood Union by 2.': {'effect_reported': 'periodic_damage_blood_union_gain',
                                                                                                                 'recipient_reported': 'your '
                                                                                                                                       'opponent',
                                                                                                                 'damage_min': 423,
                                                                                                                 'damage_max': 447,
                                                                                                                 'duration_seconds': 24,
                                                                                                                 'blood_union_gain': 2,
                                                                                                                 'damage_type': None,
                                                                                                                 'tick_interval_seconds': None,
                                                                                                                 'stacking_rules': None,
                                                                                                                 'operative_values': None,
                                                                                                                 'historical_authentication': None}}


class BloodMageSymbioteConversionRitualTests(unittest.TestCase):
    def test_reviewed_observations_preserve_unknowns(self):
        for literal, expected in CASES.items():
            with self.subTest(literal=literal):
                fact, = [f for f in effect_facts(literal)
                         if f['kind'] == 'blood_mage_symbiote_conversion_ritual_observation']
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
                    self.assertFalse(any(f['kind'] == 'blood_mage_symbiote_conversion_ritual_observation'
                                         for f in effect_facts(changed)))
