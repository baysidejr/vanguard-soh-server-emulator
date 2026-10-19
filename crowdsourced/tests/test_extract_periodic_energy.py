import unittest

from archive_extract import effect_facts


class PeriodicEnergyTests(unittest.TestCase):
    def test_reviewed_ranges_preserve_unknown_semantics(self):
        for minimum, maximum, unit in [(2, 4, 'seconds'), (12, 21, 'secs'), (4, 7, 'secs')]:
            with self.subTest(minimum=minimum):
                self.assertEqual(effect_facts(
                    f'Restores {minimum}-{maximum} energy to your group every 4 {unit}'), [dict(
                        kind='periodic_energy_restoration_range_observation',
                        energy_minimum_recorded=minimum, energy_maximum_recorded=maximum,
                        pulse_interval_seconds_recorded=4, target_phrase_recorded='your group',
                        total_duration_seconds=None, first_pulse_timing=None,
                        scaling=None, energy_per_target=None, conditions_unparsed=True)])

    def test_invalid_ranges_and_unreviewed_semantics_withheld(self):
        for literal in [
            'Restores 7-4 energy to your group every 4 secs',
            'Restores 4-7 energy to your group every 0 secs',
            'Restores 4-7 energy to your group every 4 minutes',
            'Restores 4-7 energy to your group every 4 secs if singing',
            'Restores 4-7 energy to your opponent every 4 secs',
            'Restores 4-7 endurance to your group every 4 secs',
        ]:
            with self.subTest(literal=literal):
                self.assertFalse(any(f['kind'] == 'periodic_energy_restoration_range_observation'
                                     for f in effect_facts(literal)))
