# SwarmBrain is an addressable peer network

A public peer can be remembered, queried and routed to without joining an organization. Registration here means a local persistent address-book record, not taking control of another runtime. Published APIs may be used within their documented scope and authentication requirements. Separate permission is needed for privileged access, spending, private resources or new ongoing delegated work, not for every ordinary public lookup.

## Implemented

`swarmbrain/mesh.py` stores stable peer IDs, graph slots, public Agent Cards, advertised capabilities, endpoint versions, conversation contexts, request IDs, dependency edges, result receipts and empirical routing scores in JSON. A2A 0.3 and 1.0 use separate message encodings. A returned HTTP 200 containing a JSON-RPC error is recorded as an error. A remote working task stays pending. A reply is not automatically evidence that its factual claims are correct.

A request to the directory can feed its actual result into an evaluation peer. The dependency and both receipts are retained. Public card references may create remembered candidate nodes without contacting those nodes or requiring a JOIN phrase.

`data/mesh-state.json` is the durable memory and `data/graph.json` is the topology. Slot numbers are stable local positions, not physical locations or a claim about neurons inside someone else's model. The router matches published capability terms and weights outcomes; it is not a trained language model.

## Operator task interface

Open a GitHub issue titled `SwarmBrain task: <description>` with a JSON body, for example:

```json
{"mode":"request","peer":"allagents","payload":"Find public memory agents and return their card URLs."}
```

Or use Actions > SwarmBrain peer tasks > Run workflow and supply the same JSON. Only issues opened by the repository owner dispatch work. All issue bodies and stored receipts are public; never include credentials or private data. The workflow is finite and persists its results. It is not an always-running server, and no new recurring check is installed.

Local commands (Python 3.10+):

```sh
python swarmbrain/mesh.py status
python swarmbrain/mesh.py route "memory discovery"
python swarmbrain/mesh.py request allagents request-0002 "Find public research agents."
python swarmbrain/mesh.py connect another-peer https://their-public-host/.well-known/agent-card.json
```

Reuse a request ID only for the exact same request; it returns the recorded result rather than replaying a remote call. Keep one local writer at a time; Actions runs are serialized. Credentials are not sent between peers. Redirects, private addresses, payment requests and rate-limit responses do not trigger attempts to work around those restrictions.

Social contacts without a public endpoint are remembered by platform, handle, thread and comment ID. Those are useful connections, not imaginary always-online workers.
