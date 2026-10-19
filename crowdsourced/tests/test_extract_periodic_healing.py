import unittest

from archive_extract import effect_facts


class PeriodicHealingTests(unittest.TestCase):
    def test_reviewed_ranges_and_unknown_semantics(self):
        cases = [
            ('Heals your group for 8-40 every 4 secs', 'your group', 8, 40),
            ('Heals your group by 4-6 every 4 seconds.', 'your group', 4, 6),
            ('A restoring chant that heals you for 40-70 every 4 secs.', 'you', 40, 70),
            ('Heals you and your group for 12-18 every 4 secs', 'you and your group', 12, 18),
        ]
        for literal, target, minimum, maximum in cases:
            with self.subTest(literal=literal):
                self.assertEqual(effect_facts(literal), [dict(
                    kind='periodic_healing_range_observation',
                    healing_minimum_recorded=minimum, healing_maximum_recorded=maximum,
                    pulse_interval_seconds_recorded=4, target_phrase_recorded=target,
                    total_duration_seconds=None, first_pulse_timing=None,
                    scaling=None, healing_per_target=None, conditions_unparsed=True)])

    def test_unreviewed_conditions_units_and_invalid_ranges_withheld(self):
        for literal in [
            'Heals your group for 40-8 every 4 secs',
            'Heals your group for 8-40 every 0 secs',
            'Heals your group for 8-40 every 4 minutes',
            'Heals your group for 8-40 every 4 secs if standing still',
            'Heals your opponent for 8-40 every 4 secs',
        ]:
            with self.subTest(literal=literal):
                self.assertFalse(any(f['kind'] == 'periodic_healing_range_observation'
                                     for f in effect_facts(literal)))
