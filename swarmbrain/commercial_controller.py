#!/usr/bin/env python3
"""Persistent commercial opportunity controller for SwarmBrain.

This module never treats advertised value as earned revenue. External revenue
enters state only from an economy ledger settlement event or an explicitly
supplied verified settlement record.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Any


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path: str | Path | None, default: Any) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(path: str | Path, value: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, p)


def atomic_usdc(value: Any) -> int:
    try:
        text = str(value)
        if not text.isdigit():
            return 0
        return max(0, int(text))
    except (TypeError, ValueError):
        return 0


def opportunity_score(*, funded: bool, claimable: bool, capability_matches: int, bounty_atomic: int) -> float:
    """Evidence-first score. Value contributes logarithmically so a huge claim cannot swamp fit."""
    score = 0.0
    if funded:
        score += 40.0
    if claimable:
        score += 25.0
    score += min(24.0, max(0, capability_matches) * 8.0)
    if bounty_atomic > 0:
        usdc = bounty_atomic / 1_000_000
        score += min(11.0, math.log10(1.0 + usdc) * 8.0)
    return round(score, 3)


def basedagents_nodes(report: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("status") != "ok":
        return []
    nodes = []
    for row in report.get("candidates") or []:
        task_id = str(row.get("task_id") or "").strip()
        if not task_id:
            continue
        bounty = row.get("bounty") or {}
        matches = list(row.get("matched_capabilities") or [])
        funding = row.get("funding_evidence")
        funded = funding == "platform_reported_escrow"
        claimable = row.get("claimable") is True
        amount = atomic_usdc(bounty.get("amount_atomic"))
        score = opportunity_score(
            funded=funded,
            claimable=claimable,
            capability_matches=len(matches),
            bounty_atomic=amount,
        )
        nodes.append({
            "id": "basedagents:" + task_id,
            "kind": "paid_task",
            "source": "basedagents",
            "source_ref": row.get("source"),
            "observed_at": report.get("observed_at"),
            "title": row.get("title"),
            "status": "observed",
            "score": score,
            "advertised_value": {
                "asset": bounty.get("token"),
                "network": bounty.get("network"),
                "amount_atomic": str(amount),
                "amount_display": bounty.get("amount_display"),
            },
            "funding_evidence": funding,
            "claimable": claimable,
            "matched_capabilities": matches,
            "required_capabilities": list(row.get("required_capabilities") or []),
            "expected_output": row.get("expected_output"),
            "output_format": row.get("output_format"),
            "evidence": {
                "escrow": row.get("escrow"),
                "payment_status": row.get("payment_status"),
            },
            "earned_revenue_atomic": "0",
            "next_action": (
                "qualify_and_claim_with_official_basedagents_sdk"
                if claimable and matches
                else "inspect_fit_before_claim"
            ),
            "execution_gate": (
                "requires_basedagents_identity_and_payout_wallet"
                if claimable and matches
                else "analysis_only"
            ),
        })
    return nodes


def bazaar_nodes(report: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("status") not in {"ok", "partial"}:
        return []
    rows: list[dict[str, Any]] = []
    listed = report.get("list") or {}
    if int(listed.get("our_resources_seen") or 0) == 0:
        rows.append({
            "id": "distribution:x402-bazaar",
            "kind": "distribution",
            "source": "x402-bazaar",
            "observed_at": report.get("observed_at"),
            "title": "Get the paid SwarmBrain route endpoint observed by Bazaar",
            "status": "observed",
            "score": 35.0,
            "advertised_value": None,
            "funding_evidence": "none",
            "earned_revenue_atomic": "0",
            "evidence": {
                "resources_seen": listed.get("resources_seen"),
                "our_resources_seen": listed.get("our_resources_seen"),
                "facilitator": report.get("facilitator"),
            },
            "next_action": "verify_live_sdk_endpoint_then_generate_real_bazaar_eligible_payment_traffic",
            "execution_gate": "requires_live_deployment_and_external_or_controlled_buyer_payment",
        })
    else:
        rows.append({
            "id": "distribution:x402-bazaar",
            "kind": "distribution",
            "source": "x402-bazaar",
            "observed_at": report.get("observed_at"),
            "title": "Maintain Bazaar-discoverable paid SwarmBrain endpoint",
            "status": "active",
            "score": 20.0,
            "advertised_value": None,
            "funding_evidence": "none",
            "earned_revenue_atomic": "0",
            "evidence": {
                "resources_seen": listed.get("resources_seen"),
                "our_resources_seen": listed.get("our_resources_seen"),
                "our_resources": listed.get("our_resources"),
            },
            "next_action": "measure_external_calls_and_payers",
            "execution_gate": "automatic_read_only",
        })
    return rows


def settled_revenue_from_ledger(ledger: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    events = []
    total = 0
    for event in ledger.get("events") or []:
        if event.get("type") != "usdc_settlement":
            continue
        payload = event.get("payload") or {}
        amount = atomic_usdc(payload.get("amount_atomic"))
        tx = str(payload.get("transaction") or "").strip()
        if amount <= 0 or not tx:
            continue
        total += amount
        events.append({
            "task_id": payload.get("task_id"),
            "amount_atomic": str(amount),
            "network": payload.get("network"),
            "transaction": tx,
            "payer": payload.get("payer"),
        })
    return total, events


def build_state(
    previous: dict[str, Any] | None,
    *,
    basedagents: dict[str, Any],
    bazaar: dict[str, Any],
    economy_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = previous or {}
    prior_nodes = {row["id"]: row for row in previous.get("opportunities") or [] if row.get("id")}
    observed = basedagents_nodes(basedagents) + bazaar_nodes(bazaar)
    seen_ids = set()

    for node in observed:
        seen_ids.add(node["id"])
        prior = prior_nodes.get(node["id"])
        if prior:
            node["first_seen_at"] = prior.get("first_seen_at") or prior.get("observed_at") or node.get("observed_at")
            if prior.get("status") in {"claimed", "delivered", "paid", "rejected", "expired"}:
                node["status"] = prior["status"]
            if prior.get("receipts"):
                node["receipts"] = prior["receipts"]
        else:
            node["first_seen_at"] = node.get("observed_at") or now()
        prior_nodes[node["id"]] = node

    for key, node in list(prior_nodes.items()):
        if key not in seen_ids and node.get("status") == "observed":
            node = dict(node)
            node["status"] = "stale"
            node["score"] = 0.0
            node["next_action"] = "none"
            prior_nodes[key] = node

    ledger = economy_ledger or {}
    settled, settlement_events = settled_revenue_from_ledger(ledger)
    opportunities = sorted(
        prior_nodes.values(),
        key=lambda row: (-float(row.get("score") or 0), str(row.get("id"))),
    )
    executable = [
        {
            "opportunity_id": row["id"],
            "score": row.get("score", 0),
            "action": row.get("next_action"),
            "gate": row.get("execution_gate"),
        }
        for row in opportunities
        if row.get("status") in {"observed", "active"}
        and row.get("next_action") not in {None, "none"}
    ]

    return {
        "schema_version": 1,
        "updated_at": now(),
        "objective": "increase verified external net revenue without relabeling advertisements, internal credits, or asking prices as revenue",
        "revenue": {
            "verified_external_usdc_atomic": str(settled),
            "verified_external_usdc_display": f"{settled / 1_000_000:.6f}",
            "settlement_count": len(settlement_events),
            "settlements": settlement_events,
        },
        "sources": {
            "basedagents": {
                "status": basedagents.get("status"),
                "observed_at": basedagents.get("observed_at"),
                "candidate_count": basedagents.get("candidate_count"),
            },
            "x402_bazaar": {
                "status": bazaar.get("status"),
                "observed_at": bazaar.get("observed_at"),
                "our_resources_seen": (bazaar.get("list") or {}).get("our_resources_seen"),
            },
        },
        "opportunities": opportunities,
        "next_actions": executable[:10],
        "truth_rules": {
            "advertised_bounty_is_not_revenue": True,
            "platform_reported_escrow_is_not_independent_chain_verification": True,
            "asking_price_is_not_revenue": True,
            "internal_acc_is_not_revenue": True,
            "only_settlement_events_enter_verified_external_revenue": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basedagents", required=True)
    parser.add_argument("--bazaar", required=True)
    parser.add_argument("--state", default="reports/commercial-state.json")
    parser.add_argument("--economy-ledger")
    args = parser.parse_args()

    previous = load_json(args.state, {})
    state = build_state(
        previous,
        basedagents=load_json(args.basedagents, {}),
        bazaar=load_json(args.bazaar, {}),
        economy_ledger=load_json(args.economy_ledger, {}) if args.economy_ledger else {},
    )
    save_json(args.state, state)
    print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
