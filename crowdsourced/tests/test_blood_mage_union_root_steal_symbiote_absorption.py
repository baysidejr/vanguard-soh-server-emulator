import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_union_root_steal_symbiote_absorption_observation'

class BloodMageUnionRootStealSymbioteAbsorptionTests(unittest.TestCase):
    def test_root_reports_break_chance_without_defining_hit(self):
        literal = 'Constricts the movement of your opponent, rooting them in place for 60 seconds. Has a 60% chance to break on hit.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['duration_seconds'], fact['break_on_hit_chance_percent']), (60, 60))
        for key in ('hit_definition', 'operative_values', 'historical_authentication'):
            self.assertIsNone(fact[key])
        self.assertFalse(any(f['kind'] == KIND for f in effect_facts(literal.replace('on hit', 'on spell damage'))))

    def test_symbiote_amount_does_not_invent_percent_unit(self):
        literal = 'Attaches a frenzied symbiote to an ally, increasing their damage by 63 for 1 hour. Expends 1 Frenzied Symbiote. Only 1 Symbiote allowed on a target at a time.'
        fact, = [f for f in effect_facts(literal) if f['kind'] == KIND]
        self.assertEqual((fact['damage_bonus_amount'], fact['duration_seconds'], fact['consumed_item_quantity'], fact['maximum_symbiotes_per_target']), (63, 3600, 1, 1))
        self.assertIsNone(fact['damage_bonus_unit'])
        self.assertFalse(any(f['kind'] == KIND for f in effect_facts(literal.replace('by 63', 'by 63%'))))
