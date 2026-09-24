import json, os, unittest
from unittest.mock import patch
from swarmbrain.github_bridge import parse_comment_job, make_reply

class GitHubBridgeTests(unittest.TestCase):
    def event(self, login="KungFury87", body='SwarmBrain job: {"mode":"route","query":"verification"}'):
        return {
            "repository": {"owner": {"login": "HarrowHaus"}},
            "issue": {"number": 19},
            "comment": {"id": 5800000000, "body": body, "user": {"login": login}},
        }

    @patch.dict(os.environ, {"SWARMBRAIN_TRUSTED_COMMENTERS":"KungFury87"})
    def test_trusted_comment_dispatches(self):
        job, job_id, issue = parse_comment_job(self.event())
        self.assertEqual(job["mode"], "route")
        self.assertEqual(job_id, "comment-5800000000")
        self.assertEqual(issue, 19)

    @patch.dict(os.environ, {"SWARMBRAIN_TRUSTED_COMMENTERS":"KungFury87"})
    def test_untrusted_comment_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_comment_job(self.event(login="random-user"))

    @patch.dict(os.environ, {"SWARMBRAIN_TRUSTED_COMMENTERS":"KungFury87"})
    def test_prefix_is_required(self):
        with self.assertRaises(ValueError):
            parse_comment_job(self.event(body='{"mode":"route"}'))

    def test_reply_contains_persisted_result(self):
        text = make_reply({"job_id":"x","generated_at":"now","job_result":{"mode":"route","routes":[]}})
        self.assertIn("SwarmBrain automatic result", text)
        self.assertIn('"routes": []', text)

    def test_compact_route_reply_does_not_dump_runtime_tasks(self):
        summary = {
            "job_id":"comment-1",
            "generated_at":"2026-09-24T00:00:00Z",
            "job_result":{
                "mode":"route",
                "registered_peers":19,
                "connected_peers":13,
                "routes":[{"peer":"p1","activation":0.8}],
                "tasks":[{"id":"should-not-appear","response_excerpt":"huge"}],
            },
            "economics":{"recorded":False,"reason":"none"},
        }
        reply = make_reply(summary)
        self.assertIn('"peer": "p1"', reply)
        self.assertIn('"registered_peers": 19', reply)
        self.assertNotIn("should-not-appear", reply)
        self.assertLess(len(reply), 6000)

if __name__ == "__main__":
    unittest.main()
