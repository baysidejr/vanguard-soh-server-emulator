from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import collect_archive as collector
from archive_extract import effect_facts
from test_archive import page


class AbilityEffectTests(unittest.TestCase):
    def test_bellow_details_boundary_preserves_historical_scope(self):
        r=self.parse('<h2>Effect</h2><div class="tooltip">You bellow, blasting your opponent for 84 to 91 arcane damage.</div><h2>As it was earlier</h2><div class="tooltip">You bellow, blasting your opponent for 132-143 arcane damage. Cost: Submit Info Cast Time: 0 Refresh: 6 Range: 30</div>')
        self.assertEqual([o['scope'] for o in r['effect_observations']],['current','historical'])
        self.assertEqual([o['facts'][0]['values'] for o in r['effect_observations']],[[84,91],[132,143]])
        self.assertIsNone(r['cost'])
        self.assertIsNone(r['refresh_seconds'])

    def test_bellow_boundary_does_not_discard_unrecognized_prose(self):
        for suffix in [' Only against undead.', ' Costless attacks only.', ' unless resisted. Cost: 0']:
            self.assertEqual(effect_facts('You bellow, blasting your opponent for 132-143 arcane damage.'+suffix),[])

    def test_signed_effect_stat_modifiers_preserve_labels_and_scope(self):
        facts=effect_facts('+8 Arcane Spell Damage -3 Spiritual Absorption +8% Health')
        self.assertEqual([f['values'] for f in facts],[[8],[-3]])
        self.assertEqual([f['stat_recorded'] for f in facts],['Arcane Spell Damage','Spiritual Absorption'])
        self.assertTrue(all(f['conditions_unparsed'] for f in facts))

    def test_item_chance_observations_do_not_invent_healing_or_percentage_basis(self):
        fact=effect_facts('15% chance on attack to heal wearer +8 Health')[0]
        self.assertEqual(fact['chance_percent'],15)
        self.assertIsNone(fact['healing_amount'])
        self.assertEqual(effect_facts('150% chance on attack to heal wearer'),[])
        fact=effect_facts('Attacks have a 5% greater chance of scoring a critical hit.')[0]
        self.assertEqual(fact['values'],[5])
        self.assertTrue(fact['basis_unresolved'])
        self.assertTrue(fact['conditions_unparsed'])

    def test_explicit_effect_duration_converts_only_labelled_units(self):
        for raw, expected in [('1 hour',3600),('2 minutes',120),('25 sec',25)]:
            fact=effect_facts('This effect will stay on the user for '+raw+'.')[0]
            self.assertEqual(fact['kind'],'effect_duration')
            self.assertEqual(fact['duration_seconds'],expected)
            self.assertTrue(fact['conditions_unparsed'])
        self.assertEqual(effect_facts('This effect will stay on the user for 25.'),[])

    def test_explicit_attribute_increase_is_not_a_percentage(self):
        fact=effect_facts('The words increase the users strength by 35 when spoken aloud.')[0]
        self.assertEqual(fact['attribute'],'strength')
        self.assertEqual(fact['values'],[35])
        self.assertTrue(fact['conditions_unparsed'])
        self.assertEqual(effect_facts('Increases your strength by 35%.'),[])
        self.assertEqual(effect_facts('Increases your strength by 35 %.'),[])

    def test_explicit_sleep_duration_requires_units(self):
        fact=effect_facts('This poison puts the target into a deep sleep for 25 sec.')[0]
        self.assertEqual(fact['effect'],'sleep')
        self.assertEqual(fact['duration_seconds'],25)
        self.assertTrue(fact['conditions_unparsed'])
        self.assertEqual(effect_facts('Puts the target into a deep sleep for 25.'),[])

    def test_healing_amount_and_explicit_duration_are_preserved(self):
        fact=effect_facts('Heals your defensive target for 704 over 18 sec.')[0]
        self.assertEqual(fact['values'],[704])
        self.assertEqual(fact['duration_seconds'],18)
        self.assertTrue(fact['conditions_unparsed'])

    def test_group_heal_radius_is_not_healing_amount(self):
        fact=effect_facts('Heals all allies within 10m for 555.')[0]
        self.assertEqual(fact['values'],[555])
        self.assertEqual(fact['radius_recorded'],dict(value=10,unit='m'))
        self.assertIsNone(fact['duration_seconds'])

    def test_periodic_restoration_does_not_invent_total_duration(self):
        fact=effect_facts('Restores 10 endurance every 3 sec.')[0]
        self.assertEqual(fact['values'],[10])
        self.assertEqual(fact['interval_seconds'],3)
        self.assertNotIn('duration_seconds',fact)

    def test_percent_healing_is_not_a_flat_amount(self):
        self.assertEqual(effect_facts('Heals an ally for 20%.'),[])
        self.assertEqual(effect_facts('Heals an ally for 10 to 20%.'),[])
        self.assertEqual(effect_facts('Heals an ally for 1.5 to 2.5%.'),[])

    def test_flat_healing_range_is_not_truncated(self):
        fact=effect_facts('Heals an ally for 10 to 20.')[0]
        self.assertEqual(fact['values'],[10,20])

    def test_historical_level_does_not_replace_current_level(self):
        r=self.parse('<dl class="kv"><div><dt>Level</dt><dd>6</dd></div></dl><h2>As it was earlier</h2><dl class="facts"><div><dt>Level in 2007</dt><dd>8 <span>— now 6</span></dd></div></dl><p><a href="https://example.org/old">Source</a><a href="/abilities/as-it-was">Index</a></p>')
        self.assertEqual(r['level_learned'],6)
        self.assertEqual(r['historical_level_observations'][0]['level_learned'],8)
        self.assertEqual(r['historical_source_urls_recorded'],['https://example.org/old'])

    def parse(self,body,name='Fixture I'):
        return collector.parse_page(collector.ORIGIN+'/abilities/fixture',page(name,body))[0][0]

    def test_named_resource_cost_is_used(self):
        r=self.parse('<dl class="kv"><div><dt>Endurance cost</dt><dd>20</dd></div><div><dt>Cast time</dt><dd>Instant</dd></div></dl>')
        self.assertEqual(r['cost'],{'endurance':20})
        self.assertEqual(r['cast_time_seconds'],0)
        self.assertEqual(r['rank'],'I')

    def test_conflicting_cost_labels_withhold_cost(self):
        r=self.parse('<dl class="kv"><div><dt>endurance cost</dt><dd>171</dd></div><div><dt>Endurance cost</dt><dd>30</dd></div></dl>')
        self.assertIsNone(r['cost'])
        self.assertEqual(r['cost_observations']['endurance'],[171,30])
        self.assertEqual(r['confidence'],'low')

    def test_duplicate_equal_costs_are_not_added(self):
        r=self.parse('<dl class="kv"><div><dt>Energy cost</dt><dd>10</dd></div><div><dt>Cost</dt><dd>10 energy</dd></div></dl>')
        self.assertEqual(r['cost'],{'energy':10})

    def test_current_and_historical_damage_are_kept_separate(self):
        r=self.parse('<h2>Effect</h2><div class="tooltip">A powerful attack that increases melee damage by 6.</div><h2>As it was earlier</h2><div class="tooltip">A powerful attack that increases melee damage by 7.</div>')
        self.assertEqual([o['scope'] for o in r['effect_observations']],['current','historical'])
        self.assertEqual([o['facts'][0]['values'] for o in r['effect_observations']],[[6],[7]])
        self.assertEqual(r['tooltip'],'A powerful attack that increases melee damage by 6.')

    def test_long_tooltip_is_not_replaced_with_a_paraphrase(self):
        r=self.parse('<h2>Effect</h2><div class="tooltip">Deals 359 to 382 damage. '+('Unresolved conditions and effects. '*10)+'</div>')
        self.assertIsNone(r['tooltip'])
        self.assertEqual(r['effect_observations'][0]['facts'][0]['values'],[359,382])

    def test_percentage_is_not_misread_as_flat_bonus(self):
        self.assertEqual(effect_facts('Increases melee damage by 20%.'),[])

    def test_restoration_duration_keeps_explicit_seconds(self):
        facts=effect_facts('Restoring 5 to 10 energy over 10 seconds.')
        self.assertEqual(facts[0]['resource'],'energy')
        self.assertEqual(facts[0]['duration_seconds'],10)

    def test_weaknesses_are_distinct(self):
        r=self.parse('<dl class="kv"><div><dt>Causes</dt><dd>Dazed</dd></div><div><dt>Exploits weakness</dt><dd>Soul Wracked</dd></div></dl>')
        self.assertEqual(r['causes_weakness'],'Dazed')
        self.assertEqual(r['exploits_weakness'],'Soul Wracked')

    def test_refresh_and_recast_conflict_is_not_overwritten(self):
        r=self.parse('<dl class="kv"><div><dt>Refresh</dt><dd>30 seconds</dd></div><div><dt>Recast</dt><dd>1 minute</dd></div></dl>')
        self.assertIsNone(r['refresh_seconds'])
        self.assertEqual([o['seconds'] for o in r['timing_observations']['refresh_seconds']],[30,60])
        self.assertEqual(r['confidence'],'low')

    def test_equivalent_timing_units_agree(self):
        r=self.parse('<dl class="kv"><div><dt>Refresh</dt><dd>60 seconds</dd></div><div><dt>Recast</dt><dd>1 minute</dd></div></dl>')
        self.assertEqual(r['refresh_seconds'],60)

    def test_duplicate_cast_labels_preserve_conflict(self):
        r=self.parse('<dl class="kv"><div><dt>Cast time</dt><dd>Instant</dd></div><div><dt>Cast time</dt><dd>2 seconds</dd></div></dl>')
        self.assertIsNone(r['cast_time_seconds'])
        self.assertEqual(r['confidence'],'low')


if __name__=='__main__':
    unittest.main()
