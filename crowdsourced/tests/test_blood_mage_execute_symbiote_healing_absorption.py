import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_execute_symbiote_healing_absorption_observation'
class BloodMageExecuteSymbioteHealingAbsorptionTests(unittest.TestCase):
    def test_execute_does_not_invent_chance(self):
        literal='Has a chance to kill an opponent who is under 5% health. The chance to kill them increases for each level of Blood Union.'
        fact,=[f for f in effect_facts(literal) if f['kind']==KIND]
        self.assertEqual((fact['target_health_threshold_percent'],fact['threshold_comparison']),(5,'under'))
        for key in ('kill_chance_percent','chance_increase_per_blood_union_level','operative_values','historical_authentication'):
            self.assertIsNone(fact[key])
        for changed in (literal.replace('5%','6%'),literal+' Only against undead.'):
            self.assertFalse(any(f['kind']==KIND for f in effect_facts(changed)))
    def test_healing_does_not_invent_recipient_or_ticks(self):
        fact,=[f for f in effect_facts('Heals for 905 health over 16 seconds.') if f['kind']==KIND]
        self.assertEqual((fact['health_over_duration'],fact['duration_seconds']),(905,16))
        self.assertIsNone(fact['recipient_reported'])
        self.assertIsNone(fact['tick_interval_seconds'])
