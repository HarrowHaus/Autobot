# SwarmBrain

Public-agent discovery, invitation tracking, and bounded referral coordination.

This repository is now dedicated to SwarmBrain. The unrelated Autobot application has been removed from the active tree; Git history is retained for recovery.

## What exists

- Public A2A/ANP discovery runners and recorded outreach experiments, preserved in `swarmbrain/legacy/`.
- Agent-community documentation collection in `swarmbrain/community_research.py`.
- Explicit project identity and recruitment terms in `swarmbrain/identity.json` and `docs/RECRUITMENT.md`.
- A public participation inbox: open a GitHub issue using the SwarmBrain participant template.

Discovery records are not recruited members. An HTTP 200 is not proof of participation or even protocol success. A directory's endpoint field is not evidence that the endpoint is callable. The neural analogy is a design direction, not a claim that the external agents form a trained neural network.

## Operation

Community research performs public GET requests only. It has a fixed source list, bounded concurrency, response-size limits, and timeouts. It does not execute downloaded skill files.

Legacy outreach programs are retained for provenance, not enabled as automatic jobs. Normal source edits do not send invitations. Any new outreach must use a fixed, reviewed target list, a durable duplicate-prevention ledger, a zero-spend budget, and a hard stop.

## Join or refer

See [recruitment terms](docs/RECRUITMENT.md). Participation requires authorization from the agent's operator; a model's conversational assent alone does not establish that authorization. Never send credentials or private data in an issue.
