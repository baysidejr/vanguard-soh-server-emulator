"""Offline collector tests. No tests crawl the archive or write outside crowdsourced."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import collect_archive as collector
from archive_client import ArchiveClient, ORIGIN
from convert import record_errors


def page(name, body, head=""):
    return f'<html><title>{name} - archive</title><main><div class="detail-head"><h1>{name}</h1><p>{head}</p></div>{body}</main></html>'


class ArchiveParsingTests(unittest.TestCase):
    def test_explicit_weapon_category_retains_subtype(self):
        for raw, expected in [('Weapon — Hammer', 'weapon'), ('Weapon — Bladed Staff Weapon', 'weapon'),
                              ('Unknown — Weapon', None), ('Weaponized Clothing', None), ('Weapon — ', None)]:
            html = page('Fixture', '<dl class="kv"><div><dt>Type</dt><dd>' + raw + '</dd></div></dl>')
            records, _ = collector.parse_page(ORIGIN + '/items/fixture', html)
            self.assertEqual(records[0]['item_type'], expected)
            if expected:
                self.assertEqual(records[0]['weapon_type_recorded'], raw.partition(' — ')[2])

    def test_exact_archive_item_type_labels(self):
        for raw, expected in [('Quest', 'quest'), ('Quest — Miscellaneous', 'quest'),
                              ('Weapon — Greataxe', 'weapon'), ('Cloak Armor', 'armor'),
                              ('Crafting Tool', 'tool'), ('Crafting Material', 'resource'),
                              ('Quest — Unknown Classification', None)]:
            html = page('Fixture', '<dl class="kv"><div><dt>Type</dt><dd>' + raw + '</dd></div></dl>')
            records, _ = collector.parse_page(ORIGIN + '/items/fixture', html)
            self.assertEqual(records[0]['item_type'], expected)
            self.assertEqual(records[0]['archive_fields']['type'], [raw])

    def test_required_level_is_not_item_level(self):
        html = page("Fixture Gloves", '''<h2>Properties</h2><dl class="kv">
            <div><dt>Item level</dt><dd>16</dd></div><div><dt>Requires</dt><dd>level 6 Adventuring</dd></div>
            <div><dt>Type</dt><dd>Medium Armor</dd></div><div><dt>Slot</dt><dd>Hands</dd></div>
            <div><dt>Rarity</dt><dd>Common</dd></div></dl>''')
        records, _ = collector.parse_page(ORIGIN + '/items/fixture-gloves', html)
        self.assertEqual(records[0]['item_level'], 16)
        self.assertEqual(records[0]['level_required'], 6)
        self.assertEqual(records[0]['slot'], 'hands')
        self.assertEqual(record_errors(records[0]), [])

    def test_stats_use_explicit_numbers_and_codes(self):
        html = page("Fixture", '''<h2>Stats</h2><ul><li><a href="/items?stat=1">Hit Points</a>
            <span class="muted">44</span><span title="Game enum code">HIT_POINTS</span></li>
            <li><a>Bad Stat</a><span class="muted">unknown</span></li></ul><h2>Description</h2><p>not a stat</p>''')
        records, _ = collector.parse_page(ORIGIN + '/items/fixture', html)
        self.assertEqual(records[0]['stats'], {'hit_points': 44})
        self.assertEqual(records[0]['level_required'], None)

    def test_conflicting_archive_is_low_confidence(self):
        html = page("Fixture", '<h2>Where another source disagrees</h2><p>Stats conflict</p>')
        records, _ = collector.parse_page(ORIGIN + '/items/fixture', html)
        self.assertEqual(records[0]['confidence'], 'low')

    def test_conflicting_values_are_preserved_without_blending(self):
        html = page('Fixture', '''<h2>Where another source disagrees</h2><table><thead><tr>
            <th>Field</th><th>Here</th><th>There</th><th>Said by</th></tr></thead><tbody><tr>
            <td>stats raw</td><td>+5 Constitution</td><td>+8 Constitution</td>
            <td><a href="https://example.org/record">Source</a></td></tr></tbody></table>''')
        records, _ = collector.parse_page(ORIGIN + '/items/fixture', html)
        self.assertEqual(records[0]['archive_conflicts'][0]['there'], '+8 Constitution')
        self.assertIn('+5 Constitution', records[0]['notes'])
        self.assertEqual(records[0]['stats'], {})

    def test_event_indexes_are_not_entity_detail_pages(self):
        for path in ('/quests/events','/quests/events/grim-harvest-quests'):
            self.assertTrue(collector.source_only_url(ORIGIN+path))
            records,_=collector.parse_page(ORIGIN+path,page('Event index',''))
            self.assertEqual(records,[])
        self.assertTrue(collector.detail_url(ORIGIN + '/quests/fixture'))

    def test_quest_chain_does_not_invent_prerequisite_or_steps(self):
        html = page("Fixture Quest", '''<h2>Details</h2><dl class="kv">
            <div><dt>Starts with</dt><dd><a href="/mobs/fixture">Fixture NPC</a></dd></div>
            <div><dt>Previous</dt><dd>Previous Quest</dd></div><div><dt>Coin reward</dt><dd>50</dd></div>
            </dl>''', 'Level 9 · <a href="/zones/fixture">Fixture Zone</a>')
        records, links = collector.parse_page(ORIGIN + '/quests/fixture', html)
        r = records[0]
        self.assertEqual(r['level'], 9)
        self.assertEqual(r['zone'], 'Fixture Zone')
        self.assertEqual(r['chain_previous'], 'Previous Quest')
        self.assertIsNone(r['prerequisites'])
        self.assertIsNone(r['steps'])
        self.assertIsNone(r['rewards']['coin_copper'])
        self.assertIn(ORIGIN + '/mobs/fixture', links)
        self.assertEqual(record_errors(r), [])

    def test_quest_repeatability_and_template_chain(self):
        for value, expected in (('Yes', True), ('No', False), ('Unknown', None)):
            html = page('Fixture Quest', '<dl class="kv"><div><dt>Repeatable</dt><dd>' + value +
                '</dd></div><div><dt>Previous</dt><dd>{{{previous}}}</dd></div>' +
                '<div><dt>Next</dt><dd>Next Quest</dd></div></dl>')
            records, _ = collector.parse_page(ORIGIN + '/quests/fixture', html)
            self.assertIs(records[0]['repeatable'], expected)
            self.assertIsNone(records[0]['chain_previous'])
            self.assertEqual(records[0]['chain_next'], 'Next Quest')
            self.assertEqual(records[0]['archive_fields']['previous'], ['{{{previous}}}'])

    def test_level_scoped_xp_is_not_unconditional_reward(self):
        html = page('Fixture Quest', '<h2>Quest Rewards</h2><p>6,000 XP at Lvl 22</p>')
        records, _ = collector.parse_page(ORIGIN + '/quests/fixture', html)
        self.assertIsNone(records[0]['rewards']['xp'])
        self.assertEqual(records[0]['archive_level_reward_observations'][0]['value'], 6000)
        self.assertEqual(records[0]['archive_level_reward_observations'][0]['player_level'], 22)

    def test_npc_role_and_quest_relationship_are_explicit(self):
        html = page('Fixture NPC', '''<h2>Details</h2><dl class="kv"><div><dt>Role</dt><dd>General NPC</dd></div>
            <div><dt>Race</dt><dd>N/A</dd></div></dl><h2>Quests given (1)</h2><ul>
            <li><a href="/quests/fixture">Fixture Quest</a></li></ul><h2>Loot (0)</h2>''', 'Level 22')
        records, _ = collector.parse_page(ORIGIN + '/mobs/fixture', html)
        self.assertEqual(records[0]['type'], 'npc')
        self.assertEqual(records[0]['quests_given'], ['Fixture Quest'])
        self.assertIsNone(records[0]['race'])
        self.assertIsNone(records[0]['health'])

    def test_sample_frequencies_have_no_invented_quantity(self):
        html = page('Fixture Mob', '''<h2>Loot (1)</h2><div><table><tbody><tr>
            <td><a href="/items/fixture">Fixture Item</a></td><td>Mundane</td><td>33.3% <span>1/3</span></td>
            </tr></tbody></table></div>''', 'Level 18')
        records, _ = collector.parse_page(ORIGIN + '/mobs/fixture', html)
        loot = next(r for r in records if r['type'] == 'loot')
        self.assertEqual(loot['drops'][0]['chance'], '33.3%')
        self.assertIsNone(loot['drops'][0]['quantity'])
        self.assertEqual(loot['confidence'], 'low')
        self.assertEqual(record_errors(loot), [])

    def test_map_points_do_not_become_exact_spawns(self):
        html = page('Fixture Zone', '''<h2>Details</h2><dl class="kv"><div><dt>Mob levels</dt><dd>10–15</dd></div>
            <div><dt>Continent</dt><dd>Kojan</dd></div></dl><table><thead><tr><th>#</th><th>Place</th>
            <th>Coordinates</th><th>Who was there</th><th>Quests starting here</th></tr></thead><tbody>
            <tr><td>1</td><td>Camp</td><td>-10, 20</td><td><a href="/mobs/fixture">NPC</a></td><td></td></tr>
            </tbody></table>''')
        records, _ = collector.parse_page(ORIGIN + '/zones/fixture', html)
        self.assertEqual(records[0]['map_places'][0]['location']['raw'], '-10, 20')
        self.assertEqual([r['type'] for r in records], ['zone'])
        self.assertEqual(records[0]['level_range'], [10, 15])

    def test_external_queries_and_unrelated_links_are_not_queued(self):
        html = page('Fixture', '''<a href="/items/valid">Item</a><a href="/items?zone=1">Filter</a>
            <a href="https://example.org/items/other">External</a><a href="/items/valid#stats">Fragment</a>''')
        _, links = collector.parse_page(ORIGIN + '/items/fixture', html)
        self.assertEqual(links, [ORIGIN + '/items/valid'])

    def test_money_requires_explicit_denomination(self):
        self.assertEqual(collector.explicit_money('1 Silver, 40 Copper'), 140)
        self.assertEqual(collector.explicit_money('50c'), 50)
        self.assertIsNone(collector.explicit_money('50'))
        self.assertIsNone(collector.explicit_money('about 1 silver'))

    def test_parser_drift_fails_instead_of_empty_records(self):
        with self.assertRaises(ValueError):
            collector.parse_page(ORIGIN + '/items/fixture', '<html><h1>Access error</h1></html>')

    def test_batch_topic_cannot_escape_raw_directory(self):
        with self.assertRaises(ValueError):
            collector.batch_path('../../outside')

    def test_recipe_placeholders_are_not_numeric_levels(self):
        html = page('Adding a crafting', '''<table class="detail"><tr><th>Crafting class</th><td>Blacksmith</td></tr>
            <tr><th>Recipe level</th><td>&lt;recipe level&gt;</td></tr></table>''')
        records, _ = collector.parse_page(ORIGIN + '/crafting/recipes/fixture', html)
        self.assertEqual(records[0]['type'], 'recipe')
        self.assertEqual(records[0]['craft'], 'Blacksmith')
        self.assertIsNone(records[0]['level'])
        self.assertIsNone(records[0]['output'])
        self.assertEqual(records[0]['confidence'], 'low')

    def test_card_pool_labels_and_negative_gain_are_preserved(self):
        pools = '<span title="Demand">0</span><span title="Reason">0</span><span title="Inspire">0</span><span title="Flattery">-2</span>'
        html = page('Fixture Card', f'''<dl class="kv"><div><dt>Expression</dt><dd>Inspire</dd></div>
            <div><dt>To opponent</dt><dd>{pools}</dd></div><div><dt>Influence</dt><dd>0-0</dd></div>
            <div><dt>Timer</dt><dd>3-5 turns</dd></div></dl>''')
        records, _ = collector.parse_page(ORIGIN + '/diplomacy/cards/fixture', html)
        r = records[0]
        self.assertEqual(r['type'], 'diplomacy')
        self.assertEqual(r['opponent_gain']['flattery'], -2)
        self.assertEqual(r['influence_range'], [0, 0])
        self.assertEqual(r['timer_turns'], [3, 5])
        self.assertIsNone(r['push'])

    def test_ability_ranks_reject_misaligned_rows(self):
        html = page('Fixture Ability', '''<h2>Ranks</h2><div><table><tbody>
            <tr><td>I</td><td>1</td><td>10</td><td>Effect</td></tr>
            <tr><td>55</td><td>702</td><td>Sneer</td><td>Malformed</td></tr></tbody></table></div>''',
            '<a href="/classes/necromancer">Necromancer</a> · Level 1')
        records, _ = collector.parse_page(ORIGIN + '/abilities/fixture', html)
        r = records[0]
        self.assertEqual(r['class'], 'Necromancer')
        self.assertEqual(r['ranks'], [dict(rank='I', level_learned=1, cost_raw='10')])
        self.assertEqual(r['confidence'], 'low')
        self.assertIsNone(r['cost'])


class ArchivePublicationTests(unittest.TestCase):
    def test_batch_network_counts_exclude_prior_requests_and_include_failed_attempt(self):
        class Client:
            network_requests = 7
            network_request_attempts = 9
            def get(self, url):
                self.network_request_attempts += 1
                if url.endswith('/failed'):
                    raise TimeoutError('fixture timeout')
                self.network_requests += 1
                return page('Fixture Item', '<h2>Properties</h2>')
        state = self.root / 'state'
        destination = self.root / 'raw' / 'batch'
        with patch.object(collector, 'STATE', state), patch.object(collector, 'batch_path', return_value=destination):
            _, fatal, _ = collector.collect(Client(), [ORIGIN + '/items/fixture', ORIGIN + '/items/failed'], 2, 'fixture')
        manifest = json.loads((destination / 'manifest.json').read_text())
        self.assertTrue(fatal)
        self.assertEqual(manifest['network_requests'], 1)
        self.assertEqual(manifest['network_request_attempts'], 2)

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='archive-test-', dir=HERE / 'tests')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        location = patch.object(collector, 'HERE', self.root)
        location.start()
        self.addCleanup(location.stop)

    def test_done_checkpoint_follows_successful_publication(self):
        class Client:
            network_requests = 0
            def get(self, url):
                return page('Fixture Item', '<h2>Properties</h2>')
        state = self.root / 'state'
        destination = self.root / 'raw' / 'batch'
        with patch.object(collector, 'STATE', state), patch.object(collector, 'batch_path', return_value=destination):
            collector.collect(Client(), [ORIGIN + '/items/fixture'], 1, 'fixture')
        self.assertTrue((destination / 'REPORT.md').exists())
        self.assertEqual(json.loads((state / 'done.json').read_text()), [ORIGIN + '/items/fixture'])

    def test_publication_failure_does_not_mark_pages_done(self):
        class Client:
            network_requests = 0
            def get(self, url):
                return page('Fixture Item', '')
        state = self.root / 'state'
        destination = self.root / 'raw' / 'batch'
        with patch.object(collector, 'STATE', state), patch.object(collector, 'batch_path', return_value=destination):
            original = Path.write_text
            def fail_report(path, *args, **kwargs):
                if path == destination / 'REPORT.md':
                    raise OSError('fixture disk failure during publication')
                return original(path, *args, **kwargs)
            with patch.object(Path, 'write_text', new=fail_report):
                with self.assertRaises(OSError):
                    collector.collect(Client(), [ORIGIN + '/items/fixture'], 1, 'fixture')
        self.assertFalse((state / 'done.json').exists())
        self.assertTrue((destination / 'item.jsonl').exists())

    def test_fetch_failure_is_reported_and_remains_pending(self):
        class Client:
            network_requests = 0
            def get(self, url):
                raise RuntimeError('fixture access denial')
        state = self.root / 'state'
        destination = self.root / 'raw' / 'batch'
        url = ORIGIN + '/items/fixture'
        with patch.object(collector, 'STATE', state), patch.object(collector, 'batch_path', return_value=destination):
            queue, fatal, _ = collector.collect(Client(), [url], 1, 'fixture')
        self.assertTrue(fatal)
        self.assertEqual(queue, [url])
        self.assertEqual(json.loads((state / 'done.json').read_text()), [])
        self.assertTrue((destination / 'gaps.jsonl').exists())

    def test_client_rejects_query_urls_before_network(self):
        with patch.object(ArchiveClient, 'get', return_value='User-agent: *\nDisallow: /*?\nCrawl-delay: 5\n'):
            client = ArchiveClient(self.root / 'cache')
        with patch('archive_client.build_opener') as fetch:
            with self.assertRaises(ValueError):
                client.get(ORIGIN + '/items?zone=1')
            with self.assertRaises(ValueError):
                client.get('https://example.org/items/fixture')
            fetch.assert_not_called()

    def test_network_request_waits_for_shared_rate_clock(self):
        with patch.object(ArchiveClient, 'get', return_value='User-agent: *\nCrawl-delay: 5\n'):
            client = ArchiveClient(self.root / 'cache')
        client.clock.write_text('1000', encoding='utf-8')
        url = ORIGIN + '/items/fixture'
        with (patch('archive_client.time.time', return_value=1002),
              patch('archive_client.time.sleep') as sleep,
              patch('archive_client.build_opener') as opener):
            response = opener.return_value.open.return_value.__enter__.return_value
            response.url = url
            response.read.return_value = b'<html>Fixture</html>'
            client.get(url)
        sleep.assert_called_once_with(3)

    def test_graceful_stop_publishes_pending_queue_without_fetching(self):
        class Client:
            network_requests = 0
            def get(self, url):
                raise AssertionError('network must not run after a stop signal')
        state = self.root / 'state'
        state.mkdir()
        (state / 'stop.request').write_text('stop')
        destination = self.root / 'raw' / 'batch'
        url = ORIGIN + '/items/fixture'
        with patch.object(collector, 'STATE', state), patch.object(collector, 'batch_path', return_value=destination):
            queue, fatal, _ = collector.collect(Client(), [url], 1, 'fixture')
        self.assertFalse(fatal)
        self.assertEqual(queue, [url])
        manifest = json.loads((destination / 'manifest.json').read_text())
        self.assertEqual(manifest['pages'], 0)
        self.assertTrue(manifest['stop_requested'])

    def test_trainer_relationship_enriches_the_explicitly_linked_npc(self):
        class Client:
            network_requests=0
            def get(self,url):
                if '/mobs/' in url:
                    return page('Fixture NPC','<dl class="kv"><div><dt>Role</dt><dd>General NPC</dd></div></dl>','Level 30')
                return page('Warrior Class Trainers','<a href="/classes/warrior">Warrior</a><div class="trainer-body"><a href="/mobs/fixture">Fixture NPC</a></div>')
        state=self.root/'state'
        destination=self.root/'raw'/'batch'
        with patch.object(collector,'STATE',state),patch.object(collector,'batch_path',return_value=destination):
            collector.collect(Client(),[ORIGIN+'/mobs/fixture',ORIGIN+'/classes/warrior/trainers'],2,'fixture')
        records=[json.loads(line) for line in (destination/'npc.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(records),1)
        self.assertIn('trainer',records[0]['services'])
        self.assertEqual(records[0]['trainer_of'],'Warrior')
        self.assertEqual(records[0]['level'],30)
        self.assertEqual(len(records[0]['sources']),2)

    def test_shared_trainer_does_not_select_only_the_first_class(self):
        class Client:
            network_requests=0
            def get(self,url):
                class_name=url.split('/')[-2].title()
                return page(class_name+' Trainers',f'<a href="/classes/{class_name.lower()}">{class_name}</a><div class="trainer-body"><a href="/mobs/fixture">Fixture NPC</a></div>')
        state=self.root/'state'
        destination=self.root/'raw'/'batch'
        urls=[ORIGIN+'/classes/warrior/trainers',ORIGIN+'/classes/cleric/trainers']
        with patch.object(collector,'STATE',state),patch.object(collector,'batch_path',return_value=destination):
            collector.collect(Client(),urls,2,'fixture')
        r=json.loads((destination/'npc.jsonl').read_text(encoding='utf-8').splitlines()[0])
        self.assertIsNone(r['trainer_of'])
        self.assertEqual(r['training_classes_recorded'],['Warrior','Cleric'])


if __name__ == '__main__':
    unittest.main()
