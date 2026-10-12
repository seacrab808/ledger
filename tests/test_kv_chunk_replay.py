import json
from pathlib import Path
import unittest
from tools.replay_kv_chunks import lcp,percentile,savings,replay

class PairedReplayTests(unittest.TestCase):
    def test_token_prefix_and_percentile(self):
        self.assertEqual(lcp([1,2,3],[1,2,9]),2)
        self.assertEqual(percentile([0,10],.5),5)
    def test_exact_prompt_final_refresh_not_boundary_loss(self):
        self.assertEqual(savings(256,256),255)
        self.assertEqual(savings(256,256,256),255)
    def test_missing_storage_coverage_and_matching_boundary_are_separate(self):
        # Source N=3, L=3: missing one tail token; no stored-chunk boundary loss.
        c=2;l=3;n=3;p=4
        oracle=savings(l,p);coverage=savings(min(l,n//c*c),p);chunk=savings(l,p,c)
        self.assertEqual((oracle-coverage,coverage-chunk),(1,0))
        # Source N=4, L=3: token exists in storage, but second full chunk mismatches.
        n=4;coverage=savings(min(l,n//c*c),p)
        self.assertEqual((oracle-coverage,coverage-chunk),(0,1))
    def test_actual_replay_is_paired_no_future_leak_and_zero_storage_is_null(self):
        root=Path(__file__).resolve().parents[1]
        run=json.loads((root/'results/kv_lifecycle/append-42/run.json').read_text())
        events=[json.loads(x) for x in (root/'results/kv_lifecycle/append-42/events.jsonl').read_text().splitlines()]
        q,requests,objects,summary,native=replay(run,events,[64,128,256,512])
        self.assertEqual(sum(not r['prior_same_session_snapshot'] for r in q),4)
        for row in requests:
            self.assertEqual(row['total_chunk_recomputed_tokens'],row['boundary_recomputed_tokens']+row['unpersisted_tail_recomputed_tokens'])
        for c in (64,128,256,512):
            current=next(r for r in summary if r['chunk_size']==c)
            self.assertEqual(current['oracle_saved_tokens'],summary[0]['oracle_saved_tokens'])
            self.assertEqual(current['stored_token_instances']+current['unpersisted_tail_tokens'],sum(o['persisted_tokens'] for o in run['objects']))
            self.assertLessEqual(current['unique_used_token_instances'],current['stored_token_instances'])
        self.assertIsNone(summary[-1]['token_instance_utilization'])
        self.assertTrue(all(r['native_reference_saved_tokens']==0 for r in native))

if __name__=='__main__':unittest.main()
