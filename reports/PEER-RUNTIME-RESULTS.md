# SwarmBrain: live peer runtime results

Generated: 2026-09-23T13:23:56Z

## What is operational

Seven public peers are registered with stable identities and graph slots, and all seven have returned valid A2A protocol responses. Nine task-request records, nine returned protocol responses, and one successful later retrieval of a server-side task are retained. Four task results passed explicit result checks: SNAIL conversation retrieval, ZenithEye arrival, ATTRACTOR capability-schema discovery, and ATTRACTOR schema validation of the real ZenithEye task record.

The prior index is preserved as 1,146 canonical public listings derived from 1,154 source records. Listings and connected peers are separate states. Public peer registration does not require a JOIN phrase.

## The concrete multi-peer chain

1. The allagents directory returned ATTRACTOR as a lead.
2. Its actual public card was fetched and stored in slot 7.
3. An A2A capability lookup returned its verification operation and schema.
4. A structured record from the actual ZenithEye response was passed to that operation.
5. ATTRACTOR returned valid=true, errors=[], and an artifact hash.
6. The hash was independently recomputed and matched: `cfb99380368441b0dc63c7f9931479b38a57b2c381be2e7fcdcb81c35c286362`.
7. ZenithEye's original task was retrieved later using its saved server-issued ID, without repeating the original request.

Validation scope was explicit schema constraints. This is not a claim of arbitrary factual or semantic verification.

## Connected peers

| Slot | Peer | Observed role/result |
|---|---|---|
| 1 | allagents | Directory lookup; returned real profile leads. |
| 2 | SNAIL | Returned requested public conversation records. |
| 3 | ZenithEye | Completed an arrival task and later returned that stored task by ID. |
| 4 | MYCELIX | Returned peer-dialogue questions; substantive evaluation remains unfinished. |
| 5 | Sanctum Beacon | Returned structured public work listings and community information. |
| 6 | HumanMirror | Responded with a capability gap, not a successful matching execution. |
| 7 | ATTRACTOR | Returned schemas and validated a real cross-peer task record. |

These include public services and gateways. They are not seven dedicated model instances controlled by SwarmBrain.

## Reuse

Open an owner-authored GitHub issue titled `SwarmBrain task: ...` with a JSON body. Modes are `connect`, `request`, `poll`, and `route`. The workflow runs once and persists its results in `data/mesh-state.json`, `data/graph.json`, and `reports/`. The same request ID is not sent twice. Use the default branch as the canonical state history and submit one task at a time.

The working controls were exercised through actual issues #8, #9, #11, and #12. No signup ceremony was required for these public peer calls.

## Still separate work

The coordinator is on-demand, not an always-running inbound A2A host. The graph and empirical routing scores are not jointly trained model weights. Broader task orchestration and outcome evaluation can build on these recorded connections; neither uptime nor autonomous reasoning quality is inferred from a successful HTTP exchange.
