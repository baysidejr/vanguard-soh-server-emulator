import unittest
from archive_extract import effect_facts

HASTE = 'Increases the attack speed of you and your group by 12%. Cost: 2 energy per second Song Portion: Embellishment Instrument: None Cast Time: 0 Refresh: 0 Range: 5'
DANCE = 'You move and strike with increased focus and speed, advancing to the last phase of your current dance and increasing melee accuracy and critical chance by 5% for 30 seconds.'

class HasteDanceTests(unittest.TestCase):
    def test_recorded_values_and_unknown_mechanics(self):
        haste, = effect_facts(HASTE)
        self.assertEqual(haste['attack_speed_increase_percent_recorded'], 12)
        self.assertEqual(haste['energy_upkeep_recorded'], dict(amount=2, unit_literal='per second', resource_literal='energy'))
        self.assertEqual(haste['timing_and_range_literals'], dict(cast_time='0', refresh='0', range='5'))
        for key in ('cast_time_unit', 'refresh_unit', 'range_unit', 'upkeep_schedule', 'percentage_calculation', 'operative_values'):
            self.assertIsNone(haste[key])
        dance, = effect_facts(DANCE)
        self.assertEqual(dance['melee_accuracy_increase_percent_recorded'], 5)
        self.assertEqual(dance['critical_chance_increase_percent_recorded'], 5)
        self.assertEqual(dance['duration_seconds_recorded'], 30)
        for key in ('percentage_calculation', 'resulting_critical_probability', 'dance_phase_identifier', 'operative_values'):
            self.assertIsNone(dance[key])

    def test_changed_scope_units_and_unreviewed_values_withheld(self):
        for original, kind, variants in (
            (HASTE, 'attack_speed_energy_upkeep_tooltip_observation', [HASTE.replace('12%', '15%'), HASTE.replace('per second', 'per minute'), HASTE.replace('you and your group', 'your pet'), HASTE + ' Only outdoors.']),
            (DANCE, 'dance_accuracy_critical_tooltip_observation', [DANCE.replace('5%', '6%'), DANCE.replace('30 seconds', '30 minutes'), DANCE.replace('last phase', 'first phase'), DANCE + ' Only outdoors.'])):
            for literal in variants:
                with self.subTest(literal=literal):
                    self.assertFalse(any(f['kind'] == kind for f in effect_facts(literal)))
