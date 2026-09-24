#!/usr/bin/env python3
"""Trusted GitHub issue-comment bridge for finite SwarmBrain jobs."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from urllib import request

PREFIX = "SwarmBrain job:"
MAX_JOB_BYTES = 12_000

def trusted_logins(event):
    owner = event["repository"]["owner"]["login"]
    configured = os.environ.get("SWARMBRAIN_TRUSTED_COMMENTERS", "")
    return {owner, *(x.strip() for x in configured.split(",") if x.strip())}

def parse_comment_job(event):
    comment = event.get("comment") or {}
    issue = event.get("issue") or {}
    login = (comment.get("user") or {}).get("login")
    body = str(comment.get("body") or "")
    if login not in trusted_logins(event):
        raise ValueError("Comment author is not trusted to dispatch SwarmBrain work")
    if not body.startswith(PREFIX):
        raise ValueError("Trusted task comments must start exactly with 'SwarmBrain job:'")
    raw = body[len(PREFIX):].strip()
    if not raw or len(raw.encode("utf-8")) > MAX_JOB_BYTES:
        raise ValueError("Task JSON must be between 1 byte and 12 KB")
    job = json.loads(raw)
    if not isinstance(job, dict):
        raise ValueError("Task body must decode to a JSON object")
    return job, "comment-" + str(comment["id"]), int(issue["number"])

def compact_result(summary):
    result = summary.get("job_result") or {}
    mode = result.get("mode")
    compact = {"mode": mode}
    if mode == "route":
        compact["routes"] = result.get("routes") or []
        compact["registered_peers"] = result.get("registered_peers")
        compact["connected_peers"] = result.get("connected_peers")
    elif mode == "request":
        run_key = result.get("run_key")
        compact["run_key"] = run_key
        tasks = result.get("tasks") or []
        compact["task"] = next((t for t in reversed(tasks) if t.get("id") == run_key), None)
        compact["errors"] = result.get("errors") or []
    else:
        compact.update({
            "registered_peers": result.get("registered_peers"),
            "connected_peers": result.get("connected_peers"),
            "results_received": result.get("results_received"),
            "verified_task_results": result.get("verified_task_results"),
            "errors": result.get("errors") or [],
        })
    compact["economics"] = summary.get("economics") or {"recorded": False}
    return compact

def make_reply(summary):
    result = compact_result(summary)
    body = [
        "SwarmBrain automatic result",
        "",
        f"Job ID: `{summary.get('job_id','unknown')}`",
        f"Generated: {summary.get('generated_at','unknown')}",
        "",
        "```json",
        json.dumps(result, indent=2, ensure_ascii=False)[:6000],
        "```",
        "",
        "Full receipts remain persisted in the repository. This result does not claim peer ownership or model identity."
    ]
    return "\n".join(body)

def post_latest_result():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue_number = int(event["issue"]["number"])
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    result_path = Path(os.environ.get("SWARMBRAIN_RESULT_PATH", "reports/comment-job-latest.json"))
    if not result_path.exists():
        result_path = Path("reports/runtime-latest.json")
    summary = json.loads(result_path.read_text(encoding="utf-8"))
    payload = json.dumps({"body": make_reply(summary)}).encode("utf-8")
    req = request.Request(
        f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SwarmBrain-Harrow"
        },
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"GitHub comment post failed: {response.status}")

def main():
    if len(sys.argv) != 2 or sys.argv[1] != "post":
        raise SystemExit("Usage: python swarmbrain/github_bridge.py post")
    post_latest_result()

if __name__ == "__main__":
    main()
