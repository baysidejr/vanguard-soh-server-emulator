import re
import unittest
from archive_extract import effect_facts

CASES = {'You sufffer a 5% health loss every 5 seconds, but gain one point of Blood Union. All disease and poison counters are also reset on each tick.': {'effect_reported': 'periodic_health_loss_and_blood_union_gain', 'health_loss_percent': 5, 'tick_interval_seconds': 5, 'blood_union_gain_points': 1, 'counters_reset_reported': ['disease', 'poison'], 'health_loss_basis': None, 'duration_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None}, 'Lifetaps your opponent, draining their hit points, while adding it to yours. You gain a 20% health bonus for each level of Blood Union you have built up.': {'effect_reported': 'lifetap', 'recipient_reported': 'you', 'drain_target_reported': 'your opponent', 'health_bonus_percent_per_blood_union_level': 20, 'drain_amount': None, 'bonus_basis': None, 'duration_seconds': None, 'tick_interval_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None}, 'Your healing spells are increased by 25% effectiveness, your mitigation by 15% and you regain health faster than normal. This comes at the cost of reducing your spell damage by 50%, and reducing the effect of healing spells cast on you by 50%.': {'effect_reported': 'healing_mitigation_damage_tradeoff', 'healing_spell_effectiveness_increase_percent': 25, 'mitigation_increase_percent': 15, 'spell_damage_reduction_percent': 50, 'incoming_healing_spell_effect_reduction_percent': 50, 'health_regeneration_increase_amount': None, 'duration_seconds': None, 'tick_interval_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None}, 'Deals instant damage, followed by damage over time. Also increases your Blood Union by 1.': {'effect_reported': 'instant_and_periodic_damage_with_blood_union_gain', 'blood_union_gain_points': 1, 'instant_damage_amount': None, 'periodic_damage_amount': None, 'duration_seconds': None, 'tick_interval_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None}, 'Constricts the movement of your opponent, rooting them in place for 30 seconds. Has a 60% chance to break on hit.': {'effect_reported': 'root', 'recipient_reported': 'your opponent', 'duration_seconds': 30, 'break_on_hit_chance_percent': 60, 'hit_definition': None, 'tick_interval_seconds': None, 'stacking_rules': None, 'operative_values': None, 'historical_authentication': None}}

class BloodMageFocusObservations(unittest.TestCase):
    def test_source_values_and_unknowns(self):
        for literal, expected in CASES.items():
            with self.subTest(literal=literal):
                fact, = [f for f in effect_facts(literal) if f['kind'] == 'blood_mage_focus_lifetap_root_observation']
                for key, value in expected.items():
                    self.assertEqual(fact[key], value)
                self.assertTrue(fact['conditions_unparsed'])

    def test_altered_conditions_and_numbers_are_withheld(self):
        for literal in CASES:
            altered_number = re.sub(r'\d+', lambda m: str(int(m[0])+1), literal)
            for changed in (literal+' Only while resting.', altered_number):
                self.assertNotEqual(changed, literal)
                self.assertFalse(any(f['kind'] == 'blood_mage_focus_lifetap_root_observation' for f in effect_facts(changed)))
