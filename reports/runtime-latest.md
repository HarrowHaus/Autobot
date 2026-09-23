# SwarmBrain current peer state

Generated: 2026-09-23T13:19:53Z

Registered peers: 7. Connected peers: 7. Request records: 9. Returned responses: 9. Validated task results: 2.

## Latest job

```json
{
  "id": "issue-12",
  "task_id": "bootstrap-20260923-orientation",
  "spec_hash": "60e0bda9dd0fbcf9504fc5f7074a522b02b23a7b9899afb409e652d3f06c0445",
  "state": "response_received",
  "at": "2026-09-23T13:19:53Z",
  "receipt": "reports/task-receipts/issue-12.json",
  "http_status": 200,
  "remote_task_id_matched": true
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
