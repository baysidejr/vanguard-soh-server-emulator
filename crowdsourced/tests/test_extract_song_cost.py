import sys
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / '.tools-current'))
from archive_extract import effect_facts


class SongCostTests(unittest.TestCase):
    def test_explicit_reductions_preserve_unknown_resource(self):
        for prose, amount in [('Reduce song cost by 4.', 4),
                              ('Reduces Song cost by 10', 10),
                              ('This rest song reduces song cost by 12.', 12)]:
            with self.subTest(prose=prose):
                self.assertEqual(effect_facts(prose), [dict(
                    kind='song_cost_reduction_observation', values=[amount],
                    resource=None, unit=None, conditions_unparsed=True)])

    def test_ambiguous_or_compound_costs_are_withheld(self):
        for prose in ['Reduce song cost by 4%', 'Reduce song cost by 4-8',
                      'Reduce song cost by ?', 'Reduce song cost by -4',
                      'Reduce song cost by 4 mana',
                      'Reduces Song cost by 11 and restores 30 hit points every 4 seconds.']:
            with self.subTest(prose=prose):
                self.assertFalse(any(f['kind'] == 'song_cost_reduction_observation'
                                     for f in effect_facts(prose)))
