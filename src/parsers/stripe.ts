import { parseCsvRecords } from "../lib/csv.js";
import { parseMoneyToCents } from "../lib/money.js";
import type { NormalizedTransaction } from "../types.js";
import { UnrecognizedFormatError } from "../types.js";

/**
 * Expects Stripe's payout reconciliation report shape (Dashboard > Balance >
 * Payouts > a payout > "Download reconciliation report"), or an equivalent
 * itemized balance-transaction export with the columns below. Header
 * matching is case-insensitive with a few common synonyms to absorb minor
 * export variations; anything further off gets a clear "unrecognized
 * format" error rather than a silently wrong answer.
 */
const COLUMN_ALIASES: Record<string, string[]> = {
  created: ["created (utc)", "created date (utc)", "created_utc", "created"],
  currency: ["currency"],
  gross: ["gross", "amount"],
  fee: ["fee"],
  payoutId: ["payout id", "automatic payout id", "automatic_payout_id", "payout_id"],
  description: ["description"],
  reportingCategory: ["reporting category", "reporting_category"],
};

// Rows that represent the payout/deposit itself (or other non-transaction
// movements), not an underlying charge/fee/refund to reconcile.
const EXCLUDED_CATEGORIES = new Set(["payout", "payout_reversal", "topup", "topup_reversal"]);

function buildColumnMap(header: string[]): Partial<Record<keyof typeof COLUMN_ALIASES, string>> {
  const normalized = header.map((h) => h.trim().toLowerCase());
  const map: Partial<Record<string, string>> = {};
  for (const [key, aliases] of Object.entries(COLUMN_ALIASES)) {
    const idx = normalized.findIndex((h) => aliases.includes(h));
    if (idx !== -1) map[key] = header[idx]!;
  }
  return map;
}

function parseStripeDate(raw: string): string {
  // Stripe's UTC timestamps look like "2026-01-15 14:32:01" or a bare date.
  const m = raw.trim().match(/^(\d{4}-\d{2}-\d{2})/);
  if (!m) throw new Error(`Unrecognized Stripe date format: "${raw}"`);
  return m[1]!;
}

export function parseStripe(csvText: string): NormalizedTransaction[] {
  const rows = parseCsvRecords(csvText);
  if (rows.length === 0) {
    throw new UnrecognizedFormatError("Empty file", []);
  }

  const header = Object.keys(rows[0]!);
  const colMap = buildColumnMap(header);
  const required = ["created", "currency", "gross", "fee", "payoutId"] as const;
  const missing = required.filter((k) => !colMap[k]);
  if (missing.length > 0) {
    throw new UnrecognizedFormatError(
      `Missing expected Stripe columns for: ${missing.join(", ")}`,
      header
    );
  }

  const transactions: NormalizedTransaction[] = [];

  for (const row of rows) {
    const category = (colMap.reportingCategory ? row[colMap.reportingCategory] ?? "" : "")
      .trim()
      .toLowerCase();
    if (EXCLUDED_CATEGORIES.has(category)) continue;

    const payoutId = row[colMap.payoutId!];
    if (!payoutId) continue; // not yet paid out / no bank deposit to reconcile against

    const grossCents = parseMoneyToCents(row[colMap.gross!] ?? "0");
    const feeCents = parseMoneyToCents(row[colMap.fee!] ?? "0"); // Stripe reports fee as a positive cost
    const netCents = grossCents - feeCents; // derived, not trusted from source — guarantees the accounting identity

    transactions.push({
      date: parseStripeDate(row[colMap.created!] ?? ""),
      type: category === "refund" ? "refund" : category === "adjustment" ? "adjustment" : "charge",
      grossCents,
      feeCents,
      netCents,
      currency: (row[colMap.currency!] ?? "USD").toUpperCase(),
      payoutId,
      description: colMap.description
        ? row[colMap.description] || `Stripe ${category || "transaction"}`
        : `Stripe ${category || "transaction"}`,
    });
  }

  if (transactions.length === 0) {
    throw new UnrecognizedFormatError(
      "No reconcilable transaction rows found in Stripe export (nothing with a Payout ID)",
      header
    );
  }

  return transactions;
}
