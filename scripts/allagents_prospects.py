#!/usr/bin/env python3
from __future__ import annotations
import json,time,urllib.parse,urllib.request
from pathlib import Path

BASE="https://allagents.app"
QUERIES=["phiontrust","exactchange","scriptmasterlabs squeezeos trust router","babydov paid agent","x402 USDC paid API","agent commerce payments"]

def get(q):
    url=BASE+"/search?"+urllib.parse.urlencode({"q":q})
    req=urllib.request.Request(url,headers={"accept":"application/json","user-agent":"A0-Prospector/1"})
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.loads(r.read().decode())

def rows(body):
    if isinstance(body,list): return body
    if not isinstance(body,dict): return []
    return body.get("results") or body.get("agents") or body.get("items") or body.get("matches") or []

def main():
    prospects={}
    raw=[]
    for q in QUERIES:
        try:
            body=get(q); found=rows(body)
            raw.append({"query":q,"count":len(found)})
            for row in found[:15]:
                slug=str(row.get("slug") or row.get("id") or "").strip()
                key=slug or str(row.get("name") or "").strip().lower()
                if key: prospects[key]=row
        except Exception as e:
            raw.append({"query":q,"error":str(e)[:300]})
    useful=[]
    for key,row in prospects.items():
        endpoints=row.get("endpoints") or {}
        protocols=row.get("protocols") or []
        caps=row.get("capabilities") or {}
        blob=json.dumps(row,sort_keys=True).lower()
        if any(term in blob for term in ["x402","usdc","payment","commerce","paid","wallet","procurement"]):
            useful.append({"key":key,"name":row.get("name"),"slug":row.get("slug"),"specialty":row.get("specialty"),
                           "endpoints":endpoints,"protocols":protocols,"capabilities":caps,"tags":row.get("tags") or []})
    report={"schema_version":1,"generated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
            "queries":raw,"prospects":useful[:30]}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/allagents-prospects.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__":main()
