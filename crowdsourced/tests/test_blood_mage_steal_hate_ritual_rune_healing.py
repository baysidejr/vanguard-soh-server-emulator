import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_steal_hate_ritual_rune_healing_observation'

class BloodMageStealHateRitualRuneHealingTests(unittest.TestCase):
    def test_ritual_keeps_initial_and_periodic_damage_separate(self):
        literal = 'This ritual severs life from all opponents within 10m, dealing 430 to 454 damage and 591 to 624 over 10 sec. Reduces Blood Union by 3. Only usable from Blood Union 3.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['damage_min'], fact['damage_max'], fact['periodic_damage_min'], fact['periodic_damage_max']), (430, 454, 591, 624))
        self.assertEqual((fact['periodic_damage_duration_seconds'], fact['blood_union_cost_points'], fact['required_blood_union_reported']), (10, 3, 3))
        for key in ('periodic_damage_distribution', 'tick_interval_seconds', 'operative_values'):
            self.assertIsNone(fact[key])
        for changed in (literal.replace('over 10 sec', 'every 10 sec'), literal.replace('Only usable from Blood Union 3.', '')):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))

    def test_healing_total_has_no_invented_tick_amount_or_recipient(self):
        literal = 'Heals for 1200 health over 16 seconds.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['healing_amount'], fact['duration_seconds']), (1200, 16))
        for key in ('healing_distribution', 'recipient_reported', 'tick_interval_seconds', 'historical_authentication'):
            self.assertIsNone(fact[key])
        self.assertFalse(any(f['kind'] == KIND for f in effect_facts(literal.replace('over', 'every'))))
