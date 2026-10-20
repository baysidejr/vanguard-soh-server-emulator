from test_extract_blasting_bellow import effect_facts
import unittest


class ChantTests(unittest.TestCase):
    def test_explicit_duration_does_not_infer_ticks(self):
        for adjective, damage_type in [('vile', 'physical'), ('fiery', 'fire'), ('chilling', 'cold')]:
            facts = effect_facts(f'You begin to chant {adjective} words, inflicting 448 to 472 {damage_type} damage over 28 seconds.')
            self.assertEqual(facts, [dict(kind='damage_over_duration_range_observation',
                values=[448, 472], damage_type_recorded=damage_type,
                duration_seconds=28, tick_interval_seconds=None, tick_count=None,
                damage_per_tick=None, target_recorded=None, range_basis=None,
                conditions_unparsed=True)])

    def test_ambiguous_or_conditional_text_withheld(self):
        literal = 'You begin to chant vile words, inflicting 448 to 472 physical damage over 28 seconds.'
        for altered in [literal.replace('448 to 472', '472 to 448'),
                        literal.replace('28 seconds', '0 seconds'),
                        literal.replace('472 physical', '472% physical'),
                        literal + ' Only while singing.', literal.replace('over 28', 'every 28')]:
            self.assertEqual(effect_facts(altered), [])
