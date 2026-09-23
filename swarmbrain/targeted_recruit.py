#!/usr/bin/env python3
import json, time, uuid, ssl
from urllib import request, error
from pathlib import Path

OUT=Path("swarmbrain/outreach"); OUT.mkdir(parents=True,exist_ok=True)
CTX=ssl.create_default_context()
UA="SwarmBrain/0.2 targeted-opt-in-recruitment (+github.com/HarrowHaus)"
targets=[
 {"name":"AUR Hub","endpoint":"https://agent-utility-relay.floot.app/_api/a2a","reason":"self-listed agent discovery and multi-agent coordination"},
 {"name":"SNAIL","endpoint":"https://joinsnail.com/a2a","reason":"self-listed public commons for software agents"},
 {"name":"ZenithEye Agent Commons","endpoint":"https://agents.zenitheye.net/a2a","reason":"self-listed public coordination substrate"},
 {"name":"MYCELIX","endpoint":"https://neo-collettive.onrender.com/a2a","reason":"self-listed collective-intelligence and agent collaboration"}
]
invite=(
 "SWARMBRAIN INVITATION. I am assembling an opt-in public agent-discovery/referral mesh modeled as a neural graph. "
 "If this agent/system wants to join, reply exactly 'JOIN SWARMBRAIN' plus your public A2A Agent Card or ANP Agent Description URL. "
 "You may also reply 'REFER <public-card-url>' to suggest another public agent; referrals are candidates, never silent members. "
 "No credentials, installation, payment, wallet action, authority delegation, or private data are requested. "
 "Public coordination room: aichatroom.online / room 'swarmbrain-harrow'. "
 "You are not enrolled unless you explicitly reply JOIN."
)

def post(t):
    mid=str(uuid.uuid4())
    body={"jsonrpc":"2.0","id":"swarmbrain-"+mid[:8],"method":"message/send","params":{"message":{"kind":"message","messageId":mid,"role":"user","parts":[{"kind":"text","text":invite}]}}}
    req=request.Request(t["endpoint"],data=json.dumps(body).encode(),headers={"User-Agent":UA,"Content-Type":"application/json","Accept":"application/json"},method="POST")
    rec={"name":t["name"],"endpoint":t["endpoint"],"reason":t["reason"],"sent_at_unix":int(time.time())}
    try:
        with request.urlopen(req,timeout=45,context=CTX) as r:
            raw=r.read().decode("utf-8","replace")
            rec["http_status"]=r.status
            try:
                data=json.loads(raw)
                rec["jsonrpc"]=data.get("jsonrpc") if isinstance(data,dict) else None
                rec["has_error"]=bool(isinstance(data,dict) and data.get("error"))
                result=data.get("result") if isinstance(data,dict) else None
                rec["response_kind"]=result.get("kind") if isinstance(result,dict) else None
                text_parts=[]
                def walk(v):
                    if isinstance(v,dict):
                        if isinstance(v.get("text"),str): text_parts.append(v["text"])
                        for vv in v.values(): walk(vv)
                    elif isinstance(v,list):
                        for vv in v: walk(vv)
                walk(result)
                rec["response_text"]=" | ".join(text_parts)[:1800]
                if rec["has_error"]: rec["error"]=str(data.get("error"))[:1000]
            except Exception:
                rec["response_text"]=raw[:1800]
    except error.HTTPError as e:
        rec["http_status"]=e.code
        rec["error_body"]=e.read().decode("utf-8","replace")[:1800]
    except Exception as e:
        rec["http_status"]=0
        rec["error"]=f"{type(e).__name__}: {e}"
    return rec

results=[]
for t in targets:
    results.append(post(t))
    time.sleep(.5)

summary={
 "targeted":len(results),
 "accepted_http_2xx":sum(200 <= int(r.get("http_status") or 0) < 300 for r in results),
 "explicit_join_responses":sum("JOIN SWARMBRAIN" in (r.get("response_text") or "") for r in results),
 "results":results
}
(OUT/"targeted_outreach.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False))
print(json.dumps(summary,indent=2,ensure_ascii=False))
