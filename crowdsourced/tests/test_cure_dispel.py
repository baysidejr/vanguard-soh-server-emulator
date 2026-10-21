import unittest
from archive_extract import effect_facts

class CureDispelTests(unittest.TestCase):
    def test_cure_scope_and_unknown_timing(self):
        for condition in ('disease', 'poison'):
            fact, = effect_facts(f'This voice lyric cures a friendly target of {condition}. The cure is slow, but constant.')
            self.assertEqual(fact['action_reported'], 'cure')
            self.assertEqual(fact['condition_reported'], condition)
            self.assertEqual(fact['target_reported'], 'friendly target')
            self.assertEqual(fact['timing_qualifier_reported'], 'slow but constant')
            for key in ('cure_count', 'pulse_interval_seconds', 'duration_seconds', 'dispel_strength', 'operative_values', 'historical_authentication'):
                self.assertIsNone(fact[key])

    def test_dispel_qualifiers_are_not_strength(self):
        for article, tier in (('a lesser', 'lesser'), ('an', None), ('a greater', 'greater')):
            fact, = [f for f in effect_facts(f'Strips {article} enchantment from your opponent.')
                     if f['kind'] == 'cure_dispel_tooltip_observation']
            self.assertEqual(fact['enchantment_qualifier_reported'], tier)
            self.assertEqual(fact['target_reported'], 'opponent')
            self.assertIsNone(fact['dispel_strength'])
        fact, = effect_facts('This voice lyric removes enchantment effects over time from a friendly target.')
        self.assertEqual(fact['timing_qualifier_reported'], 'over time')
        self.assertEqual(fact['target_reported'], 'friendly target')
        self.assertIsNone(fact['pulse_interval_seconds'])

    def test_changed_scope_negation_and_conditions_withheld(self):
        for literal in ('Strips a lesser enchantment from your opponent.', 'This voice lyric cures a friendly target of disease. The cure is slow, but constant.', 'This voice lyric removes enchantment effects over time from a friendly target.'):
            for changed in ('Does not: ' + literal, literal + ' Only outdoors.', literal.replace('opponent', 'ally').replace('friendly target', 'enemy')):
                self.assertFalse(any(f['kind'] == 'cure_dispel_tooltip_observation' for f in effect_facts(changed)))
