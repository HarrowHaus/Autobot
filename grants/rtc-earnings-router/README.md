# RTC Earnings Router / Payout Reconciler

Read-only contributor tool approved under RustChain micro-grant #402.

## Scope

The tool reconciles, for one contributor:

- a native RTC balance;
- a hosted-handle RTC balance;
- bounty payout evidence across `accepted -> queued/pending -> confirmed`;
- pending IDs, transaction hashes, and confirmation times;
- duplicate mentions of the same claim across GitHub comments and optional offline email evidence.

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
  --evidence-json fixtures/email-evidence.json \
  --out-json output/example-receipt.json \
  --out-html output/example-report.html
```

`--evidence-json` is an optional **offline export**. The program never logs into email or reads credentials. It exists only so a payout receipt repeated in email and GitHub can be deduplicated.

## Tests

```bash
python -m unittest discover -s tests -v
```

The fixture suite verifies:

- native/hosted balances remain separate;
- accepted/pending/confirmed state precedence;
- one claim repeated across issue body, GitHub comments, and offline email evidence is counted once;
- pending ID and transaction hash are preserved;
- JSON and static HTML outputs are generated;
- no USD field appears.

## Dedupe

Strongest identifiers win in this order:

1. explicit idempotency key;
2. pending ID;
3. transaction hash;
4. same issue + same RTC amount + compatible payout identity.

State precedence is `confirmed > pending > queued > accepted > unknown`.

## Safety

This is a read-only reporting tool. It contains no signing, transfer, withdrawal, bridge, trade, staking, or custody code.
