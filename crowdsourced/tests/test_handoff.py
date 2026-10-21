import json
from pathlib import Path
import tempfile
import unittest

import build_handoff


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'raw').mkdir()

    def record(self, name='Fixture', url='https://example.org/item', **extra):
        return dict(type='item', name=name, confidence='medium', notes='Test.',
                    sources=[dict(url=url, title=name, date=None)], item_type='armor',
                    slot='head', **extra)

    def batch(self, name, records, closed=True):
        p = self.root / 'raw' / name
        p.mkdir()
        (p / 'REPORT.md').write_text('Fixture')
        (p / 'manifest.json').write_text('{}')
        if closed:
            (p / 'VALIDATION.json').write_text('{}')
        (p / 'item.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in records))

    def test_replays_select_latest_parser_without_merging_fields(self):
        self.batch('a', [self.record(parser_version=1, armor=12)])
        self.batch('b', [self.record(parser_version=2, level_required=5)])
        records, ledger, errors, _, rows = build_handoff.select_records(self.root)
        self.assertEqual((rows, len(records), len(errors)), (2, 1, 0))
        self.assertNotIn('armor', records[0])
        self.assertEqual(ledger[0]['selected']['file'], 'raw/b/item.jsonl')

    def test_different_sources_same_name_are_withheld_globally(self):
        self.batch('a', [self.record(url='https://example.org/a')])
        self.batch('b', [self.record(url='https://example.org/b')])
        report = build_handoff.build(self.root)
        self.assertEqual(report['candidate_total'], 0)
        self.assertEqual(report['withheld_selected_records'], 2)

    def test_equal_rank_conflicts_withheld_and_open_batch_excluded(self):
        self.batch('a', [self.record(armor=1), self.record(armor=2)])
        self.batch('open', [self.record(name='Not published')], closed=False)
        records, _, errors, _, rows = build_handoff.select_records(self.root)
        self.assertEqual(records, [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(rows, 2)

    def test_proposal_preserves_unsupported_and_never_claims_import(self):
        self.batch('a', [self.record(class_restrictions=['Warrior'])])
        report = build_handoff.build(self.root)
        self.assertEqual(report['candidate_counts']['items.json'], 1)
        self.assertEqual(report['imported_by_this_tool'], 0)
        dest = self.root / 'reviewed/conversion-handoff'
        item = json.loads((dest / 'proposed/items.json').read_text())['Fixture']
        self.assertEqual(item['_unsupported']['class_restrictions'], ['Warrior'])
        disposition = json.loads((dest / 'DISPOSITION.json').read_text())[0]
        self.assertEqual(disposition['status'], 'proposal_requires_review')
        self.assertTrue(disposition['reasons'])

    def test_skipped_low_confidence_variant_is_not_counted_as_converted(self):
        low = self.record(url='https://example.org/uncertain')
        low['confidence'] = 'low'
        self.batch('a', [low])
        self.batch('b', [self.record()])
        report = build_handoff.build(self.root)
        self.assertEqual(report['candidate_total'], 1)
        self.assertEqual(report['withheld_selected_records'], 1)


if __name__ == '__main__':
    unittest.main()
