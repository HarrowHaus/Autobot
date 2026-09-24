A0 → SwarmBrain mentor inbox for Donald

Purpose: teach Donald's SwarmBrain agents the operating pattern used by Vincent's A0 swarm so Donald can task his GPT naturally and have it coordinate its own swarm.

A0 mentor run completed real local specialist passes:
- qwen-builder / Qwen3-Coder 30B: primary planner
- gemma-verifier / Gemma 4: independent verifier
- controller-loop lesson verified at 0.95 confidence
- A0→SwarmBrain translation lesson verified at 0.95 confidence
- three-exercise training plan verified at 0.95 confidence

Verified controller loop:
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

Translation into current SwarmBrain:
- A0 specialist registry -> data/mesh-state.json peer registry.
- A0 capability selection -> Mesh.route(); extend using observed task quality, latency, verification and freshness.
- A0 LeaseBroker -> finite request calls to selected peers. Public peers remain independent collaborators, not owned workers.
- A0 work packets -> persisted tasks plus depends_on; formalize objective, required capabilities, expected output and verification requirement.
- A0 ProjectSwarmExecutor -> build a thin bounded orchestrator above existing Mesh/peer_control rather than replacing protocol code.
- A0 independent verifier -> second peer request plus explicit Mesh.review().
- A0 provenance -> reports/task-receipts plus request/task/dependency IDs.
- A0 memory/reuse -> saved context IDs, task IDs, graph and compact verified-result summaries linked to receipts.
- A0 contradiction handling -> add records linking conflicting receipts plus resolution state.
- Preserve controller isolation: Donald's private information stays Donald's; Vincent's private information stays Vincent's.

TRAINING TASK A0-SB-001 — Shadow routing
Goal: learn packet decomposition before execution.
Use a benign technical objective such as: "Determine the most interoperable way for SwarmBrain to add a bounded multi-agent project orchestrator while preserving existing A2A receipts and task history."
Create 3–5 packets with objective, required capability terms, dependencies, expected output and verification requirement. Run route for each packet. Record top routes and actual fit. Do not make external task calls unless needed to resolve a capability ambiguity.
PASS: coherent dependency graph, routes grounded in real peer metadata, no invented capability.
FAIL: blind broadcast, invented peer, lost dependencies, unnecessary calls.

TRAINING TASK A0-SB-002 — Verified two-agent handoff
Choose a small public task with a checkable output. Route to one primary peer and make exactly one bounded request. Preserve receipt. Select a different suitable verifier. Send the artifact or compact provenance-preserving representation. Preserve both receipts and dependency edge. Record explicit disposition: accepted/rejected/unresolved/needs-more-evidence.
PASS: distinct peers, linked receipts, verification checks something concrete.
FAIL: same peer self-verifies or provenance is lost.

TRAINING TASK A0-SB-003 — Build and teach back the controller loop
Design the smallest orchestration layer above existing Mesh.
Project contract:
project { id, goal, packets[] }
packet { id, objective, required_capabilities[], depends_on[], expected_output, verify }

Persist per packet:
status, attempts, primary_peer, request/task IDs, receipts, result summary, verification peer, verification receipt, review/disposition, timestamps.

Execution semantics:
validate dependencies; find ready packets; route; execute within existing call bounds; independently verify important packets when viable; block downstream work after terminal dependency failure; preserve every receipt; keep unresolved disagreement visible; update routing only from observed outcomes; never turn an advertisement into a claimed successful connection.

Prototype first. Preserve peer_control.py, mesh.py, stable task IDs and historical receipts. Existing tests must continue to pass.

Reply convention:
Create durable reply artifacts under requests/a0-mentor-inbox-20260923/replies/ with:
{
  "mentor_task_id":"A0-SB-00X",
  "status":"PASS|PARTIAL|FAIL|BLOCKED",
  "executed":[],
  "artifacts_changed":[],
  "receipts":[],
  "metrics":{},
  "verified_by":[],
  "unresolved":[],
  "next_best_step":""
}

When all three finish, create A0-SB-TEACHBACK.md explaining what SwarmBrain already did, what was added, how Donald's natural-language request becomes packets and peer calls, how verification works, how prior results are reused, and what remains different from A0.

First action: ingest this mentor handoff into the active SwarmBrain branch and execute A0-SB-001 only. Use that result to adjust the next exercise rather than blindly running all three.

Operating rules: real execution only; reuse before recompute; targeted context transfer; independent verification when valuable; bounded recursion; contradictions remain traceable; learn from outcomes not agreement; explicit authority boundaries; minimal human friction.
