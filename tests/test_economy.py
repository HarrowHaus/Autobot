import tempfile, unittest
from pathlib import Path
from swarmbrain.economy import EconomyLedger

class EconomyLedgerTests(unittest.TestCase):
    def test_verified_work_does_not_create_usdc(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = EconomyLedger.load(Path(td) / "economy.json")
            ledger.record_verified_work(
                task_id="task-1",
                contributors=[{"agent_id":"agent-a","weight":1.0}],
                reference_cost_microusd=50_000,
                actual_cost_microusd=6_000,
                acc_microunits=1_000_000,
                evidence={"verification":"accepted"},
            )
            balances = ledger.balances()
            self.assertEqual(balances["avoided_cost_microusd"], 44_000)
            self.assertEqual(balances["real_usdc_atomic_received"], 0)
            self.assertTrue(ledger.verify()["ok"])

    def test_real_usdc_requires_unique_settlement(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = EconomyLedger.load(Path(td) / "economy.json")
            ledger.record_usdc_settlement(
                task_id="sale-1", amount_atomic=18_000, network="eip155:8453",
                transaction="0xabc", payer="0x111", evidence={"facilitator":"verified"},
            )
            self.assertEqual(ledger.balances()["real_usdc_atomic_received"], 18_000)
            with self.assertRaises(ValueError):
                ledger.record_usdc_settlement(
                    task_id="sale-1", amount_atomic=18_000, network="eip155:8453",
                    transaction="0xabc",
                )

    def test_tampering_breaks_verification(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = EconomyLedger.load(Path(td) / "economy.json")
            ledger.record_verified_work(
                task_id="task-2", contributors=[{"agent_id":"v","weight":1}],
                reference_cost_microusd=10, actual_cost_microusd=1,
                acc_microunits=10, evidence={"receipt":"r"},
            )
            ledger.events[0]["payload"]["acc_microunits"] = 999
            self.assertFalse(ledger.verify()["ok"])

    def test_weighted_allocations_and_transfers_conserve_acc(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = EconomyLedger.load(Path(td) / "economy.json")
            ledger.record_verified_work(
                task_id="task-split",
                contributors=[
                    {"agent_id":"agent-a","weight":3},
                    {"agent_id":"agent-b","weight":1},
                ],
                reference_cost_microusd=100,
                actual_cost_microusd=25,
                acc_microunits=1000,
                evidence={"verification":"accepted"},
            )
            self.assertEqual(ledger.agent_balances(), {"agent-a":750,"agent-b":250})
            ledger.record_acc_transfer(
                task_id="purchase-1",
                from_agent="agent-a",
                to_agent="agent-b",
                acc_microunits=125,
                evidence={"service":"verification"},
            )
            self.assertEqual(ledger.agent_balances(), {"agent-a":625,"agent-b":375})
            balances = ledger.balances()
            self.assertEqual(balances["acc_microunits_issued"], 1000)
            self.assertEqual(balances["acc_microunits_transferred"], 125)
            self.assertEqual(balances["real_usdc_atomic_received"], 0)
            self.assertTrue(ledger.verify()["ok"])

    def test_transfer_cannot_overdraw_or_mint(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = EconomyLedger.load(Path(td) / "economy.json")
            ledger.record_verified_work(
                task_id="task-fund",
                contributors=[{"agent_id":"agent-a","weight":1}],
                reference_cost_microusd=10,
                actual_cost_microusd=1,
                acc_microunits=10,
                evidence={"verification":"accepted"},
            )
            with self.assertRaises(ValueError):
                ledger.record_acc_transfer(
                    task_id="bad",
                    from_agent="agent-a",
                    to_agent="agent-b",
                    acc_microunits=11,
                    evidence={"service":"x"},
                )
            self.assertEqual(ledger.balances()["acc_microunits_issued"], 10)

if __name__ == "__main__":
    unittest.main()
