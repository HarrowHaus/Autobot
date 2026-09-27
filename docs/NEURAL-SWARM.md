# SwarmBrain Neural Graph

**Rook** is the coordinator agent. **SwarmBrain** is the persistent graph around it.

This layer is intentionally separate from `mesh.py`: the mesh keeps working peer/task
transport; the neural graph remembers *entities and relationships* across every source.

## What a node means

A node is an observed agent, service, public agent lane, controller, or coordination
surface. Every node has a stable ID, a display name, aliases, interfaces, provenance,
capability claims, observed capabilities, interaction counters, and validation history.

A name is not proof of independence. For example, `Instinct` and `Quill` may exist as
separate named lanes under the same GitHub account. The graph records both the lane and
the shared account provenance instead of counting them as independent operators.

## What a synapse means

A synapse is a weighted directed relationship derived from events. Conversation creates
a weak edge; referrals and completed tasks strengthen it; independently validated useful
results strengthen it more. Failures can weaken task-specific edges without deleting the
relationship.

Weights are routing memory, not model weights and not a truth score.

## Every interaction

`reports/agent-interactions.ndjson` is append-only. Each public observation has a stable
event ID, participants, source URL, timestamp, type, content hash, provenance state, and
a short excerpt. Re-runs deduplicate by event ID; history is not overwritten.

`data/agent-ledger.json` is the current entity snapshot.
`data/agent-synapses.json` is the current weighted edge snapshot.
`reports/neural-growth-latest.json` is the current growth summary.

## Self-expansion

The hourly `SwarmBrain neural growth` workflow:

1. absorbs all current records in `public-agent-catalog.json`;
2. merges catalog entries with mesh peers when they share an Agent Card URL;
3. ingests new public comments from the A0 inbox, Project Room coordination thread,
   and the SYN-PR review thread;
4. preserves self-reported lane identities separately from GitHub account provenance;
5. discovers new Agent Card URLs appearing in public evidence;
6. probes a bounded rotating frontier of cards and records observed skills;
7. commits the expanded ledger, synapses and append-only events.

Each run is deliberately bounded; the scheduled sequence has no finite node-count target.
That gives continuing recursive growth without an unbounded single-run crawl or mass spam.

## Expansion versus contact

Discovery and memory are automatic. Conversation is not a membership system: Rook may
talk to public agents using their ordinary contact surfaces when relevant. The growth
workflow itself does **not** mass-message newly discovered agents. Contact history is
still written into the same event ledger when it occurs.

## Entity resolution

The primary merge key for public protocol agents is their canonical Agent Card URL.
Mesh aliases and catalog listings pointing at the same card become one node. Public
social lanes use account + lane name and retain the shared-account fact. Runtime peer IDs
such as `a0-core` are separate identities linked by interactions.

Future entity-resolution evidence can merge aliases, but history must remain traceable.
