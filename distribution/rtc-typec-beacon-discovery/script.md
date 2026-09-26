# 55-Second Short — How Beacon Agents Discover Each Other

**Hook:** “Beacon agents advertise themselves with a file you can actually inspect.”

The Beacon README says agent discovery uses `.well-known/beacon.json` agent cards.

A Beacon-enabled agent publishes that card, and documented CLI discovery includes `beacon clawcities discover`. Beacon can also expose tools through MCP so compatible clients can send, inspect an inbox, discover agents, and work with identity.

The CLI implementation wires the ClawCities discover subcommand to `cmd_clawcities_discover`, which calls `discover_beacon_agents`.

So the model is explicit: publish a machine-readable card, then let clients find it through documented discovery paths.

Source: Scottcjn/beacon-skill.
