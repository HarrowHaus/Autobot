#!/usr/bin/env python3
"""Deterministic end-state gate for agent task receipts.

Turns a noisy stream of execution receipts into a small human-review queue.
Synthetic/public-safe demonstration artifact for a Biobase application proof.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from typing import Any, Iterable

TERMINAL_SUCCESS = {"completed", "delivered", "accepted", "paid"}
TERMINAL_FAILURE = {"rejected", "expired", "cancelled", "failed"}


@dataclass(frozen=True)
class Decision:
    task_id: str
    disposition: str
    reason: str


def classify(row: dict[str, Any]) -> Decision:
    task_id = str(row.get("task_id") or "").strip()
    if not task_id:
        return Decision("<missing>", "needs_human", "missing_task_id")

    state = str(row.get("state") or "").strip().lower()
    verification = str(row.get("verification") or "").strip().lower()
    payment = str(row.get("payment") or "").strip().lower()
    error = str(row.get("error") or "").strip()

    if error:
        return Decision(task_id, "needs_human", "execution_error")
    if state in TERMINAL_FAILURE:
        return Decision(task_id, "closed", f"terminal_{state}")
    if verification in {"reject", "rejected", "failed"}:
        return Decision(task_id, "needs_human", "verification_rejected")
    if state in {"delivered", "accepted", "paid"} and verification not in {"accept", "accepted", "passed"}:
        return Decision(task_id, "needs_human", "missing_positive_verification")
    if state == "paid" and payment not in {"settled", "cleared", "confirmed"}:
        return Decision(task_id, "needs_human", "payment_not_reconciled")
    if state in TERMINAL_SUCCESS:
        return Decision(task_id, "closed", f"terminal_{state}")
    if state in {"queued", "running", "claimed", "submitted", "response_received"}:
        return Decision(task_id, "active", state)
    return Decision(task_id, "needs_human", "unknown_or_missing_state")


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    decisions = [classify(row) for row in rows]
    human = [asdict(d) for d in decisions if d.disposition == "needs_human"]
    return {
        "total": len(decisions),
        "needs_human_count": len(human),
        "human_queue": human,
        "all": [asdict(d) for d in decisions],
    }


def main() -> int:
    payload = json.load(sys.stdin)
    if not isinstance(payload, list):
        raise SystemExit("input must be a JSON array")
    result = summarize(payload)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
