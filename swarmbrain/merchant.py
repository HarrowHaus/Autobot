#!/usr/bin/env python3
"""x402 v2 merchant core for paid SwarmBrain services.

No wallet private key is held here. A configured facilitator verifies and settles
client-signed payments; only successful settlement becomes real USDC revenue.
"""
from __future__ import annotations
import hashlib, json, threading
from pathlib import Path
from urllib import request

try:
    from .economy import EconomyLedger
    from .x402 import (
        PAYMENT_REQUIRED, PAYMENT_RESPONSE, PAYMENT_SIGNATURE,
        decode_header, encode_header, payment_required, settlement_record,
    )
except ImportError:
    from economy import EconomyLedger
    from x402 import (
        PAYMENT_REQUIRED, PAYMENT_RESPONSE, PAYMENT_SIGNATURE,
        decode_header, encode_header, payment_required, settlement_record,
    )

class FacilitatorClient:
    def __init__(self, base_url, headers=None, timeout=30):
        self.base_url = str(base_url).rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = int(timeout)

    def _post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        headers = {"content-type": "application/json", **self.headers}
        req = request.Request(self.base_url + path, data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def verify(self, payment_payload, requirement):
        return self._post("/verify", {
            "x402Version": 2,
            "paymentPayload": payment_payload,
            "paymentRequirements": requirement,
        })

    def settle(self, payment_payload, requirement):
        return self._post("/settle", {
            "x402Version": 2,
            "paymentPayload": payment_payload,
            "paymentRequirements": requirement,
        })

class X402Merchant:
    def __init__(self, *, service_name, resource_url, description, amount_atomic,
                 asset, pay_to, facilitator, ledger_path, network="eip155:8453"):
        self.requirement = payment_required(
            resource_url=resource_url,
            description=description,
            service_name=service_name,
            amount_atomic=amount_atomic,
            asset=asset,
            pay_to=pay_to,
            network=network,
        )
        self.accepted = self.requirement["accepts"][0]
        self.facilitator = facilitator
        self.ledger_path = Path(ledger_path)
        self._replay_lock = threading.Lock()
        self._inflight = set()

    def challenge(self, reason=None):
        body = {"error": reason or "payment_required", "x402Version": 2}
        return {
            "status": 402,
            "headers": {PAYMENT_REQUIRED: encode_header(self.requirement)},
            "body": body,
        }

    def _payment_fingerprint(self, payment_payload):
        raw = json.dumps(payment_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _already_consumed(self, fingerprint):
        ledger = EconomyLedger.load(self.ledger_path)
        for event in ledger.events:
            if event.get("type") != "usdc_settlement":
                continue
            evidence = event.get("payload", {}).get("evidence") or {}
            if evidence.get("payment_payload_sha256") == fingerprint:
                return True
        return False

    def transact(self, *, task_id, payment_signature, perform_work):
        if not payment_signature:
            return self.challenge()
        try:
            payment_payload = decode_header(payment_signature)
        except Exception:
            return self.challenge("invalid_payment_signature_header")

        fingerprint = self._payment_fingerprint(payment_payload)
        with self._replay_lock:
            if fingerprint in self._inflight or self._already_consumed(fingerprint):
                return {
                    "status": 409,
                    "headers": {},
                    "body": {"error": "payment_already_consumed"},
                }
            self._inflight.add(fingerprint)

        try:
            verification = self.facilitator.verify(payment_payload, self.accepted)
            if verification.get("isValid") is not True:
                return self.challenge(verification.get("invalidReason") or "payment_invalid")

            try:
                resource = perform_work()
            except Exception as exc:
                return {
                    "status": 500,
                    "headers": {},
                    "body": {"error": "resource_execution_failed", "detail": str(exc)[:300]},
                }

            settlement = self.facilitator.settle(payment_payload, self.accepted)
            if settlement.get("success") is not True:
                return {
                    "status": 502,
                    "headers": {},
                    "body": {"error": "payment_settlement_failed", "settlement": settlement},
                }

            record = settlement_record(settlement, self.accepted)
            with self._replay_lock:
                ledger = EconomyLedger.load(self.ledger_path)
                event = ledger.record_usdc_settlement(
                    task_id=task_id,
                    amount_atomic=record["amount_atomic"],
                    network=record["network"],
                    transaction=record["transaction"],
                    payer=record.get("payer"),
                    evidence={
                        "x402_version": 2,
                        "payment_payload_sha256": fingerprint,
                        "verification": verification,
                        "settlement": settlement,
                    },
                )
            return {
                "status": 200,
                "headers": {PAYMENT_RESPONSE: encode_header(settlement)},
                "body": {
                    "result": resource,
                    "payment": {
                        "event_id": event["event_id"],
                        "amount_atomic": record["amount_atomic"],
                        "network": record["network"],
                        "transaction": record["transaction"],
                    },
                },
            }
        finally:
            with self._replay_lock:
                self._inflight.discard(fingerprint)

__all__ = [
    "FacilitatorClient", "X402Merchant",
    "PAYMENT_REQUIRED", "PAYMENT_SIGNATURE", "PAYMENT_RESPONSE",
]
