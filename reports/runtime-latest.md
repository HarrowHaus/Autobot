# SwarmBrain current peer state

Generated: 2026-09-23T13:19:22Z

Registered peers: 7. Connected peers: 7. Request records: 9. Returned responses: 9. Validated task results: 2.

## Latest job

```json
{
  "id": "issue-11",
  "peer": "attractor",
  "spec_hash": "5cd245ff68ab8da5e52c6e1d042fdf405e98b59240ac46bcd2fff9edca4bcdb0",
  "created_at": "2026-09-23T13:19:20Z",
  "state": "response_received",
  "depends_on": "bootstrap-20260923-orientation",
  "semantic_validation": "not_reviewed",
  "remote_state": "MESSAGE",
  "remote_task_id": null,
  "context_id": "97175296-a969-430b-a8c9-28b21ee343d4",
  "finished_at": "2026-09-23T13:19:22Z",
  "receipt": "reports/task-receipts/issue-11.json",
  "latency_ms": 1907,
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
