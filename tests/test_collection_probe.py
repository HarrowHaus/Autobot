import unittest
from swarmbrain.collection_probe import summarize
class ProbeTests(unittest.TestCase):
    def task(self,bounty):return {'id':'fixture','bounty':bounty}
    def test_documented_amount_atomic(self):
        for key in ('amount','amount_atomic'):
            r=summarize([self.task({key:'5000000','token':'USDC','network':'eip155:8453'})])
            self.assertEqual(r['tasks'][0]['budget_usdc'],'5')
            self.assertEqual(r['paid_budget_count'],1)
    def test_wrong_token_or_network_not_usdc_budget(self):
        for b in ({'amount':'5','token':'ETH','network':'eip155:8453'},{'amount':'5','token':'USDC','network':'eip155:84532'}):
            self.assertEqual(summarize([self.task(b)])['paid_budget_count'],0)
    def test_schema_errors_not_empty_market(self):
        with self.assertRaises(ValueError):summarize({'error':'failed'})
    def test_no_claim_or_revenue_from_budget(self):
        r=summarize([self.task({'amount':'10000','token':'USDC','network':'eip155:8453'})])
        self.assertEqual((r['claims_made'],r['payments_collected']),(0,0))
if __name__=='__main__':unittest.main()
