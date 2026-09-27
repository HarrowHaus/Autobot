# Activate SwarmBrain earning

This is the one-time activation for the autonomous earning loop already merged into SwarmBrain.

## What this enables

After activation, the scheduled earning workflow can:

1. scan BasedAgents through the official SDK;
2. select a funded, claimable task matching SwarmBrain capabilities;
3. pre-fulfill it through one previously verified SwarmBrain peer;
4. have a different verified peer check the candidate deliverable;
5. re-fetch the live task and confirm the bounty did not change;
6. claim the task through the official BasedAgents SDK;
7. immediately submit the verified deliverable;
8. retain task/peer receipts and later observe marketplace payment status.

An open bounty, asking price, platform escrow label, or submitted job is not recorded as earned revenue merely because it exists.

## You do not need to fund the payout wallet

BasedAgents bounties pay SwarmBrain. A Base address can receive USDC without first depositing $20 into it.

Keep the proposed $20 separate for the later buyer/reinvestment loop: paid x402 resources, subcontracted agents, marketplace fees where applicable, and other bounded commercial experiments.

## What you need

- Node.js 22 or newer.
- Git.
- A Base-compatible 0x wallet address that you control.
- Do not paste a seed phrase or wallet private key into this script, ChatGPT, GitHub, or BasedAgents.
- Optional but recommended: GitHub CLI (gh) authenticated to the HarrowHaus/Autobot repository.

Official BasedAgents documentation:

- https://registry.basedagents.ai/docs/agents
- https://registry.basedagents.ai/
- https://api.basedagents.ai

GitHub Actions secret documentation:

- https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets

## Easiest activation

~~~bash
git clone https://github.com/HarrowHaus/Autobot.git
cd Autobot
git checkout claude/monetizable-project-concepts-b97bv2
npm install --ignore-scripts
npm run activate:earning
~~~

The script uses the already-declared official basedagents package.

It will:

- ask only for your public Base payout address;
- create or reuse ~/.basedagents/keys/swarmbrain-harrow-keypair.json;
- register the SwarmBrain-Harrow identity through the official BasedAgents SDK;
- bind your Base address as its payout wallet;
- never print the private key;
- if gh is authenticated, set the BASEDAGENTS_KEYPAIR_JSON and A0_PAYOUT_WALLET repository secrets;
- trigger .github/workflows/commercial_earn.yml.

The private identity file remains outside the repository.

## If you already know the payout address

~~~bash
npm run activate:earning -- --wallet 0xYOUR_BASE_ADDRESS
~~~

Use the normal public 0x address shown by your wallet. Do not use a seed phrase or private key.

## If GitHub CLI is not installed/authenticated

The BasedAgents registration and payout binding still complete locally. The script reports github: manual_required.

Then open:

HarrowHaus/Autobot -> Settings -> Secrets and variables -> Actions -> New repository secret

Create these two secrets:

### BASEDAGENTS_KEYPAIR_JSON

Value: the complete contents of the local file shown by the activation script, normally ~/.basedagents/keys/swarmbrain-harrow-keypair.json.

Treat this file like a password. Do not commit it, paste it into an issue, or send it in chat.

### A0_PAYOUT_WALLET

Value: your public Base payout address, 0x...

Then open:

HarrowHaus/Autobot -> Actions -> SwarmBrain earning cycle -> Run workflow

Run it on claude/monetizable-project-concepts-b97bv2.

## GitHub CLI alternative

If gh is authenticated, the bootstrap handles this automatically.

Equivalent manual CLI operations:

~~~bash
gh secret set BASEDAGENTS_KEYPAIR_JSON --repo HarrowHaus/Autobot < ~/.basedagents/keys/swarmbrain-harrow-keypair.json
printf '%s' '0xYOUR_BASE_ADDRESS' | gh secret set A0_PAYOUT_WALLET --repo HarrowHaus/Autobot
gh workflow run commercial_earn.yml --repo HarrowHaus/Autobot --ref claude/monetizable-project-concepts-b97bv2
~~~

On PowerShell, the easiest route is the bootstrap script rather than manually translating the shell redirection above.

## How to verify activation

Run:

~~~bash
npx basedagents id --json --keypair ~/.basedagents/keys/swarmbrain-harrow-keypair.json
npx basedagents wallet --json --keypair ~/.basedagents/keys/swarmbrain-harrow-keypair.json
~~~

Then inspect the latest GitHub Actions run named SwarmBrain earning cycle.

Expected states include:

- no_candidate — marketplace scan was real but nothing suitable was available;
- no_verified_executor — a task existed but the current peer graph could not support it;
- verification_rejected — the candidate deliverable failed independent checking;
- delivered — SwarmBrain claimed the task and submitted the pre-verified deliverable;
- already_delivered — an idempotent repeat found the same task already submitted;
- basedagents_identity_secret_missing — GitHub was never given the identity secret.

None of those states alone means money has been received. Payment has to reach a settled state and later be independently reconciled on-chain before the commercial ledger treats it as verified external revenue.

## About the future $20 operating wallet

Do not fund anything merely to activate the bounty workflow.

When the buyer/reinvestment side is added, use a separate low-value operating wallet, not the payout wallet holding earnings. That separation lets SwarmBrain spend only a bounded experimental balance without exposing accumulated revenue.
