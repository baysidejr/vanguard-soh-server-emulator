import unittest
from multisource_extract import parse_wiki


class WikiExtractionTests(unittest.TestCase):
    def test_observations_keep_conflicting_rows_and_unknown_identity(self):
        record, links = parse_wiki('https://vgoplayers.com/wiki/index.php/Test', '''
        <h1 id="firstHeading">Test</h1><div id="mw-content-text">
        <table class="infobox"><tr><th>Level</th><td>10</td></tr>
        <tr><th>Level</th><td>12</td></tr><tr><td>Unlabelled</td><td>99</td></tr></table>
        <a href="/wiki/index.php/Other">Other</a></div>''')
        self.assertEqual([r['value'] for r in record['observations']], ['10', '12'])
        self.assertIsNone(record['canonical_client_id'])
        self.assertIsNone(record['source_era'])
        self.assertFalse(record['conversion_ready'])
        self.assertEqual(links, ['https://vgoplayers.com/wiki/index.php/Other'])

    def test_metadata_is_not_game_facts(self):
        record, _ = parse_wiki('https://vgoplayers.com/wiki/index.php/Main_Page',
                              '<h1 id="firstHeading">Main</h1><div id="mw-content-text">Guide prose</div>')
        self.assertEqual(record['classification'], 'metadata only')
        self.assertEqual(record['observations'], [])
        with self.assertRaises(ValueError):
            parse_wiki('https://vgoplayers.com/wiki/index.php/Test', '<html>Access denied</html>')
