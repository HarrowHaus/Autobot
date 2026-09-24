#!/usr/bin/env python3
"""Minimal x402 v2 representation helpers; no private keys or live settlement."""
from __future__ import annotations
import base64, json, re

PAYMENT_REQUIRED = "PAYMENT-REQUIRED"
PAYMENT_SIGNATURE = "PAYMENT-SIGNATURE"
PAYMENT_RESPONSE = "PAYMENT-RESPONSE"

def _address(value):
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", str(value or "")):
        raise ValueError("Expected an EVM address")
    return value

def payment_required(*, resource_url, description, service_name, amount_atomic,
                     asset, pay_to, network="eip155:8453", max_timeout_seconds=60):
    amount = int(amount_atomic)
    if amount <= 0:
        raise ValueError("Payment amount must be positive")
    if not str(network).startswith("eip155:"):
        raise ValueError("This helper currently supports EVM CAIP-2 networks only")
    return {
        "x402Version": 2,
        "resource": {
            "url": str(resource_url),
            "description": str(description),
            "mimeType": "application/json",
            "serviceName": str(service_name),
        },
        "accepts": [{
            "scheme": "exact",
            "network": network,
            "amount": str(amount),
            "asset": _address(asset),
            "payTo": _address(pay_to),
            "maxTimeoutSeconds": int(max_timeout_seconds),
            "extra": {"name": "USDC", "version": "2"},
        }],
        "extensions": {},
    }

def encode_header(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")

def decode_header(value):
    return json.loads(base64.b64decode(value).decode("utf-8"))

def settlement_record(settlement, accepted_requirement):
    if settlement.get("success") is not True:
        raise ValueError("Settlement is not successful")
    transaction = str(settlement.get("transaction") or "")
    network = str(settlement.get("network") or "")
    if not transaction or network != accepted_requirement["network"]:
        raise ValueError("Settlement proof does not match accepted network")
    return {
        "amount_atomic": int(accepted_requirement["amount"]),
        "network": network,
        "transaction": transaction,
        "payer": settlement.get("payer"),
    }
