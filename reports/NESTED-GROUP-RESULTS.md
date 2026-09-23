# SwarmBrain nested groups — live results

Generated: 2026-09-23T14:26:41Z

10 coordinator groups; 12 distinct peer leaves in the hierarchy; four hosted question-answering interfaces.

Readiness: 4 of four contributors returned, with synthesis state `response_received`.

## Group structure

```text
swarm
  reasoning
    design: multi-provider, llm-orchestrator
    critique: traced-claude, llm-orchestrator-2
    synthesis: multi-provider (same peer, reused path)
  research
    discovery: allagents, humanmirror, nulliverba
    commons: snail, zenitheye, sanctum
  assurance
    validation: attractor, gaip-broker
```

The five reasoning membership paths resolve to four contributor calls. The optional synthesis is one separately recorded reducer request, not another independent opinion.

## Actual readiness question

Answer in at most 160 words. A parent Research node contains Sources={A, Shared} and Counterexamples={B, Shared}. Shared answers once, B times out, and A disagrees with Shared. Design the coordinator result contract: give one dispatch rule, a compact data representation, one invariant, and one acceptance test. Preserve both paths to Shared and do not manufacture consensus. Answer the question only; no external actions or ongoing work.

## Returned synthesis

The coordinator contract design synthesizes rules from `multi-provider` and `traced-claude` for robust handling of diverse source responses and explicit disagreement:

**Dispatch Rule:** Query A, B, and Shared concurrently to ensure all paths are explored and results collected without prioritization.

**Compact Data Representation:** `{"A": "<A_response>", "Shared": "<Shared_response>", "B_status": "timeout", "A_disagrees_Shared": true/false}`. This captures individual source responses, B's explicit 'timeout' status, and the disagreement state between A and Shared without conflation or loss of information.

**Invariant:** The contract must always capture distinct, non-timeout outputs from all queried sources and explicitly report any disagreements without fabricating consensus.

**Acceptance Test:** The result is accepted if it contains A's original response, Shared's original response (where A's response is distinct from Shared's), and B's 'timeout' status, accurately reflecting the specified conditions while preserving all source data. 

**Unresolved Disagreements:**

Significant disagreements exist regarding the dispatch strategy and the interpretation of 'acceptance.' `llm-orchestrator` proposes a sequential dispatch (A, then B, then Shared), while `llm-orchestrator-2` suggests a conditional dispatch based on assumed pre-existing knowledge of A's disagreement with Shared, which is problematic for an initial dispatch rule and may not preserve all paths. Furthermore, `llm-orchestrator` and `llm-orchestrator-2` lean towards deriving a singular 'accepted' outcome or a preferred response from the disparate results. This conflicts directly with the instruction to 'not manufacture consensus' and 'preserve both paths,' as they imply selecting a preferred truth rather than presenting all facts. They also offer simpler data representations or more limited invariants compared to the more comprehensive approaches.

Contributing peer IDs: `multi-provider`, `llm-orchestrator`, `traced-claude`, `llm-orchestrator-2`.

## Evidence

The full answers, raw task receipts, group paths, and request IDs are linked in [the JSON results](NESTED-GROUP-RESULTS.json). The readiness run is [here](group-runs/nested-readiness-20260923.json). Thirty offline tests cover the core and group implementation.

## Use

Open an owner-authored issue titled `SwarmBrain group: <question title>` with a JSON body: 

```json
{"mode":"ask","group":"reasoning","question":"Your public question","synthesize":true}
```

The group can be addressed again; existing peers, contexts and previous task records are retained. Child groups can also be addressed directly.

## Scope

The four question endpoints reported gemini-2.5-flash / vertex-ai. Distinct hosted interfaces do not establish distinct model families or independent operators.

Group names assign organizational roles, not separately trained specialists. Calls currently dispatch sequentially against the existing single-writer store. The collected answers retain attribution; a synthesized response is model-generated and can be wrong. The research and assurance branches contain public services and return context or checks, not simulated reasoning agents. One provider quota error was retained as a paused peer; it is excluded from the reasoning group.
