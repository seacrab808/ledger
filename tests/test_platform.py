import copy
import json
import unittest
from tools.validate_config import audit, DEFAULT
from tools.preflight_linux import evaluate
from tools.qmp_metrics import delta_metrics
from tools.setup_lab_key import payload


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(DEFAULT.read_text(encoding="utf-8"))

    def test_capacity_and_op_definitions(self):
        result = audit(self.config)
        self.assertEqual(result["raw_bytes"], 4 * 1024**3)
        self.assertEqual(result["exposed_bytes"], 3 * 1024**3)
        self.assertEqual(result["line_bytes"], 16 * 1024**2)
        self.assertEqual(result["raw_spare_fraction"], 0.25)
        self.assertAlmostEqual(result["logical_op_fraction"], 1 / 3)

    def test_no_spare_rejected(self):
        self.config["device"]["devsz_mb"] = 4096
        with self.assertRaises(ValueError):
            audit(self.config)

    def test_placement_cannot_silently_be_enabled(self):
        self.config["placement"]["fdp"] = True
        with self.assertRaises(ValueError):
            audit(self.config)

    def test_op_switch_cannot_silently_change_backend(self):
        self.config["device"]["op_pcent"] = 25
        with self.assertRaises(ValueError):
            audit(self.config)


class EnvironmentTests(unittest.TestCase):
    def base(self):
        return {"system": "Linux", "kernel": "6.8.0-generic", "virtualization": "none",
                "architecture": "x86_64", "kvm_exists": True, "kvm_access": True,
                "hardware_virtualization_flag": True, "kvm_loaded": True,
                "mem_available_bytes": 10 * 1024**3}

    def test_wsl_rejected_even_with_kvm_and_ram(self):
        info = self.base()
        info["kernel"] = "6.18-microsoft-standard-WSL2"
        info["virtualization"] = "wsl"
        self.assertFalse(evaluate(info)["eligible"])

    def test_missing_kvm_access_rejected(self):
        info = self.base()
        info["kvm_access"] = False
        self.assertFalse(evaluate(info)["eligible"])

    def test_supported_host_probe_gate(self):
        self.assertTrue(evaluate(self.base())["eligible"])


class CounterTests(unittest.TestCase):
    def fixture(self, host=100, nand=100, gc=20, erases=16):
        # Explicit synthetic unit-test fixture, NOT a measured result.
        return {"return": {"namespaces": [{"nsid": 1, "mode": "bbssd",
                "geometry": {"page-size": 4096}, "counters": {
                    "host-write-pages": host, "nand-write-pages": nand,
                    "gc-write-pages": gc, "block-erases": erases}}]}}

    def test_gc_added_once_and_window_waf_uses_deltas(self):
        result = delta_metrics(self.fixture(), self.fixture(host=200, nand=200, gc=70, erases=32))
        self.assertEqual(result["physical_program_pages"], 150)
        self.assertEqual(result["waf_pages"], 1.5)
        self.assertEqual(result["block_erases"], 16)

    def test_reset_detected(self):
        with self.assertRaises(ValueError):
            delta_metrics(self.fixture(), self.fixture(host=0, nand=0, gc=0, erases=0))

    def test_no_host_writes_has_no_waf(self):
        data = self.fixture()
        self.assertIsNone(delta_metrics(data, copy.deepcopy(data))["waf_pages"])

    def test_geometry_change_rejected(self):
        data = self.fixture()
        other = copy.deepcopy(data)
        other["return"]["namespaces"][0]["geometry"]["page-size"] = 8192
        with self.assertRaises(ValueError):
            delta_metrics(data, other)


class PublicKeySetupTests(unittest.TestCase):
    def test_script_is_stdin_payload_not_a_quoted_ssh_command(self):
        script = payload("ssh-ed25519 AAAA malicious'comment")
        self.assertIn("key='ssh-ed25519 AAAA ledger-phase1'", script)
        self.assertNotIn("malicious", script)
        self.assertNotIn("\r", script)
        self.assertIn('grep -qxF "$key"', script)

    def test_private_key_or_multiple_lines_rejected(self):
        for key in ["-----BEGIN OPENSSH PRIVATE KEY-----", "ssh-ed25519 AAAA\nssh-ed25519 BBBB"]:
            with self.assertRaises(ValueError):
                payload(key)


if __name__ == "__main__":
    unittest.main()
