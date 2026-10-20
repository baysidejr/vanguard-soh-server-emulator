import sys
from pathlib import Path
import unittest
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / '.tools-current'))
from archive_extract import effect_facts

class BlastingBellowTests(unittest.TestCase):
    def test_reviewed_ranges(self):
        for separator in (' to ', '-'):
            self.assertEqual(effect_facts(f'You bellow, blasting your opponent for 84{separator}91 arcane damage.'),
                [dict(kind='damage_range', values=[84, 91], damage_type_recorded='arcane',
                      target_recorded='your opponent', range_basis=None, conditions_unparsed=True)])

    def test_ambiguous_and_conditional_ranges_withheld(self):
        for value in ('91 to 84', '84 to 91%', '84 or 91', '84 to unknown'):
            self.assertEqual(effect_facts(f'You bellow, blasting your opponent for {value} arcane damage.'), [])
        self.assertEqual(effect_facts('You bellow, blasting your opponent for 84 to 91 arcane damage while singing.'), [])
