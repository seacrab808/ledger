import copy
import json
import unittest
from pathlib import Path
from tools.summarize_history import summarize
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless((ROOT/'records/phase-02-history.json').exists(),'Actual control not collected yet')
class HistoryIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b=json.loads((ROOT/'records/phase-02-history.json').read_bytes())
        cls.a=json.loads((ROOT/'records/phase-02-steady.json').read_bytes())
    def test_actual_windows_validate(self):
        self.assertEqual(len(summarize(self.b,self.a)['window_rows']),16)
    def test_changed_preconditioning_seed_rejects(self):
        b=copy.deepcopy(self.b);b['runs'][0]['stages'][2]['seed']+=1
        with self.assertRaises(AssertionError):summarize(b,self.a)
    def test_changed_bytes_rejects(self):
        b=copy.deepcopy(self.b);b['runs'][0]['stages'][-1]['fio_completed_bytes']-=4096
        with self.assertRaises(AssertionError):summarize(b,self.a)
    def test_broken_snapshot_continuity_rejects(self):
        b=copy.deepcopy(self.b);b['runs'][0]['stages'][-1]['before']['reply']['return']['namespaces'][0]['counters']['block-erases']+=16
        with self.assertRaises(AssertionError):summarize(b,self.a)
