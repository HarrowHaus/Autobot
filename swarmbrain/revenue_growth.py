"""Bounded, consent-aware buyer experiments; no network sends or wallet signing.

Keep this SQLite database private. Customer records never belong in a public repo.
A trusted settlement adapter must verify receipts independently before recording sales.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit

ARMS = ("fixed_price", "bounded_sample")
BASE = "eip155:8453"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def timestamp(value=None):
    value = value or datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timezone-aware datetime required")
    return int(value.timestamp())


def https_url(value):
    try:
        parsed = urlsplit(str(value))
        return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password)
    except ValueError:
        return False


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("nonnegative integer required")
    return value


def qualify(lead, service, now=None):
    """Only operator-reviewed facts qualify; discovered web content is untrusted."""
    current = timestamp(now)
    reasons = []
    if lead.get("source_kind") not in {"request_for_work", "request_for_quotes", "invited_referral"}:
        reasons.append("no_buying_intent")
    if not https_url(lead.get("source_url")) or not lead.get("request_id"):
        reasons.append("missing_request_provenance")
    if not lead.get("operator_id") or lead.get("relationship") != "independent_customer":
        reasons.append("not_a_verified_independent_customer")
    if lead.get("contact_permission") not in {"task_reply", "quotes_invited", "explicit_opt_in"}:
        reasons.append("no_permitted_offer_channel")
    if not https_url(lead.get("permission_source")) or not https_url(lead.get("contact_url")):
        reasons.append("missing_contact_provenance")
    if lead.get("reviewed_by_operator") is not True:
        reasons.append("unreviewed_external_claims")
    observed, expiry = lead.get("observed_at"), lead.get("expires_at")
    if type(observed) is not int or observed > current or current - observed > 7 * 86400:
        reasons.append("stale_or_unknown_request")
    if type(expiry) is not int or expiry <= current or lead.get("status") != "open":
        reasons.append("request_not_open")
    if lead.get("upfront_fee_atomic", 0) != 0:
        reasons.append("upfront_fee_disallowed")
    if lead.get("opted_out") is True:
        reasons.append("opted_out")
    if not set(lead.get("required_skills", [])) <= set(service.get("verified_skills", [])):
        reasons.append("capability_gap")
    for field in ("delivery_ready", "payment_ready"):
        if service.get(field) is not True or not https_url(service.get(field + "_evidence")):
            reasons.append(field + "_unverified")
    if not https_url(service.get("order_url")):
        reasons.append("no_order_endpoint")
    price, cost, budget = service.get("price_atomic"), service.get("max_cost_atomic"), lead.get("budget_atomic")
    if any(type(v) is not int for v in (price, cost, budget)) or min(price or 0, cost or 0, budget or 0) < 0:
        reasons.append("unknown_price_cost_or_budget")
    elif price <= 0 or price <= cost or price > budget:
        reasons.append("unprofitable_or_over_budget")
    if service.get("network") != BASE or service.get("asset", "").lower() != USDC:
        reasons.append("unsupported_settlement_asset")
    return sorted(set(reasons))


def offer_text(lead, service, arm):
    if arm not in ARMS:
        raise ValueError("unknown experiment arm")
    price = format(Decimal(service["price_atomic"]) / 1_000_000, "f")
    text = (f"A0 is offering {service['name']} for your request {lead['request_id']}. "
            f"Fixed quote: {price} USDC on Base. Scope: {service['scope']}. "
            f"Acceptance check: {service['acceptance_test']}. ")
    if arm == "bounded_sample":
        text += "One small sample using public or explicitly permitted input is available before purchase; no automatic charge. "
    text += ("Proceed only within your owner's purchasing authority. No subscription or automatic renewal. "
             "Declining ends this offer; no follow-up unless requested. " + service["order_url"])
    return text


class ExperimentBook:
    def __init__(self, path, campaign="a0-message-test-v1"):
        self.campaign = campaign
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS contacts (
            id TEXT PRIMARY KEY, campaign TEXT, operator_id TEXT, arm TEXT, reserved_at INTEGER,
            status TEXT, lead_json TEXT, service_json TEXT, message TEXT, remote_receipt TEXT,
            UNIQUE(campaign, operator_id));
          CREATE TABLE IF NOT EXISTS suppressed (operator_id TEXT PRIMARY KEY, at INTEGER);
          CREATE TABLE IF NOT EXISTS costs (
            reference TEXT PRIMARY KEY, contact_id TEXT, amount_atomic INTEGER, kind TEXT);
          CREATE TABLE IF NOT EXISTS sales (
            settlement_key TEXT PRIMARY KEY, order_id TEXT UNIQUE, contact_id TEXT,
            amount_atomic INTEGER, receipt_json TEXT);
        ''')

    def reserve(self, lead, service, now=None):
        reasons = qualify(lead, service, now)
        if reasons:
            raise ValueError(",".join(reasons))
        current, operator = timestamp(now), lead["operator_id"]
        key = hashlib.sha256((self.campaign + "|" + operator).encode()).hexdigest()
        arm = ARMS[int(key[:8], 16) % len(ARMS)]
        # BEGIN IMMEDIATE serializes reservation caps across processes sharing the DB.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.db.execute("SELECT 1 FROM suppressed WHERE operator_id=?", (operator,)).fetchone():
                raise ValueError("opted_out")
            if self.db.execute("SELECT 1 FROM contacts WHERE operator_id=? AND reserved_at>?", (operator, current - 7*86400)).fetchone():
                raise ValueError("operator_cooldown")
            if self.db.execute("SELECT count(*) FROM contacts WHERE reserved_at>?", (current-86400,)).fetchone()[0] >= 5:
                raise ValueError("daily_contact_cap")
            if self.db.execute("SELECT 1 FROM contacts WHERE campaign=? AND operator_id=?", (self.campaign, operator)).fetchone():
                raise ValueError("already_assigned")
            if arm == "bounded_sample" and service.get("sample_ready") is not True:
                raise ValueError("sample_arm_not_ready")
            message = offer_text(lead, service, arm)
            self.db.execute("INSERT INTO contacts VALUES (?,?,?,?,?,'reserved',?,?,?,NULL)",
                            (key, self.campaign, operator, arm, current, json.dumps(lead), json.dumps(service), message))
            self.db.commit()
            return {"id": key, "arm": arm, "status": "reserved_not_sent", "message": message}
        except Exception:
            self.db.rollback()
            raise

    def mark_sent(self, contact_id, remote_receipt):
        if not https_url(remote_receipt):
            raise ValueError("actual_transport_receipt_required")
        with self.db:
            changed = self.db.execute("UPDATE contacts SET status='sent',remote_receipt=? WHERE id=? AND status='reserved'",
                                      (remote_receipt, contact_id)).rowcount
            if changed != 1:
                raise ValueError("contact_missing_or_already_sent")

    def suppress(self, operator_id, now=None):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO suppressed VALUES (?,?)", (operator_id, timestamp(now)))

    def record_cost(self, contact_id, reference, amount_atomic, kind="fulfillment"):
        integer(amount_atomic)
        if kind not in {"fulfillment", "sample", "network_fee", "refund", "outreach"} or not reference:
            raise ValueError("invalid_cost")
        if not self.db.execute("SELECT 1 FROM contacts WHERE id=?", (contact_id,)).fetchone():
            raise ValueError("unknown_contact")
        with self.db:
            self.db.execute("INSERT INTO costs VALUES (?,?,?,?)", (reference, contact_id, amount_atomic, kind))

    def record_sale(self, contact_id, receipt, verify_receipt):
        """Trusted in-process adapter verifies chain + exact order/payer/payee binding.

        There is deliberately no HTTP route or JSON flag to declare a receipt verified.
        The adapter must return True, not merely a truthy object, after its own checks.
        """
        contact = self.db.execute("SELECT * FROM contacts WHERE id=? AND status='sent'", (contact_id,)).fetchone()
        if not contact:
            raise ValueError("no_sent_offer")
        service, lead = json.loads(contact["service_json"]), json.loads(contact["lead_json"])
        if receipt.get("network") != BASE or receipt.get("asset", "").lower() != USDC:
            raise ValueError("wrong_network_or_asset")
        if receipt.get("operator_id") != lead["operator_id"] or receipt.get("environment") != "mainnet":
            raise ValueError("not_matching_external_mainnet_customer")
        if not receipt.get("order_id") or not receipt.get("settlement_key"):
            raise ValueError("missing_order_or_chain_event_identity")
        if integer(receipt.get("amount_atomic"), 1) != service["price_atomic"]:
            raise ValueError("receipt_does_not_match_quote")
        if not callable(verify_receipt) or verify_receipt(receipt, dict(contact)) is not True:
            raise ValueError("independent_settlement_verification_required")
        with self.db:
            self.db.execute("INSERT INTO sales VALUES (?,?,?,?,?)", (receipt["settlement_key"], receipt["order_id"],
                            contact_id, receipt["amount_atomic"], json.dumps(receipt)))

    def report(self):
        rows = []
        for arm in ARMS:
            contacts = self.db.execute("SELECT * FROM contacts WHERE campaign=? AND arm=?", (self.campaign, arm)).fetchall()
            revenue = cost = orders = customers = sent = 0
            buyers = set()
            for row in contacts:
                sent += row["status"] == "sent"
                sales = self.db.execute("SELECT amount_atomic FROM sales WHERE contact_id=?", (row["id"],)).fetchall()
                orders += len(sales)
                revenue += sum(s[0] for s in sales)
                if sales:
                    buyers.add(row["operator_id"])
                cost += self.db.execute("SELECT coalesce(sum(amount_atomic),0) FROM costs WHERE contact_id=?", (row["id"],)).fetchone()[0]
            customers = len(buyers)
            rows.append({"arm": arm, "reserved": len(contacts), "sent": sent, "paying_operators": customers,
                         "paid_orders": orders, "repeat_orders": max(0, orders-customers),
                         "revenue_atomic": revenue, "recorded_costs_atomic": cost, "net_atomic": revenue-cost,
                         "net_atomic_per_sent_offer": (revenue-cost)/sent if sent else None})
        return {"campaign": self.campaign, "arms": rows, "winner": None,
                "decision": "collect_external_evidence_then_review; no automatic winner from sparse data",
                "note": "Net subtracts recorded costs only; missing costs must be reconciled before promotion."}
