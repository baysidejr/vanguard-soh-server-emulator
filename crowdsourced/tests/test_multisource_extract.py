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

    def test_article_evidence_preserves_nested_tables_without_fact_promotion(self):
        url = 'https://vgoplayers.com/wiki/index.php/Test'
        record, _ = parse_wiki(url, '''<h1 id="firstHeading">Test</h1>
        <div id="mw-content-text"><p>Possibly historical prose.</p>
        <table><tr><td>Navigation<table><tr><td>Nested</td></tr></table></td></tr></table>
        <ul><li>Parent<ul><li>Child</li></ul></li></ul>
        <table class="infobox"><tr><th>Level</th><td>10</td></tr></table></div>''')
        evidence = record['unreviewed_article_evidence']
        self.assertEqual([e['kind'] for e in evidence], ['prose', 'table', 'prose'])
        self.assertIn('<table>', evidence[1]['source_html'])
        self.assertEqual(evidence[2]['text'], 'Parent Child')
        self.assertTrue(all(e['source_url'] == url and not e['game_fact'] for e in evidence))
        self.assertEqual(record['observations'], [{'label': 'Level', 'value': '10', 'source_url': url}])
        self.assertFalse(record['conversion_ready'])

    def test_prose_and_tables_alone_remain_metadata(self):
        record, _ = parse_wiki('https://vgoplayers.com/wiki/index.php/Test',
            '<h1 id="firstHeading">Test</h1><div id="mw-content-text"><p>Claim</p><table><tr><td>12</td></tr></table></div>')
        self.assertEqual(record['classification'], 'metadata only')
        self.assertEqual(len(record['unreviewed_article_evidence']), 2)
        self.assertEqual(record['observations'], [])
