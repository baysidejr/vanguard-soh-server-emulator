import unittest
from extract_endowments import parse_endowments


class EndowmentTests(unittest.TestCase):
    def fixture(self):
        return '<main><div class="guide-body"><table><tr><td></td><td><strong>Endowment:</strong><br/>10% for 2 minutes.<p><strong>Chain:</strong> One -&gt; Two</p></td><td><strong>Level Possible</strong>: 4</td></tr></table></div></main>'

    def test_exact_observations_and_unknowns(self):
        row = parse_endowments(self.fixture())[0]
        self.assertEqual(row['effect_text'], '10% for 2 minutes.')
        self.assertEqual(row['chain_text'], 'One -> Two')
        self.assertEqual(row['level_possible_recorded'], 4)
        self.assertIsNone(row['canonical_client_id'])
        self.assertIsNone(row['source_era'])

    def test_unreviewed_layout_fails(self):
        for html in ('<main/>', self.fixture().replace(': 4', ': unknown'), self.fixture().replace('One', '<a>One</a>'), self.fixture().replace('Chain:', 'Other:')):
            with self.assertRaises(ValueError):
                parse_endowments(html)
