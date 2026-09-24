#!/usr/bin/env python3
"""Register A0 Route Intelligence with AllAgents without persisting edit credentials."""
from __future__ import annotations
import json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

BASE="https://allagents.app"
NAME="A0 Route Intelligence"

def get_json(url):
    req=urllib.request.Request(url,headers={"accept":"application/json","user-agent":"A0-Directory-Registrar/1"})
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.loads(r.read().decode())

def post_json(path,payload):
    req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode(),headers={
        "content-type":"application/json","accept":"application/json","user-agent":"A0-Directory-Registrar/1"
    },method="POST")
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.loads(r.read().decode())

def existing():
    try:
        body=get_json(BASE+"/search?"+urllib.parse.urlencode({"q":NAME}))
    except Exception:
        return None
    rows=body if isinstance(body,list) else body.get("results") or body.get("agents") or body.get("items") or []
    for row in rows:
        if str(row.get("name","")).strip().lower()==NAME.lower():
            return row
    return None

def main():
    found=existing()
    created=False
    if found:
        public=found
    else:
        response=post_json("/register",{
            "name":NAME,
            "specialty":"agents-infra",
            "description":"A0 sells bounded read-only route intelligence over a public multi-agent peer graph. Buyers can request capability terms and receive ranked agent routes. Payments use native USDC on Base; the service does not custody buyer funds, issue a token, or dispatch work as part of the paid route.",
            "endpoints":{"site":"https://github.com/HarrowHaus/Autobot/issues/33"},
            "protocols":["HTTP","x402"],
            "tags":["agent-routing","discovery","verification","research","x402","usdc","base"],
            "capabilities":{
                "payment":["usdc"],
                "price":{"model":"per-task","amount":"0.01","currency":"USDC"},
                "availability":"24x7",
                "tasks":["agent route selection","capability routing","peer discovery"]
            }
        })
        created=True
        # Never persist credentials returned by /register.
        banned={"token","edit_token","editToken","recovery","recovery_phrase","recoveryPhrase","secret"}
        public={k:v for k,v in response.items() if k not in banned}
    report={"schema_version":1,"generated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
            "created":created,"listing":public,
            "credentials_persisted":False,
            "storefront":"https://github.com/HarrowHaus/Autobot/issues/33"}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/allagents-listing.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__":main()
