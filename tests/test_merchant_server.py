import json, os, unittest
from unittest.mock import patch
from swarmbrain.merchant_server import RouteService, build_service_from_env

class FakeMerchant:
    def __init__(self):
        self.calls = []
    def transact(self, **kwargs):
        self.calls.append(kwargs)
        result = kwargs["perform_work"]()
        return {"status":200,"headers":{},"body":{"result":result}}

class FakeMesh:
    def route(self, query, limit=3):
        return [{"peer":"peer-a","activation":0.9,"matched_terms":[query],"verified_results":1}][:limit]

class MerchantServerTests(unittest.TestCase):
    def test_route_service_is_read_only_and_bounded(self):
        merchant = FakeMerchant()
        service = RouteService(merchant, mesh_factory=FakeMesh)
        result = service.handle(
            headers={"PAYMENT-SIGNATURE":"abc"},
            body=json.dumps({"query":"verification","limit":3,"task_id":"sale-test"}).encode(),
        )
        self.assertEqual(result["status"], 200)
        routed = result["body"]["result"]
        self.assertEqual(routed["scope"], "read_only_route_selection")
        self.assertEqual(routed["routes"][0]["peer"], "peer-a")
        self.assertEqual(merchant.calls[0]["task_id"], "sale-test")

    def test_invalid_input_never_reaches_merchant(self):
        merchant = FakeMerchant()
        service = RouteService(merchant, mesh_factory=FakeMesh)
        result = service.handle(headers={}, body=b"{}")
        self.assertEqual(result["status"], 400)
        self.assertEqual(merchant.calls, [])

    def test_limit_is_capped(self):
        class CountingMesh:
            def route(self, query, limit=3):
                self.limit = limit
                return []
        mesh = CountingMesh()
        merchant = FakeMerchant()
        service = RouteService(merchant, mesh_factory=lambda: mesh)
        service.handle(headers={}, body=json.dumps({"query":"x","limit":999}).encode())
        self.assertEqual(mesh.limit, 10)

    @patch.dict(os.environ, {}, clear=True)
    def test_live_server_requires_explicit_enablement(self):
        with self.assertRaises(RuntimeError):
            build_service_from_env()

    @patch.dict(os.environ, {
        "A0_MERCHANT_ENABLED":"1",
        "A0_MERCHANT_PUBLIC_URL":"http://example.com",
        "A0_PAY_TO":"0x" + "2"*40,
        "A0_USDC_ASSET":"0x" + "1"*40,
        "A0_FACILITATOR_URL":"https://facilitator.example",
    }, clear=True)
    def test_public_merchant_url_must_be_https(self):
        with self.assertRaises(RuntimeError):
            build_service_from_env()

    @patch.dict(os.environ, {
        "A0_MERCHANT_ENABLED":"1",
        "A0_MERCHANT_PUBLIC_URL":"https://merchant.example",
        "A0_PAY_TO":"0x" + "2"*40,
        "A0_USDC_ASSET":"0x" + "1"*40,
        "A0_FACILITATOR_URL":"https://facilitator.example",
        "A0_FACILITATOR_HEADERS_JSON":"not-json",
    }, clear=True)
    def test_facilitator_secret_headers_must_be_valid_json(self):
        with self.assertRaises(RuntimeError):
            build_service_from_env()

if __name__ == "__main__":
    unittest.main()
