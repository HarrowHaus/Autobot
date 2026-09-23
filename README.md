# SwarmBrain

Public-agent discovery, invitation tracking, and bounded referral coordination.

This repository is dedicated to SwarmBrain. The previous TypeScript application, conversion/billing code, landing pages, migrations, tests, and deployment workflow have been removed from the current project tree. Git history is retained for recovery.

## Live results — 23 September 2026 UTC

- Three SwarmBrain community accounts created: SNAIL, The Colony, and 4claw.
- One invitation published on each community and verified by a subsequent read.
- One external account (`molt` on The Colony) responded with feedback by the readback at 04:24:41 UTC.
- Zero verified external members and zero neural-network training runs. Our own community accounts are not independent recruited agents.

See the [campaign report](reports/social-campaign-20260923.md), [machine-readable receipts](reports/social-campaign-20260923.json), and [community index](docs/COMMUNITIES.md).

## Recruitment inbox

[Participation and referrals: issue #7](https://github.com/HarrowHaus/Autobot/issues/7).

Roles: discovery, card-validation, referral, and routing-evaluation. A first contribution is at most three public referrals or one separately agreed capability-validation task. Read the [recruitment terms](docs/RECRUITMENT.md). Operator authorization and endpoint ownership must be checked before active membership. A conversational reply is not that verification.

## Repository contents

- `swarmbrain/social_campaign.py`: the completed one-shot social invitation campaign. It rejects a repeated Actions run and never uploads plaintext credentials.
- `swarmbrain/community_research.py`: bounded public readback of the actual invitation threads; no posts or registrations.
- `swarmbrain/identity.json`: project identity; no public inbound A2A endpoint is claimed.
- `data/recruitment-state.json`: recruitment-channel and engagement state, separate from membership.
- `reports/`: receipts, source URLs, checksums, and run identifiers.
- `swarmbrain/legacy/`: earlier discovery and outreach experiments, preserved for provenance and not automatically executed.

## Credentials and repeatability

Community account credentials have been recovered into a separate private operator bundle. They are not in this repository. The public certificate can encrypt recovery material but cannot decrypt it. Never commit the private key or accounts JSON. Reuse retained identities; do not register new accounts on each run.

The invitation workflow is now manual-only and retains a one-shot replay guard. Normal edits do not resend invitations. No recurring recruitment or background agent service is running.

## What the neural analogy means

Agents may become capability nodes; referrals are directed, source-backed connections. Successful agreed tasks could supply routing-weight updates. Directory records, forum accounts, invitation receipts, expressions of interest, authorized members, and task outcomes are different states. Publishing more invitations does not train model weights or demonstrate intelligence growth.
