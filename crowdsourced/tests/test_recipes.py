from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import collect_archive as collector
from test_archive import page


class RecipeTests(unittest.TestCase):
    def parse(self,body):
        return collector.parse_page(collector.ORIGIN+'/crafting/recipes/fixture',page('Fixture Recipe',body))[0][0]

    def test_linked_component_ignores_embedded_tooltip(self):
        r=self.parse('<h2>Ingredients</h2><ul class="component-list"><li><a href="/items/hide">Hide</a><span class="tt">Hide Rare Class: Bard</span><span class="guide-mark">†</span></li></ul>')
        self.assertEqual(r['ingredients'][0]['item'],'Hide')
        self.assertIsNone(r['ingredients'][0]['count'])
        self.assertEqual(r['confidence'],'low')

    def test_unlinked_quantity_and_duplicates_remain_printed(self):
        r=self.parse('<h2>Ingredients</h2><ul class="component-list"><li><span class="qty">(3)</span>Cotton Bolt</li></ul><h2>Utilities</h2><ul class="component-list"><li>Cure</li><li>Cure</li></ul>')
        self.assertEqual(r['ingredients'][0]['count'],3)
        self.assertEqual(r['ingredients'][0]['item'],'Cotton Bolt')
        self.assertEqual(len(r['utilities']),2)
        self.assertIsNone(r['output'])

    def test_placeholder_level_is_unknown(self):
        r=self.parse('<table class="detail"><tr><th>Recipe level</th><td>xx</td></tr></table>')
        self.assertIsNone(r['level'])
        self.assertEqual(r['confidence'],'low')

    def test_multiple_products_do_not_select_one_output(self):
        r=self.parse('<h2>Produces</h2><ul class="component-list"><li>Bag A</li><li>Bag B</li></ul>')
        self.assertEqual([o['item'] for o in r['products_recorded']],['Bag A','Bag B'])
        self.assertIsNone(r['output'])
