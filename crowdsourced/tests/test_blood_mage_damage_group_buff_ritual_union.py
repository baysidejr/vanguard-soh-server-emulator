import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_damage_group_buff_ritual_union_observation'

class BloodMageDamageGroupBuffRitualUnionTests(unittest.TestCase):
    def test_full_union_does_not_invent_numeric_cap_or_cost_basis(self):
        literal = 'This ability consumes 25% health and 15% energy, but forms a full Blood Union with your enemy instantly.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['health_consumed_percent'], fact['energy_consumed_percent']), (25, 15))
        self.assertEqual(fact['blood_union_result_reported'], 'full')
        for key in ('blood_union_numeric_result', 'consumption_percentage_basis', 'operative_values', 'historical_authentication'):
            self.assertIsNone(fact[key])
        for changed in (literal.replace('25%', '20%'), literal + ' Only usable in combat.'):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))

    def test_ritual_retains_recipient_restriction_and_unstated_tick_interval(self):
        literal = 'This ritual heals an ally, other than yourself, for 4110 health over 20 seconds. Reduces Blood Union by 3. Only usable from Blood Union 3 or greater.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual(fact['recipient_reported'], 'an ally, other than yourself')
        self.assertEqual((fact['healing_amount'], fact['duration_seconds'], fact['blood_union_reduction'], fact['minimum_blood_union']), (4110, 20, 3, 3))
        self.assertIsNone(fact['tick_interval_seconds'])
        for changed in (literal.replace(', other than yourself', ''), literal.replace('3 or greater', '2 or greater')):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
