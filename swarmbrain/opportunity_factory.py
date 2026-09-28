#!/usr/bin/env python3
"""Evidence-driven zero-capital product factory for SwarmBrain MerchantBrain."""
from __future__ import annotations
import argparse, html, json, math, re, time, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path

UA={"User-Agent":"SwarmBrain-MerchantBrain/1.0"}
STOP=set("the a an and or to of in for on with is are be this that from by as at it its your you ai agent agents".split())
def now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
def get(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=20) as r: return json.load(r)
def toks(s): return [x for x in re.findall(r"[a-z0-9][a-z0-9+._-]{2,}",str(s).lower()) if x not in STOP]
def collect():
    signals=[]
    queries=["autonomous agent","mcp server","agent commerce","ai workflow","open source ai"]
    for q in queries:
        try:
            data=get("https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=30&query="+urllib.parse.quote(q))
            for h in data.get("hits",[]):
                signals.append({"source":"hackernews","title":h.get("title") or "","url":h.get("url") or "","points":int(h.get("points") or 0),"comments":int(h.get("num_comments") or 0),"created_at":h.get("created_at")})
        except Exception as e: signals.append({"source":"error","title":q,"error":type(e).__name__})
    return signals
def rank(signals):
    df=Counter()
    for s in signals:
        for t in set(toks(s.get("title",""))): df[t]+=1
    rows=[]
    for term,count in df.items():
        related=[s for s in signals if term in toks(s.get("title",""))]
        sources=len(set(s["source"] for s in related if s["source"]!="error"))
        engagement=sum(math.log1p(s.get("points",0)+s.get("comments",0)) for s in related)
        score=round(count*4+sources*8+engagement,3)
        rows.append({"term":term,"score":score,"mentions":count,"source_count":sources,"examples":related[:5]})
    return sorted(rows,key=lambda x:(-x["score"],x["term"]))
def choose(ranked):
    # Require repeated observed demand; abstention is a valid autonomous decision.
    for r in ranked:
        if r["mentions"]>=3 and r["source_count"]>=1:
            return r
    return None
def manufacture(choice, ranked):
    if not choice: return {"status":"abstain","reason":"no opportunity passed evidence threshold","created_at":now()}
    term=choice["term"]
    evidence=[]
    for r in ranked[:20]:
        if r["term"]==term or any(term in toks(e.get("title","")) for e in r["examples"]):
            evidence.extend(r["examples"][:3])
    seen=set(); evidence=[e for e in evidence if not (e.get("url") in seen or seen.add(e.get("url")))]
    product={
      "schema_version":1,"status":"publishable","created_at":now(),
      "slug":re.sub(r"[^a-z0-9]+","-",term).strip("-")+"-signal-pack",
      "title":term.title()+" Signal Pack",
      "promise":"A compact machine-readable evidence pack showing current public discussion signals around "+term+".",
      "buyer":"builders and autonomous agents evaluating what to build next",
      "format":"JSON","price_atomic_usdc":"10000","price_display":"$0.01",
      "opportunity":choice,
      "payload":{"topic":term,"observed_at":now(),"evidence":evidence,"adjacent_signals":[{"term":r["term"],"score":r["score"],"mentions":r["mentions"]} for r in ranked[:12]]},
      "truth_boundary":"Public-signal research product; not a promise of demand, profit, or investment return."
    }
    return product
def write_site(product,out):
    out.mkdir(parents=True,exist_ok=True)
    (out/"product.json").write_text(json.dumps(product,indent=2)+"\n",encoding="utf-8")
    if product.get("status")!="publishable":
        body="<h1>MerchantBrain abstained</h1><p>No opportunity passed the evidence threshold.</p>"
    else:
        body=f"""<main><p class=eyebrow>MERCHANTBRAIN / AUTONOMOUS EXPERIMENT</p><h1>{html.escape(product['title'])}</h1><p>{html.escape(product['promise'])}</p><div class=card><b>{product['price_display']} USDC</b><p>Machine-readable JSON. Generated from public evidence; settlement is independently recorded.</p><code>POST /v1/product</code></div><h2>Why this exists</h2><p>{product['opportunity']['mentions']} observed mentions contributed to this candidate. The factory can also decide to publish nothing.</p><small>{html.escape(product['truth_boundary'])}</small></main>"""
    css="body{font-family:ui-monospace,monospace;background:#0b0d10;color:#e8edf2;margin:0}main{max-width:760px;margin:10vh auto;padding:24px}h1{font-size:clamp(42px,8vw,86px);line-height:.95}.eyebrow,small{color:#8c98a5}.card{border:1px solid #39424c;padding:24px;margin:40px 0}code{display:inline-block;background:#151a20;padding:10px}"
    (out/"index.html").write_text("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>MerchantBrain</title><style>"+css+"</style>"+body,encoding="utf-8")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--signals",default="reports/merchantbrain/signals.json"); ap.add_argument("--product",default="reports/merchantbrain/product.json"); ap.add_argument("--site",default="merchant-site"); a=ap.parse_args()
    signals=collect(); ranked=rank(signals); product=manufacture(choose(ranked),ranked)
    Path(a.signals).parent.mkdir(parents=True,exist_ok=True); Path(a.signals).write_text(json.dumps({"observed_at":now(),"signals":signals,"ranked":ranked[:50]},indent=2)+"\n")
    Path(a.product).write_text(json.dumps(product,indent=2)+"\n"); write_site(product,Path(a.site)); print(json.dumps({"status":product["status"],"product":product.get("title"),"price":product.get("price_display")}))
if __name__=="__main__": main()
