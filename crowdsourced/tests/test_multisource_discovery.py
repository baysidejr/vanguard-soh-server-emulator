import unittest
from discover_multisource import wiki_links, item_search_form


class MultiSourceDiscoveryTests(unittest.TestCase):
    def test_search_preserves_distinct_source_values_and_ignores_comments(self):
        html = '''<form id="itemSearchForm" action="items.php?query=true#results" method="post">
        <!-- <input name="fake" value="bad"> -->
        <input name="name" value=""><select name="slot">
        <option value="12">Container</option><option value="27">Container</option>
        </select></form>'''
        result = item_search_form(html, 'https://vgoplayers.com/items.php')
        self.assertEqual(result['method'], 'POST')
        self.assertEqual(result['action'], 'https://vgoplayers.com/items.php?query=true')
        self.assertEqual([c['name'] for c in result['controls']], ['name', 'slot'])
        self.assertEqual([o['source_value'] for o in result['controls'][1]['options']], ['12', '27'])
        self.assertIsNone(result['canonical_id_mapping'])

    def test_search_rejects_missing_or_external_form(self):
        for html in ('<html/>', '<form id="itemSearchForm" action="https://other.test/items.php"/>'):
            with self.assertRaises(ValueError):
                item_search_form(html, 'https://vgoplayers.com/items.php')

    def test_content_links_only_and_no_action_or_personal_namespaces(self):
        html = '''<a href="/wiki/index.php/Outside">outside</a><div id="mw-content-text">
        <a href="/wiki/index.php/Qalia">Qalia</a><a href="/wiki/index.php/Category:Quests">quests</a>
        <a href="/wiki/index.php/User:Someone">user</a><a href="/wiki/index.php/File:Map">file</a>
        <a href="/wiki/index.php?title=Foo&action=edit">edit</a>
        <a href="https://elsewhere.test/wiki/index.php/Foo">external</a></div>'''
        self.assertEqual(wiki_links(html, 'https://vgoplayers.com/wiki/index.php/Main_Page'),
            ['https://vgoplayers.com/wiki/index.php/Category:Quests', 'https://vgoplayers.com/wiki/index.php/Qalia'])

    def test_missing_content_rejected(self):
        with self.assertRaises(ValueError):
            wiki_links('<html></html>', 'https://vgoplayers.com/wiki/index.php/Main_Page')

    def test_section_links_are_canonicalized_and_encoded_namespaces_rejected(self):
        html = '''<div id="mw-content-text">
        <a href="/wiki/index.php/Qalia#Quests">section</a>
        <a href="/wiki/index.php/Qalia">duplicate</a>
        <a href="#Local">self</a>
        <a href="/wiki/index.php/User%3ASomeone#Profile">user</a>
        <a href="/wiki/index.php/Category%3AQuests#A">category</a>
        <a href="/wiki/index.php/Qalia?action=edit#A">edit</a></div>'''
        self.assertEqual(wiki_links(html, 'https://vgoplayers.com/wiki/index.php/Main_Page'),
                         ['https://vgoplayers.com/wiki/index.php/Category%3AQuests',
                          'https://vgoplayers.com/wiki/index.php/Qalia'])
