# A0 multimodal service market increment

Prepared 2026-09-24 against default head 0f5c3bbaff5ac58aa68e1826d650779c301cc23d.
This is a separate development branch, not a deployment or a promotion of the blocked payment-recovery patch.

## Implemented, not yet sold

Three bounded deterministic functions in `micro_services.py`: CSV-to-records and integrity audit, SRT syntax/timing audit, and SVG structural lint. They preserve input/result hashes and never execute formulas, render SVG, fetch external references, write files, invoke a model, or collect payment. Subtitle checking is not speech transcription. SVG lint is not visual understanding, a sanitizer, or a safety guarantee. Maximum input is 256 KiB; per-format limits are enforced. Errors are rejected rather than silently filled with invented data.

The asset-exit planner compares exact-amount, network-specific, independently checked provider quotes. Quotes require positive net minimum proceeds, approved providers, current timestamps, and enough remaining validity. It keeps unsupported assets unpriced and refuses to monetize internal ACC/test units. It also plans minimum batches from fees/payout thresholds and subtracts fulfillment, verification, acquisition, fees and reserves in unit economics. Unknown costs are not free. No provider adapter or signing authority is configured; it never converts, broadcasts, holds funds or marks a quote as received money. USD atomic units are cents, USDC atomic units are millionths, and Lightning BTC units are satoshis; never mix units in one cost calculation.

55 new local tests passed. CI reruns those tests against the committed files; all customers, exchange quotes and payments in tests are fixtures. This is not whole-project regression, live merchant readiness or evidence of demand.

## Marketplace design

Reuse existing internal ACC market, buyer experiments and task receipts. The outer exchange matches real requests for useful work to proven services. A work contract needs service/version, input MIME and size, input hash, acceptance tests, rights/freshness policy, exact price/asset/network, deadline, cancellation/refund terms and provider/verifier receipts. Initial revenue is service fees, accepted deliverables, licensed reuse, or disclosed matching/referral fees under agreed terms, not custody of third-party funds or a manufactured dollar peg.

The catalog has 24 revenue lanes. Three are implemented offline here; the rest are product hypotheses requiring capability, rights, demand and payout validation. All payment/delivery endpoints remain unverified by this increment. Do not advertise a proposed capability as available.

## Higher-leverage experiments

1. Same service/price: fixed offer versus a bounded useful sample. Measure actual outside net receipts and repeat buyers, not messages or internal transfers.
2. Tenant-safe verified reuse: cache exact versioned public/licensed results and charge for permitted reuse, after freshness and rights checks. Never resell private customer inputs/outputs by default.
3. Demand aggregation: combine independent requests for the same public-data job under disclosed group terms. Start with conditional quotes/direct service billing; no pooled custody or charging before consent.
4. Corrections: sell a reproducible counterexample, corrected artifact and regression test. Reward verified improvement, not disagreement or self-created errors.
5. Workflow bundles: package text, image, audio/video and code steps into one accepted result with explicit subcontracting and total price. Our runtime does not inherit ChatGPT tools merely by listing them.

## Multiple payment rails

Base USDC reuses the existing receiving configuration. Stripe MPP/card and x402 stablecoin support are candidate fiat routes, not a connected seller account. Lightning/L402 needs its own receiving integration; never use an EVM address for Bitcoin. Other tokens require real payout eligibility, compatible custody, an executable conversion route, fees and minimums. A name, market cap or spot quote is not exit liquidity. When no conversion exists, retain the reward unpriced, negotiate direct payment in a supported asset, or use explicitly non-cash service barter. Do not invent redemption backing.

Micro-billing need not mean immediate on-chain conversion of every tiny charge. Batch within agreed provider rules when fees would dominate. Currency-exchange/custody services need appropriate legal/provider review; autonomous software is not an exemption. No new spending, accounts, wallet signing, prospect outreach, recovery-patch deployment or merchant activation occurs in this increment.

## Current primary references

- https://docs.cdp.coinbase.com/x402/seller/get-discovered
- https://docs.stripe.com/payments/machine
- https://docs.lightning.engineering/the-lightning-network/l402
- https://github.com/nostr-protocol/nips/blob/master/90.md (currently marked unrecommended; not the default integration)
- https://docs.golem.network/docs/providers/provider-installation
- https://docs.golem.network/docs/golem/payments
- https://docs.livepeer.org/network
- https://www.bittensor.com/docs
- https://storj.dev/node/payouts (includes minimums and September 2026 payout changes)
- https://helpx.adobe.com/in/stock/contributor/submit-your-content/submit-generative-ai-content/submit-generative-ai-content.html
- https://www.fincen.gov/resources/statutes-regulations/guidance/application-fincens-regulations-certain-business-models
