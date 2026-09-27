import unittest
from swarmbrain.commercial_controller import (
    basedagents_nodes,
    bazaar_nodes,
    build_state,
    opportunity_score,
    settled_revenue_from_ledger,
)


class CommercialControllerTests(unittest.TestCase):
    def based_report(self):
        return {
            "status": "ok",
            "observed_at": "2026-09-27T00:00:00Z",
            "candidate_count": 1,
            "candidates": [{
                "task_id": "task_paid",
                "title": "Verify research",
                "source": "https://api.basedagents.ai/v1/tasks/task_paid",
                "claimable": True,
                "matched_capabilities": ["verification", "research"],
                "required_capabilities": ["verification", "research"],
                "funding_evidence": "platform_reported_escrow",
                "bounty": {
                    "amount_atomic": "2500000",
                    "amount_display": "2.50",
                    "token": "USDC",
                    "network": "eip155:8453",
                },
                "escrow": {"status": "funded", "deposit_tx_hash": "0xabc"},
                "payment_status": "pending",
            }],
        }

    def test_paid_task_is_opportunity_not_revenue(self):
        nodes = basedagents_nodes(self.based_report())
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["advertised_value"]["amount_atomic"], "2500000")
        self.assertEqual(nodes[0]["earned_revenue_atomic"], "0")
        self.assertEqual(nodes[0]["next_action"], "qualify_and_claim_with_official_basedagents_sdk")

    def test_settlement_events_are_the_only_revenue_input(self):
        ledger = {
            "events": [
                {"type": "verified_work", "payload": {"acc_microunits": 999999}},
                {"type": "usdc_settlement", "payload": {
                    "task_id": "sale-1",
                    "amount_atomic": 1200000,
                    "network": "eip155:8453",
                    "transaction": "0xsettled",
                }},
            ]
        }
        total, events = settled_revenue_from_ledger(ledger)
        self.assertEqual(total, 1200000)
        self.assertEqual(len(events), 1)

    def test_bazaar_absence_becomes_distribution_action_not_sale(self):
        rows = bazaar_nodes({
            "status": "ok",
            "observed_at": "2026-09-27T00:00:00Z",
            "facilitator": "https://facilitator.example",
            "list": {"resources_seen": 10, "our_resources_seen": 0},
        })
        self.assertEqual(rows[0]["id"], "distribution:x402-bazaar")
        self.assertEqual(rows[0]["earned_revenue_atomic"], "0")
        self.assertIn("bazaar", rows[0]["id"])

    def test_state_keeps_advertised_bounty_out_of_revenue(self):
        state = build_state(
            {},
            basedagents=self.based_report(),
            bazaar={
                "status": "ok",
                "observed_at": "2026-09-27T00:00:00Z",
                "list": {"resources_seen": 10, "our_resources_seen": 0},
            },
            economy_ledger={},
        )
        self.assertEqual(state["revenue"]["verified_external_usdc_atomic"], "0")
        self.assertEqual(state["opportunities"][0]["id"], "basedagents:task_paid")
        self.assertTrue(state["truth_rules"]["advertised_bounty_is_not_revenue"])

    def test_prior_terminal_status_survives_rescan(self):
        previous = {
            "opportunities": [{
                "id": "basedagents:task_paid",
                "status": "claimed",
                "score": 90,
                "first_seen_at": "2026-09-26T00:00:00Z",
                "receipts": ["receipt-1"],
            }]
        }
        state = build_state(
            previous,
            basedagents=self.based_report(),
            bazaar={"status": "unavailable"},
            economy_ledger={},
        )
        node = next(x for x in state["opportunities"] if x["id"] == "basedagents:task_paid")
        self.assertEqual(node["status"], "claimed")
        self.assertEqual(node["receipts"], ["receipt-1"])

    def test_score_rewards_funding_fit_and_claimability(self):
        low = opportunity_score(funded=False, claimable=False, capability_matches=0, bounty_atomic=10_000_000)
        high = opportunity_score(funded=True, claimable=True, capability_matches=2, bounty_atomic=1_000_000)
        self.assertGreater(high, low)


if __name__ == "__main__":
    unittest.main()
