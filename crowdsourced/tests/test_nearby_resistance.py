import unittest
from archive_extract import effect_facts

class NearbyResistanceTests(unittest.TestCase):
    def test_reviewed_types_and_upkeep_are_separate(self):
        for types, noun, amount in [('arcane, mental and spiritual','resistances',20), ('mental and spiritual','resistances',10), ('cold, fire and physical','resistance',10)]:
            prose=f'Increases the {types} {noun} of all nearby allies by {amount}. Costs 4/sec energy.'
            fact, = effect_facts(prose)
            self.assertEqual(fact['resistance_types_recorded'], types.replace(' and ', ', ').split(', '))
            self.assertEqual(fact['increase_recorded'],amount)
            self.assertEqual(fact['energy_per_second_recorded'],4)
            for key in ('resistance_unit','nearby_radius','stacking','scaling','upkeep_tick_timing','duration_seconds','operative_values'):
                self.assertIsNone(fact[key])

    def test_unreviewed_variants_fail_closed(self):
        base='Increases the mental and spiritual resistances of all nearby allies by 10. Costs 4/sec energy.'
        for prose in [base+' While singing.',base.replace('10.', '20.'),base.replace('all nearby allies','your group'),base.replace('4/sec','5/sec'),base.replace('10.', '10%.'),base.replace('mental and spiritual','fire and cold')]:
            self.assertFalse(any(f['kind']=='nearby_resistance_tooltip_observation' for f in effect_facts(prose)))
