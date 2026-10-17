import unittest
from extract_forms import parse_forms


class FormTests(unittest.TestCase):
    def fixture(self):
        return '<main><div class="guide-body"><p>At level 10, the Disciple receives 1 combat stances.</p><table><tr><td></td><td><strong>Tiger:</strong><br/>Adds 20% damage; regens1 Jin.</td></tr></table></div></main>'

    def test_exact_effect_and_explicit_level(self):
        row = parse_forms(self.fixture())[0]
        self.assertEqual(row['effect_text'], 'Adds 20% damage; regens1 Jin.')
        self.assertEqual(row['level_received_recorded'], 10)
        self.assertIsNone(row['canonical_client_id'])
        self.assertIsNone(row['source_era'])

    def test_changed_layout_or_count_rejected(self):
        for html in ('<main/>', self.fixture().replace('1 combat', '2 combat'), self.fixture().replace('level 10', 'level unknown'), self.fixture().replace('Tiger:', '<a>Tiger:</a>'), self.fixture().replace('Tiger:', 'Tiger')):
            with self.assertRaises(ValueError):
                parse_forms(html)
