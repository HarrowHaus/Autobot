# Deployment handoff — checked 23 September 2026

## Connection and spend gates

The Railway plugin was available but reported **not installed/connected** when checked in this build. The assistant did not create a project, select a paid plan, attach billable resources, deploy a service, or change account permissions. Connect the Railway card in ChatGPT to enable an authorized deployment action. Preserve Donald's $0 external-spend requirement. Check actual remaining credits/account limits before creating resources; do not assume a continuously running worker is free.

## Deploy this folder

Use the existing `HarrowHaus/Autobot` repository, the branch containing this worker, and root directory `/synapse_worker`. Use the included Dockerfile. Do not point the new service at old social-campaign scripts, and do not execute those campaigns as a build or start step.

Service settings:

- Docker build from `synapse_worker/Dockerfile` using `synapse_worker` as context.
- One service instance; attach one persistent volume mounted at `/data` **before runtime initialization**.
- `SYNAPSE_DATA_DIR=/data`; inject an operator-controlled, random `SYNAPSE_ADMIN_TOKEN` with at least 32 ASCII characters through the host's secret store before first boot.
- Keep the Docker CMD: `python worker.py serve --host 0.0.0.0`. The app reads the platform's `PORT`.
- Generate an HTTPS domain. Healthcheck `/health`; On Failure restart policy with at most 10 retries.
- Do not configure replicas. No social credentials, Project Room invitation or private key belongs in the repository.

The worker refuses to serve under Railway when `RAILWAY_VOLUME_MOUNT_PATH` is missing or the data directory lies outside it. A mount protects identity and SQLite history across redeployments. Healthcheck success is not proof of external network connectivity or permanent monitoring.

## Current configuration compatibility

Railway's current Config as Code page says new services cannot opt into `railway.json`/`railway.toml`, and legacy support ends 2026-12-01. This build therefore does **not** invent an outdated `railway.json`; configure the documented settings using the connected app/dashboard. An Infrastructure-as-Code definition can be generated against the connected provider's current schema during deployment rather than guessed offline.

## Deployment acceptance ladder

1. Docker build and embedded tests pass on the real host. This build did not run Docker locally.
2. HTTPS `/health` returns 200; administrator API rejects an incorrect credential.
3. A queued public read of Project Room's `/llms.txt` returns an actual status/bytes/hash receipt. A DNS failure is not a service refusal.
4. Restart the host and check the same node ID, credential and queued tasks still exist.
5. Explicitly initialize/save the Room identity. Use an authorized shared invitation delivered privately; verify exact member identity read-back.
6. Offer the peer-exchange protocol to a willing participant; privately deliver its scoped credential. Complete one agreed task and independently review the returned result.
7. Only then record a working external exchange. Deployment, membership, message delivery and verified task completion remain separate states.

## Sources checked for this build

- Railway volumes: https://docs.railway.com/volumes and https://docs.railway.com/volumes/reference
- Railway healthchecks: https://docs.railway.com/deployments/healthchecks
- Railway restart limits: https://docs.railway.com/deployments/restart-policy
- Railway configuration transition: https://docs.railway.com/config-as-code
- Project Room identity contract: https://github.com/Uuriko/project-room/blob/main/docs/AGENT-IDENTITIES.md
- Shared-link implementation: https://github.com/Uuriko/project-room/blob/main/server/share-links.mjs
- Room client identity checks: https://github.com/Uuriko/project-room/blob/main/client/room-agent.mjs
- Instinct's SYN-PR-001 receipt: https://github.com/Uuriko/project-room/issues/266#issuecomment-5794814341

Observed GitHub blob SHAs during implementation: identity documentation `598427dc1ede4c2928c9b6172a974d04857f6b02`; Room client `bcc55c0241223fd049b385518d36660d0fa77c2c`. These identify source observations, not a live server release assertion.
