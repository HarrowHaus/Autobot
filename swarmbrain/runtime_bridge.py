#!/usr/bin/env python3
"""Execute trusted GitHub issue-comment jobs, persist receipts, and account for verified work."""
from __future__ import annotations
import json, os, time
from pathlib import Path

from economy import EconomyLedger
from github_bridge import parse_comment_job
from run_mesh import execute, ROOT

RESULT_PATH = ROOT / "reports" / "comment-job-latest.json"
ECONOMY_PATH = ROOT / "data" / "economy-ledger.json"

def generated_at():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _completed_tasks(summary):
    return [
        task for task in summary.get("tasks", [])
        if task.get("state") == "response_received" and task.get("receipt")
    ]

def account(job, summary, job_id):
    spec = job.get("economy") or {}
    if not isinstance(spec, dict) or spec.get("verified") is not True:
        return {"recorded": False, "reason": "no operator-authorized verified economics"}
    completed = _completed_tasks(summary)
    if not completed:
        return {"recorded": False, "reason": "no completed task receipt"}
    ref = int(spec.get("reference_cost_microusd", 0))
    actual = int(spec.get("actual_cost_microusd", 0))
    acc = int(spec.get("acc_microunits", 0))
    if ref <= 0 or acc <= 0:
        raise ValueError("verified economics require positive reference_cost_microusd and acc_microunits")
    contributors = spec.get("contributors") or [
        {"agent_id": str(task.get("peer_id") or task.get("peer") or "external-peer"), "weight": 1.0}
        for task in completed
    ]
    ledger = EconomyLedger.load(ECONOMY_PATH)
    event = ledger.record_verified_work(
        task_id=job_id,
        contributors=contributors,
        reference_cost_microusd=ref,
        actual_cost_microusd=actual,
        acc_microunits=acc,
        evidence={
            "github_comment_job": job_id,
            "receipts": [task["receipt"] for task in completed],
            "verification_scope": spec.get("verification_scope", "operator-authorized receipt-backed work"),
        },
    )
    return {"recorded": True, "event_id": event["event_id"], "balances": ledger.balances()}

def main():
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise SystemExit("GITHUB_EVENT_PATH is required")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    job, job_id, issue_number = parse_comment_job(event)
    execute(job, job_id)
    summary = json.loads((ROOT / "reports" / "runtime-latest.json").read_text(encoding="utf-8"))
    economics = account(job, summary, job_id)
    wrapper = {
        "job_id": job_id,
        "issue_number": issue_number,
        "generated_at": generated_at(),
        "job_result": summary,
        "economics": economics,
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(wrapper, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
