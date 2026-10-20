import sys
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / '.tools-current'))
from archive_extract import effect_facts


class CounterRemovalTests(unittest.TestCase):
    def test_explicit_group_counter_counts_preserve_radius(self):
        for verb, counter in [('Purifies', 'disease'), ('Cures', 'poison')]:
            for count in (2, 3, 4):
                with self.subTest(counter=counter, count=count):
                    self.assertEqual(effect_facts(
                        f'{verb} all group members within 15m, removing {count} {counter} counters.'),
                        [dict(kind='group_counter_removal_observation',
                              counter_type_recorded=counter, counters_removed=count,
                              target_recorded='all group members',
                              radius_recorded=dict(value=15, unit='m'), conditions_unparsed=True)])

    def test_ambiguous_or_conditioned_cures_are_withheld(self):
        for prose in [
            'Cures all group members within 15m, removing 2 poison counters while resting.',
            'Cures all group members within 15m, removing 2 poison effects.',
            'Cures all group members within 15m, removing 2-4 poison counters.',
            'Cures all group members within 15, removing 2 poison counters.',
            'Cures all group members within 0m, removing 2 poison counters.',
            'Cures all group members within 15m, removing 0 poison counters.',
            'Cures your target within 15m, removing 2 poison counters.',
            'Cures all group members within 15m, removing 2 curse counters.',
        ]:
            with self.subTest(prose=prose):
                self.assertEqual(effect_facts(prose), [])
