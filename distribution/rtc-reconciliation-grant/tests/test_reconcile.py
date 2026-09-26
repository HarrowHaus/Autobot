import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rtc_reconcile import (
    HTTP,
    Reconciler,
    claim_key,
    dedupe_events,
    event_from_record,
    reconcile,
    render_html,
)


class Resp:
    def __init__(self, obj):
        self._data = json.dumps(obj).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def read(self):
        return self._data


class FakeOpen:
    def __call__(self, request, timeout=20):
        url = request.full_url
        if "miner_id=tivince82" in url:
            return Resp({"amount_i64": 20_000_000, "amount_rtc": 20.0, "miner_id": "tivince82"})
        if "miner_id=RTC8a13ce90490828d7954ba1038df4873b73f7c049" in url:
            return Resp({"amount_i64": 87_524, "amount_rtc": 0.087524})
        raise AssertionError(url)


class Tests(unittest.TestCase):
    def setUp(self):
        self.wallet = "RTC8a13ce90490828d7954ba1038df4873b73f7c049"
        self.github = [
            {
                "source": "https://github.com/Scottcjn/rustchain-bounties/issues/16497",
                "created_at": "2026-09-25T19:15:20Z",
                "body": "claim_id: article-bridge-1\n@tivince82 accepted — 13 RTC\nWallet: " + self.wallet,
            },
            {
                "source": "https://github.com/Scottcjn/rustchain-bounties/issues/398",
                "created_at": "2026-09-24T20:00:00Z",
                "body": "idempotency: quest-398-vince\n@tivince82 Payout queued — pending_id 4999, tx abcdef1234567890; confirms automatically 2026-09-25 20:00 UTC\nWallet: " + self.wallet,
            },
        ]
        self.email = [
            {
                "source": "email: github notification",
                "email_ts": "2026-09-25T19:16:00Z",
                "body": "claim_id: article-bridge-1\n@tivince82 accepted — 13 RTC\nWallet: " + self.wallet + "\n> quoted prior message",
            },
            {
                "source": "email: payout confirmation",
                "email_ts": "2026-09-25T20:01:00Z",
                "body": "idempotency: quest-398-vince\n@tivince82 payout confirmed. tx abcdef1234567890\nWallet: " + self.wallet,
            },
        ]

    def test_claim_key_explicit_is_cross_channel_stable(self):
        a = claim_key(self.github[0]["body"], self.github[0]["source"])
        b = claim_key(self.email[0]["body"], self.email[0]["source"])
        self.assertEqual(a, b)
        self.assertEqual(a, "id:article-bridge-1")

    def test_dedupe_promotes_lifecycle_without_double_count(self):
        events = []
        for row in self.github:
            events.append(event_from_record(row, "github", row["source"]))
        for row in self.email:
            events.append(event_from_record(row, "email_export", row["source"]))
        events = [e for e in events if e is not None]
        deduped = dedupe_events(events)
        self.assertEqual(len(events), 4)
        self.assertEqual(len(deduped), 2)
        by_key = {e.claim_key: e for e in deduped}
        self.assertEqual(by_key["id:article-bridge-1"].status, "accepted")
        self.assertEqual(by_key["id:quest-398-vince"].status, "confirmed")

    def test_reconcile_balances_and_dedupes(self):
        rc = Reconciler(HTTP(opener=FakeOpen()), node="https://fixture.invalid")
        out = reconcile(
            "tivince82",
            self.wallet,
            [],
            self.email,
            github_fixture=self.github,
            reconciler=rc,
        )
        self.assertEqual(out["balance_total_rtc"], 20.087524)
        self.assertEqual(out["dedupe"]["input_event_count"], 4)
        self.assertEqual(out["dedupe"]["output_claim_count"], 2)
        self.assertEqual(out["dedupe"]["duplicates_removed"], 2)
        self.assertTrue(out["boundaries"]["read_only"])
        self.assertFalse(out["boundaries"]["contains_usd_fields"])

    def test_every_queued_event_exposes_pending_and_confirmation_when_present(self):
        event = event_from_record(self.github[1], "github", self.github[1]["source"])
        self.assertEqual(event.status, "queued_pending")
        self.assertEqual(event.pending_id, "4999")
        self.assertEqual(event.tx_hash, "abcdef1234567890")
        self.assertIsNotNone(event.confirmation_text)

    def test_html_has_no_usd_field_or_market_language(self):
        rc = Reconciler(HTTP(opener=FakeOpen()), node="https://fixture.invalid")
        out = reconcile("tivince82", self.wallet, [], self.email, github_fixture=self.github, reconciler=rc)
        page = render_html(out)
        self.assertNotIn("USD", page)
        self.assertNotIn("ROI", page)
        self.assertIn("Read only.", page)
        self.assertIn("20.087524 RTC", page)

    def test_output_is_deterministic_for_same_records(self):
        rc = Reconciler(HTTP(opener=FakeOpen()), node="https://fixture.invalid")
        a = reconcile("tivince82", self.wallet, [], self.email, github_fixture=self.github, reconciler=rc)
        b = reconcile("tivince82", self.wallet, [], self.email, github_fixture=self.github, reconciler=rc)
        for value in (a, b):
            value.pop("generated_at", None)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
