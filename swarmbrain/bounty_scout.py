#!/usr/bin/env python3
"""Read-only opportunity scout. Advertised budgets are never earned revenue."""
from __future__ import annotations
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib import request

API = "https://api.basedagents.ai"
ALIASES = {
    "verification": r"\b(verif\w*|validat\w*|audit\w*)\b",
    "research": r"\b(research\w*|source\w*)\b",
    "planning": r"\b(plan\w*)\b",
    "coding": r"\b(code|coding|debug\w*|regression\w*)\b",
    "data-analysis": r"\b(data[- ]analysis|dataset\w*)\b",
    "reasoning": r"\b(reason\w*)\b",
}
CAPS = set(os.environ.get("A0_BOUNTY_CAPABILITIES", ",".join(ALIASES)).split(","))


def get_json(path):
    req = request.Request(API + path, headers={"accept": "application/json", "user-agent": "A0-bounty-scout/2"})
    with request.urlopen(req, timeout=20) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("response_too_large")
    return json.loads(raw)


def amount_usdc(task):
    bounty = task.get("bounty")
    if not isinstance(bounty, dict):
        return Decimal(0)
    if str(bounty.get("currency", bounty.get("asset", "USDC"))).upper() != "USDC":
        return Decimal(0)
    try:
        if "amount_atomic" in bounty:
            value = str(bounty["amount_atomic"])
            if not re.fullmatch(r"\d+", value):
                return Decimal(0)
            amount = Decimal(value) / 1_000_000
        elif "amount_display" in bounty:
            amount = Decimal(str(bounty["amount_display"]))
        else:
            return Decimal(0)  # An unlabelled amount has ambiguous units.
        return amount if amount.is_finite() and amount > 0 else Decimal(0)
    except (InvalidOperation, ValueError):
        return Decimal(0)


def task_caps(task):
    parts = [str(task.get("title") or ""), str(task.get("description") or "")]
    for key in ("capabilities", "required_capabilities", "skills", "tags"):
        value = task.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif isinstance(value, str):
            parts.append(value)
    text = " ".join(parts).lower()
    return {cap for cap in CAPS if re.search(ALIASES.get(cap, r"\b" + re.escape(cap) + r"\b"), text)}


def funded(task):
    """Platform-reported escrow only, NOT independent on-chain verification."""
    escrow = task.get("escrow")
    return isinstance(escrow, dict) and escrow.get("status") == "funded"


def normalize_tasks(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        return data["tasks"]
    raise ValueError("unsupported_task_response_shape")


def scan(data, minimum=Decimal("0.01")):
    tasks = normalize_tasks(data)
    candidates, unpriced, malformed, seen = [], 0, 0, set()
    for task in tasks:
        if not isinstance(task, dict):
            malformed += 1
            continue
        task_id = task.get("task_id") or task.get("id")
        if not isinstance(task_id, str) or not task_id or task_id in seen:
            malformed += 1
            continue
        seen.add(task_id)
        if task.get("status", "open") != "open" or task.get("claimable") is False:
            continue
        matches = sorted(task_caps(task))
        if not matches:
            continue
        bounty = amount_usdc(task)
        if not bounty:
            unpriced += 1
            continue
        if bounty < minimum:
            continue
        escrow = task.get("escrow") if isinstance(task.get("escrow"), dict) else {}
        candidates.append({
            "task_id": task_id, "title": str(task.get("title") or "")[:300],
            "bounty_usdc": str(bounty), "matches": matches,
            "claimable": task.get("claimable") is True,
            "funding_evidence": "platform_reported_escrow" if funded(task) else "unverified_advertised_budget",
            "escrow_status": escrow.get("status"), "payment_status": task.get("payment_status"),
            "source_kind": "request_for_work", "source": API + "/v1/tasks?status=open",
            "operator_identity_verified": False, "outreach_authorized": False,
        })
    candidates.sort(key=lambda row: (-Decimal(row["bounty_usdc"]), -len(row["matches"]), row["task_id"]))
    return {"source": API, "status": "ok", "coverage": "first_response_only",
            "observed_at": datetime.now(timezone.utc).isoformat(), "tasks_examined": len(tasks),
            "candidate_count": len(candidates), "candidates": candidates[:20],
            "unpriced_matching_tasks": unpriced, "malformed_rows": malformed,
            "truncated": len(candidates) > 20, "independently_verified_funding_count": 0,
            "new_external_revenue_atomic": 0}


def main():
    try:
        minimum = Decimal(os.environ.get("A0_MIN_BOUNTY_USDC", "0.01"))
        if not minimum.is_finite() or minimum < 0:
            raise ValueError("invalid_minimum")
        result = scan(get_json("/v1/tasks?status=open"), minimum)
    except Exception as error:
        result = {"source": API, "status": "unavailable", "candidate_count": None,
                  "candidates": [], "error_type": type(error).__name__, "new_external_revenue_atomic": 0}
        print(json.dumps(result, indent=2))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
