from pathlib import Path
import json
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from build_evidence_index import build


class EvidenceIndexTests(unittest.TestCase):
    def test_conflicting_versions_remain_separate_and_explicit_zones_are_indexed(self):
        with tempfile.TemporaryDirectory(prefix='index-test-',dir=HERE/'tests') as scratch:
            root=Path(scratch)
            for name,value in [('older',10),('newer',20)]:
                folder=root/'raw'/name
                folder.mkdir(parents=True)
                (folder/'REPORT.md').write_text('Fixture report',encoding='utf-8')
                r=dict(type='creature',name='Fixture Wolf',zone='Fixture Zone',level=value,
                       sources=[dict(url='https://example.org/record')],confidence='medium')
                (folder/'creature.jsonl').write_text(json.dumps(r)+'\n',encoding='utf-8')
            index=build(root)
            self.assertEqual(len(index['records']),2)
            self.assertEqual(len(index['by_name']['creature:fixture wolf']),2)
            self.assertEqual(len(index['by_zone']['Fixture Zone']),2)
            self.assertEqual(index['summary']['errors'],0)

    def test_in_progress_batches_are_not_indexed(self):
        with tempfile.TemporaryDirectory(prefix='index-test-',dir=HERE/'tests') as scratch:
            root=Path(scratch)
            folder=root/'raw'/'incomplete'
            folder.mkdir(parents=True)
            (folder/'item.jsonl').write_text('{}\n',encoding='utf-8')
            self.assertEqual(build(root)['summary']['research_rows'],0)


if __name__=='__main__':
    unittest.main()
