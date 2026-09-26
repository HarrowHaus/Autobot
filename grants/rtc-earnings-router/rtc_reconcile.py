#!/usr/bin/env python3
"""Read-only RTC payout reconciliation for one contributor.

Payout settlement state comes from RustChain wallet history. GitHub is used only
for maintainer-authored accepted evidence. This tool never signs, transfers,
withdraws, wraps, trades, or modifies wallet state.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

GITHUB_API = "https://api.github.com"
DEFAULT_REPO = "Scottcjn/rustchain-bounties"
BALANCE_URL = "https://rustchain.org/wallet/balance?miner_id={}"
HISTORY_URL = "https://rustchain.org/wallet/history?miner_id={}&limit=200"
MAINTAINERS = {"scottcjn", "sophiaeagent-beep"}
RTC_RE = re.compile(r"(?<![A-Za-z0-9])([0-9]+(?:\.[0-9]+)?)\s*RTC\b", re.I)
WALLET_RE = re.compile(r"\b(RTC[0-9A-Fa-f]{40})\b")
ACCEPTED_LINE_RE = re.compile(
    r"^.*\baccepted\b[^\n]{0,100}\b[0-9]+(?:\.[0-9]+)?\s*RTC\b.*$|"
    r"^.*\b[0-9]+(?:\.[0-9]+)?\s*RTC\b[^\n]{0,100}\baccepted\b.*$",
    re.I | re.M,
)
NEGATED_ACCEPT_RE = re.compile(
    r"\b(?:not|isn't|is not|wasn't|was not)\s+(?:yet\s+)?accepted\b|"
    r"\b(?:cannot|can't|can not)\s+be\s+accepted\b|"
    r"\bneeds?\s+(?:a\s+)?revision\b|\bnot\s+payable\b|\brejected\b|\breturned\b",
    re.I,
)


@dataclass(frozen=True)
class Balance:
    identity: str
    amount_rtc: float
    source: str


@dataclass(frozen=True)
class Transfer:
    identity: str
    tx_hash: str
    amount_rtc: float
    state: str
    created_at: int | None
    confirmation_time: int | None
    confirmation_time_source: str | None
    pending_id: str | None
    direction: str
    counterparty: str | None
    source: str


@dataclass(frozen=True)
class Accepted:
    issue_number: int
    issue_url: str | None
    title: str
    amount_rtc: float | None
    comment_id: int
    comment_url: str
    maintainer: str


class HTTP:
    def __init__(self, token: str | None = None):
        self.token = token

    def get_json(self, url: str) -> Any:
        headers = {"User-Agent": "rtc-reconciler/2.0"}
        if self.token and url.startswith(GITHUB_API):
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)

    def list_pages(self, url: str) -> list[Any]:
        out: list[Any] = []
        page = 1
        while True:
            sep = "&" if "?" in url else "?"
            batch = self.get_json(f"{url}{sep}page={page}")
            if not isinstance(batch, list):
                raise ValueError(f"expected list response for {url}")
            out.extend(batch)
            if len(batch) < 100:
                return out
            page += 1

    def search_items(self, url: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            sep = "&" if "?" in url else "?"
            data = self.get_json(f"{url}{sep}page={page}")
            batch = data.get("items", [])
            out.extend(batch)
            if len(batch) < 100:
                return out
            page += 1


class FixtureHTTP(HTTP):
    def __init__(self, fixture_dir: Path):
        super().__init__(None)
        self.fixture_dir = fixture_dir
        self.index = json.loads((fixture_dir / "http-index.json").read_text(encoding="utf-8"))

    def get_json(self, url: str) -> Any:
        rel = self.index.get(url)
        if rel is None and url.endswith("&page=1"):
            rel = self.index.get(url[:-7])
        if rel is None and url.endswith("?page=1"):
            rel = self.index.get(url[:-7])
        if rel is not None:
            return json.loads((self.fixture_dir / rel).read_text(encoding="utf-8"))
        if re.search(r"[?&]page=\d+$", url):
            return [] if "/comments?" in url else {"items": []}
        raise KeyError(f"fixture URL not mapped: {url}")


def balance(http: HTTP, identity: str) -> Balance:
    url = BALANCE_URL.format(urllib.parse.quote(identity, safe=""))
    data = http.get_json(url)
    amount = data.get("amount_rtc", data.get("balance_rtc"))
    if amount is None:
        amount = float(data.get("amount_i64", 0)) / 1_000_000
    return Balance(identity, float(amount), url)


def _history_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        rows = data.get("transactions", data.get("history", []))
        if isinstance(rows, list):
            return rows
    raise ValueError("wallet history response has no transaction list")


def wallet_transfers(http: HTTP, identity: str) -> list[Transfer]:
    url = HISTORY_URL.format(urllib.parse.quote(identity, safe=""))
    rows = _history_payload(http.get_json(url))
    out: list[Transfer] = []
    for row in rows:
        tx_type = str(row.get("type") or row.get("direction") or "").lower()
        if tx_type not in {"transfer_in", "received"}:
            continue
        tx_hash = str(row.get("tx_hash") or row.get("tx_id") or "").strip()
        if not tx_hash:
            continue
        raw_state = str(row.get("status") or "").lower()
        state = raw_state if raw_state in {"pending", "confirmed", "failed"} else "confirmed"
        amount = row.get("amount_rtc", row.get("amount"))
        if amount is None:
            amount = abs(int(row.get("amount_i64", 0))) / 1_000_000
        created = row.get("created_at", row.get("timestamp"))
        confirmed = row.get("confirmed_at")
        confirms = row.get("confirms_at")
        source_name = None
        confirmation = None
        if state == "confirmed" and confirmed is not None:
            confirmation, source_name = int(confirmed), "confirmed_at"
        elif state == "pending" and confirms is not None:
            confirmation, source_name = int(confirms), "confirms_at"
        elif state == "pending" and created is not None:
            # Current live history omits confirms_at for pending ledger rows even
            # though the public signed-transfer contract uses a 24h confirmation window.
            confirmation, source_name = int(created) + 86400, "derived_24h"
        pending_id = row.get("pending_id")
        tx_id = str(row.get("tx_id") or "")
        if pending_id is None and tx_id.startswith("pending_"):
            pending_id = tx_id.removeprefix("pending_")
        counterparty = row.get("from") or row.get("counterparty")
        out.append(
            Transfer(
                identity=identity,
                tx_hash=tx_hash,
                amount_rtc=float(amount),
                state=state,
                created_at=int(created) if created is not None else None,
                confirmation_time=confirmation,
                confirmation_time_source=source_name,
                pending_id=str(pending_id) if pending_id is not None else None,
                direction="received",
                counterparty=str(counterparty) if counterparty else None,
                source=url,
            )
        )
    return out


def dedupe_transfers(rows: list[Transfer]) -> list[Transfer]:
    by_hash: dict[str, Transfer] = {}
    for row in rows:
        by_hash.setdefault(row.tx_hash.lower(), row)
    return sorted(by_hash.values(), key=lambda x: (x.created_at or 0, x.tx_hash), reverse=True)


def first_rtc(text: str) -> float | None:
    m = RTC_RE.search(text)
    return float(m.group(1)) if m else None


def accepted_text(text: str) -> bool:
    if NEGATED_ACCEPT_RE.search(text):
        return False
    return bool(ACCEPTED_LINE_RE.search(text))


def maintainer_accepted(http: HTTP, handle: str, repo: str = DEFAULT_REPO) -> list[Accepted]:
    q = urllib.parse.quote(f"repo:{repo} {handle} is:issue")
    items = http.search_items(f"{GITHUB_API}/search/issues?q={q}&per_page=100")
    accepted: list[Accepted] = []
    seen: set[int] = set()
    for item in items:
        issue_number = int(item["number"])
        comments_url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments?per_page=100"
        for comment in http.list_pages(comments_url):
            cid = int(comment.get("id", 0))
            if not cid or cid in seen:
                continue
            author = str((comment.get("user") or {}).get("login") or "").lower()
            body = str(comment.get("body") or "")
            if author not in MAINTAINERS:
                continue
            if handle.lower() not in body.lower():
                continue
            if not accepted_text(body):
                continue
            seen.add(cid)
            accepted.append(
                Accepted(
                    issue_number=issue_number,
                    issue_url=item.get("html_url"),
                    title=str(item.get("title") or f"issue-{issue_number}"),
                    amount_rtc=first_rtc(body),
                    comment_id=cid,
                    comment_url=str(comment.get("html_url") or comments_url),
                    maintainer=author,
                )
            )
    return sorted(accepted, key=lambda x: (x.issue_number, x.comment_id))


def payout_totals(rows: list[Transfer]) -> dict[str, float]:
    totals = {"pending": 0.0, "confirmed": 0.0, "failed": 0.0}
    for row in rows:
        if row.state in totals:
            totals[row.state] += row.amount_rtc
    return totals


def receipt(native: Balance, hosted: Balance, transfers: list[Transfer], accepted: list[Accepted], handle: str) -> dict[str, Any]:
    return {
        "schema": "rtc-reconciliation/v2",
        "contributor": handle,
        "balances": {"native": asdict(native), "hosted": asdict(hosted)},
        "payout_transfers": [asdict(x) for x in transfers],
        "payout_totals_rtc": payout_totals(transfers),
        "accepted_evidence": [asdict(x) for x in accepted],
        "rules": {
            "payout_state_source": "wallet_history",
            "accepted_source": "maintainer_github_comments_only",
            "maintainers": sorted(MAINTAINERS),
            "ledger_dedupe": "tx_hash",
            "accepted_dedupe": "comment_id",
            "distinct_ledger_rows_never_merge_by_amount": True,
        },
    }


def render_html(data: dict[str, Any]) -> str:
    def esc(v: Any) -> str:
        return html.escape("" if v is None else str(v))
    rows = []
    for t in data["payout_transfers"]:
        rows.append(
            "<tr>"
            f"<td>{esc(t['identity'])}</td><td>{esc(t['tx_hash'])}</td>"
            f"<td>{esc(t['state'])}</td><td>{esc(t['amount_rtc'])}</td>"
            f"<td>{esc(t['pending_id'])}</td><td>{esc(t['confirmation_time'])}</td>"
            "</tr>"
        )
    accepted = "".join(
        f"<li>#{esc(a['issue_number'])} — {esc(a['title'])} — {esc(a['amount_rtc'])} RTC "
        f"(<a href=\"{esc(a['comment_url'])}\">maintainer evidence</a>)</li>"
        for a in data["accepted_evidence"]
    ) or "<li>None</li>"
    n = data["balances"]["native"]
    h = data["balances"]["hosted"]
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>RTC reconciliation</title>
<style>body{{font-family:system-ui;margin:2rem;max-width:1200px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.45rem;text-align:left}}code{{background:#eee;padding:.1rem .25rem}}</style></head>
<body><h1>RTC reconciliation</h1>
<p>Contributor: <code>{esc(data['contributor'])}</code></p>
<h2>Balances</h2><ul>
<li>Native <code>{esc(n['identity'])}</code>: {esc(n['amount_rtc'])} RTC</li>
<li>Hosted <code>{esc(h['identity'])}</code>: {esc(h['amount_rtc'])} RTC</li></ul>
<h2>Wallet-history payout states</h2>
<table><thead><tr><th>Identity</th><th>tx hash</th><th>State</th><th>RTC</th><th>pending ID</th><th>Confirmation time</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>Maintainer accepted evidence</h2><ul>{accepted}</ul>
<p>Read-only public evidence only. No signing or transfer operations are performed.</p>
</body></html>"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reconcile RTC balances and payout states.")
    p.add_argument("--github-handle", required=True)
    p.add_argument("--hosted-handle", required=True)
    p.add_argument("--native-wallet", required=True)
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--fixture-dir", type=Path)
    p.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"))
    p.add_argument("--out-json", type=Path, required=True)
    p.add_argument("--out-html", type=Path, required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    http: HTTP = FixtureHTTP(args.fixture_dir) if args.fixture_dir else HTTP(args.github_token)
    native = balance(http, args.native_wallet)
    hosted = balance(http, args.hosted_handle)
    transfers = dedupe_transfers(wallet_transfers(http, args.native_wallet) + wallet_transfers(http, args.hosted_handle))
    accepted = maintainer_accepted(http, args.github_handle, args.repo)
    data = receipt(native, hosted, transfers, accepted, args.github_handle)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_html.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.out_html.write_text(render_html(data), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "native_rtc": native.amount_rtc,
        "hosted_rtc": hosted.amount_rtc,
        "pending_rtc": data["payout_totals_rtc"]["pending"],
        "confirmed_rtc": data["payout_totals_rtc"]["confirmed"],
        "accepted_records": len(accepted),
        "out_json": str(args.out_json),
        "out_html": str(args.out_html),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
