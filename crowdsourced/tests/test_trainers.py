from pathlib import Path
import sys
import tempfile
import hashlib
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import collect_archive as collector
from test_archive import page


class TrainerTests(unittest.TestCase):
    def parse(self,body):
        body='<a href="/classes/warrior">Warrior</a><h3 class="trainer-continent">Kojan</h3>'+body
        return collector.parse_page(collector.ORIGIN+'/classes/warrior/trainers',page('Warrior Class Trainers',body))

    def test_trainer_class_and_numeric_location_are_explicit(self):
        records,links=self.parse('<div class="trainer-body"><strong><a href="/mobs/chi-masa">Chi-masa</a></strong><span><a href="/zones/tanvu">Tanvu</a></span><span><code>/loc 1, -2, 3</code></span></div>')
        r=records[0]
        self.assertEqual(r['type'],'npc')
        self.assertEqual(r['trainer_of'],'Warrior')
        self.assertEqual(r['services'],['trainer'])
        self.assertEqual(r['zone'],'Tanvu')
        self.assertEqual(r['location']['raw'],'/loc 1, -2, 3')
        self.assertIsNone(r['level'])
        self.assertIsNone(r['health'])
        self.assertIn(collector.ORIGIN+'/mobs/chi-masa',links)

    def test_descriptive_loc_is_not_a_spawn(self):
        records,_=self.parse('<div class="trainer-body"><a href="/mobs/fixture">Fixture NPC</a><span><code>/loc Training Center</code></span></div>')
        self.assertEqual(records[0]['location']['format'],'descriptive source /loc label')
        self.assertIsNone(records[0]['chunk'])

    def test_unlinked_regions_remain_labels(self):
        records,_=self.parse('<div class="trainer-body"><a href="/mobs/fixture">Fixture NPC</a><span>House of Fallen Leaves</span><span>Blighted Lands</span><span>4 civic parleys</span></div>')
        self.assertIsNone(records[0]['zone'])
        self.assertEqual(records[0]['region_labels'],['House of Fallen Leaves','Blighted Lands'])
        self.assertEqual(records[0]['continent'],'Kojan')

    def test_trainer_subpages_are_typed_and_other_class_pages_are_sources(self):
        self.assertTrue(collector.detail_url(collector.ORIGIN+'/classes/warrior/trainers'))
        self.assertFalse(collector.source_only_url(collector.ORIGIN+'/classes/warrior/trainers'))
        self.assertTrue(collector.source_only_url(collector.ORIGIN+'/classes/warrior/macros'))

    def test_off_sitemap_trainer_links_are_discovered_from_cache(self):
        with tempfile.TemporaryDirectory(prefix='trainer-test-',dir=HERE/'tests') as scratch:
            cache=Path(scratch)
            url=collector.ORIGIN+'/classes/warrior'
            (cache/(hashlib.sha256(url.encode()).hexdigest()+'.txt')).write_text(
                page('Warrior','<a href="/classes/warrior/trainers">Trainers</a><a href="/classes/warrior/macros">Macros</a>'),encoding='utf-8')
            class Client:
                def __init__(self):self.cache=cache
            self.assertEqual(collector.cached_trainer_urls(Client(),[url]),[collector.ORIGIN+'/classes/warrior/trainers'])


if __name__=='__main__':
    unittest.main()
