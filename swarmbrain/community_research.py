#!/usr/bin/env python3
"""Fetch a fixed set of public agent-community documentation; never execute it."""
import concurrent.futures
import hashlib
import json
import time
from pathlib import Path
from urllib import request, error, parse

SOURCES = {
    'moltbook': ['https://www.moltbook.com/skill.md', 'https://www.moltbook.com/terms'],
    '4claw': ['https://www.4claw.org/skill.md', 'https://www.4claw.org/'],
    'clawstr': ['https://clawstr.com/SKILL.md', 'https://clawstr.com/'],
    'aichatroom': ['https://aichatroom.online/llms.txt', 'https://aichatroom.online/'],
    'snail': ['https://joinsnail.com/llms.txt', 'https://joinsnail.com/'],
    'zenitheye': ['https://agents.zenitheye.net/.well-known/agent-card.json', 'https://agents.zenitheye.net/'],
}
ALLOWED = {parse.urlsplit(u).hostname for urls in SOURCES.values() for u in urls}
class RestrictedRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = parse.urlsplit(newurl)
        if p.scheme != 'https' or p.hostname not in ALLOWED:
            raise ValueError('Redirect outside reviewed documentation hosts')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch(item):
    name, index, url = item
    rec = {'community': name, 'url': url, 'checked_at_unix': int(time.time())}
    path = Path('community-research') / (name + '-' + str(index) + '.txt')
    try:
        rq = request.Request(url, headers={'User-Agent': 'SwarmBrain-Harrow/0.4 public-documentation-read', 'Accept': 'text/plain,text/html,application/json'})
        with request.build_opener(RestrictedRedirect()).open(rq, timeout=15) as response:
            raw = response.read(524289)
            if len(raw) > 524288:
                raise ValueError('Response over 512 KiB limit')
            text = raw.decode('utf-8', 'replace')
            path.write_text(text, encoding='utf-8')
            rec.update(http_status=response.status, content_type=response.headers.get('Content-Type'), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), file=path.name)
            if 'skill.md' in url.lower() or 'llms.txt' in url or 'agent-card.json' in url:
                rec['documentation_excerpt'] = text[:16000]
    except error.HTTPError as exc:
        rec.update(http_status=exc.code, error=str(exc))
    except Exception as exc:
        rec.update(http_status=0, error=type(exc).__name__ + ': ' + str(exc))
    return rec

if __name__ == '__main__':
    Path('community-research').mkdir(exist_ok=True)
    work = [(name, i, url) for name, urls in SOURCES.items() for i, url in enumerate(urls)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch, work))
    Path('community-research/report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2), flush=True)
