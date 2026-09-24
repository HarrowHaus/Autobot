import tempfile, unittest
from pathlib import Path
from swarmbrain.economy import EconomyLedger
from swarmbrain.merchant import X402Merchant
from swarmbrain.x402 import encode_header

class FakeFacilitator:
    def __init__(self, valid=True, settled=True):
        self.valid = valid
        self.settled = settled
        self.verify_calls = 0
        self.settle_calls = 0

    def verify(self, payment_payload, requirement):
        self.verify_calls += 1
        return {"isValid": self.valid, "payer": "0x" + "3" * 40,
                **({} if self.valid else {"invalidReason":"bad_signature"})}

    def settle(self, payment_payload, requirement):
        self.settle_calls += 1
        if not self.settled:
            return {"success":False,"errorReason":"settlement_failed",
                    "payer":"0x" + "3" * 40,"transaction":"","network":requirement["network"]}
        return {"success":True,"payer":"0x" + "3" * 40,
                "transaction":"0x" + "a" * 64,"network":requirement["network"]}

def merchant(path, facilitator):
    return X402Merchant(
        service_name="A0",
        resource_url="https://example.com/v1/route",
        description="Paid swarm route",
        amount_atomic=10_000,
        asset="0x" + "1" * 40,
        pay_to="0x" + "2" * 40,
        facilitator=facilitator,
        ledger_path=path,
    )

class MerchantTests(unittest.TestCase):
    def test_missing_payment_returns_402_and_does_no_work(self):
        with tempfile.TemporaryDirectory() as td:
            f = FakeFacilitator()
            called = []
            result = merchant(Path(td)/"ledger.json", f).transact(
                task_id="sale-1", payment_signature=None,
                perform_work=lambda: called.append(True))
            self.assertEqual(result["status"], 402)
            self.assertFalse(called)
            self.assertEqual(f.verify_calls, 0)

    def test_invalid_payment_never_executes_resource(self):
        with tempfile.TemporaryDirectory() as td:
            f = FakeFacilitator(valid=False)
            called = []
            result = merchant(Path(td)/"ledger.json", f).transact(
                task_id="sale-2", payment_signature=encode_header({"x402Version":2}),
                perform_work=lambda: called.append(True))
            self.assertEqual(result["status"], 402)
            self.assertFalse(called)
            self.assertEqual(f.settle_calls, 0)

    def test_successful_settlement_records_real_usdc(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"ledger.json"
            f = FakeFacilitator()
            result = merchant(path, f).transact(
                task_id="sale-3", payment_signature=encode_header({"x402Version":2}),
                perform_work=lambda: {"routes":["peer-a"]})
            self.assertEqual(result["status"], 200)
            self.assertEqual(result["body"]["result"]["routes"], ["peer-a"])
            ledger = EconomyLedger.load(path)
            self.assertEqual(ledger.balances()["real_usdc_atomic_received"], 10_000)
            self.assertTrue(ledger.verify()["ok"])

    def test_resource_failure_does_not_settle(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"ledger.json"
            f = FakeFacilitator()
            def fail():
                raise RuntimeError("boom")
            result = merchant(path, f).transact(
                task_id="sale-4", payment_signature=encode_header({"x402Version":2}),
                perform_work=fail)
            self.assertEqual(result["status"], 500)
            self.assertEqual(f.settle_calls, 0)
            self.assertFalse(path.exists())

if __name__ == "__main__":
    unittest.main()
