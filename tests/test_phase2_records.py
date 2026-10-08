"""Measurement integrity checks against archived Phase 2 data, without guest I/O."""
import copy
import json
import unittest
from pathlib import Path
from tools.summarize_phase2 import summarize

PATH = Path(__file__).resolve().parents[1] / 'records/phase-02-pilot.json'


@unittest.skipUnless(PATH.exists(), 'Measured pilot record not present yet')
class PilotIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.batch = json.loads(PATH.read_text(encoding='utf-8'))

    def test_measured_batch_passes_integrity(self):
        result = summarize(self.batch)
        self.assertEqual(len(result['rows']), 6)
        self.assertTrue(result['same_observed_initial_state'])

    def test_completed_byte_mismatch_is_rejected(self):
        altered = copy.deepcopy(self.batch)
        altered['runs'][0]['stages'][2]['fio']['jobs'][0]['write']['io_bytes'] -= 4096
        with self.assertRaises(AssertionError):
            summarize(altered)

    def test_different_initial_counter_state_is_rejected(self):
        altered = copy.deepcopy(self.batch)
        altered['runs'][1]['initial_observed_state']['counters']['block-erases'] += 16
        with self.assertRaises(AssertionError):
            summarize(altered)


if __name__ == '__main__':
    unittest.main()
