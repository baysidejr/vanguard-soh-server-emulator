"""Evidence-based enrichment rules for previously downloaded pages."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import collect_archive as collector
from archive_extract import role_services
from enrich_cached import CacheOnlyClient
from test_archive import page
import test_convert as conversions

record = conversions.record
converter = conversions.converter


class ExtractionTests(unittest.TestCase):
    def test_explicit_class_trainer_role_and_region_labels(self):
        html=page('Fixture Trainer','<dl class="kv"><div><dt>Role</dt><dd>Class Trainer - Blood Mage</dd></div><div><dt>Continent</dt><dd>Qalia</dd></div><div><dt>Locations seen</dt><dd>Fixture Landing</dd></div></dl>','Level 50')
        r=collector.parse_page(collector.ORIGIN+'/mobs/fixture',html)[0][0]
        self.assertEqual(r['trainer_of'],'Blood Mage')
        self.assertEqual(r['training_classes_recorded'],['Blood Mage'])
        self.assertEqual(r['continent'],'Qalia')
        self.assertEqual(r['locations_seen_recorded'],'Fixture Landing')
        self.assertIsNone(r['zone'])
        self.assertIsNone(r['health'])

    def test_item_classes_on_filtered_links_are_read_without_queuing(self):
        html = page('Fixture Helm', '<h2>Usable by</h2><p><a href="/items?class=5">Cleric</a><a href="/items?class=4">Paladin</a></p>')
        records, links = collector.parse_page(collector.ORIGIN+'/items/fixture', html)
        self.assertEqual(records[0]['class_restrictions'], ['Cleric','Paladin'])
        self.assertEqual(links, [])

    def test_explicit_merchant_role_creates_npc_and_unknown_inventory(self):
        html = page('Fixture Vendor', '<dl class="kv"><div><dt>Role</dt><dd>General Goods Merchant - Repairs</dd></div></dl>', 'Level 20')
        records, _ = collector.parse_page(collector.ORIGIN+'/mobs/fixture', html)
        npc = next(r for r in records if r['type']=='npc')
        merchant = next(r for r in records if r['type']=='merchant')
        self.assertEqual(npc['services'], ['merchant','repair'])
        self.assertIsNone(merchant['sells'])
        self.assertIsNone(npc['health'])

    def test_hand_in_to_is_a_turn_in_not_an_extra_objective(self):
        html = page('Fixture Quest', '<dl class="kv"><div><dt>Hand in to</dt><dd>Fixture NPC</dd></div></dl>','Level 10')
        records, _ = collector.parse_page(collector.ORIGIN+'/quests/fixture', html)
        self.assertEqual(records[0]['turn_in'],'Fixture NPC')
        self.assertIsNone(records[0]['steps'])

    def test_reward_xp_money_and_explicit_choice_are_extracted(self):
        html = page('Fixture Quest', '''<h2>Quest Rewards</h2><p>1 Silver, 40 Copper<br>5474 XP<br>Choose one of:</p>
            <table><tr><td>1 x</td><td></td><td>Jewelry</td><td>Neck</td><td>[Clvl 13]</td><td>[Ilvl 23]</td><td>Fixture Pendant</td></tr></table>''','Level 14')
        records, _ = collector.parse_page(collector.ORIGIN+'/quests/fixture',html)
        self.assertEqual(records[0]['rewards']['xp'],5474)
        self.assertEqual(records[0]['rewards']['coin_copper'],140)
        self.assertEqual(records[0]['rewards']['choice'],['Fixture Pendant'])

    def test_reward_coin_conflict_does_not_overwrite_a_field(self):
        html = page('Fixture Quest', '''<dl class="kv"><div><dt>Coin reward</dt><dd>50c</dd></div></dl>
            <h2>Quest Rewards</h2><p>1 Silver, 40 Copper</p>''')
        records, _ = collector.parse_page(collector.ORIGIN+'/quests/fixture',html)
        self.assertEqual(records[0]['rewards']['coin_copper'],50)
        self.assertEqual(records[0]['archive_reward_values'][0]['value'],140)
        self.assertEqual(records[0]['confidence'],'low')

    def test_partial_objective_matches_do_not_become_complete_steps(self):
        html = page('Fixture Quest', '<h2>Objectives</h2><div>Fixture Item (3)\nCollect these items, then use a special device.</div>')
        records, _ = collector.parse_page(collector.ORIGIN+'/quests/fixture',html)
        self.assertIsNone(records[0]['steps'])
        self.assertEqual(records[0]['candidate_steps'][0]['count'],3)
        self.assertEqual(records[0]['candidate_steps'][0]['target'],'Fixture Item')

    def test_plural_kill_label_is_not_singularized(self):
        html = page('Fixture Quest','<h2>Objectives</h2><div>Foreststalkers Slain (12)</div>')
        records, _ = collector.parse_page(collector.ORIGIN+'/quests/fixture',html)
        self.assertIsNone(records[0]['steps'])
        self.assertIsNone(records[0]['candidate_steps'][0]['target'])
        self.assertEqual(records[0]['candidate_steps'][0]['kind'],'kill')

    def test_explicit_required_item_and_counter_match_can_be_collected(self):
        html = page('Fixture Quest','''<h2>Objectives</h2><div>Fixture Item (0/1)</div>
            <h2>Quest Required Items</h2><table><tr><td>1 x</td><td></td><td>Quest Item</td><td>Inventory</td>
            <td>[Clvl 1]</td><td>[Ilvl 1]</td><td>Fixture Item</td></tr></table>''')
        records, _ = collector.parse_page(collector.ORIGIN+'/quests/fixture',html)
        self.assertEqual(records[0]['steps'][0]['target'],'Fixture Item')
        self.assertEqual(records[0]['steps'][0]['kind'],'collect')

    def test_multiple_counters_on_one_line_are_retained(self):
        html = page('Fixture Quest','<h2>Objectives</h2><div>Item A (0/6) Item B (0/3)</div>')
        records, _ = collector.parse_page(collector.ORIGIN+'/quests/fixture',html)
        self.assertEqual([c['count'] for c in records[0]['archive_objective_counters']],[6,3])
        self.assertIsNone(records[0]['steps'])

    def test_timing_units_are_converted_only_when_explicit(self):
        html = page('Fixture Ability','''<dl class="kv"><div><dt>Cast time</dt><dd>10.0</dd></div>
            <div><dt>Refresh</dt><dd>2 minutes</dd></div><div><dt>Range</dt><dd>5m</dd></div>
            <div><dt>Cost</dt><dd>10 mana</dd></div></dl>''')
        records, _ = collector.parse_page(collector.ORIGIN+'/abilities/fixture',html)
        self.assertIsNone(records[0]['cast_time_seconds'])
        self.assertEqual(records[0]['refresh_seconds'],120)
        self.assertEqual(records[0]['range']['value'],5)
        self.assertEqual(records[0]['cost'],{'mana':10})

    def test_cache_only_client_cannot_fall_back_to_network(self):
        client=CacheOnlyClient(HERE/'tests'/'absent-cache')
        with self.assertRaises(FileNotFoundError):
            client.get(collector.ORIGIN+'/items/fixture')
        with self.assertRaises(ValueError):
            client.get(collector.ORIGIN+'/items?zone=1')

    def test_class_table_cost_and_range_do_not_get_invented_units(self):
        html=page('Warrior','''<table><thead><tr><th>Lv</th><th>Ability</th><th>School</th><th>Cost</th>
            <th>Cast</th><th>Range</th><th>Effect</th></tr></thead><tbody><tr><td>1</td>
            <td><a href="/abilities/brutal-strike-i">Brutal Strike I</a></td><td>Melee Attack</td><td>20</td>
            <td>Instant</td><td>5</td><td>A powerful attack</td></tr></tbody></table>''')
        records,links=collector.parse_page(collector.ORIGIN+'/classes/warrior',html)
        r=records[0]
        self.assertEqual(r['name'],'Brutal Strike I')
        self.assertEqual(r['level_learned'],1)
        self.assertEqual(r['class'],'Warrior')
        self.assertEqual(r['rank'],'I')
        self.assertEqual(r['cast_time_seconds'],0)
        self.assertIsNone(r['cost'])
        self.assertEqual(r['cost_recorded']['value'],20)
        self.assertIsNone(r['range'])
        self.assertEqual(r['range_recorded']['value'],5)
        self.assertEqual(links,[collector.ORIGIN+'/abilities/brutal-strike-i'])

    def test_class_ability_citations_are_not_shared_between_rows(self):
        html=page('Warrior','''<table><thead><tr><th>Lv</th><th>Ability</th><th>School</th><th>Cost</th>
            <th>Cast</th><th>Range</th><th>Effect</th></tr></thead><tbody>
            <tr><td>1</td><td><a href="/abilities/one">One</a></td><td></td><td></td><td></td><td></td><td></td></tr>
            <tr><td>2</td><td><a href="/abilities/two">Two</a></td><td></td><td></td><td></td><td></td><td></td></tr>
            </tbody></table>''')
        records,_=collector.parse_page(collector.ORIGIN+'/classes/warrior',html)
        records[0]['sources'].append(dict(url='https://example.org/other',title='Other',date=None))
        self.assertEqual(len(records[1]['sources']),1)
        self.assertEqual(records[1]['referenced_entities'],[dict(name='Two',url=collector.ORIGIN+'/abilities/two')])


class StatConversionTests(unittest.TestCase):
    setUp = conversions.ConversionTests.setUp
    batch = conversions.ConversionTests.batch
    def test_protocol_stat_and_modifier_names_accept_archive_codes(self):
        batch=self.batch([record('item','Fixture',item_type='jewelry',stats={'HIT_POINTS':44,'energy':11,'SPELL_DAMAGE_FOCUS':14})])
        item=converter.convert(batch,{})['items.json']['Fixture']
        self.assertEqual(item['stats'],{'hit_points':44,'energy':11})
        self.assertEqual(item['mods'],{'Spell Damage Focus':14})
        self.assertNotIn('_unsupported',item)
        self.assertTrue(converter.vgmsg.item_mods(item['stats'],item['mods']))

    def test_conflicting_stat_aliases_are_not_overwritten(self):
        batch=self.batch([record('item','Fixture',stats={'Hit Points':44,'hit_points':26})])
        item=converter.convert(batch,{})['items.json']['Fixture']
        self.assertNotIn('stats',item)
        self.assertEqual(item['_unsupported']['stats'],{'Hit Points':44,'hit_points':26})

    def test_fractional_modifiers_are_not_truncated(self):
        batch=self.batch([record('item','Fixture',stats={'spell_haste':0.5})])
        item=converter.convert(batch,{})['items.json']['Fixture']
        self.assertNotIn('mods',item)
        self.assertEqual(item['_unsupported']['stats'],{'spell_haste':0.5})


if __name__=='__main__':
    unittest.main()
