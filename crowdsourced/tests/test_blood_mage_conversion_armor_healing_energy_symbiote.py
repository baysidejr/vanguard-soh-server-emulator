import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_conversion_armor_healing_energy_symbiote_observation'
class BloodMageConversionArmorHealingEnergySymbioteTests(unittest.TestCase):
    def test_conversion_does_not_invent_rate_basis_or_rounding(self):
        literal = 'Draws on your physical power, transmuting 99% of your endurance into health at a 1500% rate. This process takes great toll on your physical power and lowers your damage by 25% for 10 seconds.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['endurance_consumed_percent'], fact['health_conversion_rate_percent']), (99, 1500))
        self.assertEqual((fact['damage_reduction_percent'], fact['damage_reduction_duration_seconds']), (25, 10))
        self.assertIsNone(fact['conversion_rate_basis'])
        self.assertIsNone(fact['conversion_rounding'])
        for changed in (literal.replace('1500%', '150%'), literal + ' Only in combat.'):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
    def test_symbiote_lifetime_is_not_discount_duration(self):
        literal = 'Attaches a vitalizing symbiote to an ally, giving its bearer a 10% chance on spell cast to gain a 50% energy cost reduction for one spell. Lasts 30 minutes. Expends 1 Vitalizing Symbiote. Only 1 Symbiote allowed on a target at a time.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['proc_chance_percent'], fact['energy_cost_reduction_percent'], fact['discounted_spell_count']), (10, 50, 1))
        self.assertEqual(fact['duration_seconds'], 1800)
        for key in ('proc_cooldown_seconds', 'proc_stacking_rules', 'eligible_spell_rules', 'operative_values', 'historical_authentication'):
            self.assertIsNone(fact[key])
        for changed in (literal.replace('one spell', 'two spells'), literal.replace('on spell cast', 'on spell hit')):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))
