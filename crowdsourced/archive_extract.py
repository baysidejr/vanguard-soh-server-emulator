"""Extract additional explicit facts from cached archive HTML; no network or server writes."""
import re
from bs4 import BeautifulSoup


def text(node):
    return node.get_text(' ', strip=True) if node else ''


def numeric(value):
    value = value.strip().replace(',', '')
    if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value):
        return float(value) if '.' in value else int(value)
    return None


def effect_facts(value):
    """Numeric observations, not a complete combat formula or guessed condition tree."""
    facts = []
    num = r'(\d+(?:\.\d+)?)'
    # Exact Blood Mage literals source-reviewed in iteration708.
    control_party_effect = {'Constricts the movement of your opponent, rooting them in place for 45 seconds. Has a 60% chance to break on hit.': {'effect_reported': 'root_with_break_chance',
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
                                                                                                                                                                                                        'historical_authentication': None}}.get(value.strip())
    if control_party_effect:
        facts.append(dict(kind="blood_mage_control_party_buffs_health_return_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **control_party_effect))
    # Exact Blood Mage literals source-reviewed in iteration706.
    pact_levitation_effect = {'Bonds you with your allies, allowing you to split incoming damage amongst each other. The ally who is hit takes 70% of the incoming damage; the rest of the group splits 200% of the remaining damage.': {'effect_reported': 'group_incoming_damage_sharing',
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
                                           'historical_authentication': None}}.get(value.strip())
    if pact_levitation_effect:
        facts.append(dict(kind="blood_mage_damage_pact_levitation_healing_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **pact_levitation_effect))
    # Exact Blood Mage literals source-reviewed in iteration704.
    group_ritual_effect = {"Fills your defensive target's party with life, granting them 40 additional vitality.": {'effect_reported': 'party_vitality_buff',
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
                                                                                                                        'historical_authentication': None}}.get(value.strip())
    if group_ritual_effect:
        facts.append(dict(kind="blood_mage_group_ritual_absorption_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **group_ritual_effect))
    # Exact Blood Mage literals source-reviewed in iteration702.
    symbiote_effect = {'Attaches a symbiote to an ally, cleansing their body of poison and disease over 15 minutes. Energy Cost: 1 Cleansing Symbiote Cast Time: 1.0 Refresh: None Range: 25 Controlling Symbiote': {'effect_reported': 'poison_disease_cleansing',
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
                                                                                                                 'historical_authentication': None}}.get(value.strip())
    if symbiote_effect:
        facts.append(dict(kind="blood_mage_symbiote_conversion_ritual_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **symbiote_effect))
    # Exact Blood Mage literals source-reviewed in iteration700.
    control_effect = {'Attaches a controlling symbiote to an opponent forcing them to obey your commands for 30 sec. Repeated symbiote uses will be ignored completely. Draconic, undead, construct and elemental targets are immune to suggestion. Expends 1 Controlling Symbiote. Only 1 Symbiote allowed on a target at a time.': {'effect_reported': 'target_control',
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
                                                                 'historical_authentication': None}}.get(value.strip())
    if control_effect:
        facts.append(dict(kind="blood_mage_control_health_return_hate_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **control_effect))
    # Exact Blood Mage literals source-reviewed in iteration698.
    absorption_effect = {'Covers you in a husk of energy, absorbing all incoming damage for 6 seconds. Consumes a vial of blood.': {'effect_reported': 'incoming_damage_absorption',
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
                                                                                                        'historical_authentication': None}}.get(value.strip())
    if absorption_effect:
        facts.append(dict(kind="blood_mage_absorption_sharing_healing_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **absorption_effect))
    # Exact Blood Mage literals source-reviewed in iteration696.
    group_effect = {'Fills your targets group with power.\r\n+14 Constitution\r\n+7 Vitality\r\n+16 Intelligence\r\n+11 Wisdom\r\n+150 Hit Points\r\n+2 Hit Point Regeneration\r\n+40 Physical Resistance': {'effect_reported': 'group_attribute_buff',
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
                                                                                                                                        'historical_authentication': None}}.get(value.strip())
    if group_effect:
        facts.append(dict(kind="blood_mage_group_cleansing_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **group_effect))
    # Exact Blood Mage literals source-reviewed in iteration694.
    transfer_effect = {'Forms a strong union with your opponent, dealing 291 to 309 damage over 24 sec. Increases Blood Union by 2.': {'effect_reported': 'periodic_damage_with_blood_union_gain',
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
                                                                                                                                                                      'historical_authentication': None}}.get(value.strip())
    if transfer_effect:
        facts.append(dict(kind="blood_mage_transfer_ritual_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **transfer_effect))
    # Exact Blood Mage literals source-reviewed in iteration692.
    focus_effect = {'You sufffer a 5% health loss every 5 seconds, but gain one point of Blood Union. All disease and poison counters are also reset on each tick.': {'effect_reported': 'periodic_health_loss_and_blood_union_gain',
                                                                                                                                                       'health_loss_percent': 5,
                                                                                                                                                       'tick_interval_seconds': 5,
                                                                                                                                                       'blood_union_gain_points': 1,
                                                                                                                                                       'counters_reset_reported': ['disease',
                                                                                                                                                                                   'poison'],
                                                                                                                                                       'health_loss_basis': None,
                                                                                                                                                       'duration_seconds': None,
                                                                                                                                                       'stacking_rules': None,
                                                                                                                                                       'operative_values': None,
                                                                                                                                                       'historical_authentication': None},
     'Lifetaps your opponent, draining their hit points, while adding it to yours. You gain a 20% health bonus for each level of Blood Union you have built up.': {'effect_reported': 'lifetap',
                                                                                                                                                                   'recipient_reported': 'you',
                                                                                                                                                                   'drain_target_reported': 'your '
                                                                                                                                                                                            'opponent',
                                                                                                                                                                   'health_bonus_percent_per_blood_union_level': 20,
                                                                                                                                                                   'drain_amount': None,
                                                                                                                                                                   'bonus_basis': None,
                                                                                                                                                                   'duration_seconds': None,
                                                                                                                                                                   'tick_interval_seconds': None,
                                                                                                                                                                   'stacking_rules': None,
                                                                                                                                                                   'operative_values': None,
                                                                                                                                                                   'historical_authentication': None},
     'Your healing spells are increased by 25% effectiveness, your mitigation by 15% and you regain health faster than normal. This comes at the cost of reducing your spell damage by 50%, and reducing the effect of healing spells cast on you by 50%.': {'effect_reported': 'healing_mitigation_damage_tradeoff',
                                                                                                                                                                                                                                                             'healing_spell_effectiveness_increase_percent': 25,
                                                                                                                                                                                                                                                             'mitigation_increase_percent': 15,
                                                                                                                                                                                                                                                             'spell_damage_reduction_percent': 50,
                                                                                                                                                                                                                                                             'incoming_healing_spell_effect_reduction_percent': 50,
                                                                                                                                                                                                                                                             'health_regeneration_increase_amount': None,
                                                                                                                                                                                                                                                             'duration_seconds': None,
                                                                                                                                                                                                                                                             'tick_interval_seconds': None,
                                                                                                                                                                                                                                                             'stacking_rules': None,
                                                                                                                                                                                                                                                             'operative_values': None,
                                                                                                                                                                                                                                                             'historical_authentication': None},
     'Deals instant damage, followed by damage over time. Also increases your Blood Union by 1.': {'effect_reported': 'instant_and_periodic_damage_with_blood_union_gain',
                                                                                                   'blood_union_gain_points': 1,
                                                                                                   'instant_damage_amount': None,
                                                                                                   'periodic_damage_amount': None,
                                                                                                   'duration_seconds': None,
                                                                                                   'tick_interval_seconds': None,
                                                                                                   'stacking_rules': None,
                                                                                                   'operative_values': None,
                                                                                                   'historical_authentication': None},
     'Constricts the movement of your opponent, rooting them in place for 30 seconds. Has a 60% chance to break on hit.': {'effect_reported': 'root',
                                                                                                                           'recipient_reported': 'your '
                                                                                                                                                 'opponent',
                                                                                                                           'duration_seconds': 30,
                                                                                                                           'break_on_hit_chance_percent': 60,
                                                                                                                           'hit_definition': None,
                                                                                                                           'tick_interval_seconds': None,
                                                                                                                           'stacking_rules': None,
                                                                                                                           'operative_values': None,
                                                                                                                           'historical_authentication': None}}.get(value.strip())
    if focus_effect:
        facts.append(dict(kind="blood_mage_focus_lifetap_root_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **focus_effect))
    # Exact Blood Mage literals source-reviewed in iteration690.
    blood_mage = {'Infuses 113 health into your defensive target. Heals for an extra 2% per level of Blood Union.': {'effect_reported': 'healing',
                                                                                                        'recipient_reported': 'your '
                                                                                                                              'defensive '
                                                                                                                              'target',
                                                                                                        'health_amount': 113,
                                                                                                        'blood_union_bonus_percent_per_level': 2,
                                                                                                        'bonus_basis': None,
                                                                                                        'duration_seconds': None,
                                                                                                        'tick_interval_seconds': None,
                                                                                                        'stacking_rules': None,
                                                                                                        'operative_values': None,
                                                                                                        'historical_authentication': None},
     "Grafts blood and flesh onto your defensive target's party, granting them an additional 54 health for 1 hour.": {'effect_reported': 'additional_health',
                                                                                                                      'recipient_reported': 'your '
                                                                                                                                            'defensive '
                                                                                                                                            "target's "
                                                                                                                                            'party',
                                                                                                                      'health_amount': 54,
                                                                                                                      'duration_seconds': 3600,
                                                                                                                      'health_pool_semantics': None,
                                                                                                                      'tick_interval_seconds': None,
                                                                                                                      'stacking_rules': None,
                                                                                                                      'operative_values': None,
                                                                                                                      'historical_authentication': None},
     'Infuses 321 health into your defensive target. Heals for an extra 2% per level of Blood Union.': {'effect_reported': 'healing',
                                                                                                        'recipient_reported': 'your '
                                                                                                                              'defensive '
                                                                                                                              'target',
                                                                                                        'health_amount': 321,
                                                                                                        'blood_union_bonus_percent_per_level': 2,
                                                                                                        'bonus_basis': None,
                                                                                                        'duration_seconds': None,
                                                                                                        'tick_interval_seconds': None,
                                                                                                        'stacking_rules': None,
                                                                                                        'operative_values': None,
                                                                                                        'historical_authentication': None},
     'Transmutes 115 health into 115 energy.': {'effect_reported': 'health_to_energy_conversion',
                                                'health_consumed': 115,
                                                'energy_granted': 115,
                                                'recipient_reported': None,
                                                'duration_seconds': None,
                                                'tick_interval_seconds': None,
                                                'stacking_rules': None,
                                                'operative_values': None,
                                                'historical_authentication': None},
     "Fills your defensive target's party with life, granting them 23 additional vitality.": {'effect_reported': 'stat_increase',
                                                                                              'recipient_reported': 'your '
                                                                                                                    'defensive '
                                                                                                                    "target's "
                                                                                                                    'party',
                                                                                              'stat_reported': 'vitality',
                                                                                              'amount': 23,
                                                                                              'duration_seconds': None,
                                                                                              'tick_interval_seconds': None,
                                                                                              'stacking_rules': None,
                                                                                              'operative_values': None,
                                                                                              'historical_authentication': None}}.get(value.strip())
    if blood_mage:
        facts.append(dict(kind="blood_mage_healing_conversion_buff_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **blood_mage))
    # Exact remaining Bard literals source-reviewed in iteration685.
    remaining_bard = {'This wind bridge protects you and your allies from fire and cold.': {'effect_reported': 'protection',
                                                                           'damage_types_reported': ['fire',
                                                                                                     'cold'],
                                                                           'target_reported': 'you and your '
                                                                                              'allies',
                                                                           'protection_mechanism': None,
                                                                           'magnitude': None,
                                                                           'unit': None,
                                                                           'duration_seconds': None,
                                                                           'tick_interval_seconds': None,
                                                                           'stacking_rules': None,
                                                                           'operative_values': None,
                                                                           'historical_authentication': None},
     'This brass chorus confuses your opponent, reducing accuracy and increasing the cost of their spells.': {'effect_reported': 'confusion',
                                                                                                              'target_reported': 'your '
                                                                                                                                 'opponent',
                                                                                                              'modifiers_reported': [{'stat': 'accuracy',
                                                                                                                                      'direction': 'decrease'},
                                                                                                                                     {'stat': 'spell_cost',
                                                                                                                                      'direction': 'increase'}],
                                                                                                              'magnitude': None,
                                                                                                              'unit': None,
                                                                                                              'duration_seconds': None,
                                                                                                              'tick_interval_seconds': None,
                                                                                                              'stacking_rules': None,
                                                                                                              'operative_values': None,
                                                                                                              'historical_authentication': None},
     'Increases resistance to physical, mental, arcane and increases armor class.': {'effect_reported': 'stat_increase',
                                                                                     'target_reported': None,
                                                                                     'modifiers_reported': [{'stat': 'resistance',
                                                                                                             'types': ['physical',
                                                                                                                       'mental',
                                                                                                                       'arcane']},
                                                                                                            {'stat': 'armor_class'}],
                                                                                     'magnitude': None,
                                                                                     'unit': None,
                                                                                     'duration_seconds': None,
                                                                                     'tick_interval_seconds': None,
                                                                                     'stacking_rules': None,
                                                                                     'operative_values': None,
                                                                                     'historical_authentication': None},
     'Speeds up the rate at which bard dance forms are progressed.': {'effect_reported': 'faster_dance_form_progression',
                                                                      'class_reported': 'bard',
                                                                      'progression_rate': None,
                                                                      'magnitude': None,
                                                                      'unit': None,
                                                                      'duration_seconds': None,
                                                                      'tick_interval_seconds': None,
                                                                      'stacking_rules': None,
                                                                      'operative_values': None,
                                                                      'historical_authentication': None},
     "Reduces your opponent's armor class and strength. Deals damage over time.": {'effect_reported': 'compound_debuff_and_periodic_damage',
                                                                                   'target_reported': 'your '
                                                                                                      'opponent',
                                                                                   'modifiers_reported': [{'stat': 'armor_class',
                                                                                                           'direction': 'decrease'},
                                                                                                          {'stat': 'strength',
                                                                                                           'direction': 'decrease'}],
                                                                                   'damage_type_reported': None,
                                                                                   'magnitude': None,
                                                                                   'unit': None,
                                                                                   'duration_seconds': None,
                                                                                   'tick_interval_seconds': None,
                                                                                   'stacking_rules': None,
                                                                                   'operative_values': None,
                                                                                   'historical_authentication': None}}.get(value.strip())
    if remaining_bard:
        facts.append(dict(kind="nonnumeric_bard_tooltip_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **remaining_bard))
    # Exact reactive and poison attack literals reviewed in iteration685.
    combat_observation = {
        'This voice lyric deals damage to anyone who attack you and your allies.': {'effect_reported': 'reactive_damage', 'recipient_reported': 'anyone who attack you and your allies', 'trigger_reported': 'attack you and your allies', 'damage_type_reported': None, 'magnitude': None, 'unit': None, 'duration_seconds': None, 'tick_interval_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None},
        'This brass lyric adds additional poison damage to the attacks of you and your allies. Instrument modifiers alter proc chance.': {'effect_reported': 'additional_attack_damage', 'damage_type_reported': 'poison', 'target_reported': 'you and your allies', 'proc_modifier_reported': 'Instrument modifiers alter proc chance', 'proc_chance': None, 'magnitude': None, 'unit': None, 'duration_seconds': None, 'tick_interval_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None},
    }.get(value.strip())
    if combat_observation:
        facts.append(dict(kind="nonnumeric_combat_tooltip_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **combat_observation))
    # Exact speed and damage literals reviewed in iteration683.
    speed_damage = {"This brass verse reduces your opponent's movement speed.": {'direction_reported': 'decrease',
                                                                  'stat_reported': 'movement_speed',
                                                                  'target_reported': 'your opponent',
                                                                  'attack_scope_reported': None,
                                                                  'qualitative_magnitude_reported': None,
                                                                  'magnitude': None,
                                                                  'unit': None,
                                                                  'tick_interval_seconds': None,
                                                                  'duration_seconds': None,
                                                                  'stacking_rules': None,
                                                                  'operative_values': None,
                                                                  'historical_authentication': None},
     'Causes your feet to move at great speeds, increasing your movement speed.': {'direction_reported': 'increase',
                                                                                   'stat_reported': 'movement_speed',
                                                                                   'target_reported': 'you',
                                                                                   'attack_scope_reported': None,
                                                                                   'qualitative_magnitude_reported': None,
                                                                                   'magnitude': None,
                                                                                   'unit': None,
                                                                                   'tick_interval_seconds': None,
                                                                                   'duration_seconds': None,
                                                                                   'stacking_rules': None,
                                                                                   'operative_values': None,
                                                                                   'historical_authentication': None},
     'Increases damage of all attacks made by you or your allies by a small amount.': {'direction_reported': 'increase',
                                                                                       'stat_reported': 'attack_damage',
                                                                                       'target_reported': 'you '
                                                                                                          'or '
                                                                                                          'your '
                                                                                                          'allies',
                                                                                       'attack_scope_reported': 'all '
                                                                                                                'attacks',
                                                                                       'qualitative_magnitude_reported': 'small '
                                                                                                                         'amount',
                                                                                       'magnitude': None,
                                                                                       'unit': None,
                                                                                       'tick_interval_seconds': None,
                                                                                       'duration_seconds': None,
                                                                                       'stacking_rules': None,
                                                                                       'operative_values': None,
                                                                                       'historical_authentication': None}}.get(value.strip())
    if speed_damage:
        facts.append(dict(kind="speed_damage_tooltip_observation",
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **speed_damage))
    # Exact resource literals reviewed in iteration681; no inferred tick or transfer.
    resource_observation = {'Increases health and energy regeneration of you and your allies.': {'direction_reported': 'increase',
                                                                      'resources_reported': ['health',
                                                                                             'energy'],
                                                                      'target_reported': 'you and '
                                                                                         'your '
                                                                                         'allies',
                                                                      'regeneration_reported': True,
                                                                      'drain_reported': False,
                                                                      'resource_transfer_to_caster': None,
                                                                      'magnitude': None,
                                                                      'unit': None,
                                                                      'tick_interval_seconds': None,
                                                                      'duration_seconds': None,
                                                                      'stacking_rules': None,
                                                                      'operative_values': None,
                                                                      'historical_authentication': None},
 'Drains energy from your opponent.': {'direction_reported': 'drain',
                                       'resources_reported': ['energy'],
                                       'target_reported': 'your opponent',
                                       'regeneration_reported': False,
                                       'drain_reported': True,
                                       'resource_transfer_to_caster': None,
                                       'magnitude': None,
                                       'unit': None,
                                       'tick_interval_seconds': None,
                                       'duration_seconds': None,
                                       'stacking_rules': None,
                                       'operative_values': None,
                                       'historical_authentication': None},
 'Increases mana and health regeneration of you and your allies.': {'direction_reported': 'increase',
                                                                    'resources_reported': ['mana',
                                                                                           'health'],
                                                                    'target_reported': 'you and '
                                                                                       'your '
                                                                                       'allies',
                                                                    'regeneration_reported': True,
                                                                    'drain_reported': False,
                                                                    'resource_transfer_to_caster': None,
                                                                    'magnitude': None,
                                                                    'unit': None,
                                                                    'tick_interval_seconds': None,
                                                                    'duration_seconds': None,
                                                                    'stacking_rules': None,
                                                                    'operative_values': None,
                                                                    'historical_authentication': None}}.get(value.strip())
    if resource_observation:
        facts.append(dict(kind='resource_regeneration_drain_tooltip_observation',
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **resource_observation))
    # Exact armor and absorption literals reviewed in iteration679.
    armor_absorption = {
        'This string chorus causes a curtain of sound to protect you and your allies that increases armor class, block skill and absorbs damage each pulse.': {'modifiers_reported': ['armor_class', 'block_skill'], 'direction_reported': 'increase', 'target_reported': 'you and your allies', 'damage_absorption_reported': True, 'absorption_cadence_reported': 'each pulse', 'absorption_magnitude_reported': None, 'modifier_magnitudes': None, 'absorption_amount': None, 'pulse_interval_seconds': None, 'duration_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None},
        "This string melody increases you and your allies' armor class, block, dodge, parry skills and absorbs damage each pulse.": {'modifiers_reported': ['armor_class', 'block', 'dodge', 'parry_skills'], 'direction_reported': 'increase', 'target_reported': 'you and your allies', 'damage_absorption_reported': True, 'absorption_cadence_reported': 'each pulse', 'absorption_magnitude_reported': None, 'modifier_magnitudes': None, 'absorption_amount': None, 'pulse_interval_seconds': None, 'duration_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None},
        'Instills you and your allies with pure resolution that increases armor class and absorbs a small amount of damage each pulse.': {'modifiers_reported': ['armor_class'], 'direction_reported': 'increase', 'target_reported': 'you and your allies', 'damage_absorption_reported': True, 'absorption_cadence_reported': 'each pulse', 'absorption_magnitude_reported': 'small amount', 'modifier_magnitudes': None, 'absorption_amount': None, 'pulse_interval_seconds': None, 'duration_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None},
    }.get(value.strip())
    if armor_absorption:
        facts.append(dict(kind='armor_absorption_tooltip_observation',
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **armor_absorption))
    # Exact resistance buff literals reviewed in iteration677.
    resistance_buff = {
        'This voice embellishment increases the arcane and physical resistances of you and your allies.': {'direction_reported': 'increase', 'resistance_types_reported': ['arcane', 'physical'], 'resistance_scope_reported': 'explicit_named_types', 'target_reported': 'you and your allies', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        'This voice embellishment increases the mental and spiritual resistances of you and your allies.': {'direction_reported': 'increase', 'resistance_types_reported': ['mental', 'spiritual'], 'resistance_scope_reported': 'explicit_named_types', 'target_reported': 'you and your allies', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        'This percussion melody increases fire and cold resistances of you and your allies.': {'direction_reported': 'increase', 'resistance_types_reported': ['fire', 'cold'], 'resistance_scope_reported': 'explicit_named_types', 'target_reported': 'you and your allies', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        'Increases all resistance of you and your group.': {'direction_reported': 'increase', 'resistance_types_reported': None, 'resistance_scope_reported': 'all', 'target_reported': 'you and your group', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        'Increases all resistances of you and your allies.': {'direction_reported': 'increase', 'resistance_types_reported': None, 'resistance_scope_reported': 'all', 'target_reported': 'you and your allies', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
    }.get(value.strip())
    if resistance_buff:
        facts.append(dict(kind='resistance_buff_tooltip_observation',
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **resistance_buff))
    # Exact resistance debuff literals reviewed in iteration675.
    resistance_debuff = {
        "This brass embellishment lowers your opponent's arcane resistance.": {'direction_reported': 'decrease', 'resistance_types_reported': ['arcane'], 'target_reported': 'opponent', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        'This brass embellishment lowers your opponents cold resistance.': {'direction_reported': 'decrease', 'resistance_types_reported': ['cold'], 'target_reported': 'opponent', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        "This brass embellishment lowers your opponent's physical resistance.": {'direction_reported': 'decrease', 'resistance_types_reported': ['physical'], 'target_reported': 'opponent', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        "This brass embellishment lowers your opponent's spiritual and mental restistance.": {'direction_reported': 'decrease', 'resistance_types_reported': ['spiritual', 'mental'], 'target_reported': 'opponent', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        "This brass embellishment lowers your opponent's fire resistance.": {'direction_reported': 'decrease', 'resistance_types_reported': ['fire'], 'target_reported': 'opponent', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        "This brass bridge reduces your opponent's arcane, fire and cold resistances.": {'direction_reported': 'decrease', 'resistance_types_reported': ['arcane', 'fire', 'cold'], 'target_reported': 'opponent', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
        "Reduces your opponent's physical, spiritual and mental resistances.": {'direction_reported': 'decrease', 'resistance_types_reported': ['physical', 'spiritual', 'mental'], 'target_reported': 'opponent', 'magnitude': None, 'unit': None, 'duration_seconds': None, 'stacking_rules': None, 'resistance_floor': None, 'operative_values': None, 'historical_authentication': None},
    }.get(value.strip())
    if resistance_debuff:
        facts.append(dict(kind='resistance_debuff_tooltip_observation',
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **resistance_debuff))
    # Exact cure/dispel source literals reviewed in iteration673.
    removal = {
        'This voice lyric cures a friendly target of disease. The cure is slow, but constant.': {'action_reported': 'cure', 'condition_reported': 'disease', 'target_reported': 'friendly target', 'timing_qualifier_reported': 'slow but constant', 'enchantment_qualifier_reported': None, 'cure_count': None, 'pulse_interval_seconds': None, 'duration_seconds': None, 'dispel_strength': None, 'operative_values': None, 'historical_authentication': None},
        'This voice lyric cures a friendly target of poison. The cure is slow, but constant.': {'action_reported': 'cure', 'condition_reported': 'poison', 'target_reported': 'friendly target', 'timing_qualifier_reported': 'slow but constant', 'enchantment_qualifier_reported': None, 'cure_count': None, 'pulse_interval_seconds': None, 'duration_seconds': None, 'dispel_strength': None, 'operative_values': None, 'historical_authentication': None},
        'Strips a lesser enchantment from your opponent.': {'action_reported': 'strip_enchantment', 'condition_reported': 'enchantment', 'target_reported': 'opponent', 'timing_qualifier_reported': None, 'enchantment_qualifier_reported': 'lesser', 'cure_count': None, 'pulse_interval_seconds': None, 'duration_seconds': None, 'dispel_strength': None, 'operative_values': None, 'historical_authentication': None},
        'This voice lyric removes enchantment effects over time from a friendly target.': {'action_reported': 'remove_enchantment_effects', 'condition_reported': 'enchantment effects', 'target_reported': 'friendly target', 'timing_qualifier_reported': 'over time', 'enchantment_qualifier_reported': None, 'cure_count': None, 'pulse_interval_seconds': None, 'duration_seconds': None, 'dispel_strength': None, 'operative_values': None, 'historical_authentication': None},
        'Strips an enchantment from your opponent.': {'action_reported': 'strip_enchantment', 'condition_reported': 'enchantment', 'target_reported': 'opponent', 'timing_qualifier_reported': None, 'enchantment_qualifier_reported': None, 'cure_count': None, 'pulse_interval_seconds': None, 'duration_seconds': None, 'dispel_strength': None, 'operative_values': None, 'historical_authentication': None},
        'Strips a greater enchantment from your opponent.': {'action_reported': 'strip_enchantment', 'condition_reported': 'enchantment', 'target_reported': 'opponent', 'timing_qualifier_reported': None, 'enchantment_qualifier_reported': 'greater', 'cure_count': None, 'pulse_interval_seconds': None, 'duration_seconds': None, 'dispel_strength': None, 'operative_values': None, 'historical_authentication': None},
    }.get(value.strip())
    if removal:
        facts.append(dict(kind='cure_dispel_tooltip_observation',
            effect_phrase_recorded=value.strip(), conditions_unparsed=True, **removal))
    # Exact cached Bard effect literals reviewed in iteration671.
    utility = {
        'Allows your group to fall slowly and safely from any height.':
            ('slow_fall', 'your group'),
        'Allows your group to breathe underwater.':
            ('water_breathing', 'your group'),
        'Levitates you and your nearby group members off the ground':
            ('levitation', 'you and your nearby group members'),
        'Causes you and nearby group members to become invisible':
            ('invisibility', 'you and nearby group members'),
        'This wind verse causes you and your allies to become invisible.':
            ('invisibility', 'you and your allies'),
    }.get(value.strip())
    if utility:
        effect, targets = utility
        facts.append(dict(kind='group_utility_tooltip_observation',
            effect_recorded=effect, target_phrase_recorded=targets,
            effect_phrase_recorded=value.strip(), duration_seconds=None,
            range=None, range_unit=None, break_conditions=None,
            movement_speed=None, stacking_formula=None, operative_values=None,
            conditions_unparsed=True))
    # Exact iteration667 reviews; tooltip observations do not establish mechanics.
    if value.strip() == 'Increases the attack speed of you and your group by 12%. Cost: 2 energy per second Song Portion: Embellishment Instrument: None Cast Time: 0 Refresh: 0 Range: 5':
        facts.append(dict(kind='attack_speed_energy_upkeep_tooltip_observation',
            attack_speed_increase_percent_recorded=12,
            target_phrase_recorded='you and your group',
            energy_upkeep_recorded=dict(amount=2, unit_literal='per second',
                resource_literal='energy'),
            song_portion_literal='Embellishment', instrument_literal='None',
            timing_and_range_literals=dict(cast_time='0', refresh='0', range='5'),
            cast_time_unit=None, refresh_unit=None, range_unit=None,
            percentage_calculation=None, upkeep_schedule=None, stacking_formula=None,
            operative_values=None, conditions_unparsed=True))
    if value.strip() == 'You move and strike with increased focus and speed, advancing to the last phase of your current dance and increasing melee accuracy and critical chance by 5% for 30 seconds.':
        facts.append(dict(kind='dance_accuracy_critical_tooltip_observation',
            melee_accuracy_increase_percent_recorded=5,
            critical_chance_increase_percent_recorded=5,
            duration_seconds_recorded=30,
            dance_transition_phrase_recorded='advancing to the last phase of your current dance',
            percentage_calculation=None, resulting_critical_probability=None,
            dance_phase_identifier=None, stacking_formula=None,
            operative_values=None, conditions_unparsed=True))
    # Exact reviewed fear tooltips; unqualified clauses retain unknown mode scope.
    fear = re.fullmatch(
        r'Fills your target with fear, causing it to flee in terror for 12 sec\. '
        r'Only one target can be feared at a time\. In player versus player combat '
        r'this spell stuns your target for 6 seconds\. Has a 25% chance to break on hit\. '
        r'Only affects a single target every 30 seconds\. '
        r'Effective on targets level (39|50) and lower\.', value.strip())
    if fear:
        facts.append(dict(kind='fear_pvp_stun_tooltip_observation',
            target_phrase_recorded='your target', fear_duration_seconds_recorded=12,
            maximum_feared_targets_recorded=1,
            pvp_effect_recorded=dict(effect_literal='stuns', duration_seconds=6),
            break_on_hit_chance_percent_recorded=25,
            single_target_interval_seconds_recorded=30,
            target_level_maximum_recorded=int(fear.group(1)),
            fear_mode_scope=None, break_on_hit_mode_scope=None,
            target_interval_mode_scope=None, target_level_limit_mode_scope=None,
            interval_reset_mechanics=None, hit_definition=None,
            stun_immunity_rules=None, operative_values=None, conditions_unparsed=True))
    # Exact iteration664 transcriptions; level mapping and unknown upkeep stay null.
    resistance_upkeep = {
        'Protects you and your group from the elements, increasing your fire, cold and physical resistances by 12 to 16, depending on your level. Costs 6/sec energy.':
            (['fire', 'cold', 'physical'], 6, '6'),
        'Surrounds you and your group with shielding sound, increasing your arcane, mental and spiritual resistance by 12 to 16, depending on your level. Costs ?/sec energy.':
            (['arcane', 'mental', 'spiritual'], None, '?'),
    }.get(value.strip())
    if resistance_upkeep:
        schools, upkeep, upkeep_literal = resistance_upkeep
        facts.append(dict(kind='level_dependent_resistance_upkeep_tooltip_observation',
            resistance_range_recorded=dict(minimum=12, maximum=16,
                resistance_types_literal=schools),
            target_phrase_recorded='you and your group',
            scaling_phrase_recorded='depending on your level',
            energy_upkeep_recorded=dict(amount=upkeep, amount_literal=upkeep_literal,
                unit_literal='/sec', resource_literal='energy'),
            level_scaling_formula=None, resistance_unit=None, upkeep_schedule=None,
            stacking_formula=None, instrument_scaling=None, operative_values=None,
            conditions_unparsed=True))
    # Exact iteration661 transcription; printed endpoints do not establish scaling.
    if value.strip() == 'You release a deep, booming bellow, smashing your opponent for 790 to 832 arcane damage and stunning it for 4 sec.':
        facts.append(dict(kind='arcane_damage_stun_tooltip_observation',
            damage_range_recorded=dict(minimum=790, maximum=832,
                damage_type_literal='arcane'),
            stun_duration_recorded=dict(amount=4, unit_literal='sec'),
            target_phrase_recorded='your opponent', range_scaling_basis=None,
            damage_formula=None, stun_immunity_rules=None,
            stun_break_conditions=None, stacking_formula=None,
            instrument_scaling=None, operative_values=None, conditions_unparsed=True))
    # Exact iteration658 transcriptions; no normal-damage or control mechanics inferred.
    if value.strip() == 'Deals 400% of normal damage. This ability is only available when a target is below 20% health.':
        facts.append(dict(kind='normal_damage_health_availability_tooltip_observation',
            damage_percent_of_normal_recorded=400,
            availability_condition_recorded=dict(target_health_percent=20,
                comparison_literal='below', comparison='strictly_less_than'),
            target_phrase_recorded='a target', normal_damage_definition=None,
            damage_type=None, health_denominator=None, condition_evaluation_timing=None,
            stacking_formula=None, operative_values=None, conditions_unparsed=True))
    if value.strip() == 'Single target mesmerize (28 sec)':
        facts.append(dict(kind='single_target_mesmerize_tooltip_observation',
            effect_literal='mesmerize', target_phrase_recorded='Single target',
            duration_recorded=dict(amount=28, unit_literal='sec'),
            mesmerize_break_conditions=None, immunity_rules=None,
            instrument_scaling=None, operative_values=None, conditions_unparsed=True))
    # Exact iteration655 reviews; upkeep scheduling and percentage base are unknown.
    refresh_upkeep = {
        'Reduces the spell and attack refresh timers of your group by 20%. Costs 8/sec energy.':
            ([dict(attribute_literal='spell and attack refresh timers',
                   direction_recorded='reduction', percent_recorded=20,
                   target_phrase_recorded='your group')], 8),
        'Increases all resistances of you and your allies. Costs 2/sec energy.':
            ([dict(attribute_literal='all resistances', direction_recorded='increase',
                   value=None, target_phrase_recorded='you and your allies')], 2),
    }.get(value.strip())
    if refresh_upkeep:
        modifiers, upkeep = refresh_upkeep
        facts.append(dict(kind='refresh_energy_upkeep_tooltip_observation',
                          modifiers_recorded=modifiers,
                          energy_upkeep_recorded=dict(amount=upkeep,
                              resource_literal='energy', per_unit_literal='sec'),
                          resistance_amount=None, percentage_calculation=None,
                          stacking_formula=None, instrument_scaling=None,
                          duration=None, operative_values=None, conditions_unparsed=True))
    # Exact iteration652 transcriptions; preserve spelling and unknown scaling.
    reviewed_reductions = {
        "Reduces your opponent's AC by 25-95 and strengthe by 6-8": [
            dict(attribute_literal='AC', direction_recorded='reduction',
                 range_recorded=[25, 95], unit=None),
            dict(attribute_literal='strengthe', direction_recorded='reduction',
                 range_recorded=[6, 8], unit=None)],
        'Reduces the potency of heals on your opponent by 10%.': [
            dict(attribute_literal='potency of heals', direction_recorded='reduction',
                 percent_recorded=10)],
    }.get(value.strip())
    if reviewed_reductions:
        facts.append(dict(kind='ac_strength_healing_potency_tooltip_observation',
                          modifiers_recorded=reviewed_reductions,
                          target_phrase_recorded='your opponent', range_scaling=None,
                          percentage_calculation=None, stacking_formula=None,
                          instrument_scaling=None, operative_values=None,
                          conditions_unparsed=True))
    # Exact iteration649 reviews; unquantified skills and duration scope stay unknown.
    reviewed_modifiers = {
        'This string chorus increases you and your allies evasion by 2% and increases parry and dodge skill.':
            ([('evasion', 'increase', 2), ('parry skill', 'increase', None),
              ('dodge skill', 'increase', None)], 'you and your allies', None, None),
        'Confuses your opponent, reducing their accuracy by 20% and increasing the cost of their spells by 30% for 45 sec.':
            ([('accuracy', 'reduction', 20), ('cost of spells', 'increase', 30)],
             'your opponent', 'for 45 sec.', 45),
    }.get(value.strip())
    if reviewed_modifiers:
        modifiers, target, duration_phrase, duration_seconds = reviewed_modifiers
        facts.append(dict(kind='evasion_accuracy_spell_cost_tooltip_observation',
                          modifiers_recorded=[dict(attribute_recorded=a,
                              direction_recorded=d, percent_recorded=p)
                              for a, d, p in modifiers],
                          target_phrase_recorded=target,
                          duration_phrase_recorded=duration_phrase,
                          duration_seconds_recorded=duration_seconds, duration_scope=None,
                          percentage_calculation=None, stacking_formula=None,
                          instrument_scaling=None, operative_values=None,
                          conditions_unparsed=True))
    # Exact iteration646 transcriptions; printed percentages establish no formula.
    percent_modifier = {
        'Increases spell accuracy and damage by 3% and spell critical chance by 2%. This component can only be used once in a song.':
            ([('spell accuracy', 'increase', 3), ('spell damage', 'increase', 3),
              ('spell critical chance', 'increase', 2)], None,
             'This component can only be used once in a song.'),
        "Reduces your opponent's attack speed by 15% and movement by 60%. Does not stack with other snaring components.":
            ([('attack speed', 'reduction', 15), ('movement', 'reduction', 60)],
             'your opponent', 'Does not stack with other snaring components.'),
    }.get(value.strip())
    if percent_modifier:
        modifiers, target, restriction = percent_modifier
        facts.append(dict(kind='percent_modifier_tooltip_observation',
                          modifiers_recorded=[dict(attribute_recorded=a,
                              direction_recorded=d, percent_recorded=p)
                              for a, d, p in modifiers],
                          target_phrase_recorded=target,
                          restriction_phrase_recorded=restriction,
                          duration=None, percentage_calculation=None, stacking_formula=None,
                          instrument_scaling=None, operative_values=None, conditions_unparsed=True))
    # Literal-scoped iteration643 review; printed level dependence is not a formula.
    periodic_recovery = {
        'Heals you and your group for 7-9, depending on your level, every 4 seconds. Costs 4/sec energy.':
            ('health', 7, 9, 'you and your group'),
        'Restores 6 energy, depending on your level, to your group every 4 seconds. Costs 4/sec energy.':
            ('energy', 6, 6, 'your group'),
    }.get(value.strip())
    if periodic_recovery:
        resource, low, high, target = periodic_recovery
        facts.append(dict(kind='level_dependent_periodic_recovery_tooltip_observation',
                          recovery_resource_recorded=resource,
                          recovery_minimum_recorded=low, recovery_maximum_recorded=high,
                          recovery_interval_seconds_recorded=4, target_phrase_recorded=target,
                          cost_resource_recorded='energy', cost_per_second_recorded=4,
                          level_dependency_phrase_recorded='depending on your level',
                          level_scaling_formula=None, duration=None, stacking=None,
                          eligibility=None, operative_values=None, conditions_unparsed=True))
    # Exact iteration640 transcriptions; resistance school is not damage school.
    resistance_shield = {
        'Increases the cold resistance of your group by 8 and burns any attackkers for 6 damage.':
            ('cold', 8, 'your group', 6, None, 'any attackkers'),
        'Increases the fire resistance of your group by 8 burns any attackers for 6 damage.':
            ('fire', 8, 'your group', 6, None, 'any attackers'),
        'This wind embellishment increases the cold resistance of you and your allies and grants a 2 point damage shield.':
            ('cold', None, 'you and your allies', None, 2, None),
    }.get(value.strip())
    if resistance_shield:
        school, amount, target, damage, shield, reactive_target = resistance_shield
        facts.append(dict(kind='resistance_damage_shield_tooltip_observation',
                          resistance_type_recorded=school, resistance_increase_recorded=amount,
                          target_phrase_recorded=target, reactive_damage_recorded=damage,
                          damage_shield_points_recorded=shield,
                          reactive_target_phrase_recorded=reactive_target,
                          damage_school=None, trigger=None, scaling=None, stacking=None,
                          duration=None, operative_values=None, conditions_unparsed=True))
    # Literal-scoped iteration637 reviews; percentages establish no timing formula.
    speed_modifier = {
        'Increase the spell casting speed for your group by 5%':
            ('spell casting speed', 'increase', 5, 'your group'),
        "This brass lyric reduces your opponent's attacks speed by 3%.":
            ('attacks speed', 'reduce', 3, 'your opponent'),
    }.get(value.strip())
    if speed_modifier:
        subject, direction, percentage, target = speed_modifier
        facts.append(dict(kind='speed_modifier_tooltip_observation',
                          modifier_subject_recorded=subject, direction_recorded=direction,
                          percentage_recorded=percentage, target_phrase_recorded=target,
                          stacking=None, duration=None, timing_formula=None,
                          eligibility=None, operative_values=None, conditions_unparsed=True))
    # Exact iteration635 source literals; cadence alone establishes no total damage.
    periodic_damage = {
        'Deals 12-43 damage to your offensive target every 4 secs': (12, 43, None),
        'Deals 10 arcane damage to your offensive target every 4 secs.': (10, 10, 'arcane'),
    }.get(value.strip())
    if periodic_damage:
        low, high, damage_type = periodic_damage
        facts.append(dict(kind='periodic_damage_tooltip_observation',
                          damage_min_recorded=low, damage_max_recorded=high,
                          damage_type_recorded=damage_type, interval_seconds_recorded=4,
                          target_phrase_recorded='your offensive target', scaling=None,
                          duration=None, tick_count=None, initial_tick_timing=None,
                          trigger_mechanics=None, operative_values=None,
                          conditions_unparsed=True))
    # Exact reviewed transcriptions; truncated Frost wording is deliberately retained.
    # Literal-scoped observations from the hash-verified iteration630 source review.
    # Exact resource-cost transcriptions verified in iteration632; formulas remain unknown.
    resource_cost = {
        'This brass chrous reduces the amount of mana consumed when your allies cast spells. 5% decrease in mana cost.': dict(
            resource_recorded='mana', cost_reduction_percent_recorded=5,
            beneficiary_phrase_recorded='your allies', action_phrase_recorded='cast spells'),
        'This brass chrous reduces the amount of endurance consumed by the melee attacks of you and your allies by 5%.': dict(
            resource_recorded='endurance', cost_reduction_percent_recorded=5,
            beneficiary_phrase_recorded='you and your allies', action_phrase_recorded='melee attacks'),
    }.get(value.strip())
    if resource_cost:
        facts.append(dict(kind='resource_cost_reduction_tooltip_observation',
                          **resource_cost, cost_formula=None, rounding=None, minimum_cost=None,
                          eligible_abilities=None, scaling=None, operative_values=None,
                          conditions_unparsed=True))
    hatred_critical = {
        'Calms your opponent, reducing their hatred of you by 30%.': dict(
            kind='hatred_reduction_tooltip_observation',
            hatred_reduction_percent_recorded=30, subject_phrase_recorded='your opponent',
            hatred_target_phrase_recorded='you', threat_formula=None, threat_floor=None,
            duration_seconds=None),
        'Your strikes become more precise as your weapons begin to sing, increasing critical chance by 100% for 3 sec.': dict(
            kind='critical_chance_tooltip_observation',
            critical_chance_increase_percent_recorded=100, duration_seconds_recorded=3,
            relative_or_percentage_point_increase=None, resulting_critical_probability=None,
            eligible_attack_types=None),
    }.get(value.strip())
    if hatred_critical:
        facts.append(dict(**hatred_critical, scaling=None, operative_values=None,
                          conditions_unparsed=True))
    armor_pulse = {'Causes a curtain of sound to protect your group that increases armor class by 25 and absorbs 25 damage each pulse.': {'armor_class_increase_recorded': 25,
                                                                                                                            'damage_absorbed_each_pulse_recorded': 25,
                                                                                                                            'energy_per_second_recorded': None,
                                                                                                                            'energy_cost_explicitly_unknown': False,
                                                                                                                            'recipient_phrase_recorded': 'your '
                                                                                                                                                         'group',
                                                                                                                            'pulse_interval_seconds': None,
                                                                                                                            'absorption_refresh_model': None,
                                                                                                                            'damage_types_absorbed': None,
                                                                                                                            'duration_seconds': None,
                                                                                                                            'scaling': None,
                                                                                                                            'operative_values': None},
     'Causes a curtain of sound to protect your group that increases armor class by 50 and absorbs 50 damage each pulse. Costs ?/sec energy.': {'armor_class_increase_recorded': 50,
                                                                                                                                                'damage_absorbed_each_pulse_recorded': 50,
                                                                                                                                                'energy_per_second_recorded': None,
                                                                                                                                                'energy_cost_explicitly_unknown': True,
                                                                                                                                                'recipient_phrase_recorded': 'your '
                                                                                                                                                                             'group',
                                                                                                                                                'pulse_interval_seconds': None,
                                                                                                                                                'absorption_refresh_model': None,
                                                                                                                                                'damage_types_absorbed': None,
                                                                                                                                                'duration_seconds': None,
                                                                                                                                                'scaling': None,
                                                                                                                                                'operative_values': None},
     "Increases your group's armor class by 150 and absorbs damage each pulse. Costs 2/sec energy.": {'armor_class_increase_recorded': 150,
                                                                                                      'damage_absorbed_each_pulse_recorded': None,
                                                                                                      'energy_per_second_recorded': 2,
                                                                                                      'energy_cost_explicitly_unknown': False,
                                                                                                      'recipient_phrase_recorded': 'your '
                                                                                                                                   'group',
                                                                                                      'pulse_interval_seconds': None,
                                                                                                      'absorption_refresh_model': None,
                                                                                                      'damage_types_absorbed': None,
                                                                                                      'duration_seconds': None,
                                                                                                      'scaling': None,
                                                                                                      'operative_values': None}}.get(value.strip())
    if armor_pulse:
        facts.append(dict(kind="armor_pulse_tooltip_observation", **armor_pulse,
                          conditions_unparsed=True))
    proc_damage = {'Adds a 10% chance for your group to deal 144-159 cold damage with melee and ranged attac': {'chance_percent_recorded': 10,
                                                                                                  'damage_range_recorded': [144,
                                                                                                                            159],
                                                                                                  'damage_type_recorded': 'cold',
                                                                                                  'recipient_recorded': 'your '
                                                                                                                        'group',
                                                                                                  'attack_phrase_recorded': 'melee '
                                                                                                                            'and '
                                                                                                                            'ranged '
                                                                                                                            'attac',
                                                                                                  'truncated_text': True,
                                                                                                  'energy_per_second_recorded': None,
                                                                                                  'instrument_modifier_statement_recorded': None,
                                                                                                  'trigger_probability_model': None,
                                                                                                  'trigger_eligibility': None,
                                                                                                  'damage_scaling': None,
                                                                                                  'operative_values': None},
     'Adds a 10% chance for your group to deal 186-201 fire damage with melee and ranged attacks.': {'chance_percent_recorded': 10,
                                                                                                     'damage_range_recorded': [186,
                                                                                                                               201],
                                                                                                     'damage_type_recorded': 'fire',
                                                                                                     'recipient_recorded': 'your '
                                                                                                                           'group',
                                                                                                     'attack_phrase_recorded': 'melee '
                                                                                                                               'and '
                                                                                                                               'ranged '
                                                                                                                               'attacks',
                                                                                                     'truncated_text': False,
                                                                                                     'energy_per_second_recorded': None,
                                                                                                     'instrument_modifier_statement_recorded': None,
                                                                                                     'trigger_probability_model': None,
                                                                                                     'trigger_eligibility': None,
                                                                                                     'damage_scaling': None,
                                                                                                     'operative_values': None},
     'Adds a 10% chance to deal 283 to 302 fire damage with melee and ranged attacks. Costs 3/sec energy.': {'chance_percent_recorded': 10,
                                                                                                             'damage_range_recorded': [283,
                                                                                                                                       302],
                                                                                                             'damage_type_recorded': 'fire',
                                                                                                             'recipient_recorded': None,
                                                                                                             'attack_phrase_recorded': 'melee '
                                                                                                                                       'and '
                                                                                                                                       'ranged '
                                                                                                                                       'attacks',
                                                                                                             'truncated_text': False,
                                                                                                             'energy_per_second_recorded': 3,
                                                                                                             'instrument_modifier_statement_recorded': None,
                                                                                                             'trigger_probability_model': None,
                                                                                                             'trigger_eligibility': None,
                                                                                                             'damage_scaling': None,
                                                                                                             'operative_values': None},
     'Adds a 10% chance to deal 316 to 338 cold damage with melee and ranged attacks. Costs 3/sec energy.': {'chance_percent_recorded': 10,
                                                                                                             'damage_range_recorded': [316,
                                                                                                                                       338],
                                                                                                             'damage_type_recorded': 'cold',
                                                                                                             'recipient_recorded': None,
                                                                                                             'attack_phrase_recorded': 'melee '
                                                                                                                                       'and '
                                                                                                                                       'ranged '
                                                                                                                                       'attacks',
                                                                                                             'truncated_text': False,
                                                                                                             'energy_per_second_recorded': 3,
                                                                                                             'instrument_modifier_statement_recorded': None,
                                                                                                             'trigger_probability_model': None,
                                                                                                             'trigger_eligibility': None,
                                                                                                             'damage_scaling': None,
                                                                                                             'operative_values': None},
     'Adds a 10% chance to deal 343 to 364 poison damage with melee and ranged attacks. - Instrument modifiers alter proc chance. Costs 3/sec energy.': {'chance_percent_recorded': 10,
                                                                                                                                                         'damage_range_recorded': [343,
                                                                                                                                                                                   364],
                                                                                                                                                         'damage_type_recorded': 'poison',
                                                                                                                                                         'recipient_recorded': None,
                                                                                                                                                         'attack_phrase_recorded': 'melee '
                                                                                                                                                                                   'and '
                                                                                                                                                                                   'ranged '
                                                                                                                                                                                   'attacks',
                                                                                                                                                         'truncated_text': False,
                                                                                                                                                         'energy_per_second_recorded': 3,
                                                                                                                                                         'instrument_modifier_statement_recorded': 'Instrument '
                                                                                                                                                                                                   'modifiers '
                                                                                                                                                                                                   'alter '
                                                                                                                                                                                                   'proc '
                                                                                                                                                                                                   'chance.',
                                                                                                                                                         'trigger_probability_model': None,
                                                                                                                                                         'trigger_eligibility': None,
                                                                                                                                                         'damage_scaling': None,
                                                                                                                                                         'operative_values': None}}.get(value.strip())
    if proc_damage:
        facts.append(dict(kind="proc_damage_tooltip_observation", **proc_damage,
                          conditions_unparsed=True))
    reactive = {
        'Attacks against you resonate sharply, dealing 15 damage to your attackers.':
            (15, 'your attackers', 'Attacks against you'),
        'Attacks against you resonate sharply, dealing 30 damage to your attackers.':
            (30, 'your attackers', 'Attacks against you'),
        'Strikes those that attack you or your group with discordant notes, causing 24 damage':
            (24, 'those that attack you or your group', 'attack you or your group'),
    }.get(value.strip())
    if reactive:
        damage, recipient, trigger = reactive
        facts.append(dict(kind='reactive_damage_tooltip_observation',
                          damage_recorded=damage, recipient_recorded=recipient,
                          trigger_recorded=trigger, damage_type=None,
                          trigger_probability=None, attack_eligibility=None,
                          mitigation=None, scaling=None, radius=None,
                          per_hit_behavior=None, operative_values=None,
                          conditions_unparsed=True))
    group_damage = {
        "Increases the damage of your group by 15%, strength, intelligence by 6-30 and AC by 8-62. Does not stack with Mellarien's Requiem of War":
            dict(damage_percent_recorded=15, strength_range_recorded=[6, 30],
                 intelligence_range_recorded=[6, 30], ac_range_recorded=[8, 62],
                 does_not_stack_with_recorded="Mellarien's Requiem of War",
                 percentage_base=None, range_scaling=None),
        "Increases the damage of your group by 12-20.":
            dict(damage_range_recorded=[12, 20], damage_unit=None,
                 range_scaling=None, stacking=None),
        "Increase the damage of your group by 5%, does not stack with Mellarien's Anthem of War":
            dict(damage_percent_recorded=5,
                 does_not_stack_with_recorded="Mellarien's Anthem of War",
                 percentage_base=None, range_scaling=None),
    }.get(value.strip())
    if group_damage:
        facts.append(dict(kind='group_damage_tooltip_observation', **group_damage,
                          target_phrase_recorded='your group', operative_values=None,
                          conditions_unparsed=True))
    environmental = {
        'Whistling this little tune will cause you and your nearby group mates to levitate for 60 minutes.':
            dict(action_recorded='levitate', target_phrase_recorded='you and your nearby group mates',
                 duration_minutes_recorded=60, nearby_radius=None, height=None, combat_applicability=None),
        'Enables your group to breathe underwater. Costs 7/sec energy.':
            dict(action_recorded='breathe underwater', target_phrase_recorded='your group',
                 energy_per_second_recorded=7, duration=None, upkeep_timing=None),
        'Levitates your group off of the ground. Costs 6/sec energy.':
            dict(action_recorded='Levitates', target_phrase_recorded='your group',
                 energy_per_second_recorded=6, height=None, combat_applicability=None, upkeep_timing=None),
    }.get(value.strip())
    if environmental:
        facts.append(dict(kind='environmental_movement_tooltip_observation', **environmental,
                          stacking=None, scaling=None, operative_values=None, conditions_unparsed=True))
    resistance = re.fullmatch(
        r'Increases the (arcane, mental and spiritual|mental and spiritual|cold, fire and physical) '
        r'(resistances|resistance) of all nearby allies by (20|10)\. Costs 4/sec energy\.',
        value.strip())
    if resistance and resistance.groups() in (
            ('arcane, mental and spiritual', 'resistances', '20'),
            ('mental and spiritual', 'resistances', '10'),
            ('cold, fire and physical', 'resistance', '10')):
        facts.append(dict(kind='nearby_resistance_tooltip_observation',
            action_recorded='Increases', target_phrase_recorded='all nearby allies',
            resistance_types_recorded=re.split(r', | and ', resistance.group(1)),
            increase_recorded=int(resistance.group(3)), energy_per_second_recorded=4,
            resistance_unit=None, nearby_radius=None, stacking=None, scaling=None,
            upkeep_tick_timing=None, duration_seconds=None, operative_values=None,
            conditions_unparsed=True))
    attack_speed = re.fullmatch(
        r'(Increases) the (melee attack speed) for (your gruop) by (12)%\.?'
        r'|(Increases) the (attack speed) of (your group) by (12)%\.?'
        r'|This voice melody (increases) the (attack speed) of (you and your allies) by (8) to (10)%\.?',
        value.strip())
    if attack_speed:
        groups = attack_speed.groups()
        offset = 0 if groups[0] else 4 if groups[4] else 8
        action, phrase, target, low = groups[offset:offset + 4]
        observation = dict(kind='group_attack_speed_tooltip_observation',
            action_recorded=action, target_phrase_recorded=target,
            attack_speed_phrase_recorded=phrase, stacking=None, scaling=None,
            base_attack_interval=None, attack_interval_formula=None,
            range_dependency=None, duration_seconds=None, operative_values=None,
            conditions_unparsed=True)
        if offset == 8:
            observation.update(increase_percent_min_recorded=int(low),
                               increase_percent_max_recorded=int(groups[12]))
        else:
            observation['increase_percent_recorded'] = int(low)
        facts.append(observation)
    movement = re.fullmatch(
        r'Increases the (movement speed|movement rate) of your group by (\d+)%\.?',
        value.strip())
    if movement and int(movement.group(2)) > 0:
        facts.append(dict(kind='group_movement_tooltip_observation',
            effect_word_recorded='Increases', target_phrase_recorded='your group',
            movement_word_recorded=movement.group(1),
            increase_percent_recorded=int(movement.group(2)),
            stacking=None, scaling=None, base_movement_speed=None,
            percent_interpretation=None, combat_applicability=None,
            duration_seconds=None, operative_values=None, conditions_unparsed=True))
    # Exact reviewed prose only: neither effect establishes complete action denial.
    if value.strip() == 'Lulls the target, preventing it from assisting nearby allies for 18 seconds.':
        facts.append(dict(kind='lull_tooltip_observation',
            effect_word_recorded='Lulls', target_phrase_recorded='the target',
            prevents_assisting_nearby_allies_recorded=True,
            duration_seconds_recorded=18, assistance_radius=None,
            prevents_actions=None, prevents_movement=None,
            target_level_limit=None, player_target_applicability=None,
            operative_values=None, conditions_unparsed=True))
    if value.strip() == 'Silences your opponent, preventing the casting of most spells for 10 seconds.':
        facts.append(dict(kind='silence_tooltip_observation',
            effect_word_recorded='Silences', target_phrase_recorded='your opponent',
            prevents_casting_recorded='most spells', duration_seconds_recorded=10,
            spell_exceptions=None, interrupts_active_cast=None,
            prevents_nonspell_abilities=None, target_level_limit=None,
            player_target_applicability=None, operative_values=None,
            conditions_unparsed=True))
    mesmerize = re.fullmatch(
        r'Mesmerizes your opponent, preventing any actions and movement for (18|24) '
        r'seconds or 1 hit\. Mesmerized targets begin to regenerate after 4 sec\. '
        r'Only one target can be mesmerized at once\.', value.strip())
    if mesmerize:
        facts.append(dict(kind='mesmerize_tooltip_observation',
            effect_word_recorded='Mesmerizes', prevents_actions_recorded=True,
            prevents_movement_recorded=True,
            duration_seconds_recorded=int(mesmerize.group(1)),
            hit_expiry_count_recorded=1, regeneration_delay_seconds_recorded=4,
            maximum_mesmerized_targets_recorded=1, hit_definition=None,
            regeneration_resource=None, regeneration_rate=None,
            regeneration_after_expiry=None, target_level_limit=None,
            player_target_applicability=None, operative_duration_seconds=None,
            conditions_unparsed=True))
    energy = re.fullmatch(
        r'Restores (\d+)-(\d+) energy to (your group) every (\d+) (?:secs|seconds)\.?',
        value.strip(), re.I)
    if energy:
        minimum, maximum, target, interval = energy.groups()
        minimum, maximum, interval = map(int, (minimum, maximum, interval))
        if 0 < minimum <= maximum and interval > 0:
            facts.append(dict(kind='periodic_energy_restoration_range_observation',
                energy_minimum_recorded=minimum, energy_maximum_recorded=maximum,
                pulse_interval_seconds_recorded=interval,
                target_phrase_recorded=target.lower(), total_duration_seconds=None,
                first_pulse_timing=None, scaling=None, energy_per_target=None,
                conditions_unparsed=True))
    healing = re.fullmatch(
        r'(?:A restoring chant that )?heals (you and your group|your group|you) '
        r'(?:for|by) (\d+)-(\d+) every (\d+) (?:secs|seconds)\.?',
        value.strip(), re.I)
    if healing:
        target, minimum, maximum, interval = healing.groups()
        minimum, maximum, interval = map(int, (minimum, maximum, interval))
        if 0 < minimum <= maximum and interval > 0:
            facts.append(dict(kind='periodic_healing_range_observation',
                healing_minimum_recorded=minimum, healing_maximum_recorded=maximum,
                pulse_interval_seconds_recorded=interval,
                target_phrase_recorded=target.lower(), total_duration_seconds=None,
                first_pulse_timing=None, scaling=None, healing_per_target=None,
                conditions_unparsed=True))
    fence = re.fullmatch(
        r'Raises your chance to parry incoming attacks by (\d+)% for (\d+) seconds '
        r'or until you parry\. This turns off your auto-attack\.', value.strip(), re.I)
    if fence:
        percent, duration = map(int, fence.groups())
        if percent > 0 and duration > 0:
            facts.append(dict(kind='conditional_parry_buff_observation',
                parry_chance_increase_percent_recorded=percent,
                duration_seconds_recorded=duration,
                early_expiry_condition_recorded='until you parry',
                auto_attack_disabled_recorded=True, percent_interpretation=None,
                guaranteed_parry=None, expiry_event_order=None,
                affected_attack_types=None, conditions_unparsed=True))
    echo = re.fullmatch(
        r'You shout after a successful parry, dealing (\d+) to (\d+) damage '
        r'and restoring (\d+) of your endurance\. Only usable after you parry\.',
        value.strip(), re.I)
    if echo:
        minimum, maximum, endurance = map(int, echo.groups())
        if 0 < minimum <= maximum and endurance > 0:
            facts.append(dict(kind='parry_damage_endurance_observation',
                damage_minimum_recorded=minimum, damage_maximum_recorded=maximum,
                endurance_restored_recorded=endurance,
                prerequisite_recorded='successful parry', damage_school=None,
                damage_target=None, activation_window_seconds=None, scaling=None,
                conditions_unparsed=True))
    charm = re.fullmatch(
        r'Charms your opponent, forcing it to fight for you for (\d+) seconds\. '
        r'Effective on targets level (\d+) and lower\.', value.strip(), re.I)
    if charm:
        duration, level = map(int, charm.groups())
        if duration > 0 and level > 0:
            facts.append(dict(kind='charm_duration_target_level_observation',
                charm_duration_seconds_recorded=duration,
                maximum_target_level_recorded=level, target_recorded='opponent',
                resist_check=None, break_conditions=None,
                player_target_applicability=None, stacking=None,
                conditions_unparsed=True))
    needle = re.fullmatch(
        r"A fast piercing attack that deals (\d+)% of weapon damage and lowers your opponent's damage by (\d+) for (\d+) sec\.",
        value.strip(), re.I)
    if needle:
        percent, reduction, duration = map(int, needle.groups())
        if percent > 0 and reduction > 0 and duration > 0:
            facts.append(dict(kind='weapon_damage_and_opponent_reduction_observation',
                weapon_damage_percent_recorded=percent,
                opponent_damage_reduction_recorded=reduction,
                reduction_duration_seconds_recorded=duration,
                damage_reduction_unit=None, weapon_damage_basis=None,
                damage_school=None, target_recorded='opponent', stacking=None,
                conditions_unparsed=True))
    chant = re.fullmatch(
        r'You begin to chant (?:vile|fiery|chilling) words, inflicting (\d+) to (\d+) '
        r'(physical|fire|cold) damage over (\d+) seconds\.', value.strip(), re.I)
    if chant:
        lower, upper, damage_type, duration = chant.groups()
        if int(lower) <= int(upper) and int(duration) > 0:
            facts.append(dict(kind='damage_over_duration_range_observation',
                values=[int(lower), int(upper)], damage_type_recorded=damage_type.lower(),
                duration_seconds=int(duration), tick_interval_seconds=None,
                tick_count=None, damage_per_tick=None, target_recorded=None,
                range_basis=None, conditions_unparsed=True))
    # Some embedded tooltips append Details labels after the complete sentence.
    # Only the explicit Cost label is a boundary; trailing prose is not discarded.
    bellow = re.match(
        rf'You bellow, blasting your opponent for {num}(?: to |-){num} arcane damage\.(?=$| Cost:)',
        value.strip(), re.I)
    if bellow:
        lower, upper = map(numeric, bellow.groups())
        if lower <= upper:
            facts.append(dict(kind='damage_range', values=[lower, upper],
                damage_type_recorded='arcane', target_recorded='your opponent',
                range_basis=None, conditions_unparsed=True))
    counter_removal = re.fullmatch(
        r'(?:Purifies|Cures) all group members within (\d+)m, removing (\d+) (disease|poison) counters\.',
        value.strip(), re.I)
    if counter_removal:
        radius, count, counter_type = counter_removal.groups()
        if int(radius) > 0 and int(count) > 0:
            facts.append(dict(kind='group_counter_removal_observation',
                counter_type_recorded=counter_type.lower(), counters_removed=int(count),
                target_recorded='all group members',
                radius_recorded=dict(value=int(radius), unit='m'), conditions_unparsed=True))
    group_restoration = re.fullmatch(
        rf'Restores {num} to {num} energy, depending on your level, to your group every {num} sec\.',
        value.strip(), re.I)
    if group_restoration:
        lower, upper, interval = map(numeric, group_restoration.groups())
        if lower <= upper and interval > 0:
            facts.append(dict(kind='periodic_group_energy_restoration_range_observation',
                values=[lower, upper], resource='energy', interval_seconds=interval,
                target_recorded='your group', scaling_condition_recorded='depending on your level',
                level_to_value_mapping=None, range_basis=None, conditions_unparsed=True))
    compound_restoration = re.fullmatch(
        rf'Reduces Song cost by {num} and restores {num} hit points every {num} seconds\.',
        value.strip(), re.I)
    if compound_restoration:
        cost, amount, interval = map(numeric, compound_restoration.groups())
        if interval > 0:
            facts.extend([
                dict(kind='song_cost_reduction_observation', values=[cost],
                    resource=None, unit=None, conditions_unparsed=True),
                dict(kind='periodic_hit_point_restoration_observation', values=[amount],
                    resource_recorded='hit points', interval_seconds=interval,
                    target_recorded=None, conditions_unparsed=True)])
    song_cost = re.fullmatch(
        rf'(?:This rest song reduces|Reduces?) song cost by {num}\.?',
        value.strip(), re.I)
    if song_cost:
        facts.append(dict(kind='song_cost_reduction_observation',
            values=[numeric(song_cost.group(1))], resource=None, unit=None,
            conditions_unparsed=True))
    group_attributes = re.fullmatch(
        rf'Increases the (strength|dexterity|intelligence|wisdom|constitution|vitality) and '
        rf'(strength|dexterity|intelligence|wisdom|constitution|vitality) of your group by {num}-{num}\.?',
        value.strip(), re.I)
    if group_attributes:
        first, second, lower, upper = group_attributes.groups()
        if first.lower() != second.lower() and numeric(lower) <= numeric(upper):
            facts.append(dict(kind='group_attribute_range_observation',
                attributes_recorded=[first.lower(), second.lower()],
                values=[numeric(lower), numeric(upper)], target_recorded='your group',
                range_basis=None, conditions_unparsed=True))
    patterns = [
        ('damage_range', rf'\b(?:deals?|inflicts?|inflicting)\s+(?:an additional\s+)?{num}\s+to\s+{num}\s+damage'),
        ('damage_bonus', rf'\b(?:normal|weapon|melee) damage\s+(?:plus|by)\s+{num}(?!\d|%|\.\d)'),
        ('damage_bonus', rf'\bincreases melee damage by\s+{num}(?!\d|%|\.\d)'),
        ('damage_percent', rf'\b{num}%\s+(?:weapon\s+)?damage'),
    ]
    for kind, pattern in patterns:
        for match in re.finditer(pattern, value, re.I):
            numbers = [numeric(n) for n in match.groups()]
            fact = dict(kind=kind, values=numbers, conditions_unparsed=True)
            if fact not in facts:
                facts.append(fact)
    pattern = rf'\b(?:restoring|restores)\s+{num}\s+to\s+{num}\s+(energy|endurance|mana)\s+over\s+{num}\s+seconds?'
    for match in re.finditer(pattern,value,re.I):
        facts.append(dict(kind='resource_restoration', resource=match.group(3).lower(),
                          values=[numeric(match.group(1)),numeric(match.group(2))],
                          duration_seconds=numeric(match.group(4)),conditions_unparsed=True))
    heal=rf'\b(?:heals?|healing)\s+(your defensive target|an ally|your allies|it|all allies within {num}m)\s+for\s+{num}(?:\s+to\s+{num})?(?!\d|%|\.\d)(?!\s+to\s+\d)(?:\s+over\s+{num}\s+(?:sec|seconds?)\b)?'
    for match in re.finditer(heal,value,re.I):
        target,radius,amount,upper,duration=match.groups()
        facts.append(dict(kind='healing_amount',values=[numeric(amount)]+([numeric(upper)] if upper else []),
            target_recorded=target,radius_recorded=dict(value=numeric(radius),unit='m') if radius else None,
            duration_seconds=numeric(duration) if duration else None,conditions_unparsed=True))
    periodic=rf'\b(?:restores|restoring)\s+{num}\s+(energy|endurance|mana)\s+every\s+{num}\s+(?:sec|seconds?)\b'
    for match in re.finditer(periodic,value,re.I):
        facts.append(dict(kind='periodic_resource_restoration',values=[numeric(match.group(1))],
            resource=match.group(2).lower(),interval_seconds=numeric(match.group(3)),conditions_unparsed=True))
    attribute = rf"\b(?:increases?|increasing)\s+(?:your|the users|the user's)\s+(strength|dexterity|intelligence|wisdom|constitution|vitality)\s+by\s+{num}(?!\d|%|\.\d|\s+%)"
    for match in re.finditer(attribute, value, re.I):
        facts.append(dict(kind='attribute_increase', attribute=match.group(1).lower(),
            values=[numeric(match.group(2))], conditions_unparsed=True))
    sleep = rf'\bputs the target into a deep sleep for\s+{num}\s+(?:sec|seconds?)\b'
    for match in re.finditer(sleep, value, re.I):
        facts.append(dict(kind='crowd_control_duration', effect='sleep',
            duration_seconds=numeric(match.group(1)), conditions_unparsed=True))
    effect_duration = rf'\bthis effect will stay on the user for\s+{num}\s+(hours?|minutes?|seconds?|sec)\b'
    for match in re.finditer(effect_duration, value, re.I):
        amount = numeric(match.group(1))
        unit = match.group(2).lower()
        multiplier = 3600 if unit.startswith('hour') else 60 if unit.startswith('minute') else 1
        facts.append(dict(kind='effect_duration', duration_seconds=amount * multiplier,
            conditions_unparsed=True))
    proc = rf'\b{num}% chance on attack to heal wearer\b'
    for match in re.finditer(proc, value, re.I):
        chance = numeric(match.group(1))
        if 0 <= chance <= 100:
            facts.append(dict(kind='trigger_chance_observation', chance_percent=chance,
                trigger_recorded='attack', action_recorded='heal wearer',
                healing_amount=None, conditions_unparsed=True))
    critical = rf'\battacks have a\s+{num}% greater chance of scoring a critical hit\b'
    for match in re.finditer(critical, value, re.I):
        facts.append(dict(kind='critical_chance_increase_observation', values=[numeric(match.group(1))],
            unit='percent', basis_unresolved=True, conditions_unparsed=True))
    modifier = r'([+-]\d+(?:\.\d+)?)\s+(Arcane Spell Damage|Spiritual Spell Damage|Health|Arcane Absorption|Spiritual Absorption)\b'
    for match in re.finditer(modifier, value, re.I):
        facts.append(dict(kind='effect_stat_modifier_observation', stat_recorded=match.group(2),
            values=[numeric(match.group(1))], conditions_unparsed=True))
    return facts


def section_nodes(main, label):
    for heading in main.find_all(['h2', 'h3']):
        if re.sub(r'\s+', ' ', text(heading)).lower().split(' (')[0] == label.lower():
            result = []
            for sibling in heading.next_siblings:
                if getattr(sibling, 'name', None) in ('h1', 'h2', 'h3'):
                    break
                if getattr(sibling, 'name', None):
                    result.append(sibling)
            return result
    return []


def field(record, *labels):
    for label in labels:
        values = record.get('archive_fields', {}).get(label, [])
        if values:
            return values[0]
    return None


def role_services(role):
    role = (role or '').lower()
    services = []
    for pattern, service in [(r'\bmerchant\b|\bvendor\b', 'merchant'), (r'\brepair', 'repair'),
                             (r'\bbanker\b', 'banker'), (r'\btrainer\b|\binstructor\b', 'trainer'),
                             (r'\btask ?master\b', 'task master'), (r'\bbroker\b', 'broker'),
                             (r'\bmailbox\b', 'mailbox'), (r'\brift keeper\b|\briftway\b', 'riftway')]:
        if re.search(pattern, role):
            services.append(service)
    return services


def denominations(value):
    value = value.strip().lower().replace(',', '')
    if re.fullmatch(r'\d+c', value):
        return int(value[:-1])
    matches = re.findall(r'(\d+)\s*(platinum|gold|silver|copper)\b', value)
    remainder = re.sub(r'\d+\s*(?:platinum|gold|silver|copper)\b', '', value).strip(' ,')
    if not matches or remainder:
        return None
    units = dict(copper=1, silver=100, gold=10000, platinum=1000000)
    return sum(int(n) * units[unit] for n, unit in matches)


def table_items(nodes):
    """Recognize labelled game-item rows, not arbitrary tables or guide prose."""
    items = []
    for node in nodes:
        tables = [node] if node.name == 'table' else node.find_all('table')
        for table in tables:
            for row in table.find_all('tr'):
                cells = row.find_all('td', recursive=False)
                if len(cells) < 7:
                    continue
                quantity = re.fullmatch(r'(\d+)\s*x', text(cells[0]), re.I)
                if not quantity or not re.fullmatch(r'\[Clvl\s+\d+\]', text(cells[4]), re.I):
                    continue
                if not re.fullmatch(r'\[Ilvl\s+\d+\]', text(cells[5]), re.I):
                    continue
                name = text(cells[6])
                if name:
                    items.append(dict(item=name, count=int(quantity.group(1)), item_type=text(cells[2]),
                                      slot_raw=text(cells[3]), character_level_raw=text(cells[4]), item_level_raw=text(cells[5])))
    return items


def enrich_item(record, main):
    notes = []
    classes = []
    for node in section_nodes(main, 'Usable by'):
        for link in node.find_all('a', href=True):
            # Read the class labels already on the page; never request filtered links.
            if link['href'].startswith('/classes/') or re.match(r'^/items\?(?:[^#]*&)?class=', link['href']):
                classes.append(text(link))
    if classes:
        record['class_restrictions'] = list(dict.fromkeys(classes))
    record['zone'] = field(record, 'zone')
    for labels, target in [(('stack size', 'max stack'), 'stack_size'), (('capacity', 'slots'), 'bag_slots'),
                           (('value', 'sell value'), 'value_copper')]:
        raw = field(record, *labels)
        if raw:
            value = denominations(raw) if target == 'value_copper' else numeric(raw)
            if value is not None:
                record[target] = value
    raw_damage = field(record, 'damage')
    if raw_damage:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)', raw_damage)
        if match and float(match.group(1)) <= float(match.group(2)):
            record['damage'] = [numeric(match.group(1)), numeric(match.group(2))]
    raw_delay = field(record, 'delay', 'speed')
    if raw_delay:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)', raw_delay, re.I)
        if match:
            record['delay_seconds'] = numeric(match.group(1))
    raw_bind = (field(record, 'bind', 'binding') or '').lower()
    if raw_bind in ('on equip', 'bind on equip'):
        record['bind'] = 'on equip'
    elif raw_bind in ('on pickup', 'bind on pickup'):
        record['bind'] = 'on pickup'
    # Explicit flags can be preserved without pretending that Soulbound specifies a binding trigger.
    flags = []
    for node in main.select('.tt-fields .tt-line'):
        content = text(node)
        if content in ('No Trade', 'Unique', 'Soulbound', 'No Drop'):
            flags.append(content)
    if flags:
        record['flags_recorded'] = list(dict.fromkeys(flags))
    effects = []
    for node in section_nodes(main, 'Effects'):
        paragraphs = [node] if node.name == 'p' else node.find_all('p')
        for paragraph in paragraphs:
            name = paragraph.find('strong')
            if not text(name):
                continue
            description = paragraph.select_one('span.muted')
            effects.append(dict(name=text(name),
                activation_labels=list(dict.fromkeys(text(pill) for pill in paragraph.select('.pill'))),
                observations=effect_facts(text(description)) or None))
    if effects:
        record['archive_item_effects'] = effects
        notes.append('Explicit item-effect names and activation labels recorded. Numeric observations retain unresolved conditions; unknown or malformed effect mechanics are not inferred.')
    return notes


def enrich_quest(record, main):
    notes = []
    if not record.get('turn_in'):
        record['turn_in'] = field(record, 'hand in to', 'turn in to', 'ends with')
    record['quest_chain'] = dict(name=field(record, 'series'), position=None) if field(record, 'series') else None
    required = table_items(section_nodes(main, 'Quest Required Items'))
    if required:
        record['archive_required_items'] = required
    reward_nodes = section_nodes(main, 'Quest Rewards')
    reward_items = table_items(reward_nodes)
    reward_values = []
    for node in reward_nodes:
        if node.name == 'table':
            continue
        for line in node.get_text('\n', strip=True).splitlines():
            coin = denominations(line)
            xp = re.fullmatch(r'([\d,]+)\s*(?:XP|experience)', line, re.I)
            scoped_xp = re.fullmatch(r'([\d,]+)\s*(?:XP|experience)\s+at\s+(?:Lvl|Level)\s+(\d+)', line, re.I)
            if scoped_xp:
                record.setdefault('archive_level_reward_observations', []).append(dict(
                    kind='xp', value=int(scoped_xp.group(1).replace(',', '')),
                    player_level=int(scoped_xp.group(2)), raw=line))
            if coin is not None:
                reward_values.append(dict(kind='coin_copper', value=coin))
            if xp:
                reward_values.append(dict(kind='xp', value=int(xp.group(1).replace(',', ''))))
    for key in ('xp', 'coin_copper'):
        values = list(dict.fromkeys(entry['value'] for entry in reward_values if entry['kind'] == key))
        if len(values) == 1:
            previous = record['rewards'].get(key)
            if previous is not None and previous != values[0]:
                record['confidence'] = 'low'
                notes.append(f'Conflicting {key}: field gives {previous}, reward section gives {values[0]}; both retained in archive_reward_values.')
            else:
                record['rewards'][key] = values[0]
        elif len(values) > 1:
            record['confidence'] = 'low'
            notes.append(f'Multiple {key} values in rewards; not combined.')
    if reward_values:
        record['archive_reward_values'] = reward_values
    if reward_items:
        record['archive_reward_items'] = reward_items
        reward_text = ' '.join(text(node) for node in reward_nodes)
        if re.search(r'\bchoose one of\b', reward_text, re.I):
            record['rewards']['choice'] = list(dict.fromkeys(r['item'] for r in reward_items))
        else:
            # A list of rewards without an explicit choice/all rule remains unresolved.
            notes.append('Reward item rows found, but a guaranteed-versus-choice rule was not explicit; retained for review.')

    objective_nodes = section_nodes(main, 'Objectives')
    objective_text = '\n'.join(node.get_text('\n', strip=True) for node in objective_nodes)
    counters = []
    for match in re.finditer(r'(?m)(?:^|(?<=\n)|(?<=\))|(?<= - )|(?<=\. ))\s*([^\n().!?]{1,100}?)\s*\((?:\d+\s*/\s*)?(\d+)\)', objective_text):
        label = re.sub(r'^-\s+', '', match.group(1).strip())
        count = int(match.group(2))
        if not label or re.search(r'[.!?]', label):
            continue
        # This is an explicit tracker counter, not a deduction from a walkthrough.
        counters.append(dict(label=label, count=count, objective=match.group(0).strip()))
    if counters:
        record['archive_objective_counters'] = counters
        steps = []
        entity_names = [e['name'] for e in record.get('referenced_entities', []) if '/mobs/' in e['url']]
        for counter in counters:
            label, count = counter['label'], counter['count']
            kind, target = None, None
            kill_prefix = re.fullmatch(r'(?:slay|kill)\s+(.+)', label, re.I)
            if kill_prefix:
                kind = 'kill'
                candidate = kill_prefix.group(1).strip()
                target = candidate if candidate in entity_names else None
            elif label.lower().endswith(' slain'):
                kind = 'kill'
                candidate = label[:-6].strip()
                target = candidate if candidate in entity_names else None
            else:
                candidates = [r['item'] for r in required if r['count'] == count and r['item_type'].lower() == 'quest item']
                if label in candidates:
                    kind, target = 'collect', label
                elif len(candidates) == 1 and re.search(r'\bcollect\b|\bgather\b|\bretrieve\b', objective_text, re.I):
                    kind, target = 'collect', candidates[0]
                elif re.search(r'\bcollect\b|\bgather\b|\bretrieve\b', objective_text, re.I):
                    # The tracker supplies the item name exactly; no singularization or typo correction.
                    kind, target = 'collect', label
            steps.append(dict(objective=counter['objective'], kind=kind, target=target, count=count))
        # Only claim the step list is complete when the source contains nothing beyond these counters.
        residual = objective_text
        for counter in counters:
            residual = residual.replace(counter['objective'], '')
        record['steps'] = steps if not residual.strip() and all(s['kind'] and s['target'] for s in steps) else None
        record['candidate_steps'] = steps
        if record['steps'] is None:
            notes.append('Explicit tracker counters extracted, but complete objective coverage or exact targets remain unresolved; candidate_steps are not conversion-ready steps.')
    return notes


def enrich_ability(record, main):
    notes = []
    record['target_recorded']=field(record,'target')
    head=main.select_one('.detail-head')
    aliases=[]
    if head:
        for paragraph in head.find_all('p'):
            value=text(paragraph)
            if value.startswith('Also recorded as '):
                aliases.append(value.removeprefix('Also recorded as '))
    if aliases:
        record['aliases_recorded']=list(dict.fromkeys(aliases))
    levels=[]
    for label,values in record.get('archive_fields',{}).items():
        if not re.fullmatch(r'level in \d{4}(?:-\d{4})?',label):
            continue
        for raw in values:
            match=re.fullmatch(r'(\d+)(?:\s*[—–]\s*now\s*\d+)?',raw)
            if match:
                levels.append(dict(scope=label,level_learned=int(match.group(1)),raw=raw))
    if levels:
        record['historical_level_observations']=levels
        notes.append('Historical learned levels are separate from the current labelled level; no patch-era value substituted.')
    historical_sources=[]
    for node in section_nodes(main,'As it was earlier'):
        for link in node.find_all('a',href=True):
            if link['href'].startswith(('http://','https://')) and not link['href'].startswith('https://vgsoharchive.com'):
                if link['href'] not in historical_sources:
                    historical_sources.append(link['href'])
    if historical_sources:
        record['historical_source_urls_recorded']=historical_sources
    rank = re.search(r'\s([IVX]+)$',record['name'])
    if record.get('rank') is None and rank:
        record['rank'] = rank.group(1)
    cost_values = {resource: [] for resource in ('mana','energy','endurance')}
    for resource in cost_values:
        for raw in record.get('archive_fields',{}).get(resource+' cost',[]):
            value=numeric(raw)
            if value is not None and value>=0:
                cost_values[resource].append(value)
    raw_cost = field(record,'cost')
    if raw_cost:
        matches=re.findall(r'(\d+)\s*(mana|energy|endurance)\b',raw_cost,re.I)
        residue=re.sub(r'\d+\s*(?:mana|energy|endurance)\b','',raw_cost,flags=re.I).strip(' ,+')
        if not residue:
            for value,resource in matches:
                cost_values[resource.lower()].append(int(value))
    observed={resource:list(dict.fromkeys(values)) for resource,values in cost_values.items() if values}
    if observed:
        record['cost_observations']=observed
        if all(len(values)==1 for values in observed.values()):
            record['cost']={resource:values[0] for resource,values in observed.items()}
        else:
            record['cost']=None
            record['confidence']='low'
            notes.append('Contradictory labelled resource costs retained in cost_observations; no operative cost chosen.')
    timings = {}
    for label, target in [('cast time', 'cast_time_seconds'), ('refresh', 'refresh_seconds'),
                          ('recast', 'refresh_seconds'), ('duration', 'duration_seconds')]:
        for raw in record.get('archive_fields', {}).get(label, []):
            value = None
            if raw.lower()=='instant':
                value = 0
            else:
                match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(s|secs?|seconds?|minutes?)', raw, re.I)
                if match:
                    value = numeric(match.group(1))
                    if match.group(2).lower().startswith('minute'):
                        value *= 60
            if value is not None:
                timings.setdefault(target, []).append(dict(label=label, raw=raw, seconds=value))
    if timings:
        record['timing_observations'] = timings
        for target, observations in timings.items():
            values = list(dict.fromkeys(o['seconds'] for o in observations))
            record[target] = values[0] if len(values) == 1 else None
            if len(values) > 1:
                record['confidence'] = 'low'
                notes.append(f'Contradictory {target} values retained in timing_observations; no operative timing chosen.')
    raw_range = field(record, 'range')
    if raw_range:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(m|meters?|feet|ft)', raw_range, re.I)
        if match:
            record['range'] = dict(value=numeric(match.group(1)), unit=match.group(2).lower(), raw=raw_range)
        interval = re.fullmatch(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(m|meters?|feet|ft)', raw_range, re.I)
        if interval and numeric(interval.group(1)) <= numeric(interval.group(2)):
            record['range_interval_reported_by_archive'] = dict(
                minimum=numeric(interval.group(1)), maximum=numeric(interval.group(2)),
                unit=interval.group(3).lower(), raw=raw_range,
                historical_authentication=None)
    record['trainer'] = field(record, 'learned from', 'trainer')
    record['requirements']=field(record,'requires')
    record['causes_weakness']=field(record,'causes weakness','causes')
    record['exploits_weakness']=field(record,'exploits weakness')
    observations=[]
    for heading,scope in [('Effect','current'),('Alternate description','alternate'),('As it was earlier','historical')]:
        parts=section_nodes(main,heading)
        tips=[]
        for node in parts:
            if 'tooltip' in node.get('class',[]):
                tips.append(node)
            tips.extend(node.select('.tooltip'))
        for tip in tips:
            value=text(tip)
            facts=effect_facts(value)
            if facts:
                observations.append(dict(scope=scope,facts=facts))
            if scope=='current' and record.get('tooltip') is None and len(value.split())<=25:
                record['tooltip']=value
    if observations:
        record['effect_observations']=observations
        if any(o['scope']!='current' for o in observations):
            notes.append('Current, alternate and historical effect figures are separate observations; no single historical ruleset selected.')
    note_text=' '.join(text(n) for n in section_nodes(main,'Notes'))
    if 'Read from the in-game tooltip' in note_text:
        record['verification_reported_by_archive']='tooltip read in VGO Emulator; not independently verified by this collector'
    elif 'tooltip has not been read' in note_text:
        record['verification_reported_by_archive']='spellbook existence only; numerical tooltip unverified'
    if any(text(n.select_one('strong')) == 'Not in the emulator.'
           for n in main.select('p.absent-note')):
        record['emulator_absence_reported_by_archive'] = dict(
            reported_absent=True, independently_verified=False,
            emulator_build=None, historical_authentication=None)
    return notes


def enrich_recipe(record, main):
    notes=[]
    record['crafting_stage']=field(record,'sub-class')
    record['skill']=field(record,'skill')
    for heading,target in [('Ingredients','ingredients'),('Tools','tools'),('Utilities','utilities'),('Enhancements','enhancements_recorded'),('Produces','products_recorded')]:
        observations=[]
        for node in section_nodes(main,heading):
            for li in node.select('ul.component-list > li'):
                copy=BeautifulSoup(str(li),'html.parser').find('li')
                guide=bool(copy.select('.guide-mark'))
                quantity=copy.select_one('.qty')
                raw_quantity=text(quantity) if quantity else None
                count_match=re.fullmatch(r'\((\d+)\)',raw_quantity or '')
                count=int(count_match.group(1)) if count_match else None
                link=copy.find('a',href=re.compile(r'^/items/[^/?#]+$'))
                name=text(link) if link else None
                for hidden in copy.select('.tt, .guide-mark, .qty'):
                    hidden.decompose()
                name=name or text(copy)
                if not name:
                    continue
                observations.append(dict(item=name,count=count,quantity_raw=raw_quantity,
                    item_ref_url='https://vgsoharchive.com'+link['href'] if link else None,
                    evidence_scope='launch-era guide; unconfirmed by archive' if guide else 'archive recorded'))
        if observations:
            record[target]=observations
            if any(o['evidence_scope'].startswith('launch-era') for o in observations):
                record['confidence']='low'
        if target=='ingredients' and observations:
            notes.append('Ingredient rows preserve the printed list; simultaneous requirements versus alternative materials are unverified. Missing quantities remain null.')
    raw_level=field(record,'recipe level')
    if raw_level and numeric(raw_level) is None:
        record['confidence']='low'
        notes.append('Recipe level is a nonnumeric source placeholder; no level inferred.')
    if record.get('products_recorded'):
        notes.append('Listed products are candidate outcomes, not a guaranteed single output; output remains unknown.')
    return notes


def enrich_record(record, main):
    if record['type'] in ('creature', 'npc'):
        observations = []
        for node in section_nodes(main, 'Where they stood') if main is not None else []:
            for row in node.find_all('li'):
                zones = [dict(name=text(a), url='https://vgsoharchive.com'+a['href'])
                         for a in row.find_all('a', href=re.compile(r'^/zones/[^/?#]+$'))]
                coordinates = re.search(r'—\s*([+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?)(?:\s|$)', text(row))
                observations.append(dict(source_text=text(row), zone_links=zones,
                    coordinates_raw=coordinates.group(1) if coordinates else None,
                    coordinate_format=None, spawn_certainty=None))
        record['map_location_observations'] = observations or None
    if record['type'] == 'creature':
        for target, label in [('continent', 'continent'),
                              ('locations_seen_recorded', 'locations seen'),
                              ('difficulty_recorded', 'difficulty')]:
            values = record.get('archive_fields', {}).get(label, [])
            record[target] = values[0] if len(values) == 1 else None
        return []
    if record['type'] == 'item':
        return enrich_item(record, main)
    if record['type'] == 'quest':
        return enrich_quest(record, main)
    if record['type'] == 'ability':
        return enrich_ability(record, main)
    if record['type'] == 'recipe':
        return enrich_recipe(record, main)
    if record['type'] == 'npc':
        role=field(record,'role')
        services = role_services(role)
        record['services'] = list(dict.fromkeys(record.get('services', []) + services))
        record['title'] = field(record, 'title')
        trainer=re.fullmatch(r'Class Trainer\s*[-–—]\s*(.+)',role or '',re.I)
        if trainer:
            record['trainer_of']=trainer.group(1).strip()
            record['training_classes_recorded']=[record['trainer_of']]
        record['continent']=field(record,'continent')
        record['locations_seen_recorded']=field(record,'locations seen')
        record['difficulty_recorded']=field(record,'difficulty')
        return []
    return []


def class_abilities(main, class_name, common):
    """Extract only labelled ability-table facts; bare cost/range numbers keep unknown units."""
    records = []
    unchecked = set()
    for node in section_nodes(main, 'Not yet checked against the client'):
        unchecked.update(a.get('href') for a in node.find_all('a', href=True))
    for table in main.find_all('table'):
        headers = [text(h).lower() for h in table.find_all('th')]
        if headers[:7] != ['lv', 'ability', 'school', 'cost', 'cast', 'range', 'effect']:
            continue
        for row in table.select('tbody tr'):
            cells = row.find_all('td', recursive=False)
            if len(cells) < 7:
                continue
            link = cells[1].find('a', href=re.compile(r'^/abilities/[^/?#]+$'))
            level = numeric(text(cells[0]))
            if not link or not isinstance(level, int) or level < 0:
                continue
            name = text(link)
            rank = re.search(r'\s([IVX]+)$', name)
            cast = text(cells[4])
            record = dict(common, type='ability', name=name, **{'class':class_name}, level_learned=level,
                rank=rank.group(1) if rank else None, category=text(cells[2]) or None,
                cost=None, cast_time_seconds=0 if cast.lower() == 'instant' else None,
                refresh_seconds=None, duration_seconds=None, range=None, tooltip=None,
                ability_ref_url='https://vgsoharchive.com'+link['href'],
                cost_recorded=dict(value=numeric(text(cells[3])), resource=None, raw=text(cells[3]) or None),
                range_recorded=dict(value=numeric(text(cells[5])), unit=None, raw=text(cells[5]) or None),
                cast_recorded=dict(value=numeric(cast), unit=None, raw=cast or None),
                notes='Explicit class-table facts. Cost resource and bare timing/range units are unknown; effect prose and truncated tooltips are not copied. Individual ability page still needs review.')
            # Each row owns its evidence list. Merging a shared spell across classes must not
            # add unrelated class-page citations to all other abilities from the first class.
            record['sources'] = [dict(source) for source in common['sources']]
            record['referenced_entities'] = [dict(name=name, url=record['ability_ref_url'])]
            record['archive_fields'] = {}
            if link['href'] in unchecked:
                record['confidence'] = 'low'
                record['notes'] += ' Listed as not yet checked against the client.'
            records.append(record)
    return records


def class_trainers(main, common):
    """Trainer roles and labelled locations from canonical class trainer lists."""
    class_link=main.find('a',href=re.compile(r'^/classes/[^/?#]+$'))
    class_name=text(class_link) or None
    records=[]
    for node in main.select('.trainer-body'):
        link=node.find('a',href=re.compile(r'^/mobs/[^/?#]+$'))
        if not link:
            continue
        zone_link=node.find('a',href=re.compile(r'^/zones/[^/?#]+$'))
        loc=node.find('code')
        raw=text(loc) if loc else None
        location=None
        if raw:
            numeric_loc=bool(re.fullmatch(r'/loc\s+[+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?',raw))
            location=dict(raw=raw,format='/loc as printed by source' if numeric_loc else 'descriptive source /loc label',chunk=None)
        labels=[]
        for span in node.find_all('span',recursive=False):
            if not span.find(['a','code']) and 'civic parley' not in text(span).lower():
                if text(span):labels.append(text(span))
        continent=node.find_previous('h3',class_='trainer-continent')
        record=dict(common,type='npc',name=text(link),sources=[dict(s) for s in common['sources']],
                    level=None,race=None,health=None,damage=None,zone=text(zone_link) or None,
                    chunk=None,location=location,services=['trainer'],trainer_of=class_name,
                    region_labels=labels,continent=text(continent) or None,
                    npc_ref_url='https://vgsoharchive.com'+link['href'],
                    referenced_entities=[dict(name=text(link),url='https://vgsoharchive.com'+link['href'])],
                    notes='Explicit class-trainer listing. Race, level and health unknown. Unlinked region labels are preserved without guessing a zone or chunk. Textual /loc labels are not numeric spawn coordinates.')
        records.append(record)
    return records
