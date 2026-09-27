#!/usr/bin/env python3
"""Reclassify known parser metadata markers without deleting historical events.\nRuns before each neural growth pass."""
from neural_graph import AgentGraph

INVALID = {
    "receipt","status","update","claim","sub","task","working","done",
    "blocked","pass","fail","progress","checkpoint","handoff","review",
}

def main():
    graph = AgentGraph()
    changed = []
    for aid, agent in graph.ledger.get("agents", {}).items():
        if agent.get("kind") != "public_agent_lane":
            continue
        labels = {str(agent.get("name") or "").strip().lower()}
        labels.update(str(x).strip().lower() for x in agent.get("aliases", []))
        if labels & INVALID:
            agent["prior_kind"] = "public_agent_lane"
            agent["kind"] = "invalid_identity_marker"
            agent["status"] = "retracted"
            agent["retracted_reason"] = "generic bracket metadata parsed as an agent lane"
            changed.append(aid)
    graph.save()
    print({"reclassified": len(changed), "ids": changed})

if __name__ == "__main__":
    main()
