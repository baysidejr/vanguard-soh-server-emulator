import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class GroupDamageTests(unittest.TestCase):
    def test_reviewed_values_and_unknowns(self):
        rows = json.loads(Path('reviewed/BARD_GROUP_DAMAGE_SOURCE_REVIEW_ITERATION620.json').read_text())['rows']
        for row in rows:
            with self.subTest(name=row['name']):
                fact, = effect_facts(row['literal'])
                self.assertEqual(fact['kind'], 'group_damage_tooltip_observation')
                for key, value in row['observation'].items():
                    self.assertEqual(fact[key], value)
                self.assertIsNone(fact['operative_values'])
        harmony = effect_facts(rows[1]['literal'])[0]
        self.assertNotIn('damage_percent_recorded', harmony)

    def test_unreviewed_extensions_fail_closed(self):
        base = 'Increases the damage of your group by 12-20.'
        for prose in [base + ' Only outdoors.', base.replace('your group', 'you'),
                      base.replace('12-20', '12-20%'), base.replace('12-20', '13-20')]:
            self.assertFalse(any(f['kind'] == 'group_damage_tooltip_observation'
                                 for f in effect_facts(prose)))
