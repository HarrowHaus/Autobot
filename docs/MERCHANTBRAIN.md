# MerchantBrain

MerchantBrain extends SwarmBrain with an evidence-driven autonomous commercial loop.

## Loop

1. Observe public demand signals.
2. Rank repeated signals.
3. Abstain when evidence is weak.
4. Manufacture a zero-inventory digital research asset from the evidence.
5. Generate a storefront.
6. Publish experiment artifacts.
7. Use the existing x402/USDC merchant infrastructure for paid machine delivery.
8. Judge success only from verified settlement events.

The first product class is intentionally constrained to public-data signal packs. This proves discovery -> autonomous choice -> manufacture -> storefront before executable product generation is enabled.

## Run locally

Python 3.10+; no Python dependencies:

    python -m swarmbrain.opportunity_factory

Outputs:

- reports/merchantbrain/signals.json
- reports/merchantbrain/product.json
- merchant-site/index.html
- merchant-site/product.json

Serve the generated site:

    python -m http.server 8000 --directory merchant-site

Then open http://localhost:8000.

## Run in GitHub

Actions -> MerchantBrain opportunity factory -> Run workflow.

The scheduled job runs every six hours. It stores the evidence and generated product as artifacts and commits the latest experiment state on the MerchantBrain branch.

## Existing infrastructure reused

MerchantBrain does not replace SwarmBrain's commerce stack. The repository already contains the official x402/Hono Cloudflare merchant, Bazaar discovery, BasedAgents paid-task scanning/earning, direct-USDC settlement, Clawlancer integration, and the settlement-backed commercial controller.

## Truth rule

Traffic, asking prices, advertised bounties, leads, and generated products are not revenue. Only externally verified settlements count.
