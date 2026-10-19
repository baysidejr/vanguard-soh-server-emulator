import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tools-current'))
sys.path.insert(0, str(ROOT))
from archive_extract import effect_facts


class GroupAttributeRangeTests(unittest.TestCase):
    def test_archive_range_keeps_unknown_scaling(self):
        facts = effect_facts('Increases the dexterity and vitality of your group by 10-18')
        self.assertEqual(facts, [dict(kind='group_attribute_range_observation',
            attributes_recorded=['dexterity', 'vitality'], values=[10, 18],
            target_recorded='your group', range_basis=None, conditions_unparsed=True)])

    def test_ambiguous_or_conditional_ranges_are_withheld(self):
        for value in ['10-18%', '18-10', '10', '10-18 while singing', '10-18 and strength by 5']:
            with self.subTest(value=value):
                self.assertEqual(effect_facts('Increases the dexterity and vitality of your group by ' + value), [])
        self.assertEqual(effect_facts('Increases the vitality and vitality of your group by 10-18'), [])
