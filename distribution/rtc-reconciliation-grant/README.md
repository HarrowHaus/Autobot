# RTC Contributor Reconciliation — Builder Grant #402

Read-only CLI + static HTML report for answering one narrow question:

> Where is a contributor's RTC, and which accepted payouts are accepted, queued/pending, or confirmed?

This implements the **narrowed 100 RTC Builder grant approved on 2026-09-26**.

## Boundaries

This project deliberately does **not**:

- rank earning opportunities;
- calculate Tip-to-Earn returns;
- include USD prices, values, ROI, or conversion fields;
- fetch Gmail or require email credentials;
- sign messages;
- create transfers;
- approve payouts;
- mutate RustChain or GitHub state.

Online mode reads only public RustChain and GitHub endpoints. Email evidence, when needed for cross-channel dedupe, is supplied as a local JSON/JSONL export.

## What it reports

- hosted-handle RTC balance;
- native self-custody RTC balance;
- accepted → queued/pending → confirmed payout states;
- pending ID, transaction hash, and confirmation text when present;
- deterministic dedupe when the same claim appears in GitHub comments and an exported email copy;
- one machine-readable JSON receipt plus one static HTML report.

## Online example

```bash
python rtc_reconcile.py \
  --handle tivince82 \
  --wallet RTC8a13ce90490828d7954ba1038df4873b73f7c049 \
  --issue Scottcjn/rustchain-bounties#16497 \
  --issue Scottcjn/rustchain-bounties#398 \
  --issue Scottcjn/rustchain-bounties#16601 \
  --output-dir out/live
```

Outputs:

- `out/live/reconciliation.json`
- `out/live/index.html`

## Offline fixture verification

```bash
python -m unittest discover -s tests -v
python rtc_reconcile.py \
  --handle tivince82 \
  --wallet RTC8a13ce90490828d7954ba1038df4873b73f7c049 \
  --github-fixture fixtures/github-comments.json \
  --email-export fixtures/email-export.json \
  --node https://fixture.invalid \
  --output-dir out/fixture
```

The unit suite injects a fake HTTP opener for balances, so it remains fully offline.

## Dedupe model

Claim identity is determined in this order:

1. explicit `idempotency`, `claim_id`, or `marker`;
2. a stable tuple of issue reference + deliverable URL + native wallet/handle;
3. normalized body hash fallback.

For duplicate channel copies, the strongest lifecycle state wins:

`accepted < queued_pending < confirmed`

Equal states use the newest timestamp. **Amounts are never summed across duplicate channels.**

## Public endpoint use

- RustChain balance: `GET /wallet/balance?miner_id=...`
- GitHub issue comments: public REST `GET /repos/{owner}/{repo}/issues/{number}/comments`

No secrets are required.
