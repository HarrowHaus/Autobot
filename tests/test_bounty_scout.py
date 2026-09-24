import unittest
from swarmbrain import bounty_scout

class ScoutTests(unittest.TestCase):
    def test_amount_and_match(self):
        t={"title":"Verify research code","bounty":{"amount_atomic":"2500000"},"claimable":True}
        self.assertEqual(bounty_scout.amount_usdc(t),2.5)
        self.assertIn("verification",bounty_scout.task_caps(t))
        self.assertIn("research",bounty_scout.task_caps(t))
        self.assertTrue(bounty_scout.funded(t))

    def test_unfunded_is_not_funded(self):
        self.assertFalse(bounty_scout.funded({"payment_status":"pending","claimable":False}))

if __name__=="__main__":
    unittest.main()
