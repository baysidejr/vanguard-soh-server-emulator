import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_healing_counter_symbiote_steal_observation'

class BloodMageHealingCounterSymbioteStealTests(unittest.TestCase):
    def test_proc_distinguishes_healing_window_from_buff_and_unknown_actor(self):
        literal = 'Attaches a renewing symbiote to an ally, giving its bearer a 5% chance on hit to be healed for 912 over 6 seconds. Lasts 30 minutes. Expends 1 Renewing Symbiote. Only 1 Symbiote allowed on a target at a time.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['proc_chance_percent'], fact['healing_amount'], fact['healing_duration_seconds'], fact['duration_seconds']), (5, 912, 6, 1800))
        for key in ('trigger_actor', 'proc_roll_rules', 'tick_interval_seconds', 'operative_values'):
            self.assertIsNone(fact[key])
        for changed in (literal.replace('5%', '10%'), literal.replace('on hit', 'when struck')):
            self.assertFalse(any(f['kind'] == KIND for f in effect_facts(changed)))

    def test_granted_ability_does_not_invent_healing_amount_or_identifier(self):
        literal = 'Attaches a conducive symbiote to an ally, this symbiote grants you the use of an ability that instantly heals an ally. This symbiote lasts for 1 hour. Expends 1 Conducive Symbiote. Only 1 Symbiote allowed on a target at a time.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['duration_seconds'], fact['consumed_quantity'], fact['maximum_symbiotes_per_target']), (3600, 1, 1))
        for key in ('granted_ability_identifier', 'granted_ability_healing_amount', 'historical_authentication'):
            self.assertIsNone(fact[key])
        self.assertFalse(any(f['kind'] == KIND for f in effect_facts(literal.replace('instantly heals', 'periodically heals'))))
