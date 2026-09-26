"""Read-only multi-asset exit/fee planning. Does not convert, sign, or hold money.

Quotes must be independently checked by an operator-approved adapter. Returning
'plan_only' is never a claim that a swap was executed or that USD was deposited.
"""
from __future__ import annotations
from dataclasses import dataclass

BASE_USDC = 'eip155:8453/erc20:0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
USD = 'fiat:USD'
LIGHTNING_BTC = 'lightning:bitcoin/satoshi'
INTERNAL_ACC = 'internal:ACC'


@dataclass(frozen=True)
class ExitQuote:
    quote_id: str
    provider_id: str
    input_asset: str
    output_asset: str
    amount_in_atomic: int
    minimum_out_atomic: int
    observed_at: int
    expires_at: int
    evidence_ref: str
    fee_in_output_atomic: int = 0
    output_is_net: bool = False
    source_environment: str = 'unverified'


def _uint(value):
    if type(value) is not int or value < 0:
        raise ValueError('amount_or_time_must_be_nonnegative_integer')
    return value


def choose_exit(asset, amount_atomic, quotes, *, target_asset, now,
                approved_provider_ids, verify_quote, conversion_buffer_seconds=30):
    if not isinstance(asset, str) or not asset or not isinstance(target_asset, str):
        raise ValueError('asset_identity_required')
    for value in (amount_atomic, now, conversion_buffer_seconds):
        _uint(value)
    if asset.startswith(('internal:', 'testnet:')):
        return {'status': 'not_cash', 'reason': 'internal_or_test_units', 'execution': 'none'}
    if target_asset not in {BASE_USDC, USD}:
        raise ValueError('unsupported_treasury_target')
    if asset == target_asset:
        return {'status': 'no_conversion_required', 'asset': asset,
                'amount_atomic': amount_atomic, 'execution': 'none',
                'receipt_verified': False}
    valid, rejected = [], []
    for quote in quotes:
        try:
            if not isinstance(quote, ExitQuote):
                raise ValueError('invalid_quote_type')
            for value in (quote.amount_in_atomic, quote.minimum_out_atomic, quote.fee_in_output_atomic,
                          quote.observed_at, quote.expires_at):
                _uint(value)
            if not quote.quote_id or not quote.evidence_ref:
                raise ValueError('missing_quote_evidence')
            if quote.provider_id not in approved_provider_ids:
                raise ValueError('unapproved_provider')
            if quote.input_asset != asset or quote.output_asset != target_asset or quote.amount_in_atomic != amount_atomic:
                raise ValueError('asset_network_or_amount_mismatch')
            if quote.source_environment != 'mainnet' or quote.observed_at > now or now-quote.observed_at > 300:
                raise ValueError('non_mainnet_or_stale')
            if quote.expires_at <= now+conversion_buffer_seconds:
                raise ValueError('expires_before_safe_execution')
            if quote.output_is_net is not True:
                raise ValueError('unknown_total_fees')
            if quote.minimum_out_atomic <= 0:
                raise ValueError('no_positive_proceeds')
            if not callable(verify_quote) or verify_quote(quote) is not True:
                raise ValueError('quote_not_independently_checked')
            valid.append(quote)
        except (ValueError, TypeError) as error:
            rejected.append(str(error))
    if not valid:
        return {'status': 'hold_unpriced', 'asset': asset, 'amount_atomic': amount_atomic,
                'reason': 'no_current_verified_exit', 'rejected': rejected, 'execution': 'none'}
    best = sorted(valid, key=lambda q: (-q.minimum_out_atomic, -q.expires_at, q.quote_id))[0]
    return {'status': 'plan_only', 'quote_id': best.quote_id, 'target_asset': target_asset,
            'minimum_out_atomic': best.minimum_out_atomic, 'expires_at': best.expires_at,
            'execution': 'none', 'funds_received': False}


def batch_decision(amount_atomic, fee_atomic, *, max_fee_bps=1000, payout_minimum_atomic=1):
    for value in (amount_atomic, fee_atomic, max_fee_bps, payout_minimum_atomic):
        _uint(value)
    if not 0 < max_fee_bps <= 10000:
        raise ValueError('invalid_fee_budget')
    minimum = max(payout_minimum_atomic, fee_atomic+1,
                  (fee_atomic*10000 + max_fee_bps-1)//max_fee_bps)
    return {'status': 'plan_only' if amount_atomic >= minimum else 'accumulate',
            'minimum_batch_atomic': minimum, 'execution': 'none'}


def unit_economics(price_atomic, *, fulfillment_atomic, validation_atomic, acquisition_atomic,
                   payment_fee_atomic, conversion_fee_atomic, reserve_atomic):
    parts = (price_atomic, fulfillment_atomic, validation_atomic, acquisition_atomic,
             payment_fee_atomic, conversion_fee_atomic, reserve_atomic)
    if any(value is None for value in parts):
        return {'status': 'unknown_costs', 'net_atomic': None}
    for value in parts:
        _uint(value)
    net = price_atomic-sum(parts[1:])
    return {'status': 'candidate' if net > 0 else 'reject_margin', 'net_atomic': net,
            'basis': 'same_asset_atomic_units', 'revenue_received': False}
