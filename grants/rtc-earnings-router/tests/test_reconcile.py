import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import rtc_reconcile as rr


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.here = Path(__file__).resolve().parent.parent
        self.fixtures = self.here / "fixtures"
        self.native = "RTC8a13ce90490828d7954ba1038df4873b73f7c049"
        self.hosted = "tivince82"

    def test_real_recorded_fixture_matches_live_totals(self):
        http = rr.FixtureHTTP(self.fixtures)
        native = rr.balance(http, self.native)
        hosted = rr.balance(http, self.hosted)
        transfers = rr.dedupe_transfers(
            rr.wallet_transfers(http, self.native)
            + rr.wallet_transfers(http, self.hosted)
        )
        accepted = rr.maintainer_accepted(http, "KungFury87")

        self.assertEqual(native.amount_rtc, 0.087524)
        self.assertEqual(hosted.amount_rtc, 20.0)
        self.assertEqual(len(transfers), 10)

        totals = rr.payout_totals(transfers)
        self.assertEqual(totals["confirmed"], 25.0)
        self.assertEqual(totals["pending"], 119.0)
        self.assertEqual(totals["failed"], 0.0)

        pending = [x for x in transfers if x.state == "pending"]
        self.assertEqual(len(pending), 8)
        self.assertEqual(len({x.tx_hash for x in pending}), 8)
        self.assertTrue(all(x.confirmation_time is not None for x in pending))

        # Real #402 comments include grant approval and a later "needs revision"
        # review. Neither is an accepted completion/payment record.
        self.assertEqual(accepted, [])

    def test_distinct_same_amount_ledger_rows_never_merge(self):
        fixture = json.loads((self.fixtures / "real-history-native.json").read_text())
        rows = rr._history_payload(fixture)
        hashes = [r["tx_hash"] for r in rows if r.get("status") == "pending" and r.get("amount") == 15.0]
        self.assertEqual(len(hashes), 4)
        self.assertEqual(len(set(hashes)), 4)

        http = rr.FixtureHTTP(self.fixtures)
        transfers = rr.wallet_transfers(http, self.native)
        fifteen = [x for x in transfers if x.state == "pending" and x.amount_rtc == 15.0]
        self.assertEqual(len(fifteen), 4)

    def test_accepted_matching_is_word_boundary_and_negation_aware(self):
        self.assertTrue(rr.accepted_text("Accepted — 5 RTC to @KungFury87."))
        self.assertFalse(rr.accepted_text("This cannot be accepted as written."))
        self.assertFalse(rr.accepted_text("Needs a revision before the 100 RTC completion payment."))
        self.assertFalse(rr.accepted_text("Approved as a grant, payable on completion."))

    def test_main_writes_json_and_html_offline(self):
        with tempfile.TemporaryDirectory() as td:
            out_json = Path(td) / "receipt.json"
            out_html = Path(td) / "report.html"
            rc = rr.main([
                "--github-handle", "KungFury87",
                "--hosted-handle", self.hosted,
                "--native-wallet", self.native,
                "--fixture-dir", str(self.fixtures),
                "--out-json", str(out_json),
                "--out-html", str(out_html),
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], "rtc-reconciliation/v2")
            self.assertEqual(data["payout_totals_rtc"]["confirmed"], 25.0)
            self.assertEqual(data["payout_totals_rtc"]["pending"], 119.0)
            self.assertEqual(data["accepted_evidence"], [])
            self.assertNotIn("usd", json.dumps(data).lower())
            html_text = out_html.read_text(encoding="utf-8")
            self.assertIn("Wallet-history payout states", html_text)
            self.assertIn("119.0", html_text)

    def test_dedupe_is_tx_hash_only_for_ledger(self):
        row = rr.Transfer(
            identity=self.native,
            tx_hash="abc123",
            amount_rtc=15.0,
            state="pending",
            created_at=1,
            confirmation_time=86401,
            confirmation_time_source="derived_24h",
            pending_id=None,
            direction="received",
            counterparty="founder_community",
            source="x",
        )
        other = rr.Transfer(
            identity=self.hosted,
            tx_hash="abc123",
            amount_rtc=15.0,
            state="pending",
            created_at=1,
            confirmation_time=86401,
            confirmation_time_source="derived_24h",
            pending_id=None,
            direction="received",
            counterparty="founder_community",
            source="y",
        )
        self.assertEqual(len(rr.dedupe_transfers([row, other])), 1)


if __name__ == "__main__":
    unittest.main()
