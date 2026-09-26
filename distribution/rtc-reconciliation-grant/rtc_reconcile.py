#!/usr/bin/env python3
"""Read-only RTC contributor payout reconciliation.

Uses only public RustChain/GitHub endpoints in online mode. Optional email
exports are local input files; this tool never connects to Gmail and never
uses keys, signing, transfer, payout, or mutation APIs.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

USER_AGENT = "rtc-reconcile/0.1"
RTC_RE = re.compile(r"RTC[0-9a-fA-F]{40}")
PENDING_RE = re.compile(r"pending[_ -]?id\s*[:=#]?\s*([A-Za-z0-9._-]+)", re.I)
TX_RE = re.compile(r"(?:tx(?:_hash)?|transaction(?: hash)?)\s*[:=#]?\s*[\x60'"]?([0-9a-fA-F]{8,64})", re.I)
CONFIRM_RE = re.compile(r"(?:confirm(?:s|ed|ation)?(?:\s+(?:at|around|automatically))?)[^\n]{0,80}", re.I)
IDEMPOTENCY_RE = re.compile(r"(?:idempotency|claim[_ -]?id|marker)\s*[:=#]?\s*[\x60'"]?([A-Za-z0-9._:/-]{4,160})", re.I)
ISSUE_REF_RE = re.compile(r"(?:github\.com/([^/]+/[^/]+)/issues/(\d+)|(?<!\w)#(\d+))", re.I)
URL_RE = re.compile(r"https?://[^\s>)\]}]+", re.I)

ACCEPT_WORDS = ("accepted", "approved", "award:")
QUEUE_WORDS = ("payout queued", "queued", "pending_id", "pending id")
CONFIRMED_WORDS = ("confirmed", "payout complete", "paid —", "paid -", "transferred")


@dataclass(frozen=True)
class Balance:
    identity: str
    amount_rtc: float
    source: str


@dataclass(frozen=True)
class PayoutEvent:
    claim_key: str
    channel: str
    source: str
    timestamp: str
    status: str
    pending_id: str | None
    tx_hash: str | None
    confirmation_text: str | None
    body_sha256: str


class HTTP:
    def __init__(self, opener=None, timeout: int = 20):
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def json(self, url: str) -> Any:
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
            method="GET",
        )
        with self.opener(req, timeout=self.timeout) as response:
            raw = response.read()
        return json.loads(raw or b"null")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_body(body: str) -> str:
    """Normalize cross-channel copies without silently changing claims."""
    lines: list[str] = []
    for raw in (body or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            continue
        if re.match(r"^On .+ wrote:$", line, re.I):
            continue
        if line.startswith("--"):
            continue
        lines.append(re.sub(r"\s+", " ", line).strip())
    return "\n".join(lines).lower()


def extract_issue_ref(body: str, fallback_source: str = "") -> str:
    match = ISSUE_REF_RE.search(body or "")
    if match:
        if match.group(1) and match.group(2):
            return f"{match.group(1).lower()}#{match.group(2)}"
        if match.group(3):
            repo_match = re.search(r"github\.com/([^/]+/[^/]+)", fallback_source, re.I)
            repo = repo_match.group(1).lower() if repo_match else "issue"
            return f"{repo}#{match.group(3)}"
    source_match = re.search(r"/repos/([^/]+/[^/]+)/issues/(\d+)", fallback_source, re.I)
    if source_match:
        return f"{source_match.group(1).lower()}#{source_match.group(2)}"
    return ""


def extract_deliverable(body: str) -> str:
    urls = URL_RE.findall(body or "")
    for url in urls:
        lowered = url.lower().rstrip(".,;")
        if any(host in lowered for host in ("github.com/", "dev.to/", "hashnode", "medium.com/", "substack.com/")):
            if "/issues/" not in lowered and "/pull/" not in lowered:
                return lowered
    return ""


def claim_key(body: str, source: str = "") -> str:
    """Deterministic key shared by issue-comment and exported-email copies."""
    explicit = IDEMPOTENCY_RE.search(body or "")
    if explicit:
        return "id:" + explicit.group(1).lower().strip(" `'\".,;")

    issue = extract_issue_ref(body, source)
    deliverable = extract_deliverable(body)
    wallet_match = RTC_RE.search(body or "")
    wallet = wallet_match.group(0).lower() if wallet_match else ""
    handle_match = re.search(r"@([A-Za-z0-9-]{2,39})", body or "")
    handle = handle_match.group(1).lower() if handle_match else ""

    stable_parts = [part for part in (issue, deliverable, wallet, handle) if part]
    if issue and (deliverable or wallet or handle):
        return "tuple:" + sha256_text("|".join(stable_parts))[:24]

    return "body:" + sha256_text(normalize_body(body))[:24]


def classify_status(body: str) -> str | None:
    text = (body or "").lower()
    if any(word in text for word in CONFIRMED_WORDS):
        return "confirmed"
    if any(word in text for word in QUEUE_WORDS):
        return "queued_pending"
    if any(word in text for word in ACCEPT_WORDS):
        return "accepted"
    return None


def event_from_record(record: dict[str, Any], channel: str, source: str) -> PayoutEvent | None:
    body = str(record.get("body") or record.get("text") or record.get("snippet") or "")
    status = classify_status(body)
    if not status:
        return None

    pending_match = PENDING_RE.search(body)
    tx_match = TX_RE.search(body)
    confirm_match = CONFIRM_RE.search(body)
    ts = str(record.get("created_at") or record.get("email_ts") or record.get("timestamp") or "")

    return PayoutEvent(
        claim_key=claim_key(body, source),
        channel=channel,
        source=source,
        timestamp=ts,
        status=status,
        pending_id=pending_match.group(1) if pending_match else None,
        tx_hash=tx_match.group(1) if tx_match else None,
        confirmation_text=confirm_match.group(0).strip() if confirm_match else None,
        body_sha256=sha256_text(normalize_body(body)),
    )


STATUS_ORDER = {"accepted": 1, "queued_pending": 2, "confirmed": 3}


def dedupe_events(events: Iterable[PayoutEvent]) -> list[PayoutEvent]:
    """Keep strongest/latest state per claim key; never sum duplicate channels."""
    best: dict[str, PayoutEvent] = {}
    for event in events:
        current = best.get(event.claim_key)
        if current is None:
            best[event.claim_key] = event
            continue
        incoming_rank = STATUS_ORDER.get(event.status, 0)
        current_rank = STATUS_ORDER.get(current.status, 0)
        if incoming_rank > current_rank or (
            incoming_rank == current_rank and event.timestamp >= current.timestamp
        ):
            best[event.claim_key] = event
    return sorted(best.values(), key=lambda e: (e.timestamp, e.claim_key))


def parse_issue_spec(spec: str) -> tuple[str, int]:
    match = re.fullmatch(r"([^/]+/[^#]+)#(\d+)", spec.strip())
    if not match:
        raise ValueError(f"invalid --issue value: {spec!r}; expected owner/repo#number")
    return match.group(1), int(match.group(2))


class Reconciler:
    def __init__(self, http: HTTP | None = None, node: str = "https://rustchain.org"):
        self.http = http or HTTP()
        self.node = node.rstrip("/")

    def balance(self, identity: str) -> Balance:
        query = urllib.parse.urlencode({"miner_id": identity})
        payload = self.http.json(f"{self.node}/wallet/balance?{query}")
        if not isinstance(payload, dict):
            raise ValueError("wallet balance response is not an object")
        amount = payload.get("amount_rtc")
        if amount is None:
            amount_i64 = payload.get("amount_i64")
            if amount_i64 is None:
                raise ValueError("wallet balance response has no RTC amount")
            amount = float(amount_i64) / 1_000_000
        return Balance(identity=identity, amount_rtc=float(amount), source="rustchain-public-api")

    def issue_comments(self, repo: str, issue: int, max_pages: int = 10) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            url = f"https://api.github.com/repos/{repo}/issues/{issue}/comments?per_page=100&page={page}"
            page_rows = self.http.json(url)
            if not isinstance(page_rows, list):
                raise ValueError(f"GitHub comments response for {repo}#{issue} is not a list")
            rows.extend(page_rows)
            if len(page_rows) < 100:
                break
        return rows


def load_records(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    raw = Path(path).read_text(encoding="utf-8")
    if path.endswith(".jsonl"):
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    payload = json.loads(raw)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("comments", "emails", "records"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError(f"{path}: expected a JSON array or comments/emails/records array")


def reconcile(
    handle: str,
    native_wallet: str,
    issue_specs: list[str],
    email_records: list[dict[str, Any]],
    github_fixture: list[dict[str, Any]] | None = None,
    reconciler: Reconciler | None = None,
) -> dict[str, Any]:
    rc = reconciler or Reconciler()
    balances = [rc.balance(handle), rc.balance(native_wallet)]
    events: list[PayoutEvent] = []

    if github_fixture is not None:
        for record in github_fixture:
            source = str(record.get("source") or "fixture")
            event = event_from_record(record, "github", source)
            if event:
                events.append(event)
    else:
        for spec in issue_specs:
            repo, issue = parse_issue_spec(spec)
            source = f"https://github.com/{repo}/issues/{issue}"
            for record in rc.issue_comments(repo, issue):
                body = str(record.get("body") or "")
                author = str((record.get("user") or {}).get("login") or "")
                if (
                    handle.lower() not in body.lower()
                    and native_wallet.lower() not in body.lower()
                    and author.lower() != handle.lower()
                ):
                    continue
                event = event_from_record(record, "github", source)
                if event:
                    events.append(event)

    for record in email_records:
        source = str(record.get("source") or record.get("subject") or "email-export")
        event = event_from_record(record, "email_export", source)
        if event and (handle.lower() in str(record).lower() or native_wallet.lower() in str(record).lower()):
            events.append(event)

    deduped = dedupe_events(events)
    return {
        "schema": "rtc-contributor-reconciliation/v1",
        "generated_at": utc_now(),
        "contributor": {"handle": handle, "native_wallet": native_wallet},
        "balances": [asdict(row) for row in balances],
        "balance_total_rtc": round(sum(row.amount_rtc for row in balances), 6),
        "payouts": [asdict(event) for event in deduped],
        "payout_state_counts": {
            status: sum(1 for event in deduped if event.status == status)
            for status in ("accepted", "queued_pending", "confirmed")
        },
        "dedupe": {
            "input_event_count": len(events),
            "output_claim_count": len(deduped),
            "duplicates_removed": len(events) - len(deduped),
        },
        "boundaries": {
            "read_only": True,
            "uses_public_endpoints_only": True,
            "fetches_email": False,
            "moves_rtc": False,
            "contains_usd_fields": False,
        },
    }


def render_html(data: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape("" if value is None else str(value))

    balance_rows = "".join(
        f"<tr><td>{esc(row['identity'])}</td><td>{esc(row['amount_rtc'])}</td><td>{esc(row['source'])}</td></tr>"
        for row in data["balances"]
    )
    payout_rows = "".join(
        "<tr>"
        f"<td>{esc(row['claim_key'])}</td>"
        f"<td>{esc(row['status'])}</td>"
        f"<td>{esc(row['pending_id'])}</td>"
        f"<td>{esc(row['tx_hash'])}</td>"
        f"<td>{esc(row['confirmation_text'])}</td>"
        f"<td>{esc(row['channel'])}</td>"
        f"<td><a href=\"{esc(row['source'])}\">{esc(row['source'])}</a></td>"
        "</tr>"
        for row in data["payouts"]
    ) or "<tr><td colspan=\"7\">No payout state events found.</td></tr>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RTC contributor reconciliation</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#17202a}}
table{{border-collapse:collapse;width:100%;margin:1rem 0 2rem}}
th,td{{border:1px solid #ccd1d1;padding:.55rem;text-align:left;vertical-align:top}}
th{{background:#f4f6f7}} code{{word-break:break-all}} .ok{{background:#eafaf1;padding:1rem}}
</style>
</head>
<body>
<h1>RTC contributor reconciliation</h1>
<p>Generated: {esc(data['generated_at'])}</p>
<div class="ok"><strong>Read only.</strong> This report does not sign, transfer, redeem, price, or value RTC.</div>
<h2>Contributor</h2>
<p>Hosted handle: <code>{esc(data['contributor']['handle'])}</code><br>
Native wallet: <code>{esc(data['contributor']['native_wallet'])}</code></p>
<h2>Balances</h2>
<table><thead><tr><th>Identity</th><th>RTC</th><th>Source</th></tr></thead><tbody>{balance_rows}</tbody></table>
<p><strong>Total across listed identities (not a market value): {esc(data['balance_total_rtc'])} RTC</strong></p>
<h2>Payout lifecycle</h2>
<table><thead><tr><th>Claim key</th><th>State</th><th>Pending ID</th><th>Transaction</th><th>Confirmation</th><th>Channel</th><th>Source</th></tr></thead><tbody>{payout_rows}</tbody></table>
<h2>Dedupe</h2>
<pre>{esc(json.dumps(data['dedupe'], indent=2))}</pre>
</body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handle", required=True)
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--issue", action="append", default=[], help="owner/repo#number; repeatable")
    parser.add_argument("--email-export", help="local JSON/JSONL export; never fetched by this tool")
    parser.add_argument("--github-fixture", help="offline GitHub comment fixture JSON")
    parser.add_argument("--node", default="https://rustchain.org")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    email_records = load_records(args.email_export)
    github_fixture = load_records(args.github_fixture) if args.github_fixture else None
    data = reconcile(
        handle=args.handle,
        native_wallet=args.wallet,
        issue_specs=args.issue,
        email_records=email_records,
        github_fixture=github_fixture,
        reconciler=Reconciler(node=args.node),
    )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    receipt = out / "reconciliation.json"
    report = out / "index.html"
    receipt.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.write_text(render_html(data), encoding="utf-8")
    print(json.dumps({"receipt": str(receipt), "report": str(report), "claims": len(data["payouts"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
