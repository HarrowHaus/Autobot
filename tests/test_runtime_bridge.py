import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from swarmbrain import runtime_bridge
from swarmbrain.economy import EconomyLedger

class RuntimeBridgeTests(unittest.TestCase):
    def summary(self):
        return {
            "tasks": [
                {
                    "id": "task-1",
                    "state": "response_received",
                    "receipt": "reports/receipts/task-1.json",
                    "peer_id": "peer-a",
                }
            ]
        }

    def test_no_verified_economics_mints_nothing(self):
        result = runtime_bridge.account({"mode": "route"}, self.summary(), "job-1")
        self.assertFalse(result["recorded"])

    def test_verified_receipt_backed_work_records_acc_not_usdc(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "economy.json"
            job = {
                "economy": {
                    "verified": True,
                    "reference_cost_microusd": 50_000,
                    "actual_cost_microusd": 6_000,
                    "acc_microunits": 1_000_000,
                    "verification_scope": "receipt-backed test",
                }
            }
            with patch.object(runtime_bridge, "ECONOMY_PATH", path):
                result = runtime_bridge.account(job, self.summary(), "job-2")
                self.assertTrue(result["recorded"])
                ledger = EconomyLedger.load(path)
                balances = ledger.balances()
                self.assertEqual(balances["avoided_cost_microusd"], 44_000)
                self.assertEqual(balances["real_usdc_atomic_received"], 0)
                self.assertTrue(ledger.verify()["ok"])

    def test_no_completed_receipt_means_no_acc(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "economy.json"
            job = {"economy": {
                "verified": True,
                "reference_cost_microusd": 1,
                "actual_cost_microusd": 0,
                "acc_microunits": 1,
            }}
            with patch.object(runtime_bridge, "ECONOMY_PATH", path):
                result = runtime_bridge.account(job, {"tasks":[]}, "job-3")
                self.assertFalse(result["recorded"])
                self.assertFalse(path.exists())

if __name__ == "__main__":
    unittest.main()
