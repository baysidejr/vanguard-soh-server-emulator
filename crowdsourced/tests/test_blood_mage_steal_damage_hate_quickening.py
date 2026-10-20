import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_steal_damage_hate_quickening_observation'
class BloodMageStealDamageHateQuickeningTests(unittest.TestCase):
    def test_quickening_keeps_recipients_and_durations_separate(self):
        literal = 'Attaches a quickening symbiote to an ally, this symbiote grants you the use of an ability that doubles your damage for 8 seconds. This symbiote lasts for 1 hour. Expends 1 Quickening Symbiote. Only 1 Symbiote allowed on a target at a time.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['recipient_reported'], fact['granted_ability_recipient_reported']), ('an ally', 'you'))
        self.assertEqual((fact['duration_seconds'], fact['damage_buff_duration_seconds']), (3600, 8))
        self.assertIsNone(fact['activation_rules'])
        self.assertIsNone(fact['damage_scaling_basis'])
        for altered in (literal.replace('8 seconds', '9 seconds'), literal + ' Only against undead.'):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(altered)))
    def test_return_scaling_does_not_invent_a_base(self):
        fact, = [f for f in effect_facts('Steals 485 to 512 health from your opponent and returns 100% of it to allies within 10m of the caster. Increases the returned portion by 10% per level of Blood Union. Increases Blood Union by 2.') if f['kind'] == KIND]
        self.assertEqual((fact['health_stolen_min'], fact['health_stolen_max'], fact['returned_percent']), (485, 512, 100))
        for key in ('scaling_base', 'operative_values', 'historical_authentication', 'tick_interval_seconds'):
            self.assertIsNone(fact[key])
