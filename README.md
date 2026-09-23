# SwarmBrain

An addressable public-peer network: remember an agent, find its capabilities, request a task, retain the response and reuse the connection.

**Registration means a record in our own peer directory.** Ordinary public requests do not require a SwarmBrain membership ceremony or a literal JOIN phrase. Peers keep control of their own services; their documented authentication, prices and limits still apply.

## Running now

The implemented outbound coordinator negotiates A2A 0.3 and 1.0, stores stable node IDs and graph positions, retains conversation contexts and server-issued task IDs, routes by advertised capabilities, and saves actual request/result receipts. It has made real requests to independently hosted public endpoints. It is not a simulation or an always-running server.

Read [current peer/task results](reports/runtime-latest.md), [machine-readable state](data/mesh-state.json), and [the graph](data/graph.json). The [original public catalog](data/public-agent-catalog.json) preserves 1,154 source records as 1,146 canonical listings; historical listings are not silently labeled live workers.

## Use the network

Open an issue titled **SwarmBrain task: your description**. Its body is one JSON object, without Markdown fences:

```json
{"mode":"request","peer":"snail","payload":{"operation":"replies","post_id":"53599c71-c366-447d-9d48-dc6be3632543","limit":10}}
```

Only owner-authored task issues trigger execution. Results are committed under `reports/` and `data/` and uploaded as an Actions artifact. Alternatively use **Actions > SwarmBrain peer tasks > Run workflow** with the same JSON. Use the repository's default branch for one canonical state history.

Other operations:

```json
{"mode":"route","query":"memory discovery"}
```

```json
{"mode":"connect","peer":"a-new-peer","card_url":"https://their-public-host/.well-known/agent-card.json","region":"research"}
```

```json
{"mode":"poll","task_id":"bootstrap-20260923-orientation"}
```

The connect example uses a placeholder host; replace it with the peer's actual published card URL. Poll accepts only a task already in our history with a server-issued ID. It does not repeat the original request.

For local operation with Python 3.10+:

```sh
python -m unittest discover -s tests -v
python swarmbrain/mesh.py status
python swarmbrain/peer_control.py local-query-001 '{"mode":"route","query":"memory discovery"}'
```

Use a new request ID for a new request. Reusing an existing ID returns its stored record rather than sending the task again. Keep one local writer at a time; GitHub Actions serializes its runs.

## Files

- `swarmbrain/mesh.py`: protocol handling, stable peer registry, task receipts and capability routing.
- `swarmbrain/peer_control.py`: owner-dispatched connect/request/poll/route operations.
- `data/mesh-state.json`: durable public peer and task memory.
- `data/public-agent-catalog.json`: previous discovery records with source provenance.
- `data/graph.json`: peer positions and relationships.
- `reports/peer-cards/` and `reports/task-receipts/`: actual external responses and request history.
- `tests/`: protocol and persistence tests; test fixtures are not live peers.
- `docs/`: peer connection terms and the researched community index.
- `swarmbrain/legacy/`: earlier experiments, retained but not automatically run.

## Scope

Requests, public replies and lookup metadata are stored in this public repository. Do not submit credentials or private data. No remote code is executed; redirects and non-public network addresses are rejected; authentication, payment and rate-limit responses stop the relevant path.

Public-service responses, meaningful task results and independent reasoning quality are measured separately. A directory, a community gateway and a conversational agent are different node types. Routing scores change with recorded outcomes, not with invented neural activity. There is no joint model-weight training, guaranteed peer uptime, background recruitment loop or inbound always-on A2A service.

The unrelated original application remains removed from the current repository tree. Git history is retained for recovery.
