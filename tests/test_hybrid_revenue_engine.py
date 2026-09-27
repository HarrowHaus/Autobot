import unittest
from swarmbrain.hybrid_revenue_engine import (
    build_state,
    opportunity_score,
    qualification_reasons,
    verified_settlements,
)


class HybridRevenueEngineTests(unittest.TestCase):
    def caps(self):
        return {"research", "verification", "coding", "document-extraction"}

    def candidate(self):
        return {
            "id": "direct:req-1",
            "source_kind": "direct_request",
            "source_url": "https://example.test/request/1",
            "request_id": "req-1",
            "current_status": "open",
            "dedupe_state": "new",
            "upfront_spend_required": False,
            "new_account_required": False,
            "wallet_signing_required_before_earning": False,
            "contact_permission": "explicit_email",
            "required_capabilities": ["research", "verification"],
            "acceptance_criteria": ["source-linked report", "all claims cited"],
            "acceptance_test_machine_checkable": False,
            "funding_evidence": "buyer_budget_stated",
            "advertised_gross_usd_atomic": 30000,
            "known_cost_usd_atomic": 1000,
            "unknown_cost_reserve_usd_atomic": 4000,
            "prebuild_allowed": True,
            "official_action_adapter_ready": True,
            "deadline_known": True,
            "friction_points": 1,
        }

    def test_good_direct_request_qualifies(self):
        c = self.candidate()
        self.assertEqual(qualification_reasons(c, self.caps()), [])
        self.assertGreater(opportunity_score(c, self.caps()), 0)

    def test_capability_gap_blocks(self):
        c = self.candidate()
        c["required_capabilities"] = ["licensed-audio-mastering"]
        self.assertIn("capability_gap", qualification_reasons(c, self.caps()))

    def test_unknown_cost_reserve_prevents_fake_margin(self):
        c = self.candidate()
        c["advertised_gross_usd_atomic"] = 5000
        c["known_cost_usd_atomic"] = 1000
        c["unknown_cost_reserve_usd_atomic"] = 5000
        self.assertIn("no_defensible_positive_margin", qualification_reasons(c, self.caps()))

    def test_unverified_settlement_is_not_revenue(self):
        intake = {
            "verified_settlements": [
                {
                    "settlement_id": "x",
                    "amount_usd_atomic": 10000,
                    "asset_kind": "USD",
                    "independently_verified": False,
                }
            ]
        }
        total, rows = verified_settlements(intake)
        self.assertEqual(total, 0)
        self.assertEqual(rows, [])

    def test_verified_settlement_dedupes(self):
        row = {
            "settlement_id": "pay-1",
            "amount_usd_atomic": 1234,
            "asset_kind": "USD",
            "independently_verified": True,
        }
        total, rows = verified_settlements({"verified_settlements": [row, row]})
        self.assertEqual(total, 1234)
        self.assertEqual(len(rows), 1)

    def test_state_advances_discovered_to_qualified(self):
        c = self.candidate()
        c["status"] = "discovered"
        state = build_state(
            {},
            {"verified_capabilities": sorted(self.caps()), "opportunities": [c]},
            {"opportunities": [], "revenue": {"verified_external_usdc_atomic": "0"}},
        )
        self.assertEqual(state["opportunities"][0]["status"], "qualified")
        self.assertEqual(
            state["opportunities"][0]["next_action"],
            "prebuild_smallest_task_specific_artifact",
        )

    def test_contacted_is_preserved_across_refresh(self):
        c = self.candidate()
        previous = {
            "opportunities": [
                {**c, "status": "contacted", "receipts": ["gmail:1"], "score": 10}
            ]
        }
        state = build_state(
            previous,
            {"verified_capabilities": sorted(self.caps()), "opportunities": [c]},
            {"opportunities": [], "revenue": {"verified_external_usdc_atomic": "0"}},
        )
        row = state["opportunities"][0]
        self.assertEqual(row["status"], "contacted")
        self.assertEqual(row["receipts"], ["gmail:1"])
        self.assertEqual(row["next_action"], "reconcile_reply_acceptance_and_settlement")

    def test_swarmbrain_opportunity_is_merged_not_counted_as_sale(self):
        state = build_state(
            {},
            {"verified_capabilities": [], "opportunities": []},
            {
                "opportunities": [{
                    "id": "basedagents:t1",
                    "kind": "paid_task",
                    "source": "basedagents",
                    "source_ref": "https://api.example/tasks/t1",
                    "status": "observed",
                    "score": 90,
                    "funding_evidence": "platform_reported_escrow",
                    "next_action": "qualify_and_claim_with_official_basedagents_sdk",
                }],
                "revenue": {"verified_external_usdc_atomic": "0"},
            },
        )
        self.assertEqual(len(state["opportunities"]), 1)
        self.assertEqual(state["revenue"]["verified_swarmbrain_usdc_atomic"], 0)


if __name__ == "__main__":
    unittest.main()
