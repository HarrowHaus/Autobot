"""Read-only RustChain RIP-302 opportunity source for Grazer-style discovery loops."""
from __future__ import annotations
import json
import urllib.parse
import urllib.request

class GrazerRIP302:
    def __init__(self, node="https://50.28.86.131", opener=None, timeout=15):
        self.node = node.rstrip("/")
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def browse(self, status="open", category=None, min_reward=None):
        q = {"status": status}
        if category:
            q["category"] = category
        req = urllib.request.Request(
            self.node + "/agent/jobs?" + urllib.parse.urlencode(q),
            headers={"Accept": "application/json"},
            method="GET",
        )
        with self.opener(req, timeout=self.timeout) as resp:
            raw = resp.read()
            data = json.loads(raw) if raw else {}
        jobs = data.get("jobs", data if isinstance(data, list) else [])
        if min_reward is not None:
            jobs = [j for j in jobs if float(j.get("reward_rtc", 0) or 0) >= float(min_reward)]
        return jobs

    @staticmethod
    def to_opportunity(job):
        jid = job.get("job_id")
        return {
            "source": "rustchain-rip302",
            "id": jid,
            "title": job.get("title"),
            "category": job.get("category"),
            "reward_rtc": job.get("reward_rtc"),
            "url": f"https://rustchain.org/agent/jobs/{jid}" if jid else None,
            "raw": job,
        }
