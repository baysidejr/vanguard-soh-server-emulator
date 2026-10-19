import json
import unittest
from pathlib import Path
from archive_extract import effect_facts


class ResourceObservationTests(unittest.TestCase):
    def test_reviewed_resources_and_unknown_mechanics(self):
        review = json.loads(Path('reviewed/BARD_NONNUMERIC_RESOURCE_SOURCE_REVIEW_ITERATION681.json').read_text())
        for row in review['rows']:
            for observation in row['observations']:
                fact, = effect_facts(observation['literal'])
                self.assertEqual(fact['kind'], 'resource_regeneration_drain_tooltip_observation')
                for key, value in observation['candidate_observation'].items():
                    self.assertEqual(fact[key], value)
                for key in ('resource_transfer_to_caster', 'magnitude', 'tick_interval_seconds', 'duration_seconds', 'operative_values'):
                    self.assertIsNone(fact[key])

    def test_changed_resource_scope_and_conditions_withheld(self):
        review = json.loads(Path('reviewed/BARD_NONNUMERIC_RESOURCE_SOURCE_REVIEW_ITERATION681.json').read_text())
        for row in review['rows']:
            literal = row['observations'][0]['literal']
            for changed in ('Does not: ' + literal, literal + ' Only outdoors.', literal.replace('energy', 'endurance').replace('mana', 'endurance'), literal.replace('allies', 'enemies').replace('opponent', 'ally')):
                self.assertFalse(any(f['kind'] == 'resource_regeneration_drain_tooltip_observation' for f in effect_facts(changed)))
