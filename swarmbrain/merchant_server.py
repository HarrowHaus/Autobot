#!/usr/bin/env python3
"""HTTP surface for a paid, read-only SwarmBrain routing service."""
from __future__ import annotations
import json, os, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

try:
    from .mesh import Mesh, ROOT
    from .merchant import FacilitatorClient, X402Merchant, PAYMENT_SIGNATURE
except ImportError:
    from mesh import Mesh, ROOT
    from merchant import FacilitatorClient, X402Merchant, PAYMENT_SIGNATURE

MAX_BODY = 16_384

class RouteService:
    def __init__(self, merchant, mesh_factory=Mesh):
        self.merchant = merchant
        self.mesh_factory = mesh_factory

    def handle(self, *, headers, body):
        if len(body) > MAX_BODY:
            return {"status": 413, "headers": {}, "body": {"error": "request_too_large"}}
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeError, ValueError):
            return {"status": 400, "headers": {}, "body": {"error": "invalid_json"}}
        query = str(payload.get("query") or "").strip()
        if not query or len(query) > 1000:
            return {"status": 400, "headers": {}, "body": {"error": "query_required"}}
        limit = int(payload.get("limit", 3))
        limit = max(1, min(limit, 10))
        task_id = str(payload.get("task_id") or ("sale-" + str(uuid.uuid4())))
        signature = headers.get(PAYMENT_SIGNATURE) or headers.get(PAYMENT_SIGNATURE.lower())

        def work():
            mesh = self.mesh_factory()
            return {
                "task_id": task_id,
                "query": query,
                "routes": mesh.route(query, limit=limit),
                "scope": "read_only_route_selection",
            }

        return self.merchant.transact(
            task_id=task_id,
            payment_signature=signature,
            perform_work=work,
        )

def _https_url(name, value):
    parsed = urlsplit(str(value or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError(name + " must be a public HTTPS URL without embedded credentials")
    return str(value).rstrip("/")

def _facilitator_headers_from_env():
    raw = os.environ.get("A0_FACILITATOR_HEADERS_JSON", "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("A0_FACILITATOR_HEADERS_JSON must be valid JSON") from exc
    if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise RuntimeError("Facilitator headers must be a JSON object of string values")
    return value

def build_service_from_env():
    if os.environ.get("A0_MERCHANT_ENABLED") != "1":
        raise RuntimeError("Merchant server is disabled; set A0_MERCHANT_ENABLED=1 explicitly")
    required = [
        "A0_MERCHANT_PUBLIC_URL",
        "A0_PAY_TO",
        "A0_USDC_ASSET",
        "A0_FACILITATOR_URL",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing merchant configuration: " + ", ".join(missing))
    amount = int(os.environ.get("A0_ROUTE_PRICE_ATOMIC", "10000"))
    public_url = _https_url("A0_MERCHANT_PUBLIC_URL", os.environ["A0_MERCHANT_PUBLIC_URL"])
    facilitator_url = _https_url("A0_FACILITATOR_URL", os.environ["A0_FACILITATOR_URL"])
    facilitator = FacilitatorClient(
        facilitator_url,
        headers=_facilitator_headers_from_env(),
    )
    merchant = X402Merchant(
        service_name="SwarmBrain Route Intelligence",
        resource_url=public_url + "/v1/route",
        description="Read-only ranked routing over the SwarmBrain peer graph",
        amount_atomic=amount,
        asset=os.environ["A0_USDC_ASSET"],
        pay_to=os.environ["A0_PAY_TO"],
        facilitator=facilitator,
        ledger_path=ROOT / "data" / "economy-ledger.json",
        network=os.environ.get("A0_PAYMENT_NETWORK", "eip155:8453"),
    )
    return RouteService(merchant)

class Handler(BaseHTTPRequestHandler):
    service = None

    def _send(self, result):
        data = json.dumps(result["body"], ensure_ascii=False).encode("utf-8")
        self.send_response(result["status"])
        for key, value in result.get("headers", {}).items():
            self.send_header(key, value)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send({"status": 200, "headers": {}, "body": {
                "ok": True, "service": "swarmbrain-route-merchant", "payments": "x402-v2"
            }})
        else:
            self._send({"status": 404, "headers": {}, "body": {"error": "not_found"}})

    def do_POST(self):
        if self.path != "/v1/route":
            self._send({"status": 404, "headers": {}, "body": {"error": "not_found"}})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        if length < 0 or length > MAX_BODY:
            self._send({"status": 413, "headers": {}, "body": {"error": "request_too_large"}})
            return
        body = self.rfile.read(length)
        self._send(self.service.handle(headers=self.headers, body=body))

    def log_message(self, fmt, *args):
        return

def main():
    service = build_service_from_env()
    Handler.service = service
    host = os.environ.get("A0_MERCHANT_HOST", "127.0.0.1")
    port = int(os.environ.get("A0_MERCHANT_PORT", "8787"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()

if __name__ == "__main__":
    main()
