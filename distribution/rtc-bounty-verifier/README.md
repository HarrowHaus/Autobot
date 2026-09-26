# RTC Bounty Verification Bot

Read-only verification tooling for RustChain/Elyan Labs bounty claims, built for rustchain-bounties #747.

## Milestones covered

- Star/follow verification
- RustChain wallet existence/balance check
- Article/URL liveness
- Article word-count check
- Duplicate-claim detection

The tool **never executes a payout**. It produces evidence for human review.

## CLI

    python verify_claim.py --claim-json claim.json

## Tests

    python -m unittest discover -s tests -v

All tests are offline and use fake HTTP responses.

## Deployment model

A GitHub Action can call the CLI from an issue-comment or manual trigger. The recommended permissions are read-only for repository content; the verifier itself does not need payment authority. A maintainer remains responsible for payout decisions.

## Rate limits

Star and duplicate scans paginate in 100-item pages with finite page bounds. GitHub authentication may be supplied through GITHUB_TOKEN. Failed checks remain failed/unknown rather than being treated as zero or success.
