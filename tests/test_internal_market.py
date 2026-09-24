import tempfile, unittest
from pathlib import Path
from swarmbrain.economy import EconomyLedger
from swarmbrain.internal_market import InternalMarket

class InternalMarketTests(unittest.TestCase):
    def funded(self, path):
        ledger = EconomyLedger.load(path)
        ledger.record_verified_work(
            task_id="seed-work",
            contributors=[{"agent_id":"buyer","weight":1}],
            reference_cost_microusd=100,
            actual_cost_microusd=20,
            acc_microunits=1000,
            evidence={"receipt":"seed"},
        )
        return ledger

    def test_verified_service_moves_existing_acc(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=self.funded(Path(td)/"econ.json")
            market=InternalMarket(ledger,{("provider","verification"):125})
            quote=market.quote(buyer="buyer",provider="provider",service="verification")
            event=market.settle(task_id="verify-1",quote=quote,verified=True,evidence={"receipt":"r1"})
            self.assertEqual(event["type"],"acc_transfer")
            self.assertEqual(ledger.agent_balances(),{"buyer":875,"provider":125})
            self.assertEqual(ledger.balances()["acc_microunits_issued"],1000)

    def test_unverified_or_tampered_service_does_not_pay(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=self.funded(Path(td)/"econ.json")
            market=InternalMarket(ledger,{("provider","research"):50})
            quote=market.quote(buyer="buyer",provider="provider",service="research")
            with self.assertRaises(ValueError):
                market.settle(task_id="r1",quote=quote,verified=False,evidence={"receipt":"x"})
            quote["acc_microunits"]=500
            with self.assertRaises(ValueError):
                market.settle(task_id="r2",quote=quote,verified=True,evidence={"receipt":"x"})
            self.assertEqual(ledger.agent_balances(),{"buyer":1000})

    def test_expired_quote_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=self.funded(Path(td)/"econ.json")
            market=InternalMarket(ledger,{("provider","routing"):10})
            quote=market.quote(buyer="buyer",provider="provider",service="routing",ttl_seconds=1)
            self.assertFalse(market.verify_quote(quote,now_unix=quote["expires_at_unix"]+1))

if __name__=="__main__":
    unittest.main()
