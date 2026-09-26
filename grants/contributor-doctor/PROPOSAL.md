# Grant Proposal

**Title:** RustChain Contributor Doctor — Environment + Documentation Contract Checker  
**Tier:** Builder — 100 RTC  
**Contributor:** @tivince82 / @KungFury87  
**RTC wallet:** `RTC8a13ce90490828d7954ba1038df4873b73f7c049`

## What

Build a read-only contributor diagnostic tool that checks whether the commands and assumptions in RustChain contributor/onboarding documentation still match the current repository and installed CLI surfaces.

The tool will verify things such as:

- documented command names and flags against actual `--help` output or source-defined parsers
- referenced files/paths that no longer exist
- documented package/version claims against current repository metadata
- endpoint examples that no longer match the current public read-only API shape
- duplicated or contradictory setup instructions
- OS-specific instructions that are presented as universal
- stale references to disabled or retired integrations

It will produce both human-readable and JSON reports with exact source locations and reproducible checks.

## Why

Contributor-facing drift is already producing wasted work: stale commands, duplicate setup sections, outdated transport counts, and examples that do not match current CLI behavior. A deterministic read-only doctor can catch these problems before new contributors or agents follow broken instructions.

This is distinct from:
- the RTC Earnings Router / Payout Reconciler grant, which reconciles balances and payout evidence;
- the RIP-302 Conformance Harness proposal, which validates Agent Economy API/client contracts;
- bounty-spec linting, which validates bounty definitions rather than contributor docs/runtime instructions.

## How

Python standard library first, with optional subprocess checks against locally installed CLIs.

- local repository scan only by default
- optional public GET-only endpoint checks
- no signing
- no transfers
- no wallet mutation
- no security probing
- no private-key access
- fixture-backed offline tests
- deterministic JSON schema and nonzero exit status for selected drift classes

## Timeline

5–7 days after greenlight.

## Deliverables

- runnable CLI
- static HTML/Markdown summary report
- JSON output schema
- offline fixtures
- tests
- README with operator/contributor workflow
- one current-main RustChain report
- example checks against at least two adjacent Elyan Labs tools where their docs reference RustChain

## Acceptance boundary

The tool reports documentation/runtime mismatches only. It does not rank earning opportunities, estimate token value, execute payments, or perform security testing.

AI assistance disclosed.
