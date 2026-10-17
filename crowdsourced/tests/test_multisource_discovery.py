import unittest
from discover_multisource import wiki_links


class MultiSourceDiscoveryTests(unittest.TestCase):
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
