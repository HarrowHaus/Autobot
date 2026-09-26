# Grant Proposal — RTC Earnings Router + Payout Reconciler

**Title:** RTC Earnings Router + Payout Reconciler  
**Tier:** Builder — 100 RTC  
**Contributor:** @tivince82 / @KungFury87  
**RTC wallet:** `RTC8a13ce90490828d7954ba1038df4873b73f7c049`

## What

Build a small, read-only contributor tool that reconciles RustChain earning state across native self-custody balances, hosted handle balances, bounty issue evidence, accepted-but-unsettled claims, queued/pending transfers, and confirmed payouts.

The same tool also ranks current **non-security** RTC earning opportunities and displays explicitly-advertised compounding programs such as Tip-to-Earn, while never moving funds automatically.

## Why

RustChain contributors currently have to read multiple wallet endpoints, bounty comments, pending IDs, and payout notices to answer simple questions:

- How much RTC is actually spendable now?
- How much is hosted under a GitHub handle?
- Which accepted claims have not settled yet?
- Which pending transfers have confirmed?
- Which open bounties are genuinely actionable rather than stale/duplicated?
- Which incentive programs can increase RTC balance, and what are their caps/lock periods?

A provenance-first reconciler would reduce payout confusion without treating internal reference rates as cash value.

## How

Python standard-library core with optional static HTML report.

- Public/read-only RustChain and GitHub inputs only.
- Resolver for native RTC addresses vs hosted GitHub-handle balances.
- Explicit state machine:
  `discovered -> submitted -> accepted -> queued -> confirmed`.
- Separate fields for:
  - spendable native RTC,
  - hosted RTC,
  - accepted/pending RTC,
  - confirmed RTC,
  - internal reference value,
  - realized external USD (only when independently evidenced).
- Non-security opportunity ranking for docs, tooling, integrations, content, testing, and onboarding work.
- Incentive registry for programs such as Tip-to-Earn with cap, hold period, required proof, and net-RTC math.
- Immutable JSON reconciliation receipts.
- Offline fixture mode and deterministic tests.
- No signing, transfers, trading, custody, private-key access, or automatic financial actions.

## Timeline

7–10 days after approval.

## Deliverable

Public repository containing:

- runnable CLI,
- static HTML summary,
- fixture-backed tests,
- README,
- example reconciliation receipt,
- contributor integration notes.

## Acceptance Checks

1. Given fixture evidence containing a hosted balance, native balance, accepted claim, queued transfer, and confirmed transfer, the tool reports each state separately without double counting.
2. Internal RTC reference rate is never reported as realized USD.
3. Duplicate/stale bounty evidence is deduplicated deterministically.
4. Opportunity ranking excludes configured security/red-team categories.
5. Tip-to-Earn example computes gross return and net RTC gain without executing a transfer.
6. All tests pass offline.

AI assistance disclosed. The proposed tool remains read-only and does not perform financial transactions.
