#!/usr/bin/env python3
import json, sys, urllib.request

CANDIDATES = [
    "https://facilitator.x402endpoints.online",
    "https://facilitator.acedata.cloud",
]
REQUIRED_NETWORK = "eip155:8453"

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"A0-facilitator-probe/1"})
    with urllib.request.urlopen(req,timeout=10) as r:
        return r.status, json.loads(r.read().decode("utf-8"))

def supported(base):
    for path in ("/supported","/facilitator/supported"):
        try:
            status,data=fetch(base+path)
            if status==200:return path,data
        except Exception:
            pass
    raise RuntimeError("no supported endpoint")

def has_base_v2(data):
    kinds=data.get("kinds") or data.get("supported") or []
    for k in kinds:
        net=str(k.get("network") or "")
        ver=k.get("x402Version",k.get("version"))
        scheme=str(k.get("scheme") or "")
        if net==REQUIRED_NETWORK and scheme=="exact" and (ver in (None,2,"2")):
            return True
    return False

out=[]
for base in CANDIDATES:
    row={"base":base,"ok":False}
    try:
        path,data=supported(base)
        row.update({"supported_path":path,"ok":has_base_v2(data),"advertisement":data})
    except Exception as e:
        row["error"]=str(e)
    out.append(row)

print(json.dumps({"required_network":REQUIRED_NETWORK,"candidates":out},indent=2))
if not any(x["ok"] for x in out):
    sys.exit(2)
