import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from swarmbrain.revenue_growth import ExperimentBook, qualify, BASE, USDC
from swarmbrain.revenue_discovery import discover, catalog_signals

NOW = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
TS = int(NOW.timestamp())

def lead(operator="external-test-1", **changes):
    value = {"operator_id": operator, "relationship": "independent_customer", "source_kind": "request_for_quotes",
             "source_url": "https://buyer.example/rfq/1", "request_id": "rfq-1", "status": "open",
             "contact_permission": "quotes_invited", "permission_source": "https://buyer.example/terms",
             "contact_url": "https://buyer.example/rfq/1", "reviewed_by_operator": True,
             "observed_at": TS-60, "expires_at": TS+86400, "budget_atomic": 100000,
             "required_skills": ["route_selection"]}
    value.update(changes)
    return value

def service(**changes):
    value = {"name": "Read-only route selection", "scope": "Three ranked routes from a dated public snapshot",
             "acceptance_test": "Bounded JSON response with provenance; no promise that downstream peers execute work",
             "verified_skills": ["route_selection"], "delivery_ready": True, "payment_ready": True,
             "delivery_ready_evidence": "https://a0.example/test/1", "payment_ready_evidence": "https://a0.example/test/2",
             "order_url": "https://a0.example/order", "network": BASE, "asset": USDC,
             "price_atomic": 10000, "max_cost_atomic": 3000, "sample_ready": True}
    value.update(changes)
    return value

class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "private.sqlite")
        self.book = ExperimentBook(self.path)

    def tearDown(self):
        self.book.db.close()
        self.temp.cleanup()

    def reserve(self, operator="external-test-1"):
        return self.book.reserve(lead(operator), service(), NOW)

    def sent(self):
        item = self.reserve()
        self.book.mark_sent(item["id"], "https://buyer.example/replies/1")
        return item

    def receipt(self, **changes):
        value = {"network": BASE, "asset": USDC, "operator_id": "external-test-1", "environment": "mainnet",
                 "order_id": "TEST-order-1", "settlement_key": "TEST-only-chain-event", "amount_atomic": 10000}
        value.update(changes)
        return value

    def test_good_lead_qualifies(self):
        self.assertEqual(qualify(lead(), service(), NOW), [])

    def test_wallet_and_seller_catalog_are_not_buyers(self):
        for kind in ("wallet_balance", "seller_catalog", "agent_directory"):
            self.assertIn("no_buying_intent", qualify(lead(source_kind=kind), service(), NOW))

    def test_no_opt_out_is_not_permission(self):
        self.assertIn("no_permitted_offer_channel", qualify(lead(contact_permission="not_opted_out"), service(), NOW))

    def test_unreviewed_source_cannot_authorize_contact(self):
        self.assertIn("unreviewed_external_claims", qualify(lead(reviewed_by_operator=False), service(), NOW))

    def test_controlled_or_unverified_customer_excluded(self):
        for relationship in ("same_owner", "partner_test", "unknown"):
            self.assertIn("not_a_verified_independent_customer", qualify(lead(relationship=relationship), service(), NOW))

    def test_expired_and_stale_lead_blocked(self):
        self.assertIn("request_not_open", qualify(lead(expires_at=TS-1), service(), NOW))
        self.assertIn("stale_or_unknown_request", qualify(lead(observed_at=TS-8*86400), service(), NOW))

    def test_not_ready_or_negative_margin_blocks_offer(self):
        self.assertIn("payment_ready_unverified", qualify(lead(), service(payment_ready=False), NOW))
        self.assertIn("unprofitable_or_over_budget", qualify(lead(), service(max_cost_atomic=11000), NOW))

    def test_upfront_fee_blocked(self):
        self.assertIn("upfront_fee_disallowed", qualify(lead(upfront_fee_atomic=1), service(), NOW))

    def test_restart_does_not_reassign_or_resend(self):
        first = self.reserve()
        self.book.db.close()
        self.book = ExperimentBook(self.path)
        with self.assertRaisesRegex(ValueError, "cooldown"):
            self.reserve()
        self.assertEqual(self.book.db.execute("SELECT count(*) FROM contacts").fetchone()[0], 1)
        self.assertEqual(first["status"], "reserved_not_sent")

    def test_five_contact_daily_cap(self):
        for n in range(5):
            self.reserve(f"customer-{n}")
        with self.assertRaisesRegex(ValueError, "daily_contact_cap"):
            self.reserve("customer-6")

    def test_suppression_persists(self):
        self.book.suppress("external-test-1", NOW)
        with self.assertRaisesRegex(ValueError, "opted_out"):
            self.reserve()

    def test_transport_receipt_required(self):
        item = self.reserve()
        with self.assertRaises(ValueError):
            self.book.mark_sent(item["id"], "sent=true")
        self.assertEqual(sum(r["sent"] for r in self.book.report()["arms"]), 0)

    def test_offer_has_explicit_terms_not_hidden_instructions(self):
        text = self.reserve()["message"]
        self.assertIn("0.01 USDC", text)
        self.assertIn("owner's purchasing authority", text)
        self.assertIn("no follow-up unless requested", text)

    def test_confirmed_json_flag_is_not_verification(self):
        item = self.sent()
        for verifier in (None, lambda *_: False, lambda *_: {"confirmed": True}):
            with self.assertRaisesRegex(ValueError, "independent_settlement"):
                self.book.record_sale(item["id"], self.receipt(confirmed=True), verifier)

    def test_simulated_testnet_wrong_payer_amount_asset_blocked(self):
        item = self.sent()
        for change in ({"environment": "testnet"}, {"operator_id": "a0-core"}, {"amount_atomic": 1}, {"asset": "OTHER"}, {"network": "eip155:84532"}):
            with self.assertRaises(ValueError):
                self.book.record_sale(item["id"], self.receipt(**change), lambda *_: True)

    def test_duplicate_sale_rejected(self):
        item = self.sent()
        self.book.record_sale(item["id"], self.receipt(), lambda *_: True)  # Test verifier, NOT a real payment.
        with self.assertRaises(sqlite3.IntegrityError):
            self.book.record_sale(item["id"], self.receipt(), lambda *_: True)

    def test_net_subtracts_samples_fees_and_refunds(self):
        item = self.sent()
        self.book.record_sale(item["id"], self.receipt(), lambda *_: True)
        for kind, amount in (("sample", 1000), ("fulfillment", 2000), ("network_fee", 500), ("refund", 1000)):
            self.book.record_cost(item["id"], "TEST-"+kind, amount, kind)
        row = next(r for r in self.book.report()["arms"] if r["sent"])
        self.assertEqual(row["net_atomic"], 5500)
        self.assertIsNone(self.book.report()["winner"])

    def test_reservations_do_not_count_as_sent_or_revenue(self):
        self.reserve()
        self.assertEqual(sum(r["sent"] for r in self.book.report()["arms"]), 0)
        self.assertEqual(sum(r["revenue_atomic"] for r in self.book.report()["arms"]), 0)

    def test_source_failure_not_zero_opportunities(self):
        def fail(_):
            raise TimeoutError()
        result = discover(fail)
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(all(r["result"] is None for r in result["sources"]))
        self.assertEqual(result["paid_calls"], 0)

    def test_catalog_volume_is_not_lead_permission(self):
        result = catalog_signals({"resources": [{"resource": "https://seller.example/", "quality": {"l30DaysTotalCalls": 500, "l30DaysUniquePayers": 80}}]})
        self.assertFalse(result["signals"][0]["contact_allowed"])
        self.assertEqual(result["qualified_buyer_count"], 0)

if __name__ == "__main__":
    unittest.main()
