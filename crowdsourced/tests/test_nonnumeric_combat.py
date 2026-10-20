import json
import unittest
from pathlib import Path

from archive_extract import effect_facts


class NonnumericCombatTests(unittest.TestCase):
    def test_reviewed_trigger_recipient_and_proc_uncertainty(self):
        review = json.loads(Path('reviewed/BARD_REMAINING_NONNUMERIC_COMBAT_SOURCE_REVIEW_ITERATION685.json').read_text())
        for row in review['rows'][:2]:
            observation, = row['observations']
            fact, = effect_facts(observation['literal'])
            self.assertEqual(fact['kind'], 'nonnumeric_combat_tooltip_observation')
            for key, value in observation['candidate_observation'].items():
                self.assertEqual(fact[key], value)
            self.assertIsNone(fact['magnitude'])
            self.assertIsNone(fact['operative_values'])

    def test_negation_scope_and_proc_direction_changes_withheld(self):
        literals = [
            'This voice lyric deals damage to anyone who attack you and your allies.',
            'This brass lyric adds additional poison damage to the attacks of you and your allies. Instrument modifiers alter proc chance.',
        ]
        for literal in literals:
            for changed in ('Does not: ' + literal, literal + ' Only outdoors.',
                            literal.replace('allies', 'opponents'),
                            literal.replace('damage', 'healing'),
                            literal.replace('alter', 'increase')):
                if changed != literal:
                    self.assertFalse(any(f['kind'] == 'nonnumeric_combat_tooltip_observation'
                                         for f in effect_facts(changed)))
