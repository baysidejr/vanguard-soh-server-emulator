import unittest
from extract_patrons import parse_patrons


class PatronTests(unittest.TestCase):
    def fixture(self, extra=''):
        return '<main><div class="guide-body"><h4>Patron (Wolf)</h4><p>Balanced between melee and spell casting.</p><ul><li>Patron Shaman Endowments</li></ul>'+extra+'<hr/></div></main>'

    def test_observation_preserves_prose_and_unknowns(self):
        row = parse_patrons(self.fixture())[0]
        self.assertEqual(row['totem_recorded'], 'Wolf')
        self.assertEqual(row['description_text'], 'Balanced between melee and spell casting.')
        self.assertIsNone(row['canonical_client_id'])
        self.assertIsNone(row['level_required'])
        self.assertIsNone(row['source_era'])

    def test_unreviewed_layout_and_links_fail_closed(self):
        for html in ('<main/>', self.fixture('<p>Extra effect</p>'), self.fixture().replace('Patron Shaman Endowments', '<a href="/ability">Ability</a>'), self.fixture().replace('Patron (Wolf)', 'Unknown')):
            with self.assertRaises(ValueError):
                parse_patrons(html)
