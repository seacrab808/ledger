"""Measurement-integrity tests; no emulation or generated research measurements."""
import copy
import json
import unittest
from pathlib import Path
from tools.summarize_steady import convergence, summarize

ROOT = Path(__file__).resolve().parents[1]

class PlateauRule(unittest.TestCase):
    gate = {'max_relative_range': .01, 'max_abs_relative_slope_per_window': .005}

    def test_constant_accepts(self):
        self.assertTrue(convergence([1., 1., 1.], self.gate)['passed'])

    def test_monotonic_drift_rejects(self):
        self.assertFalse(convergence([1., 1.02, 1.04], self.gate)['passed'])

    def test_zero_slope_is_insufficient(self):
        result = convergence([1., 1.02, 1.], self.gate)
        self.assertEqual(result['abs_relative_slope_per_window'], 0)
        self.assertFalse(result['passed'])

@unittest.skipUnless((ROOT / 'records/phase-02-steady.json').exists(), 'Actual longer-run batch not collected yet')
class ActualSteadyRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = json.loads((ROOT / 'records/phase-02-steady.json').read_text(encoding='utf-8'))
        cls.pilot = json.loads((ROOT / 'records/phase-02-pilot.json').read_text(encoding='utf-8'))

    def test_actual_record_validates(self):
        result = summarize(self.batch, self.pilot)
        self.assertEqual(len(result['window_rows']), 36)
        self.assertEqual(len(result['terminal_runs']), 6)

    def test_changed_completed_bytes_rejects(self):
        raw = copy.deepcopy(self.batch)
        raw['runs'][0]['stages'][-1]['fio_completed_bytes'] -= 4096
        with self.assertRaises(AssertionError):
            summarize(raw, self.pilot)

    def test_changed_baseline_rejects(self):
        raw = copy.deepcopy(self.batch)
        raw['runs'][0]['initial_observed_state']['counters']['block-erases'] += 1
        with self.assertRaises(AssertionError):
            summarize(raw, self.pilot)

    def test_later_counter_mismatch_rejects(self):
        raw = copy.deepcopy(self.batch)
        raw['runs'][0]['stages'][-1]['metrics']['native_counter_deltas']['gc-write-pages'] += 1
        with self.assertRaises(AssertionError):
            summarize(raw, self.pilot)

if __name__ == '__main__':
    unittest.main()
