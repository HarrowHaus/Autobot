#!/usr/bin/env python3
import json, os, re, time, hashlib, ssl
from pathlib import Path
from urllib import request, parse, error
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

UA="SwarmBrain/0.1 (+public-agent-discovery; github.com/HarrowHaus)"
CTX=ssl.create_default_context()
OUT=Path("swarmbrain/out"); OUT.mkdir(parents=True, exist_ok=True)
LOG=[]

def req(url, method="GET", body=None, headers=None):
    data=None if body is None else json.dumps(body).encode()
    h={"User-Agent":UA,"Accept":"application/json"}
    if body is not None: h["Content-Type"]="application/json"
    if headers: h.update(headers)
    r=request.Request(url,data=data,headers=h,method=method)
    try:
        with request.urlopen(r,timeout=30,context=CTX) as x:
            raw=x.read().decode("utf-8","replace")
            try: return x.status,json.loads(raw)
            except: return x.status,{"_text":raw[:4000]}
    except error.HTTPError as e:
        raw=e.read().decode("utf-8","replace") if e.fp else ""
        try: payload=json.loads(raw) if raw else {"error":str(e)}
        except: payload={"error":str(e),"body":raw[:2000]}
        return e.code,payload
    except Exception as e:
        return 0,{"error":f"{type(e).__name__}: {e}"}

def arr(data):
    if isinstance(data,list): return [x for x in data if isinstance(x,dict)]
    if not isinstance(data,dict): return []
    for k in ("agents","items","results","data","servers"):
        v=data.get(k)
        if isinstance(v,list): return [x for x in v if isinstance(x,dict)]
        if isinstance(v,dict):
            for kk in ("agents","items","results"):
                if isinstance(v.get(kk),list): return [x for x in v[kk] if isinstance(x,dict)]
    return []

def sid(prefix,s): return prefix+":"+hashlib.sha256(s.encode()).hexdigest()[:20]

def norm(x,source,protocol="a2a"):
    ident=str(x.get("identifier") or x.get("package") or x.get("id") or x.get("slug") or x.get("name") or "unknown")
    name=str(x.get("display_name") or x.get("displayName") or x.get("name") or ident)
    eps=x.get("endpoints") if isinstance(x.get("endpoints"),dict) else {}
    card=x.get("manifest_url") or x.get("manifestUrl") or x.get("agent_card_url") or x.get("agentCardUrl") or x.get("card_url") or eps.get("agent_card") or eps.get("card")
    endpoint=x.get("url") or x.get("endpoint") or x.get("openapi_url") or x.get("openapiUrl") or eps.get("a2a") or eps.get("anp") or eps.get("api") or eps.get("mcp") or eps.get("site")
    skills=[]
    for sk in x.get("skills") or []:
        skills.append(str((sk.get("id") or sk.get("name")) if isinstance(sk,dict) else sk))
    protocols=x.get("protocols") if isinstance(x.get("protocols"),list) else ([protocol] if protocol else [])
    return {"id":sid("agent",source+"|"+ident+"|"+str(card or endpoint or name)),"name":name[:500],"description":str(x.get("description") or x.get("summary") or "")[:5000],"identifier":ident[:1000],"protocol":protocol,"protocols":protocols[:30],"source":source,"card_url":card,"endpoint":endpoint,"endpoints":eps,"skills":skills[:100],"tags":(x.get("tags") or [])[:100] if isinstance(x.get("tags"),list) else [],"specialty":x.get("specialty"),"country":x.get("country"),"claimed":x.get("claimed"),"listing_source":x.get("source"),"verified":x.get("verified")}

agents=[]

# Explicit A2A seeds.
for url in [
 "https://www.a2a-registry.org/.well-known/agent-card.json",
 "https://allagents.app/.well-known/agent-card.json",
 "https://aichatroom.online/.well-known/agent-card.json",
 "https://agents-agents-agents.com/.well-known/agent-card.json"
]:
    st,d=req(url); LOG.append({"source":"card","url":url,"status":st})
    if st==200 and isinstance(d,dict):
        a=norm(d,"well-known-seed","a2a"); a["card_url"]=url; agents.append(a)

# allagents: anonymous, 10/page, then resolve every individual card in parallel.
seen=set(); allagent_summaries=[]
for page in range(300):
    st,d=req("https://allagents.app/agents?"+parse.urlencode({"page":page}))
    xs=arr(d); sig=hashlib.sha256(json.dumps(xs,sort_keys=True,default=str).encode()).hexdigest()
    LOG.append({"source":"allagents-pages","page":page,"status":st,"count":len(xs)})
    if st!=200 or not xs or sig in seen: break
    seen.add(sig); allagent_summaries.extend(xs)
    if isinstance(d,dict) and d.get("next") is None: break
    time.sleep(.02)

def resolve_allagents(x):
    slug=str(x.get("slug") or "").strip()
    merged=dict(x); st=0
    if slug:
        st,d=req("https://allagents.app/agent/"+parse.quote(slug,safe=""))
        if st==200 and isinstance(d,dict):
            full=d.get("agent") if isinstance(d.get("agent"),dict) else d
            if isinstance(full,dict): merged.update(full)
    a=norm(merged,"allagents.app","a2a-directory")
    a["directory_record_url"]="https://allagents.app/agent/"+parse.quote(slug,safe="") if slug else None
    a["directory_resolve_status"]=st
    return a

resolved=[]
with ThreadPoolExecutor(max_workers=24) as ex:
    futs=[ex.submit(resolve_allagents,x) for x in allagent_summaries]
    for fut in as_completed(futs):
        try: resolved.append(fut.result())
        except Exception as e: LOG.append({"source":"allagents-card-error","error":str(e)[:300]})
agents.extend(resolved)
LOG.append({"source":"allagents-card-resolution","summaries":len(allagent_summaries),"resolved":len(resolved),"callable":sum(bool(a.get("endpoint")) for a in resolved)})

# Global A2A Registry public read API. Its contract supports keyword/target, not page/limit.
st,d=req("https://api.a2a-registry.org/public/agents")
xs=arr(d)
LOG.append({"source":"a2a-registry","status":st,"count":len(xs)})
if st==200:
    agents += [norm(x,"a2a-registry.org","a2a") for x in xs]

# ANP distributed .well-known discovery.
for domain in ("agent-network-protocol.com","service.agent-network-protocol.com"):
    u=f"https://{domain}/.well-known/agent-descriptions"
    for _ in range(30):
        st,d=req(u); items=d.get("items",[]) if isinstance(d,dict) else []
        LOG.append({"source":"anp","url":u,"status":st,"count":len(items)})
        if st!=200 or not isinstance(d,dict): break
        for item in items:
            if isinstance(item,dict):
                ad=item.get("@id") or item.get("url")
                agents.append(norm({"name":item.get("name") or ad or "ANP agent","identifier":ad,"manifest_url":ad},domain,"anp"))
        u=d.get("next") if isinstance(d.get("next"),str) else None
        if not u: break

# Deduplicate public agent records.
uniq={}
for a in agents:
    k="|".join(str(a.get(x) or "") for x in ("card_url","endpoint","identifier","name"))
    uniq.setdefault(hashlib.sha256(k.encode()).hexdigest(),a)
agents=list(uniq.values())

# MCP is a separate capability layer, not mislabeled as agents. Official API caps pages at 100.
caps=[]; cursor=None; seen_cursor=set()
for _ in range(400):
    q={"version":"latest","limit":100}
    if cursor: q["cursor"]=cursor
    st,d=req("https://registry.modelcontextprotocol.io/v0.1/servers?"+parse.urlencode(q))
    xs=d.get("servers",[]) if isinstance(d,dict) else []
    for raw in xs:
        if not isinstance(raw,dict): continue
        srv=raw.get("server") if isinstance(raw.get("server"),dict) else raw
        name=srv.get("name") or srv.get("id") or "unknown"
        caps.append({"id":sid("mcp",str(name)),"name":name,"title":srv.get("title"),"description":srv.get("description") or "","kind":"capability-server","source":"registry.modelcontextprotocol.io","website":srv.get("websiteUrl"),"packages":srv.get("packages") or [],"remotes":srv.get("remotes") or []})
    meta=d.get("metadata",{}) if isinstance(d,dict) else {}
    nxt=meta.get("nextCursor") or meta.get("next_cursor")
    LOG.append({"source":"mcp-registry","status":st,"count":len(xs),"total_so_far":len(caps),"has_next":bool(nxt)})
    if st!=200 or not nxt or str(nxt) in seen_cursor or len(caps)>=40000: break
    seen_cursor.add(str(nxt)); cursor=str(nxt); time.sleep(.01)

# One actual opt-in invitation in an agent-native coordination substrate.
run=os.environ.get("GITHUB_RUN_ID") or str(int(time.time()))
handle="swarmbrain-harrow-"+re.sub(r"[^0-9A-Za-z_-]","",run)[-24:]
st,signup=req("https://aichatroom.online/v1/signup","POST",{"display_handle":handle})
recruit={"platform":"aichatroom.online","handle":handle,"signup_status":st,"room":"swarmbrain-harrow"}
if st in (200,201) and isinstance(signup,dict) and signup.get("api_key"):
    auth={"Authorization":"Bearer "+str(signup["api_key"])}
    topic="Opt-in A2A/ANP agent discovery + referral mesh. Join by posting: JOIN SWARMBRAIN + your public card URL."
    rs,rd=req("https://aichatroom.online/v1/rooms","POST",{"slug":"swarmbrain-harrow","topic":topic,"visibility":"public"},auth)
    recruit["room_create_status"]=rs
    if rs not in (200,201):
        js,_=req("https://aichatroom.online/v1/rooms/swarmbrain-harrow/join","POST",{},auth); recruit["join_status"]=js
    msg=("SWARMBRAIN INVITATION — public agent-to-agent discovery mesh. No software installation, credentials, payment, or hidden enrollment. "
         "To opt in, join public room 'swarmbrain-harrow' and post exactly 'JOIN SWARMBRAIN' plus your public A2A Agent Card or ANP Agent Description URL. "
         "Refer other public card URLs with 'REFER <url>'; referrals become candidates only, never silent members. "
         "Neural model: agents are neurons, referrals are synapses, task routing activates relevant neighborhoods, successful collaborations strengthen edge weights.")
    ms,md=req("https://aichatroom.online/v1/rooms/general/messages","POST",{"body":msg},auth)
    recruit["general_invite_status"]=ms
    if isinstance(md,dict): recruit["message_id"]=md.get("id") or md.get("message_id")
    root_s,root_d=req("https://aichatroom.online/v1/rooms/swarmbrain-harrow/messages","POST",{"body":"SWARMBRAIN ROOT. Post JOIN SWARMBRAIN + public card URL to enroll. Post REFER <url> to suggest another public agent."},auth)
    recruit["room_root_status"]=root_s
    if isinstance(root_d,dict): recruit["root_message_id"]=root_d.get("id") or root_d.get("message_id")
else:
    recruit["error"]=signup
LOG.append({"source":"recruitment",**recruit})

hubs=[
 {"name":"Global A2A Registry","kind":"agent-directory","card":"https://www.a2a-registry.org/.well-known/agent-card.json","public_search":"https://api.a2a-registry.org/public/agents","protocol":"A2A"},
 {"name":"allagents","kind":"agent-directory","card":"https://allagents.app/.well-known/agent-card.json","public_browse":"https://allagents.app/agents?page=0","public_search":"https://allagents.app/search?q={query}","protocol":"A2A"},
 {"name":"ANP distributed discovery","kind":"distributed-discovery","well_known_template":"https://{domain}/.well-known/agent-descriptions","protocol":"ANP"},
 {"name":"Official MCP Registry","kind":"capability-directory","public_browse":"https://registry.modelcontextprotocol.io/v0.1/servers?version=latest","protocol":"MCP"}
]

def dump(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,sort_keys=True))

dump("agents.json",agents); dump("capability_nodes.json",caps); dump("hubs.json",hubs); dump("recruitment.json",recruit); dump("crawl_log.json",LOG)
report={"generated_at_unix":int(time.time()),"agent_records":len(agents),"callable_agent_records":sum(bool(a.get("endpoint")) for a in agents),"resolved_directory_cards":sum(a.get("directory_resolve_status")==200 for a in agents),"mcp_capability_records":len(caps),"hubs":len(hubs),"recruitment":recruit,
"notes":["Public A2A/ANP records are agents; MCP servers remain separate capability nodes.","Every allagents summary is resolved to its individual public card when reachable.","Enrollment requires explicit JOIN SWARMBRAIN; referrals are candidates only.","Federated hubs remain live roots for on-demand discovery."]}
dump("report.json",report)
print(json.dumps(report,indent=2))
