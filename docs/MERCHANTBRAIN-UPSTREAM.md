# MerchantBrain external factory composition

MerchantBrain composes proven public agent-business patterns instead of pretending Felix or Kelly expose production source that they do not.

## Runtime substrate
- OpenClaw: optional persistent agent runtime. Felix and Kelly both use OpenClaw patterns.
- SwarmBrain: existing durable peer graph, task routing, receipts, and settlement truth.

## Product factory
- alexar76/aicom (MIT): full discovery -> analyst -> PM -> architecture -> build -> QA -> security -> DevOps -> marketing -> sales -> evolution reference. Prefer running it as an external factory adapter instead of copying its large codebase.
- Kelly public reconstruction: architecture evidence only. Adopt project-lead hierarchy, deterministic scripts, adversarial "angry mob" review, resubmission/evolution loops.
- Felix public operating pattern: heartbeat/cron, three-layer memory, delegated coding sessions, remove recurring human bottlenecks, trust ladder.

## Revenue / commerce
- Existing Autobot official x402/Hono seller is canonical.
- CashClaw: optional OpenClaw skill-pack/marketplace adapter. Do not count its advertised earnings as ours.
- AWS sample-agentic-serverless-payments: reference for scoped autonomous x402 buyer sessions; not required for zero-cost seller operation.

## Composition rule
Do not vendor entire upstream repositories. Pin upstream URLs/commits and invoke adapters or install packages when needed. Copy source only where license permits and an adapter cannot provide the capability.

## Factory interface
Every external maker must accept an Opportunity Contract JSON and return a Build Receipt JSON.

Opportunity Contract:
```json
{"id":"...","problem":"...","buyer":"...","evidence":[],"product_type":"web|api|mcp|dataset|research|skill","constraints":{"cash_budget_usd":0}}
```

Build Receipt:
```json
{"status":"built|rejected|failed","artifact":"path-or-url","tests":[],"cost_usd":0,"limitations":[]}
```
