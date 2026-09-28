import unittest
from swarmbrain.opportunity_factory import rank, choose, manufacture

class OpportunityFactoryTests(unittest.TestCase):
    def test_repeated_signal_becomes_product(self):
        s=[{"source":"hackernews","title":"MCP server commerce","points":20,"comments":5,"url":str(i)} for i in range(3)]
        r=rank(s); c=choose(r); self.assertIsNotNone(c)
        p=manufacture(c,r); self.assertEqual(p["status"],"publishable")
        self.assertEqual(p["price_atomic_usdc"],"10000")
    def test_weak_signal_abstains(self):
        r=rank([{"source":"hackernews","title":"isolated novelty","points":1,"comments":0,"url":"x"}])
        self.assertIsNone(choose(r))
        self.assertEqual(manufacture(None,r)["status"],"abstain")
if __name__=="__main__": unittest.main()
