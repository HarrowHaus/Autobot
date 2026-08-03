import { parseCsvRecords } from "../lib/csv.js";
import { parseMoneyToCents } from "../lib/money.js";
import type { NormalizedTransaction } from "../types.js";
import { UnrecognizedFormatError } from "../types.js";

// The subset of PayPal's "Activity" CSV export columns we depend on.
// PayPal exports many more columns; we only require these to recognize the format.
const REQUIRED_HEADERS = ["Date", "Type", "Currency", "Gross", "Fee", "Transaction ID"];

function parsePayPalDate(raw: string): string {
  // PayPal exports dates as MM/DD/YYYY by default.
  const m = raw.trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!m) {
    // Fall back to ISO-ish input if already YYYY-MM-DD.
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw.trim())) return raw.trim();
    throw new Error(`Unrecognized PayPal date format: "${raw}"`);
  }
  const [, month, day, year] = m;
  return `${year}-${month!.padStart(2, "0")}-${day!.padStart(2, "0")}`;
}

export function parsePayPal(csvText: string): NormalizedTransaction[] {
  const rows = parseCsvRecords(csvText);
  if (rows.length === 0) {
    throw new UnrecognizedFormatError("Empty file", []);
  }

  const header = Object.keys(rows[0]!);
  const missing = REQUIRED_HEADERS.filter((h) => !header.includes(h));
  if (missing.length > 0) {
    throw new UnrecognizedFormatError(
      `Missing expected PayPal columns: ${missing.join(", ")}`,
      header
    );
  }

  const transactions: NormalizedTransaction[] = [];

  for (const row of rows) {
    const txnId = row["Transaction ID"];
    if (!txnId) continue; // skip footer/summary rows without a transaction id

    const grossCents = parseMoneyToCents(row["Gross"] ?? "0");
    // PayPal reports Fee as a negative number (a cost). We store fee as a
    // signed "cost" value: positive = fee charged, negative = fee credited back.
    const feeCents = -parseMoneyToCents(row["Fee"] ?? "0");
    const netCents = grossCents - feeCents; // derived, not trusted from source — guarantees the accounting identity

    const type = row["Type"] ?? "other";
    transactions.push({
      date: parsePayPalDate(row["Date"] ?? ""),
      type: /refund/i.test(type) ? "refund" : "charge",
      grossCents,
      feeCents,
      netCents,
      currency: (row["Currency"] ?? "USD").toUpperCase(),
      // PayPal MVP scope: no payout-batch grouping yet — each settled
      // transaction stands as its own single-row bank deposit line.
      payoutId: txnId,
      description: `PayPal ${type} — ${row["Name"] ?? txnId}`.trim(),
    });
  }

  if (transactions.length === 0) {
    throw new UnrecognizedFormatError("No transaction rows found in PayPal export", header);
  }

  return transactions;
}
