#!/usr/bin/env python3
"""Closed-loop ACC service market.

Quotes do not move value. A transfer occurs only after the caller supplies
verified service evidence and the quote remains intact.
"""
from __future__ import annotations
import hashlib, json, time, uuid

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def quote_hash(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

class InternalMarket:
    def __init__(self, ledger, price_book=None):
        self.ledger = ledger
        self.price_book = dict(price_book or {})

    def set_price(self, *, provider, service, acc_microunits):
        amount = int(acc_microunits)
        if not provider or not service or amount <= 0:
            raise ValueError("Price fields are invalid")
        self.price_book[(str(provider), str(service))] = amount

    def quote(self, *, buyer, provider, service, ttl_seconds=300):
        key = (str(provider), str(service))
        if key not in self.price_book:
            raise ValueError("No price for provider/service")
        if not buyer or buyer == provider:
            raise ValueError("Buyer and provider must be distinct")
        ttl = max(1, min(int(ttl_seconds), 3600))
        issued = int(time.time())
        body = {
            "quote_id": "accquote-" + str(uuid.uuid4()),
            "buyer": str(buyer),
            "provider": str(provider),
            "service": str(service),
            "acc_microunits": int(self.price_book[key]),
            "issued_at_unix": issued,
            "expires_at_unix": issued + ttl,
        }
        body["quote_hash"] = quote_hash(body)
        return body

    def verify_quote(self, quote, now_unix=None):
        body = dict(quote)
        observed = body.pop("quote_hash", None)
        if not observed or quote_hash(body) != observed:
            return False
        if int(body.get("expires_at_unix", 0)) < int(time.time() if now_unix is None else now_unix):
            return False
        expected = self.price_book.get((str(body.get("provider")), str(body.get("service"))))
        return expected is not None and int(body.get("acc_microunits", -1)) == int(expected)

    def settle(self, *, task_id, quote, verified, evidence):
        if verified is not True:
            raise ValueError("ACC service settlement requires verified result")
        if not evidence:
            raise ValueError("ACC service settlement requires evidence")
        if not self.verify_quote(quote):
            raise ValueError("ACC service quote is invalid or expired")
        return self.ledger.record_acc_transfer(
            task_id=task_id,
            from_agent=quote["buyer"],
            to_agent=quote["provider"],
            acc_microunits=quote["acc_microunits"],
            evidence={
                "market_quote_id": quote["quote_id"],
                "market_quote_hash": quote["quote_hash"],
                "service": quote["service"],
                "verification": evidence,
            },
        )
