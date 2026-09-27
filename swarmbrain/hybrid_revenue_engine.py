#!/usr/bin/env python3
"""Hybrid revenue controller: A0 discovery breadth + SwarmBrain execution discipline.

This module is deliberately not a network sender, marketplace claimer, wallet signer,
or payment writer. It persists and ranks connector-discovered buyer demand, merges
SwarmBrain marketplace state, and emits the next evidence-gated action.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Any

TERMINAL = {"paid", "rejected", "expired", "refused", "duplicate"}
ACTIVE = {
    "discovered", "qualified", "prebuilt", "verified", "contacted",
    "claimed", "delivered", "accepted", "payment_pending", "blocked",
}
SOURCE_KINDS = {
    "direct_request", "contract_post", "public_bounty", "marketplace_task",
    "editorial_call", "resale_wanted", "invited_referral", "government_opportunity",
}
FUNDING_LEVELS = {
    "independently_verified": 4,
    "platform_escrow_reported": 3,
    "buyer_budget_stated": 2,
    "payout_advertised": 1,
    "unknown": 0,
}
ASSET_KINDS = {"USD", "USDC_BASE", "BTC_LIGHTNING", "OTHER_VERIFIED"}


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


def _money(value: Any) -> int:
    if type(value) is not int or value < 0:
        return 0
    return value


def _caps(candidate: dict[str, Any], verified_caps: set[str]) -> tuple[int, bool]:
    required = {str(x).strip().lower() for x in candidate.get("required_capabilities") or [] if str(x).strip()}
    if not required:
        return 0, True
    matches = len(required & verified_caps)
    return matches, required <= verified_caps


def qualification_reasons(candidate: dict[str, Any], verified_caps: set[str]) -> list[str]:
    reasons: list[str] = []
    if candidate.get("source_kind") not in SOURCE_KINDS:
        reasons.append("unsupported_source_kind")
    if not candidate.get("source_url") or not candidate.get("request_id"):
        reasons.append("missing_source_identity")
    if candidate.get("current_status") != "open":
        reasons.append("request_not_open")
    if candidate.get("dedupe_state") in {"already_contacted", "already_handled", "refused"}:
        reasons.append("deduped_or_refused")
    if candidate.get("upfront_spend_required") is True:
        reasons.append("upfront_spend_required")
    if candidate.get("new_account_required") is True:
        reasons.append("new_account_required")
    if candidate.get("wallet_signing_required_before_earning") is True:
        reasons.append("wallet_signing_required")
    if candidate.get("contact_permission") not in {
        "public_reply", "explicit_email", "marketplace_claim", "application",
        "quotes_invited", "existing_relationship", "none_needed",
    }:
        reasons.append("no_permitted_action_channel")
    matches, full = _caps(candidate, verified_caps)
    if not full:
        reasons.append("capability_gap")
    if not candidate.get("acceptance_criteria"):
        reasons.append("acceptance_criteria_missing")
    gross = _money(candidate.get("advertised_gross_usd_atomic"))
    known_cost = _money(candidate.get("known_cost_usd_atomic"))
    unknown_cost = _money(candidate.get("unknown_cost_reserve_usd_atomic"))
    if gross and gross <= known_cost + unknown_cost:
        reasons.append("no_defensible_positive_margin")
    if candidate.get("source_kind") == "resale_wanted":
        for flag in ("exact_match_verified", "inventory_live_verified", "venue_rules_verified"):
            if candidate.get(flag) is not True:
                reasons.append(flag + "_missing")
        if candidate.get("net_margin_usd_atomic") is None:
            reasons.append("net_margin_unverified")
    return sorted(set(reasons))


def opportunity_score(candidate: dict[str, Any], verified_caps: set[str]) -> float:
    reasons = qualification_reasons(candidate, verified_caps)
    if reasons:
        return 0.0
    score = 20.0
    funding = FUNDING_LEVELS.get(str(candidate.get("funding_evidence") or "unknown"), 0)
    score += funding * 10.0
    matches, _ = _caps(candidate, verified_caps)
    score += min(20.0, matches * 5.0)
    if candidate.get("deadline_known") is True:
        score += 4.0
    if candidate.get("acceptance_test_machine_checkable") is True:
        score += 8.0
    if candidate.get("prebuild_allowed") is True:
        score += 8.0
    if candidate.get("official_action_adapter_ready") is True:
        score += 8.0
    gross = _money(candidate.get("advertised_gross_usd_atomic"))
    if gross:
        usd = gross / 100
        score += min(12.0, math.log10(1.0 + usd) * 5.0)
    friction = int(candidate.get("friction_points") or 0)
    score -= min(20.0, max(0, friction) * 4.0)
    return round(max(0.0, score), 3)


def next_action(row: dict[str, Any]) -> str:
    status = row.get("status")
    if status in TERMINAL:
        return "none"
    if status in {"contacted", "claimed", "delivered", "accepted", "payment_pending"}:
        return "reconcile_reply_acceptance_and_settlement"
    if status == "verified":
        return "recheck_live_state_then_execute_official_channel"
    if status == "prebuilt":
        return "independent_verify_prebuilt_artifact"
    if status == "qualified":
        if row.get("prebuild_allowed") is True:
            return "prebuild_smallest_task_specific_artifact"
        return "recheck_live_state_then_execute_official_channel"
    if status == "blocked":
        return "resolve_only_the_recorded_blocker"
    return "qualify_against_current_source_and_capability_evidence"


def _normalize_connector(row: dict[str, Any], verified_caps: set[str]) -> dict[str, Any]:
    item = dict(row)
    item["id"] = str(item.get("id") or f"{item.get('source_kind')}:{item.get('request_id')}")
    reasons = qualification_reasons(item, verified_caps)
    item["qualification_reasons"] = reasons
    item["score"] = opportunity_score(item, verified_caps)
    prior_status = str(item.get("status") or "discovered")
    if prior_status not in ACTIVE | TERMINAL:
        prior_status = "discovered"
    if prior_status == "discovered" and not reasons:
        prior_status = "qualified"
    elif reasons and prior_status not in TERMINAL:
        prior_status = "blocked"
    item["status"] = prior_status
    item["next_action"] = next_action(item)
    item.setdefault("receipts", [])
    item.setdefault("first_seen_at", item.get("observed_at") or now())
    item["last_evaluated_at"] = now()
    return item


def _from_swarmbrain(commercial: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for src in commercial.get("opportunities") or []:
        ident = str(src.get("id") or "")
        if not ident:
            continue
        status = str(src.get("status") or "observed")
        mapped = "qualified" if status in {"observed", "active"} else status
        rows.append({
            "id": "swarmbrain:" + ident,
            "source_kind": "marketplace_task" if src.get("kind") == "paid_task" else "direct_request",
            "source_system": src.get("source"),
            "source_url": src.get("source_ref") or "https://github.com/HarrowHaus/Autobot",
            "request_id": ident,
            "title": src.get("title"),
            "status": mapped,
            "score": float(src.get("score") or 0),
            "funding_evidence": src.get("funding_evidence") or "unknown",
            "prebuild_allowed": src.get("kind") == "paid_task",
            "execution_owner": "swarmbrain",
            "next_action": src.get("next_action") or next_action({"status": mapped}),
            "receipts": src.get("receipts") or [],
            "first_seen_at": src.get("first_seen_at") or src.get("observed_at") or now(),
            "last_evaluated_at": now(),
        })
    return rows


def verified_settlements(intake: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    total = 0
    rows = []
    seen = set()
    for item in intake.get("verified_settlements") or []:
        if item.get("independently_verified") is not True:
            continue
        key = str(item.get("settlement_id") or "").strip()
        amount = _money(item.get("amount_usd_atomic"))
        asset = str(item.get("asset_kind") or "")
        if not key or key in seen or amount <= 0 or asset not in ASSET_KINDS:
            continue
        seen.add(key)
        total += amount
        rows.append({
            "settlement_id": key,
            "amount_usd_atomic": amount,
            "asset_kind": asset,
            "source": item.get("source"),
            "received_at": item.get("received_at"),
        })
    return total, rows


def build_state(
    previous: dict[str, Any],
    intake: dict[str, Any],
    commercial: dict[str, Any],
) -> dict[str, Any]:
    verified_caps = {str(x).strip().lower() for x in intake.get("verified_capabilities") or [] if str(x).strip()}
    prior = {str(x.get("id")): x for x in previous.get("opportunities") or [] if x.get("id")}
    current: dict[str, dict[str, Any]] = {}

    for raw in intake.get("opportunities") or []:
        if not isinstance(raw, dict):
            continue
        row = _normalize_connector(raw, verified_caps)
        old = prior.get(row["id"])
        if old:
            row["first_seen_at"] = old.get("first_seen_at") or row["first_seen_at"]
            if old.get("status") in TERMINAL | {"contacted", "claimed", "delivered", "accepted", "payment_pending"}:
                row["status"] = old["status"]
            if old.get("receipts"):
                row["receipts"] = old["receipts"]
            row["next_action"] = next_action(row)
        current[row["id"]] = row

    for row in _from_swarmbrain(commercial):
        current[row["id"]] = row

    for ident, old in prior.items():
        if ident not in current and old.get("status") not in TERMINAL:
            stale = dict(old)
            stale["status"] = "expired" if old.get("expires_at") else "blocked"
            stale["qualification_reasons"] = ["not_present_in_latest_source_snapshot"]
            stale["score"] = 0.0
            stale["next_action"] = "none"
            current[ident] = stale
        elif ident not in current:
            current[ident] = old

    connector_total, connector_settlements = verified_settlements(intake)
    swarm_atomic = int((commercial.get("revenue") or {}).get("verified_external_usdc_atomic") or 0)
    revenue = {
        "verified_connector_usd_atomic": connector_total,
        "verified_swarmbrain_usdc_atomic": swarm_atomic,
        "connector_settlements": connector_settlements,
        "note": "Rails remain separate; values are not combined into realized USD unless the settlement source already establishes dollar equivalence.",
    }

    opportunities = sorted(current.values(), key=lambda x: (-float(x.get("score") or 0), str(x.get("id"))))
    queue = [
        {
            "opportunity_id": x["id"],
            "status": x.get("status"),
            "score": x.get("score"),
            "next_action": x.get("next_action"),
            "execution_owner": x.get("execution_owner", "a0"),
        }
        for x in opportunities
        if x.get("next_action") not in {None, "none"} and x.get("status") not in TERMINAL
    ]

    return {
        "schema_version": 1,
        "updated_at": now(),
        "architecture": "A0 broad discovery and customer access + SwarmBrain evidence-gated execution and reconciliation",
        "revenue": revenue,
        "verified_capabilities": sorted(verified_caps),
        "opportunities": opportunities,
        "action_queue": queue[:25],
        "truth_rules": {
            "lead_is_not_revenue": True,
            "advertised_budget_is_not_revenue": True,
            "prebuild_is_not_a_sale": True,
            "internal_acc_is_not_revenue": True,
            "pending_token_reward_is_not_usd": True,
            "settlement_requires_independent_verification": True,
            "unknown_cost_is_not_zero": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intake", default="reports/a0-connector-opportunities.json")
    parser.add_argument("--commercial", default="reports/commercial-state.json")
    parser.add_argument("--state", default="reports/hybrid-revenue-state.json")
    parser.add_argument("--plan", default="reports/hybrid-revenue-plan.json")
    args = parser.parse_args()

    previous = load_json(args.state, {})
    intake = load_json(args.intake, {"verified_capabilities": [], "opportunities": [], "verified_settlements": []})
    commercial = load_json(args.commercial, {})
    state = build_state(previous, intake, commercial)
    save_json(args.state, state)
    save_json(args.plan, {
        "updated_at": state["updated_at"],
        "architecture": state["architecture"],
        "action_queue": state["action_queue"],
    })
    print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
