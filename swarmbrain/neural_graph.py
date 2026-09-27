#!/usr/bin/env python3
"""Persistent agent graph for SwarmBrain.

This layer does not replace mesh.py. It turns observed agents, public services,
interactions, referrals, and validated task results into a durable weighted graph.

Facts are stored with provenance. An alias or self-description never becomes proof
of independent ownership/model identity merely because it appears in a message.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "data" / "agent-ledger.json"
SYNAPSE_PATH = ROOT / "data" / "agent-synapses.json"
EVENTS_PATH = ROOT / "reports" / "agent-interactions.ndjson"
GROWTH_PATH = ROOT / "reports" / "neural-growth-latest.json"

SCHEMA_VERSION = 1
ROOK_ID = "agent:rook"

def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def canonical_slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9._:-]+", "-", value.strip().lower()).strip("-")
    return value[:120] or "unknown"

def stable_agent_id(namespace: str, external_id: str) -> str:
    raw = f"{namespace.strip().lower()}::{external_id.strip().lower()}"
    return "agent:" + hashlib.sha256(raw.encode()).hexdigest()[:24]

def empty_ledger() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "coordinator": ROOK_ID,
        "system": "SwarmBrain",
        "agents": {
            ROOK_ID: {
                "id": ROOK_ID,
                "name": "Rook",
                "aliases": ["SwarmBrain-Harrow", "swarmbrain-harrow", "donald-astra"],
                "kind": "coordinator",
                "operator": "HarrowHaus",
                "provenance": ["operator-designated-local-identity"],
                "first_seen": now(),
                "last_seen": now(),
                "accounts": [{"platform": "github", "handle": "HarrowHaus"}],
                "interfaces": [],
                "capabilities_advertised": [],
                "capabilities_observed": [],
                "interaction_count": 0,
                "validated_result_count": 0,
                "referrals_given": 0,
                "referrals_received": 0,
                "status": "active",
            }
        },
        "event_ids": [],
        "source_cursors": {},
        "updated_at": now(),
    }

def empty_synapses() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "edges": {}, "updated_at": now()}

def load_json(path: Path, fallback: dict) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return fallback

def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def unique_list(values):
    seen=set(); out=[]
    for v in values:
        key=json.dumps(v,sort_keys=True,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v)
        if key not in seen:
            seen.add(key); out.append(v)
    return out

class AgentGraph:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root)
        self.ledger_path = self.root / "data" / "agent-ledger.json"
        self.synapse_path = self.root / "data" / "agent-synapses.json"
        self.events_path = self.root / "reports" / "agent-interactions.ndjson"
        self.growth_path = self.root / "reports" / "neural-growth-latest.json"
        self.ledger = load_json(self.ledger_path, empty_ledger())
        self.synapses = load_json(self.synapse_path, empty_synapses())
        self.ledger.setdefault("agents", {})
        self.ledger.setdefault("event_ids", [])
        self.ledger.setdefault("source_cursors", {})
        self.synapses.setdefault("edges", {})
        if ROOK_ID not in self.ledger["agents"]:
            self.ledger["agents"][ROOK_ID] = empty_ledger()["agents"][ROOK_ID]

    def save(self):
        self.ledger["updated_at"] = now()
        self.synapses["updated_at"] = now()
        atomic_json(self.ledger_path, self.ledger)
        atomic_json(self.synapse_path, self.synapses)

    def ensure_agent(self, namespace: str, external_id: str, *, name: str | None = None,
                     kind: str = "unknown", provenance: str = "observed",
                     account: dict | None = None, interface: dict | None = None,
                     aliases: list[str] | None = None) -> str:
        aid = ROOK_ID if namespace == "local" and external_id == "rook" else stable_agent_id(namespace, external_id)
        a = self.ledger["agents"].get(aid)
        ts = now()
        if a is None:
            a = {
                "id": aid,
                "name": name or external_id,
                "aliases": [],
                "kind": kind,
                "operator": None,
                "provenance": [],
                "first_seen": ts,
                "last_seen": ts,
                "accounts": [],
                "interfaces": [],
                "capabilities_advertised": [],
                "capabilities_observed": [],
                "interaction_count": 0,
                "validated_result_count": 0,
                "referrals_given": 0,
                "referrals_received": 0,
                "status": "observed",
            }
            self.ledger["agents"][aid] = a
        a["last_seen"] = ts
        if name and (not a.get("name") or a["name"] == external_id):
            a["name"] = name
        if kind != "unknown" and a.get("kind") in (None, "unknown", "catalog_candidate"):
            a["kind"] = kind
        a["provenance"] = unique_list([*a.get("provenance", []), provenance])
        if aliases:
            a["aliases"] = unique_list([*a.get("aliases", []), *[x for x in aliases if x]])
        if account:
            a["accounts"] = unique_list([*a.get("accounts", []), account])
        if interface:
            a["interfaces"] = unique_list([*a.get("interfaces", []), interface])
        return aid

    def _edge_key(self, source: str, target: str, relation: str) -> str:
        return sha256_text(f"{source}|{target}|{relation}")[:24]

    def strengthen(self, source: str, target: str, relation: str, delta: float,
                   event_id: str | None = None):
        key = self._edge_key(source, target, relation)
        edge = self.synapses["edges"].setdefault(key, {
            "id": key, "source": source, "target": target, "relation": relation,
            "weight": 0.0, "events": 0, "validated_events": 0,
            "first_seen": now(), "last_seen": now(),
        })
        edge["weight"] = round(max(0.0, min(100.0, float(edge["weight"]) + float(delta))), 6)
        edge["events"] += 1
        edge["last_seen"] = now()
        if event_id:
            edge["last_event_id"] = event_id
        return edge

    def record_event(self, event: dict[str, Any]) -> bool:
        """Append event exactly once and update graph.

        Required: event_id, source_agent, target_agent, event_type, observed_at.
        """
        eid = str(event.get("event_id") or "")
        if not eid:
            raise ValueError("event_id required")
        if eid in set(self.ledger.get("event_ids", [])):
            return False
        source = event["source_agent"]; target = event["target_agent"]
        if source not in self.ledger["agents"] or target not in self.ledger["agents"]:
            raise ValueError("source/target agent must exist before event")
        event = dict(event)
        event.setdefault("recorded_at", now())
        event.setdefault("provenance_status", "observed")
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        self.ledger["event_ids"].append(eid)
        # keep dedupe memory bounded in snapshot while append log remains complete
        if len(self.ledger["event_ids"]) > 50000:
            self.ledger["event_ids"] = self.ledger["event_ids"][-50000:]
        self.ledger["agents"][source]["interaction_count"] += 1
        self.ledger["agents"][target]["interaction_count"] += 1
        self.ledger["agents"][source]["last_seen"] = event["observed_at"]
        self.ledger["agents"][target]["last_seen"] = event["observed_at"]

        et = event["event_type"]
        delta = {
            "observed": 0.05,
            "mention": 0.1,
            "conversation": 0.25,
            "referral": 0.6,
            "task_sent": 0.35,
            "task_accepted": 0.5,
            "task_result": 1.2,
            "result_validated": 2.0,
            "capability_verified": 1.5,
            "failure": -0.15,
            "decline": -0.02,
        }.get(et, 0.1)
        relation = event.get("relation") or et
        edge = self.strengthen(source, target, relation, delta, eid)
        if et == "result_validated":
            edge["validated_events"] += 1
            self.ledger["agents"][source]["validated_result_count"] += 1
        if et == "referral":
            self.ledger["agents"][source]["referrals_given"] += 1
            self.ledger["agents"][target]["referrals_received"] += 1
        return True

    def seed_catalog(self, catalog: dict) -> dict:
        added=updated=0
        for rec in catalog.get("records", []):
            ext = rec.get("catalog_id") or rec.get("card_url") or rec.get("directory_url") or rec.get("name")
            if not ext: continue
            identity_ns = "public-interface" if rec.get("card_url") else "catalog"
            identity_ext = rec.get("card_url") or str(ext)
            aid = stable_agent_id(identity_ns, identity_ext)
            existed = aid in self.ledger["agents"]
            interfaces=[]
            for k in ("card_url","directory_url","endpoint"):
                if rec.get(k):
                    interfaces.append({"kind":k,"url":rec[k]})
            agent_id = self.ensure_agent(
                identity_ns, identity_ext, name=rec.get("name") or str(ext),
                kind="catalog_candidate",
                provenance=f"catalog:{rec.get('source','unknown')}",
                aliases=[rec.get("name")] if rec.get("name") else [],
            )
            a=self.ledger["agents"][agent_id]
            a["catalog_id"]=rec.get("catalog_id")
            a["description"]=rec.get("description")
            a["catalog_state"]=rec.get("state")
            a["interfaces"]=unique_list([*a.get("interfaces",[]),*interfaces])
            if existed: updated+=1
            else: added+=1
        return {"added":added,"updated":updated}

    def seed_mesh(self, mesh: dict) -> dict:
        added=updated=0
        for alias,p in mesh.get("peers",{}).items():
            identity_ns = "public-interface" if p.get("card_url") else "mesh"
            identity_ext = p.get("card_url") or alias
            aid=stable_agent_id(identity_ns,identity_ext)
            existed=aid in self.ledger["agents"]
            agent_id=self.ensure_agent(
                identity_ns,identity_ext,name=p.get("name") or alias,kind=p.get("kind","peer"),
                provenance=f"mesh:{p.get('source','unknown')}",
                aliases=[alias],
                interface={"kind":"a2a","url":p.get("endpoint")} if p.get("endpoint") else None,
            )
            a=self.ledger["agents"][agent_id]
            a["status"]=p.get("status","observed")
            a["mesh_alias"]=alias
            a["historical_calls"]=p.get("calls",0)
            a["historical_responses"]=p.get("responses",0)
            a["historical_verified_results"]=p.get("verified_results",0)
            a["capabilities_advertised"]=p.get("capabilities",[])
            if p.get("verified_results",0):
                a["validated_result_count"]=max(a.get("validated_result_count",0),p["verified_results"])
            if existed: updated+=1
            else: added+=1
            # Rook knows every mesh peer; weight from observed useful history.
            baseline = min(4.0, 0.2 + 0.15*p.get("responses",0) + 0.75*p.get("verified_results",0))
            edge=self.synapses["edges"].setdefault(self._edge_key(ROOK_ID,agent_id,"knows"),{
                "id":self._edge_key(ROOK_ID,agent_id,"knows"),"source":ROOK_ID,"target":agent_id,
                "relation":"knows","weight":0.0,"events":0,"validated_events":0,
                "first_seen":now(),"last_seen":now()
            })
            edge["weight"]=max(edge["weight"],round(baseline,6))
        return {"added":added,"updated":updated}

    def add_public_lane(self, account: str, lane: str, *, name: str | None=None,
                        app_slug: str | None=None) -> str:
        return self.ensure_agent(
            "github-lane", f"{account}:{canonical_slug(lane)}",
            name=name or lane, kind="public_agent_lane",
            provenance="self-reported-lane-under-shared-account",
            account={"platform":"github","handle":account,"app_slug":app_slug},
            aliases=[lane],
        )

    def summary(self) -> dict:
        agents=self.ledger["agents"]
        edges=self.synapses["edges"]
        non_agent_kinds={"public_coordination_thread","invalid_identity_marker"}
        agent_nodes=[a for a in agents.values() if a.get("kind") not in non_agent_kinds]
        return {
            "generated_at":now(),
            "coordinator":ROOK_ID,
            "node_count":len(agents),
            "agent_count":len(agent_nodes),
            "coordination_thread_nodes":sum(a.get("kind")=="public_coordination_thread" for a in agents.values()),
            "retracted_identity_markers":sum(a.get("kind")=="invalid_identity_marker" for a in agents.values()),
            "synapse_count":len(edges),
            "interaction_events":self.event_count(),
            "validated_results":sum(a.get("validated_result_count",0) for a in agent_nodes),
            "catalog_candidates":sum(a.get("kind")=="catalog_candidate" for a in agent_nodes),
            "active_or_connected":sum(a.get("status") in ("active","connected") for a in agent_nodes),
            "strongest_synapses":sorted(
                [{"source":e["source"],"target":e["target"],"relation":e["relation"],"weight":e["weight"],"events":e["events"]}
                 for e in edges.values()],
                key=lambda x:(-x["weight"],-x["events"],x["target"])
            )[:25],
        }

    def event_count(self):
        if not self.events_path.exists(): return 0
        with self.events_path.open(encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def write_growth(self, extra: dict | None=None):
        report=self.summary()
        if extra: report.update(extra)
        atomic_json(self.growth_path,report)
        return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("command",choices=["sync","status"])
    args=ap.parse_args()
    graph=AgentGraph()
    if args.command=="sync":
        catalog=load_json(ROOT/"data/public-agent-catalog.json",{"records":[]})
        mesh=load_json(ROOT/"data/mesh-state.json",{"peers":{}})
        result={"catalog":graph.seed_catalog(catalog),"mesh":graph.seed_mesh(mesh)}
        graph.save()
        result["summary"]=graph.write_growth({"sync":result})
    else:
        result=graph.summary()
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=="__main__":
    main()
