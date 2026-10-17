import unittest
from extract_spirit_bonds import parse_spirit_bonds


class SpiritBondTests(unittest.TestCase):
    def fixture(self, level='??', extra=''):
        return '<main><div class="guide-body"><table><tr><th>Level</th><th colspan="2">Name</th><th>Effect</th></tr><tr><td>'+level+'</td><td>'+extra+'</td><td>Strong Bond</td><td>Adds a chance to drain life.</td></tr></table></div></main>'

    def test_unknown_and_exact_effect(self):
        record = parse_spirit_bonds(self.fixture())[0]
        self.assertIsNone(record['spirit_bond_observation']['level_recorded'])
        self.assertIsNone(record['level_required'])
        self.assertFalse(record['conversion_ready'])
        self.assertEqual(record['spirit_bond_observation']['effect_text'], 'Adds a chance to drain life.')
        self.assertEqual(parse_spirit_bonds(self.fixture('12'))[0]['spirit_bond_observation']['level_recorded'], 12)

    def test_changed_layout_fails_closed(self):
        for html in ('<main/>', self.fixture('unknown'), self.fixture(extra='Unexpected')):
            with self.assertRaises(ValueError):
                parse_spirit_bonds(html)
