import io
import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grazer_rip302 import GrazerRIP302


class ContractEdges(unittest.TestCase):
    def client(self, obj):
        self.requests = []
        def opener(req, timeout):
            self.requests.append(req)
            return io.BytesIO(json.dumps(obj).encode())
        return GrazerRIP302("http://127.0.0.1:9999", opener=opener)

    def test_list_envelope(self):
        rows = [{"job_id": "a", "reward_rtc": 1}]
        self.assertEqual(self.client(rows).browse(), rows)

    def test_empty_list(self):
        self.assertEqual(self.client([]).browse(), [])

    def test_distinct_equal_rewards(self):
        rows = [{"job_id": k, "reward_rtc": 15} for k in ("a", "b", "c", "d")]
        self.assertEqual(self.client({"jobs": rows}).browse(min_reward=15), rows)

    def test_get_parameters(self):
        self.client({"jobs": []}).browse(category="writing", min_reward=2, limit=2, offset=4)
        req = self.requests[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(parse_qs(urlsplit(req.full_url).query), {"status": ["open"], "category": ["writing"], "min_reward": ["2.0"], "limit": ["2"], "offset": ["4"]})
        self.assertIsNone(req.data)

    def test_local_provenance(self):
        row = {"job_id": "local/one", "reward_rtc": 1}
        result = GrazerRIP302.to_opportunity(row, node="http://127.0.0.1:9999")
        self.assertEqual(result["url"], "http://127.0.0.1:9999/agent/jobs/local%2Fone")
        self.assertEqual(result["raw"], row)

    def test_missing_id_no_url(self):
        self.assertIsNone(GrazerRIP302.to_opportunity({})["url"])

    def test_bad_envelopes_remain_errors(self):
        for obj in ({}, None, 1, "bad", {"jobs": None}, {"jobs": {}}, {"jobs": [None]}, {"jobs": [], "ok": False}, {"jobs": [], "error": "down"}):
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                self.client(obj).browse()

    def test_bad_minimum_no_request(self):
        for value in (-1, float("nan"), float("inf"), True, "bad"):
            c = self.client({"jobs": []})
            with self.subTest(value=value), self.assertRaises(ValueError):
                c.browse(min_reward=value)
            self.assertEqual(self.requests, [])

    def test_bad_paging_no_request(self):
        for kwargs in ({"limit": 0}, {"limit": 101}, {"limit": True}, {"limit": 1.5}, {"offset": -1}, {"offset": True}):
            c = self.client({"jobs": []})
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                c.browse(**kwargs)
            self.assertEqual(self.requests, [])

    def test_bad_reward_not_silent(self):
        for value in (True, -1, "bad", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client({"jobs": [{"reward_rtc": value}]}).browse(min_reward=1)

    def test_invalid_json_surfaces(self):
        c = GrazerRIP302(opener=lambda *a, **k: io.BytesIO(b"not json"))
        with self.assertRaises(ValueError):
            c.browse()

    def test_empty_body_surfaces(self):
        c = GrazerRIP302(opener=lambda *a, **k: io.BytesIO(b""))
        with self.assertRaises(ValueError):
            c.browse()

    def test_network_failure_surfaces(self):
        def fail(*args, **kwargs):
            raise TimeoutError("fixture timeout")
        with self.assertRaises(TimeoutError):
            GrazerRIP302(opener=fail).browse()


if __name__ == "__main__":
    unittest.main()
