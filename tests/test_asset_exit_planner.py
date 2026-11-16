import unittest
from dataclasses import replace
from swarmbrain.asset_exit_planner import (ExitQuote, choose_exit, batch_decision, unit_economics,
                                           BASE_USDC, USD, LIGHTNING_BTC, INTERNAL_ACC)

NOW=1000
ALT='eip155:137/erc20:EXAMPLE_TEST_ASSET_NOT_LIVE'
# All quotes/verifiers below are fixtures; no exchange is contacted.
def quote(**kw):
    q=ExitQuote('fixture-quote','fixture-provider',ALT,BASE_USDC,100,950000,990,1100,'fixture:evidence',output_is_net=True,source_environment='mainnet')
    return replace(q,**kw)

def plan(qs, asset=ALT, amount=100, **kw):
    args=dict(target_asset=BASE_USDC,now=NOW,approved_provider_ids={'fixture-provider'},verify_quote=lambda q:True)
    args.update(kw)
    return choose_exit(asset,amount,qs,**args)

class ExitPlannerTests(unittest.TestCase):
    def test_unknown_exit_holds_unpriced(self):self.assertEqual(plan([])['status'],'hold_unpriced')
    def test_internal_units_never_cash(self):self.assertEqual(plan([quote(input_asset=INTERNAL_ACC)],asset=INTERNAL_ACC)['status'],'not_cash')
    def test_testnet_never_cash(self):self.assertEqual(plan([],asset='testnet:USDC')['status'],'not_cash')
    def test_direct_base_still_requires_receipt(self):
        r=plan([],asset=BASE_USDC);self.assertEqual(r['status'],'no_conversion_required');self.assertFalse(r['receipt_verified'])
    def test_valid_quote_is_only_a_plan(self):
        r=plan([quote()]);self.assertEqual(r['status'],'plan_only');self.assertFalse(r['funds_received']);self.assertEqual(r['execution'],'none')
    def test_rank_net_not_gross_or_name(self):
        r=plan([quote(quote_id='lower',minimum_out_atomic=900000),quote(quote_id='higher',minimum_out_atomic=950000)]);self.assertEqual(r['quote_id'],'higher')
    def test_expired_quote_rejected(self):self.assertEqual(plan([quote(expires_at=1000)])['status'],'hold_unpriced')
    def test_buffer_rejects_near_expiry(self):self.assertEqual(plan([quote(expires_at=1030)])['status'],'hold_unpriced')
    def test_wrong_network_same_symbol_not_interchangeable(self):
        r=plan([quote(input_asset='eip155:1/erc20:EXAMPLE_TEST_ASSET_NOT_LIVE')]);self.assertEqual(r['status'],'hold_unpriced')
    def test_wrong_amount_rejected(self):self.assertEqual(plan([quote(amount_in_atomic=99)])['status'],'hold_unpriced')
    def test_no_verified_quote_from_json_flag(self):
        for verify in (None, lambda q:False, lambda q:{'confirmed':True}):
            self.assertEqual(plan([quote()],verify_quote=verify)['status'],'hold_unpriced')
    def test_unapproved_provider_rejected(self):self.assertEqual(plan([quote(provider_id='other')])['status'],'hold_unpriced')
    def test_unknown_fees_rejected(self):self.assertEqual(plan([quote(output_is_net=False)])['status'],'hold_unpriced')
    def test_wrong_environment_rejected(self):self.assertEqual(plan([quote(source_environment='testnet')])['status'],'hold_unpriced')
    def test_future_or_stale_observation_rejected(self):
        for t in (1001,699):self.assertEqual(plan([quote(observed_at=t)])['status'],'hold_unpriced')
    def test_no_synthetic_redeemability(self):
        for q in (quote(evidence_ref=''), quote(minimum_out_atomic=0)):
            self.assertEqual(plan([q])['status'],'hold_unpriced')
    def test_atomic_numbers_no_float_or_bool(self):
        for n in (1.5,True,-1):self.assertEqual(plan([quote(amount_in_atomic=n)])['status'],'hold_unpriced')
    def test_fiat_target_is_separate_quote(self):
        r=plan([quote()],target_asset=USD);self.assertEqual(r['status'],'hold_unpriced')
        r=plan([quote(output_asset=USD,minimum_out_atomic=95)],target_asset=USD);self.assertEqual(r['minimum_out_atomic'],95)
    def test_lightning_needs_exit_not_evm_address(self):self.assertEqual(plan([],asset=LIGHTNING_BTC)['status'],'hold_unpriced')
    def test_fee_floor_batching(self):
        r=batch_decision(5,1,max_fee_bps=1000);self.assertEqual(r['status'],'accumulate');self.assertEqual(r['minimum_batch_atomic'],10)
        self.assertEqual(batch_decision(10,1,max_fee_bps=1000)['status'],'plan_only')
    def test_payout_threshold_matters(self):self.assertEqual(batch_decision(100,1,payout_minimum_atomic=500)['minimum_batch_atomic'],500)
    def test_zero_and_invalid_fee_budget(self):
        self.assertEqual(batch_decision(0,0)['status'],'accumulate')
        for n in (0,10001):
            with self.assertRaises(ValueError):batch_decision(1,0,max_fee_bps=n)
    def test_economics_subtract_every_cost(self):
        r=unit_economics(100,fulfillment_atomic=20,validation_atomic=10,acquisition_atomic=5,payment_fee_atomic=1,conversion_fee_atomic=2,reserve_atomic=2);self.assertEqual(r['net_atomic'],60)
    def test_unknown_cost_is_not_free(self):
        r=unit_economics(100,fulfillment_atomic=None,validation_atomic=0,acquisition_atomic=0,payment_fee_atomic=0,conversion_fee_atomic=0,reserve_atomic=0);self.assertEqual(r['status'],'unknown_costs')
    def test_negative_margin_rejected(self):
        r=unit_economics(1,fulfillment_atomic=2,validation_atomic=0,acquisition_atomic=0,payment_fee_atomic=0,conversion_fee_atomic=0,reserve_atomic=0);self.assertEqual(r['status'],'reject_margin')

if __name__=='__main__':unittest.main()
