#!/usr/bin/env python3
"""Read-only RTC payout reconciliation for one contributor.

Uses only public RustChain and GitHub GET endpoints. It never signs, transfers,
withdraws, wraps, trades, or modifies wallet state.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

GITHUB_API = "https://api.github.com"
DEFAULT_REPO = "Scottcjn/rustchain-bounties"
BALANCE_URL = "https://rustchain.org/wallet/balance?miner_id={}"
STATE_RANK = {"unknown": 0, "accepted": 1, "queued": 2, "pending": 3, "confirmed": 4}

RTC_RE = re.compile(r"(?<![A-Za-z0-9])([0-9]+(?:\.[0-9]+)?)\s*RTC\b", re.I)
PENDING_RE = re.compile(r"pending[_ -]?id\s*[:=#]?\s*`?([A-Za-z0-9._-]+)", re.I)
TX_RE = re.compile(r"(?:tx(?:_hash)?|transaction(?: hash)?)\s*[:=#]?\s*`?([A-Fa-f0-9]{8,64})", re.I)
CONFIRM_RE = re.compile(
    r"(?:confirm(?:ed|s|ation)?(?:\s+(?:automatically|at|time))?)\s*[:=]?\s*"
    r"(d{4}-d{2}-d{2}[T ][0-9:.+-]+(?:Z|UTC)?)",
    re.I,
)
IDEM_RE = re.compile(r"(?:idem|idempotency(?:[_ -]?key)?)\s*[:= ]+`?([A-Za-z0-9._:/-]+)", re.I)
WALLET_RE = re.compile(r"\b(RTC[0-9A-Fa-f]{40})\b")


@dataclass(frozen=True)
class Balance:
    identity: str
    amount_rtc: float
    source: str


@dataclass
class Claim:
    key: str
    issue_number: int | None
    issue_url: str | None
    title: str
    state: str
    amount_rtc: float | None
    payout_identity: str | None
    pending_id: str | None
    tx_hash: str | None
    confirmation_time: str | None
    evidence_urls: list[str]

    def merge(self, other: "Claim") -> None:
        if STATE_RANK.get(other.state, 0) > STATE_RANK.get(self.state, 0):
            self.state = other.state
        for field in ("amount_rtc", "payout_identity", "pending_id", "tx_hash", "confirmation_time"):
            if getattr(self, field) in (None, "") and getattr(other, field) not in (None, ""):
                setattr(self, field, getattr(other, field))
        self.evidence_urls = sorted(set(self.evidence_urls + other.evidence_urls))


class HTTP:
    def get_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": "rtc-reconciler/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)


class FixtureHTTP(HTTP):
    """URL-to-file deterministic fixture transport."""

    def __init__(self, fixture_dir: Path):
        self.fixture_dir = fixture_dir
        self.index = json.loads((fixture_dir / "http-index.json").read_text(encoding="utf-8"))

    def get_json(self, url: str) -> Any:
        try:
            rel = self.index[url]
        except KeyError as exc:
            raise KeyError(f"fixture URL not mapped: {url}") from exc
        return json.loads((self.fixture_dir / rel).read_text(encoding="utf-8"))


def balance(http: HTTP, identity: str) -> Balance:
    url = BALANCE_URL.format(urllib.parse.quote(identity, safe=""))
    data = http.get_json(url)
    amount = data.get("amount_rtc")
    if amount is None and "balance_rtc" in data:
        amount = data["balance_rtc"]
    if amount is None:
        amount_i64 = data.get("amount_i64", 0)
        amount = float(amount_i64) / 1_000_000
    return Balance(identity=identity, amount_rtc=float(amount), source=url)


def state_from_text(text: str) -> str:
    lower = text.lower()
    # Strongest state wins; "pending" must not overwrite explicit confirmation.
    if any(word in lower for word in ("confirmed", "confirmation complete", "transfer complete")):
        return "confirmed"
    if "pending_id" in lower or "pending id" in lower or " pending " in f" {lower} ":
        return "pending"
    if any(word in lower for word in ("queued", "payout queued", "queue payout")):
        return "queued"
    if any(word in lower for word in ("accepted", "approved", "greenlit")):
        return "accepted"
    return "unknown"


def first_rtc(text: str) -> float | None:
    m = RTC_RE.search(text)
    return float(m.group(1)) if m else None


def first_match(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def payout_identity(text: str) -> str | None:
    native = WALLET_RE.search(text)
    if native:
        return native.group(1)
    for label in ("wallet:", "destination:", "payout target:", "hosted handle wallet"):
        idx = text.lower().find(label)
        if idx >= 0:
            tail = text[idx + len(label):].strip().splitlines()[0].strip(" `*_")
            if tail:
                return tail[:128]
    return None


def make_key(issue_number: int | None, title: str, text: str) -> str:
    idem = first_match(IDEM_RE, text)
    if idem:
        return f"idem:{idem.lower()}"
    pid = first_match(PENDING_RE, text)
    if pid:
        return f"pending:{pid.lower()}"
    normalized = re.sub(r"\s+", " ", title.strip().lower())
    return f"issue:{issue_number}:{normalized}"


def claim_from_record(issue: dict[str, Any], text: str, evidence_url: str) -> Claim:
    issue_number = issue.get("number")
    title = str(issue.get("title") or f"issue-{issue_number}")
    return Claim(
        key=make_key(issue_number, title, text),
        issue_number=issue_number,
        issue_url=issue.get("html_url"),
        title=title,
        state=state_from_text(text),
        amount_rtc=first_rtc(text),
        payout_identity=payout_identity(text),
        pending_id=first_match(PENDING_RE, text),
        tx_hash=first_match(TX_RE, text),
        confirmation_time=first_match(CONFIRM_RE, text),
        evidence_urls=[evidence_url],
    )


def github_claims(http: HTTP, handle: str, repo: str = DEFAULT_REPO) -> list[Claim]:
    q = urllib.parse.quote(f"repo:{repo} {handle} is:issue")
    search_url = f"{GITHUB_API}/search/issues?q={q}&per_page=100"
    search = http.get_json(search_url)
    records: list[Claim] = []

    for item in search.get("items", []):
        issue_number = int(item["number"])
        issue = {
            "number": issue_number,
            "title": item.get("title", ""),
            "html_url": item.get("html_url"),
        }
        issue_text = item.get("body") or ""
        issue_claim = claim_from_record(issue, issue_text, item.get("html_url") or "")
        if handle.lower() in issue_text.lower():
            records.append(issue_claim)

        comments_url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments?per_page=100"
        for comment in http.get_json(comments_url):
            body = comment.get("body") or ""
            if handle.lower() not in body.lower():
                continue
            c = claim_from_record(issue, body, comment.get("html_url") or comments_url)
            records.append(c)

    return dedupe_claims(records)


def _same_claim(a: Claim, b: Claim) -> bool:
    """Return True when two evidence records describe the same payout claim."""
    if a.key.startswith("idem:") and a.key == b.key:
        return True
    if a.pending_id and b.pending_id and a.pending_id.lower() == b.pending_id.lower():
        return True
    if a.tx_hash and b.tx_hash and a.tx_hash.lower() == b.tx_hash.lower():
        return True
    if a.issue_number != b.issue_number:
        return False
    # Within an issue, the same amount + compatible payout identity is treated as
    # one state progression (accepted -> queued/pending -> confirmed).
    if a.amount_rtc is not None and b.amount_rtc is not None and a.amount_rtc == b.amount_rtc:
        if not a.payout_identity or not b.payout_identity:
            return True
        return a.payout_identity.lower() == b.payout_identity.lower()
    return False


def dedupe_claims(records: Iterable[Claim]) -> list[Claim]:
    merged: list[Claim] = []
    for record in records:
        match = next((existing for existing in merged if _same_claim(existing, record)), None)
        if match is None:
            merged.append(record)
        else:
            match.merge(record)
            # Prefer the strongest durable identifier as the canonical key.
            if record.key.startswith("idem:"):
                match.key = record.key
            elif record.pending_id and not match.key.startswith("idem:"):
                match.key = f"pending:{record.pending_id.lower()}"
    return sorted(merged, key=lambda c: (c.issue_number or 0, c.key))


def external_evidence(path: Path | None) -> list[Claim]:
    """Load an optional offline export of issue/email evidence.

    This never connects to mail. It lets a contributor provide previously
    exported evidence so the same payout mentioned in GitHub and email can be
    deterministically deduplicated.
    """
    if path is None:
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("evidence JSON must be a list")
    claims: list[Claim] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each evidence record must be an object")
        issue = {
            "number": item.get("issue_number"),
            "title": item.get("title") or "external-evidence",
            "html_url": item.get("issue_url"),
        }
        claims.append(claim_from_record(
            issue,
            str(item.get("body") or ""),
            str(item.get("evidence_url") or "offline:evidence"),
        ))
    return claims


def totals(claims: Iterable[Claim]) -> dict[str, float]:
    result = {state: 0.0 for state in ("accepted", "queued", "pending", "confirmed")}
    for c in claims:
        if c.state in result and c.amount_rtc is not None:
            result[c.state] += c.amount_rtc
    return result


def receipt(native: Balance, hosted: Balance, claims: list[Claim], handle: str) -> dict[str, Any]:
    return {
        "schema": "rtc-reconciliation/v1",
        "contributor": handle,
        "balances": {
            "native": asdict(native),
            "hosted": asdict(hosted),
        },
        "claims": [asdict(c) for c in claims],
        "claim_totals_rtc": totals(claims),
        "rules": {
            "balances_are_separate_identities": True,
            "claim_dedupe_precedence": ["idempotency", "pending_id", "issue+title"],
            "state_precedence": ["confirmed", "pending", "queued", "accepted", "unknown"],
            "usd_fields_prohibited": True,
        },
    }


def render_html(data: dict[str, Any]) -> str:
    def esc(v: Any) -> str:
        return html.escape("" if v is None else str(v))

    rows = []
    for c in data["claims"]:
        rows.append(
            "<tr>"
            f"<td>{esc(c['issue_number'])}</td>"
            f"<td>{esc(c['title'])}</td>"
            f"<td>{esc(c['state'])}</td>"
            f"<td>{esc(c['amount_rtc'])}</td>"
            f"<td>{esc(c['pending_id'])}</td>"
            f"<td>{esc(c['confirmation_time'])}</td>"
            "</tr>"
        )
    native = data["balances"]["native"]
    hosted = data["balances"]["hosted"]
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>RTC reconciliation</title>
<style>body{{font-family:system-ui;margin:2rem;max-width:1100px}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:.45rem;text-align:left}}code{{background:#eee;padding:.1rem .25rem}}</style></head>
<body><h1>RTC reconciliation</h1>
<p>Contributor: <code>{esc(data['contributor'])}</code></p>
<h2>Balances</h2>
<ul><li>Native <code>{esc(native['identity'])}</code>: {esc(native['amount_rtc'])} RTC</li>
<li>Hosted <code>{esc(hosted['identity'])}</code>: {esc(hosted['amount_rtc'])} RTC</li></ul>
<h2>Payout states</h2>
<table><thead><tr><th>Issue</th><th>Claim</th><th>State</th><th>RTC</th><th>Pending ID</th><th>Confirmation time</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p>Generated read-only from public evidence. No signing or transfer operations are performed.</p>
</body></html>"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reconcile RTC balances and payout states.")
    p.add_argument("--github-handle", required=True)
    p.add_argument("--hosted-handle", required=True)
    p.add_argument("--native-wallet", required=True)
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--fixture-dir", type=Path)
    p.add_argument("--evidence-json", type=Path, help="optional offline issue/email evidence export")
    p.add_argument("--out-json", type=Path, required=True)
    p.add_argument("--out-html", type=Path, required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    http: HTTP = FixtureHTTP(args.fixture_dir) if args.fixture_dir else HTTP()
    native = balance(http, args.native_wallet)
    hosted = balance(http, args.hosted_handle)
    claims = dedupe_claims(
        github_claims(http, args.github_handle, args.repo)
        + external_evidence(args.evidence_json)
    )
    data = receipt(native, hosted, claims, args.github_handle)

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_html.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.out_html.write_text(render_html(data), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "claims": len(claims),
        "native_rtc": native.amount_rtc,
        "hosted_rtc": hosted.amount_rtc,
        "out_json": str(args.out_json),
        "out_html": str(args.out_html),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
