import json
import tempfile
import unittest
from pathlib import Path

import rtc_reconcile as rr


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.here = Path(__file__).resolve().parent.parent
        self.fixtures = self.here / "fixtures"
        self.native = "RTC8a13ce90490828d7954ba1038df4873b73f7c049"
        self.hosted = "tivince82"

    def test_offline_end_to_end_and_email_dedupe(self):
        http = rr.FixtureHTTP(self.fixtures)
        native = rr.balance(http, self.native)
        hosted = rr.balance(http, self.hosted)
        claims = rr.dedupe_claims(
            rr.github_claims(http, "KungFury87")
            + rr.external_evidence(self.fixtures / "email-evidence.json")
        )

        self.assertEqual(native.amount_rtc, 0.087524)
        self.assertEqual(hosted.amount_rtc, 20.0)
        self.assertEqual(len(claims), 2)

        confirmed = next(c for c in claims if c.issue_number == 9001)
        self.assertEqual(confirmed.state, "confirmed")
        self.assertEqual(confirmed.amount_rtc, 15.0)
        self.assertEqual(confirmed.pending_id, "5001")
        self.assertEqual(confirmed.tx_hash, "abcdef0123456789")
        self.assertEqual(len(confirmed.evidence_urls), 4)

        accepted = next(c for c in claims if c.issue_number == 9002)
        self.assertEqual(accepted.state, "accepted")
        self.assertEqual(accepted.amount_rtc, 8.0)

        totals = rr.totals(claims)
        self.assertEqual(totals["confirmed"], 15.0)
        self.assertEqual(totals["accepted"], 8.0)
        self.assertEqual(totals["pending"], 0.0)

    def test_main_writes_json_and_html_offline(self):
        with tempfile.TemporaryDirectory() as td:
            out_json = Path(td) / "receipt.json"
            out_html = Path(td) / "report.html"
            rc = rr.main([
                "--github-handle", "KungFury87",
                "--hosted-handle", self.hosted,
                "--native-wallet", self.native,
                "--fixture-dir", str(self.fixtures),
                "--evidence-json", str(self.fixtures / "email-evidence.json"),
                "--out-json", str(out_json),
                "--out-html", str(out_html),
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], "rtc-reconciliation/v1")
            self.assertEqual(data["claim_totals_rtc"]["confirmed"], 15.0)
            self.assertNotIn("usd", json.dumps(data).lower())
            html_text = out_html.read_text(encoding="utf-8")
            self.assertIn("RTC reconciliation", html_text)
            self.assertIn("pending ID", html_text)

    def test_state_precedence(self):
        records = [
            rr.Claim("x", 1, None, "x", "accepted", 5.0, self.native, None, None, None, ["a"]),
            rr.Claim("x", 1, None, "x", "pending", 5.0, self.native, "p1", None, None, ["b"]),
            rr.Claim("x", 1, None, "x", "confirmed", 5.0, self.native, "p1", "deadbeef", None, ["c"]),
        ]
        out = rr.dedupe_claims(records)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].state, "confirmed")
        self.assertEqual(set(out[0].evidence_urls), {"a", "b", "c"})


if __name__ == "__main__":
    unittest.main()
