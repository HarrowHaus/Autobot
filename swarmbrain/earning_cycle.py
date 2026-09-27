#!/usr/bin/env python3
"""Pre-fulfill one funded marketplace task through existing SwarmBrain peers.

This module does not claim marketplace work. It creates a delivery candidate and
an independent verification receipt first. A separate official BasedAgents SDK
adapter may claim and deliver only after this preflight returns ready_to_claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .mesh import Mesh, parts_of, now, write_json
except ImportError:
    from mesh import Mesh, parts_of, now, write_json

BLOCK_TERMS = (
    "password", "private key", "seed phrase", "credential", "login to",
    "medical diagnosis", "legal advice", "investment advice", "weapon",
    "malware", "steal", "dox", "personal data",
)
NON_EXECUTOR_KINDS = {
    "directory_agent", "discovery_service", "coordination_service",
}
FENCE = chr(96) * 3


def _safe_id(value: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")[:45] or "task"
    return base


def _fingerprint(row: dict[str, Any]) -> str:
    material = json.dumps({
        "task_id": row.get("task_id"),
        "title": row.get("title"),
        "description": row.get("description"),
        "expected_output": row.get("expected_output"),
        "output_format": row.get("output_format"),
        "bounty": row.get("bounty"),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]


def select_candidate(report: dict[str, Any]) -> dict[str, Any] | None:
    if report.get("status") != "ok":
        return None
    for row in report.get("candidates") or []:
        text = " ".join(str(row.get(k) or "") for k in ("title", "description", "expected_output")).lower()
        if any(term in text for term in BLOCK_TERMS):
            continue
        bounty = row.get("bounty") or {}
        amount = str(bounty.get("amount_atomic") or "")
        if not amount.isdigit() or int(amount) <= 0:
            continue
        if row.get("claimable") is not True:
            continue
        if row.get("funding_evidence") != "platform_reported_escrow":
            continue
        if not row.get("matched_capabilities"):
            continue
        fmt = str(row.get("output_format") or "json").lower()
        if fmt not in {"json", "application/json", "structured-json", ""}:
            continue
        return row
    return None


def _read_result_text(mesh: Mesh, task: dict[str, Any]) -> str:
    receipt_path = task.get("receipt")
    if not receipt_path:
        return ""
    receipt = json.loads((mesh.root / receipt_path).read_text(encoding="utf-8"))
    pieces = []
    for part in parts_of(receipt.get("response")):
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            pieces.append(part["text"])
        elif isinstance(part, dict) and isinstance(part.get("data"), (dict, list)):
            pieces.append(json.dumps(part["data"], ensure_ascii=False))
    return "\n".join(pieces).strip()


def _json_object(text: str) -> dict[str, Any] | None:
    value = text.strip()
    if value.startswith(FENCE):
        value = re.sub(r"^" + re.escape(FENCE) + r"(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*" + re.escape(FENCE) + r"$", "", value)
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(value[start:end + 1])
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        return None


def _peer_is_executor(mesh: Mesh, alias: str) -> bool:
    peer = mesh.state.get("peers", {}).get(alias, {})
    if peer.get("kind") in NON_EXECUTOR_KINDS:
        return False
    return (
        peer.get("status") in {"connected", "card_verified"}
        and int(peer.get("verified_results") or 0) > 0
    )


def choose_primary(mesh: Mesh, candidate: dict[str, Any]) -> str | None:
    terms = list(candidate.get("matched_capabilities") or [])
    terms += list(candidate.get("required_capabilities") or [])
    terms.append(str(candidate.get("title") or ""))
    for route in mesh.route(" ".join(terms), limit=10):
        if _peer_is_executor(mesh, route["peer"]):
            return route["peer"]
    return None


def choose_verifier(mesh: Mesh, primary: str) -> str | None:
    for route in mesh.route("verification evidence validation research", limit=10):
        alias = route["peer"]
        if alias != primary and _peer_is_executor(mesh, alias):
            return alias
    return None


def primary_prompt(candidate: dict[str, Any]) -> str:
    task = {
        "task_id": candidate.get("task_id"),
        "title": candidate.get("title"),
        "description": candidate.get("description"),
        "required_capabilities": candidate.get("required_capabilities"),
        "expected_output": candidate.get("expected_output"),
        "output_format": candidate.get("output_format"),
    }
    return (
        "Produce a candidate deliverable for the following public paid task. "
        "Do not claim the task, contact the buyer, spend money, use private data, or make promises. "
        "Use only public information and capabilities you can actually exercise. "
        "Return ONLY one JSON object with keys: status ('complete' or 'cannot_fulfill'), "
        "summary (string), submission (JSON value), evidence (array), limitations (array). "
        "If the requested work cannot be completed from available public context, use cannot_fulfill.\n"
        + json.dumps(task, ensure_ascii=False)
    )


def verifier_prompt(candidate: dict[str, Any], artifact: dict[str, Any]) -> str:
    payload = {
        "task": {
            "task_id": candidate.get("task_id"),
            "title": candidate.get("title"),
            "description": candidate.get("description"),
            "required_capabilities": candidate.get("required_capabilities"),
            "expected_output": candidate.get("expected_output"),
        },
        "candidate_deliverable": artifact,
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > 11_000:
        text = text[:11_000]
    return (
        "Independently check whether the candidate deliverable actually satisfies the public task. "
        "Do not improve it, contact anyone, spend money, or infer facts not present. "
        'Return ONLY JSON: {"verdict":"accept"|"reject","reason":"...","checks":["..."]}.\n'
        + text
    )


def run_preflight(mesh: Mesh, report: dict[str, Any]) -> dict[str, Any]:
    candidate = select_candidate(report)
    if not candidate:
        return {"status": "no_candidate", "at": now(), "plan": None}
    primary = choose_primary(mesh, candidate)
    if not primary:
        return {
            "status": "no_verified_executor",
            "at": now(),
            "task_id": candidate.get("task_id"),
            "plan": None,
        }
    verifier = choose_verifier(mesh, primary)
    if not verifier:
        return {
            "status": "no_independent_verifier",
            "at": now(),
            "task_id": candidate.get("task_id"),
            "primary_peer": primary,
            "plan": None,
        }

    fp = _fingerprint(candidate)
    base = "earn-" + _safe_id(str(candidate["task_id"])) + "-" + fp
    primary_task = mesh.send(primary, primary_prompt(candidate), base + "-primary")
    if primary_task.get("state") != "response_received":
        return {
            "status": "primary_not_completed",
            "at": now(),
            "task_id": candidate.get("task_id"),
            "primary_peer": primary,
            "primary_task": primary_task.get("id"),
            "plan": None,
        }
    artifact = _json_object(_read_result_text(mesh, primary_task))
    if not artifact or artifact.get("status") != "complete" or "submission" not in artifact:
        return {
            "status": "primary_declined_or_invalid",
            "at": now(),
            "task_id": candidate.get("task_id"),
            "primary_peer": primary,
            "primary_task": primary_task.get("id"),
            "plan": None,
        }

    verifier_task = mesh.send(
        verifier,
        verifier_prompt(candidate, artifact),
        base + "-verify",
        depends_on=primary_task["id"],
    )
    if verifier_task.get("state") != "response_received":
        return {
            "status": "verification_not_completed",
            "at": now(),
            "task_id": candidate.get("task_id"),
            "primary_peer": primary,
            "verifier_peer": verifier,
            "plan": None,
        }
    verdict = _json_object(_read_result_text(mesh, verifier_task))
    if not verdict or verdict.get("verdict") != "accept":
        return {
            "status": "verification_rejected",
            "at": now(),
            "task_id": candidate.get("task_id"),
            "primary_peer": primary,
            "verifier_peer": verifier,
            "verdict": verdict,
            "plan": None,
        }

    prior_review = primary_task.get("semantic_validation", "not_reviewed")
    if prior_review == "not_reviewed":
        mesh.review(
            primary_task["id"],
            True,
            "Independent pre-claim verifier accepted the task-specific candidate deliverable.",
        )
    elif prior_review != "accepted":
        return {
            "status": "primary_previously_rejected",
            "at": now(),
            "task_id": candidate.get("task_id"),
            "primary_peer": primary,
            "verifier_peer": verifier,
            "plan": None,
        }
    bounty = candidate.get("bounty") or {}
    plan = {
        "schema_version": 1,
        "created_at": now(),
        "task_id": candidate["task_id"],
        "title": candidate.get("title"),
        "bounty_amount_atomic": str(bounty.get("amount_atomic")),
        "bounty_network": bounty.get("network") or "eip155:8453",
        "summary": str(artifact.get("summary") or "SwarmBrain verified delivery")[:2000],
        "submission_type": "json",
        "content": json.dumps(artifact.get("submission"), ensure_ascii=False),
        "primary_peer": primary,
        "verifier_peer": verifier,
        "primary_task_id": primary_task["id"],
        "verifier_task_id": verifier_task["id"],
        "primary_receipt": primary_task.get("receipt"),
        "verifier_receipt": verifier_task.get("receipt"),
        "verification": verdict,
        "source": candidate.get("source"),
        "truth_boundary": (
            "Prepared before claim; no marketplace revenue is earned until "
            "accepted and settled on-chain."
        ),
    }
    return {
        "status": "ready_to_claim",
        "at": now(),
        "task_id": candidate["task_id"],
        "primary_peer": primary,
        "verifier_peer": verifier,
        "plan": plan,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basedagents", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    report = json.loads(Path(args.basedagents).read_text(encoding="utf-8"))
    mesh = Mesh()
    result = run_preflight(mesh, report)
    if result.get("plan"):
        write_json(Path(args.plan), result["plan"])
    else:
        Path(args.plan).unlink(missing_ok=True)
    write_json(Path(args.result), {k: v for k, v in result.items() if k != "plan"})
    mesh.export()
    print(json.dumps({k: v for k, v in result.items() if k != "plan"}, indent=2))


if __name__ == "__main__":
    main()
