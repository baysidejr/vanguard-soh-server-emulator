import unittest
from archive_extract import effect_facts

REVOLUTION = 'Protects you and your group from the elements, increasing your fire, cold and physical resistances by 12 to 16, depending on your level. Costs 6/sec energy.'
SEGUE = 'Surrounds you and your group with shielding sound, increasing your arcane, mental and spiritual resistance by 12 to 16, depending on your level. Costs ?/sec energy.'
KIND = 'level_dependent_resistance_upkeep_tooltip_observation'

class ResistanceUpkeepTests(unittest.TestCase):
    def test_reviewed_intervals_and_unknown_upkeep(self):
        for literal, schools, upkeep in ((REVOLUTION, ['fire', 'cold', 'physical'], 6),
                                        (SEGUE, ['arcane', 'mental', 'spiritual'], None)):
            with self.subTest(literal=literal):
                fact, = effect_facts(literal)
                self.assertEqual(fact['kind'], KIND)
                self.assertEqual(fact['resistance_range_recorded'], dict(
                    minimum=12, maximum=16, resistance_types_literal=schools))
                self.assertEqual(fact['energy_upkeep_recorded']['amount'], upkeep)
                self.assertEqual(fact['energy_upkeep_recorded']['amount_literal'],
                                 '?' if upkeep is None else '6')
                for key in ('level_scaling_formula', 'resistance_unit', 'upkeep_schedule',
                            'stacking_formula', 'instrument_scaling', 'operative_values'):
                    self.assertIsNone(fact[key])

    def test_unreviewed_conditions_and_numbers_are_withheld(self):
        for original in (REVOLUTION, SEGUE):
            for literal in (original + ' Only outdoors.', original.replace('12 to 16', '16 to 12'),
                            original.replace('12 to 16', '13 to 16'),
                            original.replace('depending on your level', 'at every level'),
                            original.replace('/sec', ''), original.replace('your group', 'your pet')):
                with self.subTest(literal=literal):
                    self.assertFalse(any(f['kind'] == KIND for f in effect_facts(literal)))
