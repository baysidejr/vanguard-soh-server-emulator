import unittest
from archive_extract import effect_facts


LITERAL = ('Fills your target with fear, causing it to flee in terror for 12 sec. '
           'Only one target can be feared at a time. In player versus player combat '
           'this spell stuns your target for 6 seconds. Has a 25% chance to break on hit. '
           'Only affects a single target every 30 seconds. '
           'Effective on targets level 39 and lower.')


class FearPvpStunTests(unittest.TestCase):
    def test_reviewed_limits_and_mode_uncertainty(self):
        for level in (39, 50):
            fact, = effect_facts(LITERAL.replace('39', str(level)))
            self.assertEqual(fact['target_level_maximum_recorded'], level)
            self.assertEqual(fact['fear_duration_seconds_recorded'], 12)
            self.assertEqual(fact['maximum_feared_targets_recorded'], 1)
            self.assertEqual(fact['pvp_effect_recorded'],
                             dict(effect_literal='stuns', duration_seconds=6))
            self.assertEqual(fact['break_on_hit_chance_percent_recorded'], 25)
            self.assertEqual(fact['single_target_interval_seconds_recorded'], 30)
            for key in ('fear_mode_scope', 'break_on_hit_mode_scope',
                        'target_interval_mode_scope', 'target_level_limit_mode_scope',
                        'interval_reset_mechanics', 'hit_definition',
                        'stun_immunity_rules', 'operative_values'):
                self.assertIsNone(fact[key])

    def test_changed_qualifiers_and_unreviewed_values_withheld(self):
        for literal in (LITERAL + ' Only outdoors.', LITERAL.replace('39', '40'),
                        LITERAL.replace('and lower', 'and higher'),
                        LITERAL.replace('player versus player', 'player versus environment'),
                        LITERAL.replace('25%', '20%'), LITERAL.replace('12 sec', '12'),
                        LITERAL.replace('30 seconds', '30 minutes')):
            with self.subTest(literal=literal):
                self.assertFalse(any(f['kind'] == 'fear_pvp_stun_tooltip_observation'
                                     for f in effect_facts(literal)))
