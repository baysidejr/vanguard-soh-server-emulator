import unittest
from archive_extract import effect_facts

CASES = [
 ('Allows your group to fall slowly and safely from any height.', 'slow_fall', 'your group'),
 ('Allows your group to breathe underwater.', 'water_breathing', 'your group'),
 ('Levitates you and your nearby group members off the ground', 'levitation', 'you and your nearby group members'),
 ('Causes you and nearby group members to become invisible', 'invisibility', 'you and nearby group members'),
 ('This wind verse causes you and your allies to become invisible.', 'invisibility', 'you and your allies'),
]
class GroupUtilityTests(unittest.TestCase):
    def test_reviewed_effects_preserve_scope_and_unknowns(self):
        for literal, effect, targets in CASES:
            with self.subTest(literal=literal):
                fact, = effect_facts(literal)
                self.assertEqual(fact['effect_recorded'], effect)
                self.assertEqual(fact['target_phrase_recorded'], targets)
                self.assertEqual(fact['effect_phrase_recorded'], literal)
                for key in ('duration_seconds', 'range', 'range_unit', 'break_conditions', 'movement_speed', 'stacking_formula', 'operative_values'):
                    self.assertIsNone(fact[key])
                self.assertTrue(fact['conditions_unparsed'])
    def test_changed_scope_and_added_conditions_withheld(self):
        for literal, _, _ in CASES:
            for changed in (literal.replace('group members', 'enemies').replace('your group', 'your pet').replace('your allies', 'your enemies'), literal + ' Only outdoors.', 'Does not: ' + literal):
                with self.subTest(changed=changed):
                    self.assertFalse(any(f['kind'] == 'group_utility_tooltip_observation' for f in effect_facts(changed)))

