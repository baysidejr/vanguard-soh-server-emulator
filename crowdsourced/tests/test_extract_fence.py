from test_extract_blasting_bellow import effect_facts
import unittest


class FenceTests(unittest.TestCase):
    literal = ('Raises your chance to parry incoming attacks by 100% for 60 seconds '
               'or until you parry. This turns off your auto-attack.')

    def test_reviewed_conditional_buff_preserves_unknowns(self):
        self.assertEqual(effect_facts(self.literal), [dict(
            kind='conditional_parry_buff_observation',
            parry_chance_increase_percent_recorded=100,
            duration_seconds_recorded=60,
            early_expiry_condition_recorded='until you parry',
            auto_attack_disabled_recorded=True, percent_interpretation=None,
            guaranteed_parry=None, expiry_event_order=None,
            affected_attack_types=None, conditions_unparsed=True)])

    def test_missing_or_altered_conditions_withheld(self):
        for altered in (self.literal.replace('100%', '0%'),
                        self.literal.replace('60 seconds', '0 seconds'),
                        self.literal.replace('or until you parry', 'and until you parry'),
                        self.literal.replace('or until you parry', ''),
                        self.literal.replace('parry', 'dodge'),
                        self.literal.replace(' This turns off your auto-attack.', ''),
                        self.literal + ' Only against undead.'):
            self.assertEqual(effect_facts(altered), [])
