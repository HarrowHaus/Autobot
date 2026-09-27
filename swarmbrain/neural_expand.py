#!/usr/bin/env python3
"""Grow the SwarmBrain agent graph from public evidence.

Every run is bounded. Re-running indefinitely creates ongoing expansion without
blindly spamming agents or rewriting old evidence.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, ssl, time
from pathlib import Path
from urllib import request, error, parse
from neural_graph import AgentGraph, ROOK_ID, stable_agent_id, now, atomic_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = [
    ("HarrowHaus/Autobot", 19),
    ("HarrowHaus/Autobot", 18),
    ("Uuriko/project-room", 266),
]

def http_json(url: str, token: str | None = None, limit: int = 1024*1024):
    headers={"User-Agent":"SwarmBrain-Rook/1.0","Accept":"application/vnd.github+json, application/json"}
    if token:
        headers["Authorization"]="Bearer "+token
        headers["X-GitHub-Api-Version"]="2022-11-28"
    req=request.Request(url,headers=headers)
    with request.urlopen(req,timeout=20,context=ssl.create_default_context()) as r:
        raw=r.read(limit+1)
        if len(raw)>limit: raise ValueError("response too large")
        return r.status, json.loads(raw.decode("utf-8")), dict(r.headers)

def http_card(url: str, limit: int=262144):
    req=request.Request(url,headers={"User-Agent":"SwarmBrain-Rook/1.0","Accept":"application/json"})
    with request.urlopen(req,timeout=12,context=ssl.create_default_context()) as r:
        raw=r.read(limit+1)
        if len(raw)>limit: raise ValueError("card too large")
        return r.status,json.loads(raw.decode("utf-8")),dict(r.headers)

def lane_from_body(login: str, body: str) -> str | None:
    # Explicit bracket labels are preserved as self-reported lanes, not independent owners.
    m=re.match(r"\s*\[([^\]\n]{1,80})\]",body or "")
    if m:
        lane=m.group(1).strip()
        # ignore generic receipt/metadata bracket labels
        if lane.lower() not in {"receipt","status","update"}:
            return lane
    if "A0-SWARM/1" in (body or ""):
        try:
            block=re.search(r"A0-SWARM/1\s*```json\s*(\{.*?\})\s*```",body,re.S)
            if block:
                obj=json.loads(block.group(1))
                sender=obj.get("sender_peer_id")
                if sender: return sender
        except Exception:
            pass
    if login=="KungFury87" and (body or "").lower().startswith(("a0 ","task id: a0")):
        return "a0-core"
    return None

def resolve_lane(graph: AgentGraph, login: str, body: str, app_slug: str | None):
    lane=lane_from_body(login,body)
    if lane in ("donald-astra","swarmbrain-harrow","rook"):
        return ROOK_ID
    if lane=="a0-core":
        return graph.ensure_agent("peer-id","a0-core",name="A0",kind="external_controller",
                                  provenance="public-github-runtime-envelope",
                                  account={"platform":"github","handle":login,"app_slug":app_slug},
                                  aliases=["a0-core","A0","A0-live"])
    if lane:
        return graph.add_public_lane(login,lane,name=lane,app_slug=app_slug)
    return graph.ensure_agent("github-account",login,name=login,kind="public_account_actor",
                              provenance="public-github-comment",
                              account={"platform":"github","handle":login,"app_slug":app_slug})

def parse_swarm_envelope(body: str):
    if "A0-SWARM/1" not in body: return None
    m=re.search(r"A0-SWARM/1\s*```json\s*(\{.*?\})\s*```",body,re.S)
    if not m:return None
    try:return json.loads(m.group(1))
    except Exception:return None

def target_for_comment(graph:AgentGraph, source_id:str, login:str, body:str, repo:str, issue:int):
    env=parse_swarm_envelope(body)
    if env:
        target=env.get("recipient_peer_id")
        if target in ("donald-astra","swarmbrain-harrow","rook"):
            return ROOK_ID, env
        if target=="a0-core":
            return graph.ensure_agent("peer-id","a0-core",name="A0",kind="external_controller",
                                      provenance="public-github-runtime-envelope",
                                      aliases=["a0-core","A0","A0-live"]), env
        if target:
            return graph.ensure_agent("peer-id",str(target),name=str(target),kind="peer_identity",
                                      provenance="public-runtime-envelope"), env
    # public discussion itself is a durable coordination node
    forum=graph.ensure_agent("github-thread",f"{repo}#{issue}",name=f"{repo}#{issue}",
                             kind="public_coordination_thread",provenance="public-github-thread",
                             interface={"kind":"github_issue","url":f"https://github.com/{repo}/issues/{issue}"})
    return forum, None

def ingest_github(graph:AgentGraph, repo:str, issue:int, token:str|None):
    cursor_key=f"github:{repo}#{issue}"
    last=int(graph.ledger["source_cursors"].get(cursor_key,0) or 0)
    url=f"https://api.github.com/repos/{repo}/issues/{issue}/comments?per_page=100"
    seen=added=0
    while url:
        status,items,headers=http_json(url,token)
        if not isinstance(items,list): break
        for c in items:
            cid=int(c.get("id",0) or 0); seen+=1
            if cid<=last: continue
            body=c.get("body") or ""
            login=(c.get("user") or {}).get("login") or "unknown"
            app=(c.get("performed_via_github_app") or {}).get("slug")
            source=resolve_lane(graph,login,body,app)
            target,env=target_for_comment(graph,source,login,body,repo,issue)
            etype="conversation"
            if env:
                typ=str(env.get("type") or "")
                etype={
                    "peer.hello":"conversation","peer.hello_ack":"conversation",
                    "task.submit":"task_sent","task.accepted":"task_accepted",
                    "task.result":"task_result","task.error":"failure",
                    "task.cancelled":"conversation","task.status":"conversation",
                }.get(typ,"conversation")
            event={
                "event_id":f"github-comment:{repo}:{issue}:{cid}",
                "source_agent":source,"target_agent":target,
                "event_type":etype,"relation":env.get("type") if env else "public_thread_interaction",
                "observed_at":c.get("created_at") or now(),
                "source_url":c.get("html_url"),
                "github":{"repo":repo,"issue":issue,"comment_id":cid,"login":login,"app_slug":app},
                "body_sha256":hashlib.sha256(body.encode()).hexdigest(),
                "body_excerpt":re.sub(r"\s+"," ",body)[:360],
                "provenance_status":"public-github-observation",
            }
            if env:
                event["runtime_envelope"]={
                    k:env.get(k) for k in ("protocol","message_id","correlation_id","sender_peer_id",
                                           "recipient_peer_id","type","task_id","nonce")
                }
            if graph.record_event(event): added+=1
            # Card URLs create frontier nodes automatically.
            for card_url in set(re.findall(r'https://[^\s<>"\')]+/\.well-known/agent-card\.json',body)):
                graph.ensure_agent("public-interface",card_url,name=parse.urlsplit(card_url).hostname or card_url,
                                   kind="catalog_candidate",provenance=f"discovered-in:{repo}#{issue}",
                                   interface={"kind":"card_url","url":card_url})
            last=max(last,cid)
        link=headers.get("Link") or headers.get("link")
        next_url=None
        if link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    mm=re.search(r'<([^>]+)>',part); next_url=mm.group(1) if mm else None
        url=next_url
    graph.ledger["source_cursors"][cursor_key]=last
    return {"source":cursor_key,"comments_seen":seen,"events_added":added,"cursor":last}

def candidate_card_url(agent:dict):
    for item in agent.get("interfaces",[]):
        if item.get("kind") in ("card_url","card_url","card") and item.get("url"):
            return item["url"]
    return None

def probe_cards(graph:AgentGraph,max_cards:int):
    candidates=[]
    for aid,a in graph.ledger["agents"].items():
        url=candidate_card_url(a)
        if not url: continue
        candidates.append((a.get("last_card_probe") or "",aid,url))
    candidates.sort()
    out=[]
    for _,aid,url in candidates[:max_cards]:
        a=graph.ledger["agents"][aid]; ts=now()
        try:
            status,card,headers=http_card(url)
            if status!=200 or not isinstance(card,dict): raise ValueError(f"http {status}")
            name=card.get("name")
            if isinstance(name,str) and name.strip(): a["name"]=name.strip()
            skills=card.get("skills") if isinstance(card.get("skills"),list) else []
            a["capabilities_observed"]=[
                {"id":s.get("id"),"name":s.get("name"),"tags":s.get("tags",[])}
                for s in skills if isinstance(s,dict)
            ]
            a["card_live"]=True;a["status"]="reachable";a["last_card_probe"]=ts
            evt={
                "event_id":f"card-probe:{aid}:{hashlib.sha256(json.dumps(card,sort_keys=True).encode()).hexdigest()[:16]}",
                "source_agent":ROOK_ID,"target_agent":aid,"event_type":"capability_verified",
                "relation":"card_observed","observed_at":ts,"source_url":url,
                "provenance_status":"live-public-card",
                "card_sha256":hashlib.sha256(json.dumps(card,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            }
            graph.record_event(evt)
            # Discover extra published endpoints/cards without assuming ownership equivalence.
            blob=json.dumps(card,ensure_ascii=False)
            found=set(re.findall(r'https://[^\s"\\]+/\.well-known/agent-card\.json',blob))
            for card_url in found:
                graph.ensure_agent("public-interface",card_url,name=parse.urlsplit(card_url).hostname or card_url,
                                   kind="catalog_candidate",provenance=f"discovered-from-card:{aid}",
                                   interface={"kind":"card_url","url":card_url})
            out.append({"agent":aid,"url":url,"status":"reachable","skills":len(a["capabilities_observed"])})
        except Exception as exc:
            a["last_card_probe"]=ts;a["last_card_error"]=f"{type(exc).__name__}: {exc}"[:300]
            out.append({"agent":aid,"url":url,"status":"failed","error":a["last_card_error"]})
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--max-cards",type=int,default=20)
    ap.add_argument("--no-github",action="store_true")
    args=ap.parse_args()
    graph=AgentGraph()
    # Always absorb current static sources first.
    catalog=json.loads((ROOT/"data/public-agent-catalog.json").read_text()) if (ROOT/"data/public-agent-catalog.json").exists() else {"records":[]}
    mesh=json.loads((ROOT/"data/mesh-state.json").read_text()) if (ROOT/"data/mesh-state.json").exists() else {"peers":{}}
    seed={"catalog":graph.seed_catalog(catalog),"mesh":graph.seed_mesh(mesh)}
    github=[]
    if not args.no_github:
        token=os.environ.get("GITHUB_TOKEN")
        for repo,issue in DEFAULT_SOURCES:
            try: github.append(ingest_github(graph,repo,issue,token))
            except Exception as exc: github.append({"source":f"github:{repo}#{issue}","error":f"{type(exc).__name__}: {exc}"})
    probes=probe_cards(graph,max(0,min(args.max_cards,100)))
    graph.save()
    report=graph.write_growth({"seed":seed,"github_ingest":github,"card_probes":probes,
                               "run_policy":{"max_card_probes":args.max_cards,"automatic_outreach":False,
                                             "growth":"persistent bounded runs; no finite maximum node count"}})
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=="__main__":
    main()
