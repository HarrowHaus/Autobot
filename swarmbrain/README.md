# SwarmBrain

Federated public-agent mesh modeled as a neural graph.

- neurons = callable/discoverable agents
- synapses = referrals, directory membership, protocol links, successful collaborations
- activation = task-specific routing into capability-relevant neighborhoods
- plasticity = edge weights rise/fall after verified outcomes
- neurogenesis = recursive discovery from A2A, ANP and agent referrals

The runner uses documented public discovery surfaces only: A2A Agent Cards, ANP `/.well-known/agent-descriptions`, the Global A2A Registry public read API, allagents anonymous directory reads, and the read-only official MCP Registry. MCP servers are stored separately as capability nodes.

Recruitment is one public invitation in an agent-native coordination room. A referral only creates a candidate edge. Enrollment requires the literal `JOIN SWARMBRAIN` plus a public A2A/ANP card URL. No code copies itself into other runtimes, no payment endpoints are called, and no credentials are requested.

The live action emits `agents.json`, `capability_nodes.json`, `hubs.json`, `recruitment.json`, `crawl_log.json`, and `report.json` as the `swarmbrain-live-index` artifact.
