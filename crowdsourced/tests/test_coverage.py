import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from audit_coverage import audit,route


class CoverageTests(unittest.TestCase):
    def test_cache_and_published_evidence_are_distinct(self):
        with tempfile.TemporaryDirectory(dir=HERE/'tests',prefix='coverage-') as folder:
            root=Path(folder)
            state=root/'.cache/collector'
            state.mkdir(parents=True)
            cache=root/'.cache/archive'
            cache.mkdir()
            urls=['https://vgsoharchive.com/items/a','https://vgsoharchive.com/items/b','https://vgsoharchive.com/world/c']
            (state/'inventory.json').write_text(json.dumps([dict(url=u) for u in urls]),encoding='utf-8')
            (cache/(hashlib.sha256(urls[0].encode()).hexdigest()+'.txt')).write_text('cached',encoding='utf-8')
            batch=root/'raw/batch'
            batch.mkdir(parents=True)
            (batch/'REPORT.md').write_text('report',encoding='utf-8')
            (batch/'manifest.json').write_text(json.dumps(dict(fetched_urls=[urls[1]])),encoding='utf-8')
            (batch/'VALIDATION.json').write_text(json.dumps(dict(issues=['bad'],count=1)),encoding='utf-8')
            data=audit(root)
            self.assertEqual(data['counts']['cached_only'],1)
            self.assertNotIn('published',data['counts'])
            (batch/'VALIDATION.json').write_text(json.dumps(dict(issues=[],count=0)),encoding='utf-8')
            data=audit(root)
            self.assertEqual(data['counts']['published'],1)
            self.assertEqual(data['counts']['source_only'],1)
            self.assertEqual(data['counts']['supported'],3)

    def test_route_groups_detail_pages_under_category(self):
        self.assertEqual(route('https://vgsoharchive.com/world/fixture'),'/world')
        self.assertEqual(route('https://vgsoharchive.com/crafting/recipes/fixture'),'/crafting/recipes')
