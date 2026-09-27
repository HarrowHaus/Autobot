import unittest

from swarmbrain.earning_cycle import select_candidate, _json_object


class EarningCycleTests(unittest.TestCase):
    def candidate(self, **changes):
        row = {
            "task_id": "task_1",
            "title": "Verify public research",
            "description": "Return a structured result from public evidence.",
            "expected_output": "JSON result",
            "output_format": "json",
            "claimable": True,
            "matched_capabilities": ["verification", "research"],
            "required_capabilities": ["verification"],
            "funding_evidence": "platform_reported_escrow",
            "bounty": {
                "amount_atomic": "2500000",
                "amount_display": "2.50",
                "token": "USDC",
                "network": "eip155:8453",
            },
        }
        row.update(changes)
        return row

    def test_selects_only_funded_claimable_capability_fit(self):
        report = {"status": "ok", "candidates": [self.candidate()]}
        self.assertEqual(select_candidate(report)["task_id"], "task_1")
        self.assertIsNone(
            select_candidate({
                "status": "ok",
                "candidates": [self.candidate(funding_evidence="advertised_bounty")],
            })
        )
        self.assertIsNone(
            select_candidate({
                "status": "ok",
                "candidates": [self.candidate(claimable=False)],
            })
        )
        self.assertIsNone(
            select_candidate({
                "status": "ok",
                "candidates": [self.candidate(matched_capabilities=[])],
            })
        )

    def test_skips_secret_or_private_data_jobs(self):
        report = {
            "status": "ok",
            "candidates": [self.candidate(description="Use this password to log in")],
        }
        self.assertIsNone(select_candidate(report))

    def test_json_parser_accepts_plain_or_fenced_object(self):
        self.assertEqual(_json_object('{"verdict":"accept"}')["verdict"], "accept")
        fenced = chr(96) * 3 + 'json\n{"verdict":"reject"}\n' + chr(96) * 3
        self.assertEqual(_json_object(fenced)["verdict"], "reject")


if __name__ == "__main__":
    unittest.main()
