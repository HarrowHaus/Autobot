"""Read-only verifier for RustChain/Elyan Labs bounty claims.

This tool verifies evidence only. It never approves or executes payments.
"""
from __future__ import annotations
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict

USER_AGENT = "rtc-bounty-verifier/0.1"
WALLET_RE = re.compile(r"RTC[0-9a-fA-F]{40}|[A-Za-z0-9_.-]{2,64}")

@dataclass
class Check:
    name: str
    ok: bool
    detail: str

class HTTP:
    def __init__(self, opener=None, github_token=None, timeout=15):
        self.opener = opener or urllib.request.urlopen
        self.github_token = github_token
        self.timeout = timeout

    def get(self, url, accept="application/json"):
        headers={"User-Agent":USER_AGENT,"Accept":accept}
        if self.github_token and "api.github.com" in url:
            headers["Authorization"]=f"Bearer {self.github_token}"
            headers["X-GitHub-Api-Version"]="2022-11-28"
        req=urllib.request.Request(url,headers=headers,method="GET")
        try:
            with self.opener(req,timeout=self.timeout) as resp:
                return getattr(resp,"status",200), resp.read(), dict(getattr(resp,"headers",{}))
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers or {})

class Verifier:
    def __init__(self,http=None,owner="Scottcjn",node="https://50.28.86.131"):
        self.http=http or HTTP()
        self.owner=owner
        self.node=node.rstrip("/")

    def follows_owner(self,user):
        status,_,_=self.http.get(f"https://api.github.com/users/{urllib.parse.quote(user)}/following/{self.owner}")
        return Check("follows_owner", status==204, f"HTTP {status}")

    def starred_owner_repos(self,user,max_pages=10):
        count=0
        for page in range(1,max_pages+1):
            status,raw,_=self.http.get(
                f"https://api.github.com/users/{urllib.parse.quote(user)}/starred?per_page=100&page={page}",
                "application/vnd.github.star+json",
            )
            if status!=200:
                return Check("starred_owner_repos",False,f"HTTP {status}")
            rows=json.loads(raw or b"[]")
            if not rows:
                break
            for item in rows:
                repo=item.get("repo",item)
                if (repo.get("owner") or {}).get("login")==self.owner:
                    count+=1
            if len(rows)<100:
                break
        return Check("starred_owner_repos",True,str(count))

    def wallet_exists(self,wallet):
        if not wallet or not WALLET_RE.fullmatch(wallet):
            return Check("wallet_exists",False,"invalid wallet format")
        q=urllib.parse.urlencode({"miner_id":wallet})
        status,raw,_=self.http.get(f"{self.node}/wallet/balance?{q}")
        if status!=200:
            return Check("wallet_exists",False,f"HTTP {status}")
        try:
            body=json.loads(raw)
        except Exception:
            return Check("wallet_exists",False,"non-JSON response")
        amount=body.get("balance_rtc",body.get("balance",body.get("amount_i64")))
        return Check("wallet_exists",True,f"balance={amount}")

    def article(self,url,min_words=0):
        if not url or not url.lower().startswith(("http://","https://")):
            return Check("article",False,"invalid URL")
        status,raw,_=self.http.get(url,"text/html,application/xhtml+xml,text/plain")
        if status<200 or status>=400:
            return Check("article",False,f"HTTP {status}")
        text=raw.decode("utf-8",errors="replace")
        cleaned=re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>"," ",text,flags=re.I|re.S)
        cleaned=re.sub(r"<[^>]+>"," ",cleaned)
        cleaned=re.sub(r"&[a-zA-Z#0-9]+;"," ",cleaned)
        words=re.findall(r"\b[\w'-]+\b",cleaned)
        return Check("article",len(words)>=min_words,f"HTTP {status}; words={len(words)}; minimum={min_words}")

    def duplicate_claims(self,repo,issue,user,marker=None,max_pages=10):
        matches=[]
        for page in range(1,max_pages+1):
            status,raw,_=self.http.get(f"https://api.github.com/repos/{repo}/issues/{issue}/comments?per_page=100&page={page}")
            if status!=200:
                return Check("duplicate_claims",False,f"HTTP {status}")
            rows=json.loads(raw or b"[]")
            for row in rows:
                if (row.get("user") or {}).get("login") != user:
                    continue
                body=row.get("body") or ""
                if marker is None or marker.lower() in body.lower():
                    matches.append(row.get("html_url") or str(row.get("id")))
            if len(rows)<100:
                break
        return Check("duplicate_claims",len(matches)<=1,f"matching_claims={len(matches)}; refs={matches[:5]}")

    def verify(self,claim):
        checks=[]
        user=claim.get("github")
        if claim.get("check_follow",True):
            checks.append(self.follows_owner(user))
        if claim.get("check_stars",True):
            checks.append(self.starred_owner_repos(user))
        if claim.get("wallet"):
            checks.append(self.wallet_exists(claim["wallet"]))
        if claim.get("article_url"):
            checks.append(self.article(claim["article_url"],int(claim.get("min_words",0))))
        if claim.get("repo") and claim.get("issue"):
            checks.append(self.duplicate_claims(claim["repo"],int(claim["issue"]),user,claim.get("duplicate_marker")))
        return {"github":user,"checks":[asdict(x) for x in checks],"all_checks_ok":all(x.ok for x in checks)}

def parse_claim_text(text):
    def first(pattern):
        m=re.search(pattern,text,re.I)
        return m.group(1).strip() if m else None
    return {
        "github": first(r"(?:github|claimant)\s*:\s*@?([A-Za-z0-9-]+)"),
        "wallet": first(r"(?:wallet|rtc wallet)\s*:\s*([A-Za-z0-9_.-]+)"),
        "article_url": first(r"(?:live-url|article|url)\s*:\s*(https?://\S+)"),
    }
