"""Bounded public market research. Never calls a paid service or contacts a buyer."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from urllib import parse, request
from .bounty_scout import scan

SOURCES = (
    ("basedagents", "https://api.basedagents.ai/v1/tasks?status=open"),
    ("bazaar_validation", "https://api.cdp.coinbase.com/platform/v2/x402/discovery/search?" + parse.urlencode({"query": "JSON schema validation", "network": "eip155:8453", "limit": 5})),
    ("bazaar_routing", "https://api.cdp.coinbase.com/platform/v2/x402/discovery/search?" + parse.urlencode({"query": "agent routing verification", "network": "eip155:8453", "limit": 5})),
)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_public(url):
    if url not in dict(SOURCES).values():
        raise ValueError("unapproved_discovery_url")
    req = request.Request(url, headers={"accept": "application/json", "user-agent": "A0-revenue-research/1"})
    with request.build_opener(NoRedirect()).open(req, timeout=15) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("response_too_large")
    return json.loads(raw)


def catalog_signals(data):
    if not isinstance(data, dict) or not isinstance(data.get("resources"), list):
        raise ValueError("unsupported_bazaar_schema")
    signals = []
    for row in data["resources"][:5]:
        if not isinstance(row, dict):
            continue
        quality = row.get("quality") if isinstance(row.get("quality"), dict) else {}
        signals.append({"resource": row.get("resource"), "description": str(row.get("description", ""))[:400],
                        "reported_calls_30d": quality.get("l30DaysTotalCalls"),
                        "reported_unique_payers_30d": quality.get("l30DaysUniquePayers"),
                        "last_called_at": quality.get("lastCalledAt"),
                        "classification": "seller_market_signal_not_a_buyer_lead", "contact_allowed": False})
    return {"signals": signals, "partial_results": data.get("partialResults"), "qualified_buyer_count": 0}


def discover(fetch_fn=fetch_public):
    results = []
    for name, url in SOURCES:
        row = {"name": name, "url": url, "observed_at": datetime.now(timezone.utc).isoformat()}
        try:
            data = fetch_fn(url)
            row["response_sha256"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            row["result"] = scan(data) if name == "basedagents" else catalog_signals(data)
            row["status"] = "ok"
        except Exception as error:
            row.update(status="unavailable", error_type=type(error).__name__, result=None)
        results.append(row)
    return {"sources": results, "status": "ok" if all(r["status"] == "ok" for r in results) else "degraded",
            "paid_calls": 0, "third_party_offers_sent": 0, "verified_external_revenue_atomic": 0}


if __name__ == "__main__":
    print(json.dumps(discover(), indent=2))
