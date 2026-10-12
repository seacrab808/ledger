"""Evidence conservation, paired inputs, resource and quality invariants."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class NativeEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=ROOT/'results/lmcache_native/native-01'
        cls.summary=json.loads((ROOT/'records/lmcache-native-summary.json').read_text(encoding='utf-8'))

    def test_paired_archived_inputs(self):
        traces=json.loads((self.path/'input.json').read_text(encoding='utf-8'))
        self.assertEqual(len(traces),12)
        for t in traces:
            old=json.loads((ROOT/'results/kv_lifecycle'/t['id']/'run.json').read_text(encoding='utf-8'))
            self.assertEqual(t['requests'],old['requests'])
        baseline=json.loads((self.path/'baseline.json').read_text(encoding='utf-8'))
        for c in [64,128,256]:
            arm=json.loads((self.path/f'{c}.json').read_text(encoding='utf-8'))
            self.assertEqual([(r['trace'],r['index'],r['prompt_tokens']) for r in baseline],[(r['trace'],r['index'],r['prompt_tokens']) for r in arm])

    def test_payload_and_compute_conservation(self):
        for r in self.summary['overall']:
            self.assertEqual(r['prefill_tokens_saved']+r['actual_forward_tokens'],r['prompt_tokens'])
            self.assertEqual(r['prefill_tokens_saved']+r['recompute_vs_LCP_tokens'],r['oracle_LCP_tokens'])
            self.assertEqual(r['disk_write_bytes'],r['stored_unique_bytes'])
            self.assertEqual(r['disk_read_bytes'],r['prefill_tokens_saved']*12288)
            self.assertLessEqual(r['derived_unique_consumed_bytes'],r['stored_unique_bytes'])
            self.assertEqual(r['derived_never_consumed_bytes']+r['derived_unique_consumed_bytes'],r['stored_unique_bytes'])

    def test_quality_is_not_hidden(self):
        checks=json.loads((self.path/'correctness.json').read_text(encoding='utf-8'))
        self.assertEqual(self.summary['checks_passed'],sum(c['passed'] for c in checks))
        self.assertEqual(self.summary['valid_performance_claim'],all(c['passed'] for c in checks))
        self.assertFalse(self.summary['valid_performance_claim'])
        self.assertIsNone(self.summary['not_measured']['physical_NAND_bytes'])

    def test_bounded_cleanup(self):
        validation=json.loads((ROOT/'records/lmcache-runtime-validation.json').read_text(encoding='utf-8'))
        self.assertLess(validation['project_runtime_bytes'],10*2**30)
        for v in validation.values():
            if isinstance(v,dict) and 'owned_group_alive' in v:
                self.assertEqual(v['owned_group_alive'],[])
                self.assertLessEqual(v['status']['max_GPU'],4*2**30)
                self.assertLessEqual(v['status']['max_RSS'],8*2**30)

    def test_batch_bytes_and_hash(self):
        rows=self.summary['batch_component'];self.assertEqual(len(rows),18)
        for r in rows:
            self.assertTrue(r['hash_correctness'])
            for kind in ['write','read']:
                self.assertEqual(sum(e['bytes'] for e in r[kind+'_events']),r['payload_bytes'])
                self.assertEqual(len(r[kind+'_events']),r['objects'])

    def test_collected_text_hashes_survive_checkout(self):
        for manifest in (ROOT/'results/lmcache_native').glob('*/manifest.json'):
            record=json.loads(manifest.read_text(encoding='utf-8'))
            for name,value in record['files'].items():
                self.assertEqual(hashlib.sha256((manifest.parent/name).read_bytes()).hexdigest(),value['sha256'],str(manifest.parent/name))

if __name__=='__main__':unittest.main()
