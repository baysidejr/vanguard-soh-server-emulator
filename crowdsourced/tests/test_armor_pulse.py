import json
import unittest
from pathlib import Path
from archive_extract import effect_facts

class ArmorPulseTests(unittest.TestCase):
    def test_reviewed_values_and_unknowns(self):
        rows=json.loads(Path('reviewed/BARD_ARMOR_PULSE_ABSORPTION_SOURCE_REVIEW_ITERATION627.json').read_text())['rows']
        for row in rows:
            for obs in row['observations']:
                facts=[f for f in effect_facts(obs['literal']) if f['kind']=='armor_pulse_tooltip_observation']
                self.assertEqual(len(facts),1)
                for k,v in obs.items():
                    if k not in ('literal','text_sha256','recognized_effect_facts'):
                        self.assertEqual(facts[0][k],v)
                self.assertIsNone(facts[0]['operative_values'])
                self.assertIsNone(facts[0]['pulse_interval_seconds'])
                self.assertIsNone(facts[0]['absorption_refresh_model'])

    def test_unreviewed_changes_fail_closed(self):
        base='Causes a curtain of sound to protect your group that increases armor class by 25 and absorbs 25 damage each pulse.'
        for prose in (base+' Only outdoors.',base.replace('25','26'),base.replace('each pulse','each second'),base.replace('your group','you')):
            self.assertFalse(any(f['kind']=='armor_pulse_tooltip_observation' for f in effect_facts(prose)))
