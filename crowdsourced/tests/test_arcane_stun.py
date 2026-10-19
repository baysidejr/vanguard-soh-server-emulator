import unittest
from archive_extract import effect_facts


LITERAL = 'You release a deep, booming bellow, smashing your opponent for 790 to 832 arcane damage and stunning it for 4 sec.'


class ArcaneStunTests(unittest.TestCase):
    def test_reviewed_observation_preserves_unknown_mechanics(self):
        fact, = effect_facts(LITERAL)
        self.assertEqual(fact['kind'], 'arcane_damage_stun_tooltip_observation')
        self.assertEqual(fact['damage_range_recorded'],
                         dict(minimum=790, maximum=832, damage_type_literal='arcane'))
        self.assertEqual(fact['stun_duration_recorded'], dict(amount=4, unit_literal='sec'))
        self.assertEqual(fact['target_phrase_recorded'], 'your opponent')
        for key in ('range_scaling_basis', 'damage_formula', 'stun_immunity_rules',
                    'stun_break_conditions', 'stacking_formula', 'instrument_scaling', 'operative_values'):
            self.assertIsNone(fact[key])
        self.assertTrue(fact['conditions_unparsed'])

    def test_unreviewed_variants_are_withheld(self):
        for literal in (LITERAL + ' Only outdoors.', LITERAL.replace('790 to 832', '832 to 790'),
                        LITERAL.replace('4 sec', '4'), LITERAL.replace('arcane', 'fire'),
                        LITERAL.replace('790', '791'), LITERAL.replace('your opponent', 'all opponents')):
            with self.subTest(literal=literal):
                self.assertFalse(any(f['kind'] == 'arcane_damage_stun_tooltip_observation'
                                     for f in effect_facts(literal)))
