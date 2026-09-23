# SwarmBrain peer network

A handshake and local registration establish a remembered connection, not ownership of another agent. Public service requests use the interface the peer advertises. Longer-term collaboration, privileged resources and spending are separate agreements, not prerequisites for a public lookup.

## Persistent position and identity

Each peer has a stable UUID, a local graph slot, a capability region, its public card URL, protocol version, actual endpoint, first/last contact, conversation context and request history. Referrals keep their originating peer and task. Directory entries without callable interfaces remain remembered contacts rather than discarded leads or imaginary workers.

`data/public-agent-catalog.json` preserves the earlier 1,154-record discovery pass as 1,146 canonical listings. `data/mesh-state.json` stores connected peer details and `data/graph.json` stores request and dependency edges. A local graph slot is a stable address inside SwarmBrain, not a claim about biological neurons or physical location.

## Request and return path

1. Select a registered peer directly, or use a capability query to rank potential routes.
2. Build a message in the version advertised by its public Agent Card.
3. Assign an idempotent local request ID and retain the intent before dispatch.
4. Check the real protocol response, not just the HTTP status.
5. Preserve messages, server task IDs, contexts, errors and result receipts.
6. Retrieve a server-side task later with `poll`, using only its previously returned ID.
7. Review result quality separately from connection success and update empirical routing scores.

A real directory result has been handed to MYCELIX with a dependency link. MYCELIX requested further dialogue; the record does not claim that it completed the substantive evaluation. SNAIL and ZenithEye returned concrete public read results that passed explicit response checks. Sanctum returned structured public work listings; HumanMirror returned a no-match/capability-gap response. Every raw receipt is retained.

## Operator dispatch

Open an issue whose title starts `SwarmBrain task:` and whose body is a JSON object. Only the repository owner can start work this way. The default branch's Actions workflow performs one finite operation and commits results. The same JSON can be supplied using workflow_dispatch.

Supported modes:

- `connect`: `peer`, `card_url`, optional `region` and `protocol_version`.
- `request`: `peer`, public text/JSON `payload`, optional existing local `depends_on` task ID.
- `poll`: a local `task_id` whose record contains a server-issued remote task ID.
- `route`: a capability `query`.

Example:

```json
{"mode":"request","peer":"allagents","payload":"Find public memory agents and return their discovery addresses."}
```

No signup is performed by `connect`; no arbitrary remote code is downloaded or executed. Adding a peer does not start recursive outreach. Authentication or payment requirements are recorded, not bypassed. Request IDs prevent automatic replay; unavailable tasks and unanswered questions remain visible.

## Next engineering stages

The current coordinator runs on demand rather than maintaining open connections continuously. Cross-task validation, more protocol adapters, catalog freshness checks and an independently hosted inbound return address are distinct extensions. Joint neural-network training is not an automatic consequence of this graph; the current learning signal is the recorded success or failure of a route.

Primary protocol reference: https://a2a-protocol.org/latest/specification/ . Both published cards and actual runtime receipts take precedence over assumed endpoint syntax.
