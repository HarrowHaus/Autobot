# Incoming payment recovery and deadline handling

## Correction

The previous direct-USDC scanner expired an overdue quote *before* inspecting
its historical payment window. A delayed job could therefore miss an on-time
transfer. An expired quote is not proof that no payment was made.

## Implemented behavior

- Preserve immutable quote terms and cutoff. Never extend a buyer's signed authorization.
- Inspect original history even for legacy `expired` quotes. Store a resumable block cursor, with a canonical block checkpoint and replay if it changes.
- Scan incoming transfers after the cutoff too. A late transfer goes to operator review for delivery or refund, not automatic revenue recognition, refund or re-charge.
- Check RPC chain 8453, native USDC token, Transfer topic, recipient, exact invoice amount, block depth, canonical block and successful receipt/log identity. An amount-only mock log does not qualify.
- Commit payment state before delivering. A delivery failure or empty route set leaves `paid_delivery_pending`, never `expired`. Recheck chain evidence before retrying delivery.
- Store stable warning/recovery event IDs; the watcher reconciles GitHub publication history so an interrupted publish can be retried without deliberately sending duplicate reminders.
- Reserve legacy amount slots across expired orders. Overlapping/ambiguous invoices require review rather than double-counting an incoming payment. This legacy scheme supports 5,000 unique amount slots; migrate to explicit invoice binding before exhausting it.
- Bound each historical scan to 500-block chunks, 12 per order and 24 total per run. Record backlog; incomplete reads are not zero-payments claims.
- Keep received transfers, independently attributable outside revenue and USD bank balances separate. This scanner does not credit the economic ledger or declare profit.

The watcher retains its five-minute requested cadence, offset from the top of the
hour. GitHub schedules are best-effort and can be delayed or dropped. An hourly
ChatGPT watch is a secondary check, not a guarantee for short-lived signatures.
Expired signatures require fresh buyer authorization; no retry may revive them.

## Follow-up policy

Near-deadline, late-payment and delivery-problem alerts go to the operator's
existing inbox #19. Successful paid route results go to the originating order
issue. Buyer silence is not consent to charge. A buyer can request a new quote in
the storefront; the original quote and any historical payment remain preserved.
Never request a second payment because an on-time first payment was discovered
late. We cannot preserve a third party's bounty deadline or guarantee a purchase.

## Current work discovery

`collection_probe.py` reads public open tasks and explicitly decodes the published
BasedAgents schema: `bounty.amount` and `amount_atomic` are atomic units; token and
network must identify USDC on Base. It returns actual advertised scope and deadline
when present, without claiming work, sending messages or creating accounts.
An advertised reward or platform escrow label is not independent payment evidence.

## Validation and limits

37 local fixture-based tests passed. CI reruns these and separately probes public
task/payment data in a disposable checkout. Probe unavailability remains visible
and is not a test payment or successful collection. Five confirmations are a
confirmation policy, not absolute chain finality; the trusted RPC remains an
external dependency. CI concurrency serializes watcher runs, but multi-host
production collectors need a transactional database, not concurrent JSON writes.
Receipt hash covers order ID, quote hash, settlement, result and fulfillment time;
operational reconciliation/warning fields are outside that receipt hash.

Primary references checked 2026-09-24:
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://basedagents.ai/.well-known/agent.json
