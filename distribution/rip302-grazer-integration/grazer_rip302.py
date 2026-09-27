"""GET-only RIP-302 discovery client; no signing, claims, or payments."""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request


class GrazerRIP302:
    def __init__(self, node="https://50.28.86.131", opener=None, timeout=15):
        self.node = node.rstrip("/")
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def browse(self, status="open", category=None, min_reward=None, *, limit=50, offset=0):
        """Return one explicit page. Errors remain errors, not empty demand."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        minimum = None
        if min_reward is not None:
            if isinstance(min_reward, bool):
                raise ValueError("min_reward must be a finite non-negative number")
            minimum = float(min_reward)
            if not math.isfinite(minimum) or minimum < 0:
                raise ValueError("min_reward must be a finite non-negative number")
        q = {"status": status, "limit": limit, "offset": offset}
        if category:
            q["category"] = category
        if minimum is not None:
            q["min_reward"] = minimum
        req = urllib.request.Request(
            self.node + "/agent/jobs?" + urllib.parse.urlencode(q),
            headers={"Accept": "application/json"},
            method="GET",
        )
        with self.opener(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())
        if isinstance(data, list):
            jobs = data
        elif isinstance(data, dict):
            if data.get("ok") is False or "error" in data:
                raise ValueError("RIP-302 returned an error response")
            jobs = data.get("jobs")
        else:
            raise ValueError("RIP-302 response must be a job array or an object containing jobs")
        if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
            raise ValueError("RIP-302 jobs must be an array of objects")
        if minimum is not None:
            selected = []
            for job in jobs:
                raw = job.get("reward_rtc")
                if isinstance(raw, bool):
                    raise ValueError("job reward must be a finite non-negative number")
                reward = float(raw)
                if not math.isfinite(reward) or reward < 0:
                    raise ValueError("job reward must be a finite non-negative number")
                if reward >= minimum:
                    selected.append(job)
            jobs = selected
        return jobs

    @staticmethod
    def to_opportunity(job, *, node="https://rustchain.org"):
        jid = job.get("job_id")
        return {
            "source": "rustchain-rip302",
            "id": jid,
            "title": job.get("title"),
            "category": job.get("category"),
            "reward_rtc": job.get("reward_rtc"),
            "url": node.rstrip("/") + "/agent/jobs/" + urllib.parse.quote(str(jid), safe="") if jid else None,
            "raw": job,
        }
