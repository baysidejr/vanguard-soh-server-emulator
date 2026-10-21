import unittest

from archive_extract import effect_facts


class FavorLineEndings(unittest.TestCase):
    literal = ('Fills your targets group with power.\n+14 Constitution\n'
               '+7 Vitality\n+16 Intelligence\n+11 Wisdom\n+150 Hit Points\n'
               '+2 Hit Point Regeneration\n+40 Physical Resistance')

    def test_line_endings_preserve_typed_values_and_unknowns(self):
        expected = effect_facts(self.literal.replace('\n', '\r\n'))
        self.assertEqual(len(expected), 1)
        for ending in ('\n', '\r\n', '\r'):
            with self.subTest(ending=repr(ending)):
                facts = effect_facts(self.literal.replace('\n', ending))
                self.assertEqual(facts, expected)
                self.assertEqual(facts[0]['constitution_bonus'], 14)
                self.assertEqual(facts[0]['hit_point_regeneration_bonus'], 2)
                self.assertIsNone(facts[0]['regeneration_time_basis'])
                self.assertIsNone(facts[0]['operative_values'])

    def test_unreviewed_values_and_qualifiers_do_not_match(self):
        for literal in (self.literal.replace('+14', '+15'),
                        self.literal + '\nOnly at level 55',
                        self.literal.replace('Constitution', 'Constitution percent')):
            self.assertEqual(effect_facts(literal), [])
