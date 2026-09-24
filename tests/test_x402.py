import unittest
from swarmbrain.x402 import (
    PAYMENT_REQUIRED, PAYMENT_RESPONSE, PAYMENT_SIGNATURE,
    decode_header, encode_header, payment_required, settlement_record,
)

class X402Tests(unittest.TestCase):
    def test_v2_payment_required_header_round_trip(self):
        requirement = payment_required(
            resource_url="https://example.com/a0/work",
            description="Verified swarm work",
            service_name="A0",
            amount_atomic=10_000,
            asset="0x" + "1" * 40,
            pay_to="0x" + "2" * 40,
        )
        self.assertEqual(requirement["x402Version"], 2)
        self.assertEqual(requirement["accepts"][0]["network"], "eip155:8453")
        self.assertEqual(decode_header(encode_header(requirement)), requirement)
        self.assertEqual(PAYMENT_REQUIRED, "PAYMENT-REQUIRED")
        self.assertEqual(PAYMENT_SIGNATURE, "PAYMENT-SIGNATURE")
        self.assertEqual(PAYMENT_RESPONSE, "PAYMENT-RESPONSE")

    def test_successful_settlement_becomes_revenue_evidence(self):
        accepted = payment_required(
            resource_url="https://example.com/a0/work",
            description="Verified swarm work",
            service_name="A0",
            amount_atomic=18_000,
            asset="0x" + "1" * 40,
            pay_to="0x" + "2" * 40,
        )["accepts"][0]
        record = settlement_record({
            "success": True,
            "transaction": "0xdeadbeef",
            "network": "eip155:8453",
            "payer": "0x" + "3" * 40,
        }, accepted)
        self.assertEqual(record["amount_atomic"], 18_000)

    def test_failed_settlement_is_not_revenue(self):
        accepted = {"network":"eip155:8453","amount":"1"}
        with self.assertRaises(ValueError):
            settlement_record({"success":False}, accepted)

if __name__ == "__main__":
    unittest.main()
