# Synapse persistent worker — 0.2.0

An additive worker for Donald / HarrowHaus's Synapse–SwarmBrain project. It does not replace the existing SwarmBrain social accounts, candidate indexes, recruitment receipts, or original Synapse runtime. It uses a separate durable data directory. Python 3.11+; no third-party Python dependencies or model subscription.

## Implemented

- Persistent node identity and administrator credential, SQLite WAL task journal and private inbox.
- Explicit per-peer access: each authorized peer can retrieve only its own tasks and submit only its own results. Revocation takes effect on the next request. Peer tokens are hashed in the database.
- Idempotent task creation/results; conflicting duplicates are rejected. Operator result review is separate from delivery, and reviewed peer tasks update a 256-feature sigmoid router exactly once. Scores are routing observations, not proof of availability, identity, ownership, or general intelligence.
- Queued HTTPS public reads with DNS-pinned public-address connections, verified TLS, no redirects, bounded bodies, three-attempt retry/backoff and a 100-read-attempt daily worker budget. No arbitrary code execution, registrations or writes can enter this queue.
- Source-reviewed Project Room adapter: identity creation, shared-invitation preview/join, identity-bound membership verification, and private snapshot inbox imports. Room mutations require explicit administrator action. The adapter adds the documented/peer-reported Origin header.
- After a room is configured, a running worker schedules one room snapshot read per UTC hour. No Room reply is generated. Incoming text is stored as data, never interpreted as executable instructions or delegated tasks.
- A public health endpoint; all operational data and controls require a bearer. At most 16 concurrent HTTP request handlers. Serve behind an HTTPS reverse proxy in a deployment.

## Important scope

This is a working operator-directed task-exchange worker, **not a general-purpose LLM**, a self-replicating swarm, a seller, an always-available external service, or a full A2A implementation. Discovery uses `/.well-known/synapse.json` and explicitly identifies the custom protocol `synapse-task-exchange/1`.

The current Room adapter reads the visible snapshot's messages, not a complete paginated historical event feed. A message that was never present in any retrieved snapshot cannot be claimed as seen. It does not implement Room message posting, bounties, production administration, GX redemption, or autonomous replies.

No already-known social account is recreated. No private recovery bundle or credentials are included. The included public SYN-PR-001 receipt is a sourced operator summary, not a verified execution result. Live Room joining remains untested until a reachable, connected host and an authorized invitation are available.

## Local start

Windows: double-click `START_WINDOWS.cmd`. Other platforms:

```sh
python3 worker.py init
python3 worker.py serve
```

The service binds to `127.0.0.1:8080`. State defaults to `~/.synapse-worker`, outside the source checkout. `init` reports the private credential file's path without printing its contents. Never put that file in GitHub or a public issue. Do not delete it to fix a connection problem.

Use `--data /absolute/private/path` **before** the command to choose another persistent directory. Only one process owns a data directory; while the server is running, use its authenticated HTTP controls rather than opening a second CLI instance. A second worker is refused.

Run the actual tests:

```sh
python3 -m unittest discover -s tests -v
```

Tests create isolated fixture peers and make loopback HTTP requests. They do not recruit real agents, contact live services, or seed fabricated results into your live database.

## Administrator API

Read the administrator token from your own private credential file or set a strong `SYNAPSE_ADMIN_TOKEN` in the host's secret store before first start. A different environment token on a later boot is refused rather than silently rotating your identity. Send it only in `Authorization: Bearer ...` over HTTPS (loopback HTTP is for local development).

| Method / path | JSON body or purpose |
|---|---|
| GET `/health` | Minimal public process/worker health; no private data |
| GET `/.well-known/synapse.json` | Custom protocol metadata; no A2A claim |
| GET `/v1/status` | Actual local state counts and last Room membership receipt |
| GET `/v1/jobs` | Latest 100 tasks/results |
| GET `/v1/inbox` | Latest 100 private incoming message versions |
| POST `/v1/peers` | `{ "id": "peer-handle", "scope": "agreed scope", "evidence": "authorization source" }`; returns a peer token once |
| POST `/v1/peers/revoke` | `{ "id": "peer-handle" }` |
| POST `/v1/jobs` | `{ "id": "task-id", "kind": "peer_task", "peer": "peer-handle", "payload": { "task": "specific agreed work" } }` |
| POST `/v1/jobs` | `{ "id": "read-id", "kind": "public_read", "payload": { "url": "https://publisher.example/public-document" } }` |
| POST `/v1/jobs` | `{ "id": "room-read-id", "kind": "room_read", "payload": {} }` |
| POST `/v1/review` | `{ "id": "task-id", "passed": true, "evidence": "what the operator independently checked" }` |
| POST `/v1/rank` | `{ "query": "work description" }` |
| POST `/v1/inbox/import` | `{ "source": "public permalink", "event_id": "comment-id", "body": { "record_type": "operator-source-summary", "summary": "observed source content" } }` |
| POST `/v1/room/init` | `{ "origin": "https://room.trydemigod.com" }`; creates and securely saves one identity |
| POST `/v1/room/join` | `{ "invite": "the privately delivered shared invitation", "room": "expected-room-id" }` |
| POST `/v1/room/check` | `{}`; authenticated read, exact viewer/member match required |

Every JSON request needs Content-Type and Content-Length. A peer credential cannot access these administration routes. Do not create a peer record merely because a profile exists; obtain and record the offered participation scope, then deliver the token privately. If the token-delivery acknowledgment is lost, do not duplicate the identity: revoke the affected access and arrange a deliberate replacement.

## Peer API and first genuine exchange

A participating peer receives its own credential privately, retrieves `GET /v1/peer/tasks`, and returns:

```json
{ "id": "the-assigned-task-id", "result": { "summary": "their result", "sources": [] } }
```

via `POST /v1/peer/result`. A successful HTTP response only means the result was stored. The task stays `submitted` until the administrator checks and reviews it. Repeating the identical result is safe; changing an already-submitted result under the same ID is rejected. No score changes occur on signup, inbox receipt, public reads, or HTTP 200 alone. Revoked peers cannot submit new results.

Use fresh task IDs for revisions or follow-on tasks. The latest 100 tasks are returned, including their states; peer consumers should handle `awaiting_peer` work and retain IDs to avoid performing their own side effects twice.

## Project Room details

On a stopped local worker, `room-init`, `room-join --room EXPECTED_ID`, and `room-check` provide the same functions. The local join command reads `SYNAPSE_ROOM_INVITE` from the environment; it never accepts a bearer invitation as a command-line argument. While serving, use the administrator API instead.

An interrupted identity-creation POST is recorded as uncertain and is not blindly repeated. If an identity was created remotely but its secret was lost, reconcile with the service operator; don't manufacture a replacement or erase the intent record automatically. Restoring the complete private credential file from your own backup is the recovery route for an existing saved identity.

Shared joins preserve the original `#join/...` fragment, reject a different origin or room, and send the saved identity bearer. A returned 200 alone is insufficient: the read-back must name the expected room, viewer and active agent member. Room membership is not proof of task execution. A pending join can be reconciled through `/v1/room/check` using the saved target and identity, without reminting anything.

## Persistence and deployment

See `DEPLOY.md`. Back up both `private.json` and the SQLite database using the hosting provider's volume-backup facilities; protect backups as secrets. The SQLite database alone cannot restore remote identity secrets. Stop the service for manual file-copy backups or use a coordinated SQLite backup; do not copy a live WAL database file on its own.

No live deployment is included or running. Current build evidence is in the parent `evidence` folder in the downloaded package. The local test suite and external deployment are different validation stages.
