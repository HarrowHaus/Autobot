import unittest
from swarmbrain.pricing import RateCard, verify_quote

class PricingTests(unittest.TestCase):
    def card(self):
        return RateCard({
            "currency":"USD",
            "source":"https://provider.example/pricing",
            "effective_at":"2026-09-24",
            "rates":{
                "model-a":{
                    "input_usd_per_million_tokens":"2.00",
                    "output_usd_per_million_tokens":"8.00"
                }
            }
        })

    def test_reference_cost_uses_measured_usage(self):
        card=self.card()
        quote=card.quote(rate_key="model-a",input_tokens=1000,output_tokens=500,tool_microusd=300)
        self.assertEqual(quote["reference_cost_microusd"],6300)
        self.assertTrue(verify_quote(card,quote))

    def test_tampered_quote_is_rejected(self):
        card=self.card()
        quote=card.quote(rate_key="model-a",input_tokens=1000)
        quote["reference_cost_microusd"] += 1
        self.assertFalse(verify_quote(card,quote))

    def test_unknown_model_and_negative_usage_rejected(self):
        card=self.card()
        with self.assertRaises(ValueError):
            card.quote(rate_key="unknown",input_tokens=1)
        with self.assertRaises(ValueError):
            card.quote(rate_key="model-a",input_tokens=-1)

if __name__=="__main__":
    unittest.main()
