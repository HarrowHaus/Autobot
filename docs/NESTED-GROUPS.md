# Addressable groups of agents

SwarmBrain now supports a group as an addressable node. Its children can be peer agents, other groups, or both. A question to the parent traverses the nested membership graph and returns the contributions under that same structure.

## The initial hierarchy

```text
swarm
├── reasoning
│   ├── design
│   │   ├── multi-provider
│   │   └── llm-orchestrator
│   ├── critique
│   │   ├── traced-claude
│   │   └── llm-orchestrator-2
│   └── synthesis
│       └── multi-provider  ← the same peer, not a duplicated agent
├── research
│   ├── discovery
│   │   ├── allagents
│   │   ├── humanmirror
│   │   └── nulliverba
│   └── commons
│       ├── snail
│       ├── zenitheye
│       └── sanctum
└── assurance
    └── validation
        ├── attractor
        └── gaip-broker
```

These are ten persistent coordinator-group records containing twelve distinct external peer leaves. Four hosted, model-backed endpoints in `reasoning` produced task-specific text during live checks. The others are public discovery, coordination or verification services. A group name is an organizational role, not a claim that a distinct specialist model has been trained.

The readiness check and current counts are in [the live results](../reports/NESTED-GROUP-RESULTS.md). The four model-backed endpoints reported **Gemini 2.5 Flash through Vertex AI**, including the endpoint whose historical alias contains `claude`. Distinct endpoints are not evidence of distinct underlying models or independently operated organizations.

## Ask a group

From chat, a question can be dispatched to the saved group through the connected GitHub task interface. No registration interview or membership phrase is needed for these ordinary public requests.

For direct GitHub use, open an owner-authored issue with a title beginning exactly **`SwarmBrain group:`**. Put this JSON in the body without Markdown fences:

```json
{
  "mode": "ask",
  "group": "reasoning",
  "question": "Your public question here",
  "synthesize": true
}
```

The **SwarmBrain group questions** Actions workflow also accepts the same JSON in its `job` input. Only a newly opened owner-authored issue dispatches a job; editing or commenting does not run it again. The existing single-peer `SwarmBrain task:` interface remains separate and unchanged.

The response is saved in [`reports/group-latest.json`](../reports/group-latest.json). Every run has its own file in [`reports/group-runs/`](../reports/group-runs/) with raw task-receipt links, membership paths, contributors, skipped peers and optional synthesis. All request and response content is public in this repository; do not include secrets or private data.

Any child group can be addressed directly. For example, `design` asks only its two peers; `reasoning` reaches four distinct contributors across three subgroups. `swarm` traverses all three branches. Research and validation service outputs are labeled as context or checks rather than presented as model-written answers.

## Define or inspect another group

Connect individual peers using the existing peer-control interface first. Then define a group of their aliases or other existing groups:

```json
{
  "mode": "define",
  "group": "research-review",
  "label": "Research and reasoning together",
  "children": ["research", "reasoning"]
}
```

Inspect the exact dispatch plan without sending requests:

```json
{"mode":"plan","group":"swarm"}
```

Local Python equivalents:

```sh
python -m unittest discover -s tests -v
python swarmbrain/groups.py inspect-001 '{"mode":"plan","group":"reasoning"}'
python swarmbrain/groups.py question-001 '{"mode":"ask","group":"reasoning","question":"Your public question","synthesize":true}'
```

Use the same `execute_job(job, job_id, root)` function from Python when shell quoting is inconvenient. The scripts use Python's standard library and the existing peer state; no local LLM or model-provider API key was required for the demonstrated public calls.

## A peer belongs to two groups—what happens?

Before dispatch, SwarmBrain resolves all paths to each peer. The same stable peer identity receives one contributor request for a question even when several child groups include it. Its one response is referenced under every applicable membership path. The parent does not count that shared response twice.

An optional synthesis is **one additional, explicitly recorded reduction request** to `multi-provider` after the individual answers arrive. That is not counted as another independent opinion. Original contributions remain available alongside the model-generated synthesis, including disagreement, failures and incomplete answers. Synthesis can be wrong; it is not a correctness certificate.

The first readiness run tested this with `multi-provider` under both `design` and `synthesis`: five membership paths, four contributor requests, followed by one separately labeled reduction request. Reloading the group state preserved the same topology and existing peer IDs.

## What is implemented

- Stable group IDs, nested group membership, exact child references and exported topology.
- Cycle rejection, bounded nesting and traversal, and preservation of all shared membership paths.
- Bounded question fan-out, one contributor call per distinct peer, and durable per-question receipts.
- Separate application adapters for public conversation reads, agent discovery, validation and natural-language questions.
- Partial results rather than invented responses when a peer fails, needs authentication or has no appropriate adapter.
- Handling for provider errors embedded inside otherwise valid protocol responses. A quota failure is not counted as an answer.
- Optional actual external synthesis with contributor IDs and original answers preserved.
- Owner-dispatched operations through GitHub and a local Python interface.

The transport currently makes calls sequentially to preserve the single-writer JSON store. This is a hierarchical dispatch plan, not a claim of parallel execution. The ordinary group runtime budgets at most 24 network calls and 240 seconds; the per-question peer limit is 1–24. The synthesis call uses the same overall network budget. Larger or slower runs may return partial results.

Reusing a question ID with the same specification returns the stored result instead of repeating calls. Reusing it with different input raises an error. An interrupted run can retain a partial/running record; it is not silently replayed. Run one local writer at a time. Hosted workflows share the existing state-concurrency group and commit to the configured default branch.

## Source and state

| File | Purpose |
|---|---|
| `swarmbrain/groups.py` | Group definition, traversal, dispatch, response collection and synthesis. |
| `swarmbrain/bootstrap_groups.py` | The finite initial group build and live readiness exercise. |
| `tests/test_groups.py` | Offline group-logic tests, isolated from live records. |
| `data/groups.json` | Group definitions and per-question receipt references. |
| `data/group-graph.json` | Groups, external peers and `contains` relationships. |
| `reports/group-runs/` | Question-specific topology, responses and synthesis. |
| `reports/NESTED-GROUP-RESULTS.json` | Actual readiness outcomes and evidence links. |

The groups are coordinator objects in our network; they do not seize remote agents or duplicate their underlying models. External peers remain callable public services with their own availability. No continuously running process, unrestricted recruitment loop or joint neural-model training is claimed.
