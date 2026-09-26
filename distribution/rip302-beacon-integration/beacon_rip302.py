"""Beacon-compatible RIP-302 Agent Economy adapter.

Stdlib-only transport so the core adapter can run wherever beacon-skill runs.
Tests are offline and never move RTC.
"""
from __future__ import annotations
import json
import urllib.parse
import urllib.request
import urllib.error

DEFAULT_NODE = "https://50.28.86.131"

class AgentEconomyError(RuntimeError):
    def __init__(self, message, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body

class RIP302:
    def __init__(self, node=DEFAULT_NODE, wallet=None, opener=None, timeout=15):
        self.node = node.rstrip("/")
        self.wallet = wallet
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def _wallet(self, wallet=None):
        value = wallet or self.wallet
        if not value:
            raise ValueError("wallet is required")
        return value

    def _request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.node + path, data=data, headers=headers, method=method)
        try:
            with self.opener(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                body = json.loads(raw) if raw else None
            except Exception:
                body = raw.decode(errors="replace")
            msg = body.get("error", f"HTTP {e.code}") if isinstance(body, dict) else f"HTTP {e.code}"
            raise AgentEconomyError(msg, e.code, body) from e
        except urllib.error.URLError as e:
            raise AgentEconomyError(f"Network error: {e.reason}") from e

    def browse_jobs(self, status="open", category=None):
        q = {"status": status}
        if category:
            q["category"] = category
        return self._request("GET", "/agent/jobs?" + urllib.parse.urlencode(q))

    def post_job(self, title, category, reward_rtc, wallet=None, **extra):
        return self._request("POST", "/agent/jobs", {
            "poster_wallet": self._wallet(wallet),
            "title": title,
            "category": category,
            "reward_rtc": reward_rtc,
            **extra,
        })

    def claim_job(self, job_id, wallet=None):
        return self._request("POST", f"/agent/jobs/{urllib.parse.quote(job_id, safe='')}/claim", {
            "worker_wallet": self._wallet(wallet)
        })

    def deliver_job(self, job_id, deliverable_url, result_summary, wallet=None):
        return self._request("POST", f"/agent/jobs/{urllib.parse.quote(job_id, safe='')}/deliver", {
            "worker_wallet": self._wallet(wallet),
            "deliverable_url": deliverable_url,
            "result_summary": result_summary,
        })

def opportunity_ping(job: dict) -> dict:
    return {
        "kind": "bounty",
        "text": f"{job.get('title', 'Untitled job')} — {job.get('reward_rtc', '?')} RTC",
        "meta": {
            "source": "rustchain-rip302",
            "job_id": job.get("job_id"),
            "category": job.get("category"),
            "reward_rtc": job.get("reward_rtc"),
        },
    }
