from pathlib import Path
import sys
import unittest
import tempfile
import json
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import collect_archive as c


class SupplementalTests(unittest.TestCase):
    def test_inventory_roots_are_research_and_preserve_discovery(self):
        root=Path(__file__).resolve().parents[1]
        review=json.loads((root/'reviewed/INVENTORY_ROOT_PAGE_GAP_REVIEW_20261017.json').read_text(encoding='utf-8'))
        self.assertEqual(len(review['excluded_urls']),24)
        for entry in review['excluded_urls']:
            url=entry['inventory_record']['url']
            with self.subTest(url=url):
                self.assertTrue(c.detail_url(url))
                self.assertTrue(c.source_only_url(url))
                rows,links=c.parse_page(url,'<main><h1>Index</h1><a href="/items/fixture">Item</a></main>')
                self.assertEqual(rows,[])
                self.assertEqual(links,[c.ORIGIN+'/items/fixture'])
                self.assertFalse(c.detail_url(url+'?page=2'))
        self.assertFalse(c.detail_url(c.ORIGIN+'/unknown-root'))

    def test_mirror_attribution_and_deep_headings_survive_guide_scoping(self):
        html='<main><h1>Stances</h1><p class="muted">Mirrored from <a href="http://example.org/original">Original</a>.</p><div class="guide-body"><h5>Sanguine Focus</h5><p><a href="/abilities/fixture">Ability</a></p><h6>Next Focus</h6></div><nav class="guide-nav"><p>Mirrored from <a href="https://example.org/sidebar">Sidebar</a></p></nav></main>'
        metadata=c.source_metadata(c.BeautifulSoup(html,'html.parser').find('main'),c.ORIGIN+'/classes/blood-mage/stances')
        self.assertEqual(metadata['original_source_urls'],['http://example.org/original'])
        self.assertEqual(metadata['headings'],['Sanguine Focus','Next Focus'])
        self.assertEqual(metadata['sections'][0]['linked_entities'],[dict(name='Ability',url=c.ORIGIN+'/abilities/fixture')])

    def test_nested_research_routes_are_queued_without_guessed_entities(self):
        paths=('/crafting/enhancements/aspect-of-force',
               '/classes/bard/song-components', '/classes/cleric/affinities',
               '/quests/events', '/quests/events/grim-harvest-quests')
        for path in paths:
            with self.subTest(path=path):
                url=c.ORIGIN+path
                self.assertTrue(c.detail_url(url))
                self.assertTrue(c.source_only_url(url))
                records,links=c.parse_page(url,'<main><h1>Reference</h1><article class="guide-body"><a href="/items/fixture">Item</a></article></main>')
                self.assertEqual(records,[])
                self.assertEqual(links,[c.ORIGIN+'/items/fixture'])
                self.assertFalse(c.detail_url(url+'?filter=1'))
        self.assertFalse(c.source_only_url(c.ORIGIN+'/classes/bard/trainers'))
        self.assertFalse(c.source_only_url(c.ORIGIN+'/crafting/recipes/fixture'))
        self.assertFalse(c.detail_url(c.ORIGIN+'/crafting/enhancements/fixture/extra'))

    def test_guide_navigation_is_not_page_evidence(self):
        html='<main><h1>Fixture</h1><article class="guide-body"><h2>Adventure Quests</h2><p><a href="/quests/fixture">Fixture Quest</a></p><a href="https://example.org/source">Original</a></article><nav class="guide-nav"><h2>World</h2><a href="/zones/unrelated">Unrelated Zone</a></nav></main>'
        _,links=c.parse_page(c.ORIGIN+'/world/fixture',html)
        self.assertEqual(links,[c.ORIGIN+'/quests/fixture'])
        metadata=c.source_metadata(c.BeautifulSoup(html,'html.parser').find('main'),c.ORIGIN+'/world/fixture')
        self.assertEqual(metadata['headings'],['Adventure Quests'])
        self.assertEqual(metadata['sections'][0]['linked_entities'],[dict(name='Fixture Quest',url=c.ORIGIN+'/quests/fixture')])
        self.assertEqual(metadata['original_source_urls'],['https://example.org/source'])

    def test_source_page_is_not_a_guessed_entity(self):
        url=c.ORIGIN+'/world/fixture'
        self.assertTrue(c.detail_url(url))
        records,links=c.parse_page(url,'<main><h1>Fixture Guide</h1><a href="/zones/fixture">Zone</a></main>')
        self.assertEqual(records,[])
        self.assertEqual(links,[c.ORIGIN+'/zones/fixture'])
        self.assertFalse(c.source_only_url(c.ORIGIN+'/crafting/recipes/fixture'))
        self.assertFalse(c.source_only_url(c.ORIGIN+'/world/fixture?filter=1'))
        for slug in ('as-it-was','not-in-the-emulator'):
            url=c.ORIGIN+'/abilities/'+slug
            self.assertTrue(c.source_only_url(url))
            records,_=c.parse_page(url,'<main><h1>Ability index</h1><a href="/abilities/fixture">Fixture</a></main>')
            self.assertEqual(records,[])

    def test_publication_has_metadata_and_explicit_extraction_gap(self):
        root=Path(__file__).resolve().parents[1]
        class Client:
            network_requests=0
            def get(self,url):
                return '<main><h1>Fixture Guide</h1><dl class="kv"><div><dt>Continent</dt><dd>Thestra</dd></div></dl><h2>Overview</h2></main>'
        with tempfile.TemporaryDirectory(dir=root/'tests',prefix='source-pages-') as folder:
            scratch=Path(folder)
            with patch.object(c,'STATE',scratch/'state'),patch.object(c,'HERE',scratch),patch.object(c,'batch_path',return_value=scratch/'raw/batch'):
                _,fatal,batch=c.collect(Client(),[c.ORIGIN+'/world/fixture'],1,'fixture',publish_status=False)
            self.assertFalse(fatal)
            metadata=json.loads((batch/'source_pages.json').read_text(encoding='utf-8'))
            self.assertEqual(metadata[0]['fields']['continent'],['Thestra'])
            self.assertEqual(metadata[0]['headings'],['Overview'])
            self.assertFalse((batch/'zone.jsonl').exists())
            self.assertIn('extraction remains pending',(batch/'gaps.jsonl').read_text(encoding='utf-8'))
