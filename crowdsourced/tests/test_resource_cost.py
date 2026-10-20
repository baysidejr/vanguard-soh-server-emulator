import json
import unittest
from pathlib import Path
from archive_extract import effect_facts

class ResourceCostTests(unittest.TestCase):
    def test_reviewed_values_and_unknowns(self):
        rows=json.loads(Path('reviewed/BARD_RESOURCE_COST_SOURCE_REVIEW_ITERATION632.json').read_text())['rows']
        for row in rows:
            for obs in row['observations']:
                facts=[f for f in effect_facts(obs['literal']) if f['kind'] in ('resource_cost_reduction_tooltip_observation',)]
                self.assertEqual(len(facts),1)
                for k,v in obs.items():
                    if k not in ('literal','text_sha256','recognized_effect_facts'):
                        self.assertEqual(facts[0][k],v)
                self.assertIsNone(facts[0]['operative_values'])

    def test_unreviewed_changes_fail_closed(self):
        rows=json.loads(Path('reviewed/BARD_RESOURCE_COST_SOURCE_REVIEW_ITERATION632.json').read_text())['rows']
        for row in rows:
            base=row['observations'][0]['literal']
            for prose in (base+' Only outdoors.', base.replace('5%', '6%'), base.replace('your', 'their'), base.replace('mana', 'energy').replace('endurance', 'energy')):
                self.assertFalse(any(f['kind'] in ('resource_cost_reduction_tooltip_observation',) for f in effect_facts(prose)))
