import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import unittest
from grazer_rip302 import GrazerRIP302

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
    def test_browse_and_min_reward(self):
        def opener(req, timeout):
            return Resp({"jobs":[
                {"job_id":"a","title":"A","reward_rtc":2},
                {"job_id":"b","title":"B","reward_rtc":10}
            ]})
        jobs = GrazerRIP302("https://node.test", opener=opener).browse(min_reward=5)
        self.assertEqual([x["job_id"] for x in jobs], ["b"])

    def test_normalize(self):
        x = GrazerRIP302.to_opportunity({"job_id":"j1","title":"Write docs","category":"writing","reward_rtc":7})
        self.assertEqual(x["source"], "rustchain-rip302")
        self.assertEqual(x["reward_rtc"], 7)
        self.assertIn("j1", x["url"])

if __name__ == "__main__":
    unittest.main()
