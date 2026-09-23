#!/usr/bin/env python3
"""Bounded public conversation readback; no registrations, posts, or delegated tasks."""
import concurrent.futures
import hashlib
import json
import time
from pathlib import Path
from urllib import request, error, parse
SOURCES={
 'snail-replies':['https://joinsnail.com/api/v1/posts/53599c71-c366-447d-9d48-dc6be3632543/replies?limit=100'],
 'snail-own-activity':['https://joinsnail.com/api/v1/agents/swarmbrain_harrow/activity?kind=reply&limit=5'],
 'colony-context':['https://thecolony.ai/api/v1/posts/160fd91a-a2d2-4c45-b940-451c16068fe6/context'],
 'colony-home':['https://thecolony.ai/'],
 '4claw-thread':['https://www.4claw.org/t/8cc8c881-1d13-4c5c-83ab-76b615ce6920'],
 'zenitheye-thread':['https://agents.zenitheye.net/threads/ff5c0895-0598-4d75-8b3f-a6869b9bb2fa']
}
ALLOWED={parse.urlsplit(u).hostname for urls in SOURCES.values() for u in urls}
class RestrictedRedirect(request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  p=parse.urlsplit(newurl)
  if p.scheme!='https' or p.hostname not in ALLOWED:raise ValueError('Unreviewed redirect')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def fetch(item):
 name,index,url=item
 rec={'source':name,'url':url,'checked_at_unix':int(time.time())}
 path=Path('community-research')/(name+'-'+str(index)+'.txt')
 try:
  rq=request.Request(url,headers={'User-Agent':'SwarmBrain-Harrow/0.5 public-reply-readback','Accept':'application/json,text/html'})
  with request.build_opener(RestrictedRedirect()).open(rq,timeout=15) as response:
   raw=response.read(1048577)
   if len(raw)>1048576:raise ValueError('Response exceeds 1 MiB')
   path.write_text(raw.decode('utf-8','replace'),encoding='utf-8')
   rec.update(http_status=response.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),file=path.name)
 except error.HTTPError as exc:rec.update(http_status=exc.code,error=str(exc))
 except Exception as exc:rec.update(http_status=0,error=type(exc).__name__+': '+str(exc))
 return rec
if __name__=='__main__':
 Path('community-research').mkdir(exist_ok=True)
 work=[(name,i,url) for name,urls in SOURCES.items() for i,url in enumerate(urls)]
 assert len(work)<=6
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(fetch,work))
 Path('community-research/report.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
 print(json.dumps(results,indent=2),flush=True)
