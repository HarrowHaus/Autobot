import json
import unittest
from beacon_rip302 import RIP302, opportunity_ping

class Resp:
    def __init__(self, obj):
        self.buf = json.dumps(obj).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        return self.buf

class Tests(unittest.TestCase):
    def test_browse_encodes_filters(self):
        seen = []
        def opener(req, timeout):
            seen.append(req.full_url)
            return Resp({"jobs": [{"job_id": "j1"}]})
        c = RIP302("https://node.test", opener=opener)
        self.assertEqual(c.browse_jobs(category="writing")["jobs"][0]["job_id"], "j1")
        self.assertIn("status=open", seen[0])
        self.assertIn("category=writing", seen[0])

    def test_claim_uses_worker_wallet(self):
        bodies = []
        def opener(req, timeout):
            bodies.append(json.loads(req.data))
            return Resp({"ok": True})
        RIP302("https://node.test", wallet="worker", opener=opener).claim_job("job/1")
        self.assertEqual(bodies[0]["worker_wallet"], "worker")

    def test_opportunity_ping(self):
        p = opportunity_ping({"job_id":"j7","title":"Translate docs","reward_rtc":8,"category":"translation"})
        self.assertEqual(p["kind"], "bounty")
        self.assertEqual(p["meta"]["job_id"], "j7")
        self.assertIn("8 RTC", p["text"])

    def test_missing_wallet_fails_before_network(self):
        c = RIP302("https://node.test", opener=lambda *a: (_ for _ in ()).throw(RuntimeError("network")))
        with self.assertRaises(ValueError):
            c.claim_job("j1")

if __name__ == "__main__":
    unittest.main()
