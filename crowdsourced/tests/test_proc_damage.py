import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class ProcDamageTests(unittest.TestCase):
    def test_reviewed_ranges_truncation_and_unknowns(self):
        rows = json.loads(Path('reviewed/BARD_GAMAEL_PROC_DAMAGE_SOURCE_REVIEW_ITERATION625.json').read_text())['rows']
        for row in rows:
            for obs in row['observations']:
                with self.subTest(name=row['name']):
                    fact, = [f for f in effect_facts(obs['literal']) if f['kind'] == 'proc_damage_tooltip_observation']
                    for key, value in obs.items():
                        if key not in ('literal', 'text_sha256', 'recognized_effect_facts'):
                            self.assertEqual(fact[key], value)
                    self.assertTrue(fact['conditions_unparsed'])
            if not row['observations']:
                self.assertFalse(any(f['kind'] == 'proc_damage_tooltip_observation'
                                     for section in row['effect_sections'] for f in effect_facts(section)))

    def test_unreviewed_mechanics_fail_closed(self):
        base = 'Adds a 10% chance for your group to deal 186-201 fire damage with melee and ranged attacks.'
        for prose in (base.replace('10%', '20%'), base + ' Only outdoors.',
                      base.replace('fire', 'cold'), base.replace('your group', 'you')):
            self.assertFalse(any(f['kind'] == 'proc_damage_tooltip_observation'
                                 for f in effect_facts(prose)))
