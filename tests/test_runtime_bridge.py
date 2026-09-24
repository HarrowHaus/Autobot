import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from swarmbrain import runtime_bridge
from swarmbrain.economy import EconomyLedger
from swarmbrain.pricing import RateCard

class RuntimeBridgeTests(unittest.TestCase):
    def summary(self):
        return {
            "mode": "request",
            "tasks": [
                {
                    "id": "job-2",
                    "state": "response_received",
                    "receipt": "reports/receipts/job-2.json",
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
            rate_card = {
                "currency":"USD",
                "source":"https://provider.example/pricing",
                "effective_at":"2026-09-24",
                "rates":{"model-a":{"input_usd_per_million_tokens":"50","output_usd_per_million_tokens":"0"}}
            }
            quote = RateCard(rate_card).quote(rate_key="model-a", input_tokens=1000)
            job = {
                "economy": {
                    "verified": True,
                    "rate_card": rate_card,
                    "reference_quote": quote,
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

    def test_historical_receipt_cannot_back_new_job(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "economy.json"
            job = {"economy": {
                "verified": True,
                "reference_cost_microusd": 50,
                "actual_cost_microusd": 10,
                "acc_microunits": 100,
            }}
            summary = {
                "mode":"request",
                "tasks":[{
                    "id":"old-job",
                    "state":"response_received",
                    "receipt":"reports/old.json",
                    "peer_id":"peer-a",
                }]
            }
            with patch.object(runtime_bridge, "ECONOMY_PATH", path):
                result = runtime_bridge.account(job, summary, "new-job")
                self.assertFalse(result["recorded"])
                self.assertFalse(path.exists())

    def test_route_mode_never_issues_acc_from_prior_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "economy.json"
            job = {"economy": {
                "verified": True,
                "reference_cost_microusd": 50,
                "actual_cost_microusd": 10,
                "acc_microunits": 100,
            }}
            summary = {
                "mode":"route",
                "tasks":[{
                    "id":"new-job",
                    "state":"response_received",
                    "receipt":"reports/prior.json",
                    "peer_id":"peer-a",
                }]
            }
            with patch.object(runtime_bridge, "ECONOMY_PATH", path):
                result = runtime_bridge.account(job, summary, "new-job")
                self.assertFalse(result["recorded"])

    def test_bare_reference_cost_is_rejected_for_current_verified_job(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "economy.json"
            job = {"economy": {
                "verified": True,
                "reference_cost_microusd": 50_000,
                "actual_cost_microusd": 6_000,
                "acc_microunits": 100,
            }}
            with patch.object(runtime_bridge, "ECONOMY_PATH", path):
                with self.assertRaises(ValueError):
                    runtime_bridge.account(job, self.summary(), "job-2")
                self.assertFalse(path.exists())

if __name__ == "__main__":
    unittest.main()
