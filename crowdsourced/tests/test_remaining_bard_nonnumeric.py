import json
import unittest
from pathlib import Path
from archive_extract import effect_facts

class RemainingBardTests(unittest.TestCase):
    def test_reviewed_mechanics_and_unknowns(self):
        rows=json.loads(Path('reviewed/BARD_REMAINING_NONNUMERIC_COMBAT_SOURCE_REVIEW_ITERATION685.json').read_text())['rows'][2:]
        self.assertEqual(len(rows),5)
        for row in rows:
            for obs in row['observations']:
                facts=[f for f in effect_facts(obs['literal']) if f['kind']=='nonnumeric_bard_tooltip_observation']
                self.assertEqual(len(facts),1)
                for key,value in obs['candidate_observation'].items():
                    self.assertEqual(facts[0][key],value)
                self.assertIsNone(facts[0]['operative_values'])
                self.assertIsNone(facts[0]['duration_seconds'])
                self.assertTrue(facts[0]['conditions_unparsed'])

    def test_changes_and_added_conditions_fail_closed(self):
        literals=['Speeds up the rate at which bard dance forms are progressed.', 'Reduces your opponent\'s armor class and strength. Deals damage over time.']
        for literal in literals:
            for changed in (literal+' Only outdoors.',literal.replace('bard','warrior').replace('strength','dexterity')):
                self.assertFalse(any(f['kind']=='nonnumeric_bard_tooltip_observation' for f in effect_facts(changed)))
