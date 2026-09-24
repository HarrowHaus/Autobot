#!/usr/bin/env python3
"""Tamper-evident internal economy ledger for SwarmBrain/A0."""
from __future__ import annotations
import hashlib, json, os, time, uuid
from pathlib import Path

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

class EconomyLedger:
    def __init__(self, path, snapshot=None):
        self.path = Path(path)
        snapshot = snapshot or {}
        self.ledger_id = snapshot.get("ledger_id") or "econ-" + str(uuid.uuid4())
        self.events = list(snapshot.get("events") or [])

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.exists():
            return cls(path, json.loads(path.read_text(encoding="utf-8")))
        return cls(path)

    def append(self, event_type, payload):
        previous = self.events[-1]["event_hash"] if self.events else None
        event = {
            "sequence": len(self.events) + 1,
            "event_id": "econevt-" + str(uuid.uuid4()),
            "at": now(),
            "type": event_type,
            "payload": payload,
            "previous_hash": previous,
        }
        event["event_hash"] = sha256(event)
        self.events.append(event)
        self.save()
        return event

    def record_verified_work(self, *, task_id, contributors, reference_cost_microusd,
                             actual_cost_microusd, acc_microunits, evidence):
        ref = int(reference_cost_microusd)
        actual = int(actual_cost_microusd)
        acc = int(acc_microunits)
        if min(ref, actual, acc) < 0 or actual > ref:
            raise ValueError("Cost and ACC values are invalid")
        if not task_id or not contributors or not evidence:
            raise ValueError("Verified work requires task, contributors, and evidence")
        return self.append("verified_work", {
            "task_id": task_id,
            "contributors": contributors,
            "reference_cost_microusd": ref,
            "actual_cost_microusd": actual,
            "avoided_cost_microusd": ref - actual,
            "acc_microunits": acc,
            "evidence": evidence,
        })

    def record_usdc_settlement(self, *, task_id, amount_atomic, network, transaction,
                               payer=None, evidence=None):
        amount = int(amount_atomic)
        if amount <= 0 or not task_id or not network or not transaction:
            raise ValueError("Settlement fields are incomplete")
        for event in self.events:
            if event["type"] == "usdc_settlement" and event["payload"]["transaction"] == transaction:
                raise ValueError("Duplicate settlement transaction")
        return self.append("usdc_settlement", {
            "task_id": task_id,
            "asset": "USDC",
            "amount_atomic": amount,
            "network": network,
            "transaction": transaction,
            "payer": payer,
            "evidence": evidence or {},
        })

    def verify(self):
        previous = None
        for index, event in enumerate(self.events, 1):
            if event.get("sequence") != index or event.get("previous_hash") != previous:
                return {"ok": False, "sequence": index, "error": "chain mismatch"}
            copy = dict(event)
            observed = copy.pop("event_hash", None)
            if sha256(copy) != observed:
                return {"ok": False, "sequence": index, "error": "event hash mismatch"}
            previous = observed
        return {"ok": True, "event_count": len(self.events), "head_hash": previous}

    def balances(self):
        acc = 0
        avoided = 0
        usdc = 0
        for event in self.events:
            payload = event["payload"]
            if event["type"] == "verified_work":
                acc += int(payload["acc_microunits"])
                avoided += int(payload["avoided_cost_microusd"])
            elif event["type"] == "usdc_settlement":
                usdc += int(payload["amount_atomic"])
        return {
            "acc_microunits_issued": acc,
            "avoided_cost_microusd": avoided,
            "real_usdc_atomic_received": usdc,
        }

    def snapshot(self):
        return {
            "schema_version": 1,
            "ledger_id": self.ledger_id,
            "events": self.events,
            "verification": self.verify(),
            "balances": self.balances(),
            "rules": {
                "acc_is_internal_accounting_only": True,
                "avoided_cost_is_not_cash": True,
                "usdc_balance_requires_settlement_event": True,
            },
        }

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(self.snapshot(), indent=2) + "\n", encoding="utf-8")
        os.replace(temp, self.path)
