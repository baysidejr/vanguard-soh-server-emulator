import unittest
from extract_instruments import parse_instruments

class InstrumentTests(unittest.TestCase):
    def test_badges_unknowns_and_link(self):
        html='''<main><h2>String</h2><table><thead><tr><th>Name</th><th>Mod</th><th>Level</th><th>Origin</th><th>Drops from / quest</th></tr></thead><tbody><tr><td><a href="/items/lute">Lute</a><span class="pill">1H</span></td><td>2.2</td><td>—</td><td>Quest</td><td>—</td></tr></tbody></table></main>'''
        row=parse_instruments(html)[0]
        self.assertEqual(row['name'],'Lute')
        self.assertIsNone(row['level_required'])
        self.assertIsNone(row['instrument_observation']['level_recorded'])
        self.assertEqual(row['instrument_observation']['modifier'],2.2)
        self.assertEqual(row['instrument_observation']['handedness_badges'],['1H'])
        self.assertEqual(row['instrument_observation']['linked_item_url'],'https://vgsoharchive.com/items/lute')
        self.assertFalse(row['conversion_ready'])

    def test_unknown_layout_fails(self):
        for html in ('<main><table><th>Changed</th></table></main>', '<main></main>', '<html></html>'):
            with self.assertRaises(ValueError):
                parse_instruments(html)
