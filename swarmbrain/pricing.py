#!/usr/bin/env python3
"""Deterministic reference-pricing for avoided-cost accounting."""
from __future__ import annotations
import hashlib, json
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

class RateCard:
    def __init__(self, document):
        if document.get("currency") != "USD" or not document.get("source") or not document.get("effective_at"):
            raise ValueError("Rate card requires USD currency, source, and effective_at")
        rates = document.get("rates")
        if not isinstance(rates, dict) or not rates:
            raise ValueError("Rate card rates are required")
        self.document = document
        self.hash = digest(document)

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def quote(self, *, rate_key, input_tokens=0, output_tokens=0,
              fixed_microusd=0, tool_microusd=0):
        if rate_key not in self.document["rates"]:
            raise ValueError("Unknown rate key")
        values = [int(input_tokens), int(output_tokens), int(fixed_microusd), int(tool_microusd)]
        if min(values) < 0:
            raise ValueError("Usage cannot be negative")
        rate = self.document["rates"][rate_key]
        input_rate = Decimal(str(rate.get("input_usd_per_million_tokens", 0)))
        output_rate = Decimal(str(rate.get("output_usd_per_million_tokens", 0)))
        token_usd = (
            Decimal(values[0]) * input_rate / Decimal(1_000_000) +
            Decimal(values[1]) * output_rate / Decimal(1_000_000)
        )
        token_microusd = int((token_usd * Decimal(1_000_000)).to_integral_value(rounding=ROUND_CEILING))
        total = token_microusd + values[2] + values[3]
        return {
            "schema_version": 1,
            "rate_card_hash": self.hash,
            "rate_card_source": self.document["source"],
            "rate_card_effective_at": self.document["effective_at"],
            "rate_key": rate_key,
            "usage": {
                "input_tokens": values[0],
                "output_tokens": values[1],
                "fixed_microusd": values[2],
                "tool_microusd": values[3],
            },
            "reference_cost_microusd": total,
        }

def verify_quote(rate_card, quote):
    expected = rate_card.quote(
        rate_key=quote["rate_key"],
        input_tokens=quote["usage"]["input_tokens"],
        output_tokens=quote["usage"]["output_tokens"],
        fixed_microusd=quote["usage"]["fixed_microusd"],
        tool_microusd=quote["usage"]["tool_microusd"],
    )
    return expected == quote
