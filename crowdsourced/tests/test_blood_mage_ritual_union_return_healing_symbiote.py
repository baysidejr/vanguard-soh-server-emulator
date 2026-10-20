import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_ritual_union_return_healing_symbiote_observation'
class BloodMageRitualUnionReturnHealingSymbioteTests(unittest.TestCase):
    def test_ritual_keeps_initial_and_periodic_damage_separate(self):
        literal = 'This ritual severs life from all opponents within 10m, dealing 350 to 370 damage and 479 to 506 over 10 sec. Reduces Blood Union by 3. Only usable from Blood Union 3.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['damage_min'], fact['damage_max']), (350, 370))
        self.assertEqual((fact['damage_over_duration_min'], fact['damage_over_duration_max'], fact['duration_seconds']), (479, 506, 10))
        self.assertEqual((fact['blood_union_reduction'], fact['required_blood_union']), (3, 3))
        self.assertIsNone(fact['radius_origin'])
        self.assertIsNone(fact['tick_interval_seconds'])
        for changed in (literal.replace('350', '351'), literal + ' Only against undead.'):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
    def test_healing_excludes_caster_without_assuming_scaling_base(self):
        literal = 'You use your blood to heal an ally, other than yourself, for 2334. Heals for an extra 2% per level of Blood Union.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual(fact['recipient_reported'], 'an ally, other than yourself')
        self.assertEqual(fact['healing_amount'], 2334)
        self.assertEqual(fact['extra_healing_percent_per_blood_union_level'], 2)
        for key in ('scaling_base', 'operative_values', 'historical_authentication'):
            self.assertIsNone(fact[key])
