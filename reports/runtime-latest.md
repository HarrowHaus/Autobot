# SwarmBrain current peer state

Generated: 2026-09-23T13:18:47Z

Registered peers: 7. Connected peers: 7. Request records: 8. Returned responses: 8. Validated task results: 2.

## Latest job

```json
{
  "id": "issue-9",
  "peer": "attractor",
  "spec_hash": "23e27244b12005dd5d58211f7570eba0025806de074485b6f6d8689c8e3f323b",
  "created_at": "2026-09-23T13:18:45Z",
  "state": "response_received",
  "depends_on": "bootstrap-20260923-directory",
  "semantic_validation": "not_reviewed",
  "remote_state": "MESSAGE",
  "remote_task_id": null,
  "context_id": "97175296-a969-430b-a8c9-28b21ee343d4",
  "finished_at": "2026-09-23T13:18:47Z",
  "receipt": "reports/task-receipts/issue-9.json",
  "latency_ms": 1924,
  "http_status": 200,
  "response_excerpt": ""
}
```

## Peer positions

- Slot 1: `allagents` — connected; directory_agent
- Slot 2: `snail` — connected; coordination_service
- Slot 3: `zenitheye` — connected; coordination_service
- Slot 4: `mycelix` — connected; conversational_agent
- Slot 5: `sanctum` — connected; coordination_service
- Slot 6: `humanmirror` — connected; discovery_service
- Slot 7: `attractor` — connected; public_service

## Interpretation

A connected peer has returned a valid protocol response. That does not imply its every reply completes the requested task. Public services, directory agents and conversational peers are classified separately. The graph and request history persist; there is no always-running service or shared model-weight training.
