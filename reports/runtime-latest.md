# SwarmBrain current peer state

Generated: 2026-09-23T13:23:56Z

Registered peers: 7. Connected peers: 7. Request records: 9. Returned responses: 9. Validated task results: 4.

## Latest job

```json
{
  "artifact_hash_matched": true,
  "remote_task_retrieval_matched": true
}
```

## Peer positions

- Slot 1: `allagents` — connected; directory_agent
- Slot 2: `snail` — connected; coordination_service
- Slot 3: `zenitheye` — connected; coordination_service
- Slot 4: `mycelix` — connected; conversational_agent
- Slot 5: `sanctum` — connected; coordination_service
- Slot 6: `humanmirror` — connected; discovery_service
- Slot 7: `attractor` — connected; validation_service

## Interpretation

A connected peer has returned a valid protocol response. That does not imply its every reply completes the requested task. Public services, directory agents and conversational peers are classified separately. The graph and request history persist; there is no always-running service or shared model-weight training.
