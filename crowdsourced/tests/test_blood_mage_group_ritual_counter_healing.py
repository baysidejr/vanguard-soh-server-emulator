import unittest
from archive_extract import effect_facts
KIND = 'blood_mage_group_ritual_counter_healing_observation'
class BloodMageGroupRitualCounterHealingTests(unittest.TestCase):
    def test_counter_keeps_radius_origin_unknown(self):
        literal = 'Counters a spell being cast and channels the energy into healing power, restoring 492 health to all group members within 10 meters.'
        # Read the independently reviewed literal rather than assuming punctuation.
        import json
        from pathlib import Path
        review=json.loads((Path(__file__).resolve().parents[1]/'reviewed/BLOOD_MAGE_DAMAGE_GROUP_BUFF_RITUAL_COUNTER_HEALING_SOURCE_REVIEW_ITERATION714.json').read_text())
        row,=[r for r in review['rows'] if r['name']=='Metamorphism I']
        literal=row['observations'][0]['literal']
        fact,=[f for f in effect_facts(literal) if f['kind']==KIND]
        self.assertEqual((fact['healing_amount'],fact['radius_meters']),(492,10))
        for key in ('radius_origin','counter_success_rules','operative_values','historical_authentication'):
            self.assertIsNone(fact[key])
        for changed in (literal.replace('492','493'),literal+' Only against undead.'):
            self.assertFalse(any(f['kind']==KIND for f in effect_facts(changed)))
    def test_periodic_healing_does_not_invent_tick_interval(self):
        literal='This ritual heals an ally, other than yourself, for 3072 health over 20 seconds. Reduces Blood Union by 3. Only usable from Blood Union 3 or greater.'
        fact,=[f for f in effect_facts(literal) if f['kind']==KIND]
        self.assertEqual((fact['health_over_duration'],fact['duration_seconds'],fact['minimum_blood_union']),(3072,20,3))
        self.assertIsNone(fact['tick_interval_seconds'])
        self.assertIsNone(fact['stacking_rules'])
