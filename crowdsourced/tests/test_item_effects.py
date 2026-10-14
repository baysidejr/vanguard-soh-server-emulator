from pathlib import Path
import sys
import unittest
import tempfile
import json
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import collect_archive as collector


class ItemEffectTests(unittest.TestCase):
    def test_shared_name_does_not_merge_effect_into_class_ability(self):
        root=Path(__file__).resolve().parents[1]
        class Client:
            network_requests=0
            def get(self,url):
                return '<main><h1>Shared Name</h1><p class="lead">Fixture.</p></main>'
        with tempfile.TemporaryDirectory(dir=root/'tests',prefix='effects-') as folder:
            scratch=Path(folder)
            with patch.object(collector,'STATE',scratch/'state'),patch.object(collector,'HERE',scratch),patch.object(collector,'batch_path',return_value=scratch/'raw/batch'):
                _,fatal,batch=collector.collect(Client(),[collector.ORIGIN+'/abilities/shared',collector.ORIGIN+'/effects/shared'],2,'fixture',publish_status=False)
            self.assertFalse(fatal)
            records=[json.loads(line) for line in (batch/'ability.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(records),2)
            self.assertEqual([r.get('record_kind') for r in records],[None,'item_effect'])
            self.assertTrue(all('archive_variants' not in r for r in records))

    def test_effect_route_and_explicit_item_relationship(self):
        url=collector.ORIGIN+'/effects/fixture'
        self.assertTrue(collector.detail_url(url))
        records,links=collector.parse_page(url,'<main><h1>Fixture Effect <span class="pill">activated</span></h1><p class="lead">Grants a Diplomacy Ability.</p><h2>Items with this effect</h2><ul><li><a href="/items/fixture">Fixture Item</a></li></ul></main>')
        r=records[0]
        self.assertEqual(r['name'],'Fixture Effect')
        self.assertEqual(r['record_kind'],'item_effect')
        self.assertEqual(r['activation_labels'],['activated'])
        self.assertEqual(r['items_recorded'],['Fixture Item'])
        self.assertIn(collector.ORIGIN+'/items/fixture',links)
        self.assertIsNone(r['cost'])

    def test_filter_links_are_not_requested(self):
        _,links=collector.parse_page(collector.ORIGIN+'/effects/fixture','<main><h1>Fixture</h1><p class="lead">Deals 10 to 20 damage.</p><a href="/items?effect=1">Search</a></main>')
        self.assertEqual(links,[])
        self.assertFalse(collector.detail_url(collector.ORIGIN+'/effects/fixture?x=1'))
