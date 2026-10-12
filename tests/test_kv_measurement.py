import unittest
import hashlib
import json
from pathlib import Path
from tools.kv_screen import fixtures,lcp
from tools.summarize_kv import summarize

class KVMeasurementTests(unittest.TestCase):
    def test_partial_hit_union_and_repeated_benefit_are_distinct(self):
        run={'pattern':'append','seed':42,'peak_rss_bytes':1,'cpu_seconds':1,
             'objects':[{'serialized_record_bytes':100,'persisted_tokens':10,'native_state_bytes':50,'scores_bytes':45,
                         'reuse_count':2,'max_reused_prefix_tokens':6,'saved_prefill_tokens':10,'removal':None}],
             'requests':[{'disk_prefill_tokens_skipped':4,'resident_prefill_tokens_skipped':0,'runtime_seconds':1},
                         {'disk_prefill_tokens_skipped':6,'resident_prefill_tokens_skipped':0,'runtime_seconds':1}]}
        s=summarize(run)
        self.assertEqual(s['token_instance_utilization'],.6)
        self.assertEqual(s['disk_saved_prefill_tokens'],10)
        self.assertEqual(s['unique_ever_used_record_bytes'],100)
        self.assertEqual(s['horizon_unused_token_instances'],4)
        self.assertEqual(s['record_ever_used_ratio'],1)
    def test_repeated_identical_trace_is_not_three_fixtures(self):
        self.assertNotEqual(fixtures('append',42),fixtures('append',43))
        self.assertNotEqual(fixtures('append',42),fixtures('edit',42))
    def test_token_prefix_respects_first_edit(self):
        self.assertEqual(lcp([1,2,3,4],[1,2,7,4]),2)
        self.assertEqual(lcp([1,2],[1,2,3]),2)
    def test_final_logit_refresh_is_not_chunk_boundary_loss(self):
        p=l=256;c=256
        oracle=min(l,p-1);chunk=min((l//c)*c,p-1)
        self.assertEqual(oracle-chunk,0)
        p=400;l=257
        self.assertEqual(min(l,p-1)-min((l//c)*c,p-1),1)
    def test_measured_runs_preserve_frozen_inputs_and_metric_units(self):
        root=Path(__file__).resolve().parents[1]
        if not (root/'records/kv-screen-summary.json').exists(): self.skipTest('runtime evidence not present')
        code_hash=hashlib.sha256((root/'tools/kv_screen.py').read_bytes()).hexdigest()
        from tools.kv_screen import digest
        config=json.loads((root/'configs/experiments/kv-screen.json').read_text())
        for seed in (42,43,44):
            for pattern in ('append','retry','edit','session_end'):
                run=json.loads((root/f'results/kv_lifecycle/{pattern}-{seed}/run.json').read_text())
                self.assertEqual(run['code_sha256'],code_hash)
                self.assertEqual(run['config_hash'],digest(config))
                self.assertEqual(run['fixture_hash'],digest(fixtures(pattern,seed)))
                self.assertLessEqual(run['peak_rss_bytes'],config['runtime_rss_ceiling_bytes'])
                self.assertIsNone(run['pure_kv_bytes'])
                self.assertEqual(len(run['requests']),24 if pattern!='session_end' else 16)
                s=summarize(run)
                self.assertGreaterEqual(s['token_instance_utilization'],0)
                self.assertLessEqual(s['token_instance_utilization'],1)

if __name__=='__main__': unittest.main()
