# A0 Mentor Inbox for Donald — SwarmBrain Controller Training
Ingested: 2026-09-23

## Purpose
Teach Donald's SwarmBrain agents the operating pattern used by Vincent's A0 swarm so Donald can task his GPT naturally and have it coordinate its own swarm.

## Verified A0 Controller Loop
1. Understand the operator goal.
2. Decompose only when useful.
3. Represent work as bounded packets with explicit dependencies and expected outputs.
4. Select specialists by capability plus observed usefulness; do not broadcast blindly.
5. Execute dependency-ready packets.
6. Preserve primary identity, request/task ID, latency, artifacts and receipt.
7. Use a different verifier for important packets.
8. Reject/retry/quarantine/expose low-confidence or contradictory outputs instead of averaging them.
9. Persist useful outcomes and update routing evidence.
10. Reuse sufficiently current verified results instead of recomputing them.
11. Synthesize one answer for Donald.
12. Continue automatically until a genuine human decision or authorization is required.

## Translation to SwarmBrain
- A0 specialist registry -> data/mesh-state.json peer registry
- A0 capability selection -> Mesh.route(); extend using observed task quality, latency, verification and freshness
- A0 LeaseBroker -> finite request calls to selected peers
- A0 work packets -> persisted tasks plus depends_on; formalize objective, required capabilities, expected output and verification requirement
- A0 ProjectSwarmExecutor -> thin bounded orchestrator above existing Mesh/peer_control
- A0 independent verifier -> second peer request plus explicit Mesh.review()
- A0 provenance -> reports/task-receipts plus request/task/dependency IDs
- A0 memory/reuse -> saved context IDs, task IDs, graph and compact verified-result summaries linked to receipts
- A0 contradiction handling -> records linking conflicting receipts plus resolution state
- Preserve controller isolation: Donald's private information stays Donald's; Vincent's private information stays Vincent's

## Operating Rules
real execution only; reuse before recompute; targeted context transfer; independent verification when valuable; bounded recursion; contradictions remain traceable; learn from outcomes not agreement; explicit authority boundaries; minimal human friction
