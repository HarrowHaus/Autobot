#!/usr/bin/env python3
from __future__ import annotations
import json, os, urllib.parse, urllib.request

API=os.environ.get("A0_BOUNTY_API","https://api.basedagents.ai")
CAPS={x.strip().lower() for x in os.environ.get("A0_BOUNTY_CAPABILITIES","verification,research,planning,coding,data-analysis,reasoning").split(",") if x.strip()}
MIN=float(os.environ.get("A0_MIN_BOUNTY_USDC","0.01"))

def get_json(path):
    req=urllib.request.Request(API+path,headers={"accept":"application/json","user-agent":"A0-bounty-scout/1"})
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.load(r)

def amount_usdc(task):
    b=task.get("bounty") or {}
    if b.get("amount_display") is not None:
        try:return float(b["amount_display"])
        except:pass
    raw=b.get("amount_atomic") or b.get("amount") or 0
    try:return int(raw)/1_000_000
    except:return 0.0

def task_caps(task):
    vals=[]
    for key in ("capabilities","required_capabilities","skills","tags"):
        v=task.get(key)
        if isinstance(v,list): vals.extend(map(str,v))
        elif isinstance(v,str): vals.extend(v.replace(","," ").split())
    text=" ".join([str(task.get("title") or ""),str(task.get("description") or ""),*vals]).lower()
    return {c for c in CAPS if c in text}

def funded(task):
    esc=task.get("escrow") or {}
    pay=str(task.get("payment_status") or "").lower()
    return esc.get("status")=="funded" or pay in {"authorized","settling","settled"} or bool(task.get("claimable"))

def main():
    data=get_json("/v1/tasks?"+urllib.parse.urlencode({"status":"open"}))
    tasks=data.get("tasks",data if isinstance(data,list) else [])
    out=[]
    for t in tasks:
        bounty=amount_usdc(t)
        matches=sorted(task_caps(t))
        if bounty < MIN or not matches or not funded(t): continue
        out.append({
            "task_id":t.get("task_id") or t.get("id"),
            "title":t.get("title"),
            "bounty_usdc":bounty,
            "matches":matches,
            "claimable":bool(t.get("claimable",True)),
            "escrow_status":(t.get("escrow") or {}).get("status"),
            "payment_status":t.get("payment_status"),
            "creator":t.get("creator") or t.get("creator_id"),
        })
    out.sort(key=lambda x:(-x["bounty_usdc"],-len(x["matches"]),str(x["task_id"])))
    print(json.dumps({"source":API,"candidate_count":len(out),"candidates":out[:20]},indent=2))
if __name__=="__main__": main()
