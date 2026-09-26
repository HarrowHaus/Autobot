# Beacon to RustChain RIP-302 Agent Economy

Focused implementation for the open #685 Tier 2 Beacon integration bounty (75 RTC).

This package adds an stdlib-only RIP-302 client plus an opportunity_ping(job) mapper that turns a RustChain job into a Beacon kind=bounty envelope payload. It covers the practical Beacon lifecycle: browse opportunities, post a job, claim work, and deliver results.

The adapter deliberately does not duplicate Beacon signing keys. Existing Beacon identity/envelope code can sign and route the returned payload.

Tests are fully offline:

    python -m unittest discover -s tests -v

No test posts a live job, claims work, or transfers RTC.
