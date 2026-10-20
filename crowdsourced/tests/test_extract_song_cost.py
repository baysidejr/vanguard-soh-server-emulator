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
                      'Reduces Song cost by 11 and restores 30 hit points every 4 seconds while resting.']:
            with self.subTest(prose=prose):
                self.assertFalse(any(f['kind'] == 'song_cost_reduction_observation'
                                     for f in effect_facts(prose)))

    def test_compound_restoration_keeps_unknown_target_and_resource(self):
        facts = effect_facts('Reduces Song cost by 11 and restores 30 hit points every 4 seconds.')
        self.assertEqual(facts, [dict(kind='song_cost_reduction_observation',
            values=[11], resource=None, unit=None, conditions_unparsed=True),
            dict(kind='periodic_hit_point_restoration_observation', values=[30],
                resource_recorded='hit points', interval_seconds=4,
                target_recorded=None, conditions_unparsed=True)])

    def test_level_dependent_restoration_is_not_a_rate_or_total(self):
        facts = effect_facts('Restores 2 to 4 energy, depending on your level, to your group every 4 sec.')
        self.assertEqual(facts, [dict(kind='periodic_group_energy_restoration_range_observation',
            values=[2, 4], resource='energy', interval_seconds=4,
            target_recorded='your group', scaling_condition_recorded='depending on your level',
            level_to_value_mapping=None, range_basis=None, conditions_unparsed=True)])

    def test_invalid_or_extended_restoration_is_withheld(self):
        template = 'Restores {} energy, depending on your level, to your group every {} sec.'
        for prose in [template.format('4 to 2', 4), template.format('2 to 4', 0),
                      template.format('2 to 4', 4) + ' Only while resting.',
                      template.format('2 to 4%', 4),
                      'Reduces Song cost by 11 and restores 30 hit points every 0 seconds.']:
            with self.subTest(prose=prose):
                self.assertEqual(effect_facts(prose), [])
