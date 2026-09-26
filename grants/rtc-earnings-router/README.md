# RTC Earnings Router / Payout Reconciler

Read-only contributor tool approved under RustChain micro-grant #402.

## Scope

The tool reconciles, for one contributor:

- a native RTC balance;
- a hosted-handle RTC balance;
- bounty payout evidence with **wallet history as the pending/confirmed source of truth** and maintainer GitHub comments used only for accepted evidence;
- pending IDs, transaction hashes, and confirmation times;
- exact ledger-row preservation keyed by transaction hash, so same-amount payouts never collapse into one record.

It does **not** rank earning opportunities, calculate investment returns, expose private keys, sign transactions, move funds, or emit USD values.

## Live run

```bash
python rtc_reconcile.py \
  --github-handle KungFury87 \
  --hosted-handle tivince82 \
  --native-wallet RTC8a13ce90490828d7954ba1038df4873b73f7c049 \
  --out-json output/receipt.json \
  --out-html output/report.html
```

The default live mode uses only public RustChain and GitHub GET endpoints.

## Offline deterministic run

```bash
python rtc_reconcile.py \
  --github-handle KungFury87 \
  --hosted-handle tivince82 \
  --native-wallet RTC8a13ce90490828d7954ba1038df4873b73f7c049 \
  --fixture-dir fixtures \
  --out-json output/example-receipt.json \
  --out-html output/example-report.html
```

## Tests

```bash
python -m unittest discover -s tests -v
```

The fixture suite verifies:

- native/hosted balances remain separate;
- the real recorded payout fixture reconciles to **25 RTC confirmed / 119 RTC pending**;
- four separate 15 RTC pending transfers remain four distinct rows;
- grant approval / "needs revision" language does not become a false confirmed payout;
- transaction hash and confirmation time are preserved;
- JSON and static HTML outputs are generated;
- no USD field appears.

## Evidence rules

- `/wallet/history` is authoritative for `pending`, `confirmed`, and `failed` transfer state.
- Incoming payout rows are deduplicated **only by transaction hash**; same issue + same amount is never enough to merge them.
- GitHub contributes only maintainer-authored `accepted` evidence. The accepted matcher is word-boundary and negation-aware.
- GitHub comments are paginated. `--github-token` (or `GITHUB_TOKEN` / `GH_TOKEN`) is optional for higher API limits.
- The current live node omits `confirms_at` on pending rows; while that remains true, the report transparently derives the scheduled confirmation time as `created_at + 24h` and marks the source as `derived_24h`.

## Safety

This is a read-only reporting tool. It contains no signing, transfer, withdrawal, bridge, trade, staking, or custody code.
