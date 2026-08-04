/**
 * Synthetic Stripe Payout Reconciliation Itemized (v7) fixtures.
 *
 * ⚠️ THESE ARE SYNTHETIC. No real Stripe export has been run through this
 * parser. Stripe publishes no example CSV rows for any financial report, so
 * these were constructed from the documented column schema plus the
 * arithmetic identity stated in the BalanceTransaction API reference:
 *
 *      net = gross - fee,  with fee a POSITIVE magnitude
 *
 * Every row helper below satisfies that identity by construction. If a real
 * export turns out to use the opposite convention, these fixtures encode the
 * wrong assumption and the validator's per-row identity check is what will
 * surface it — see identityError() in the validator.
 */

export interface FixtureRow {
  balance_transaction_id: string;
  automatic_payout_id: string;
  automatic_payout_effective_at_utc?: string;
  currency: string;
  gross: string;
  fee: string;
  net: string;
  reporting_category: string;
  description?: string;
  automatic_payout_status?: string;
}

const COLUMNS = [
  "balance_transaction_id",
  "automatic_payout_id",
  "automatic_payout_effective_at_utc",
  "currency",
  "gross",
  "fee",
  "net",
  "reporting_category",
  "description",
] as const;

function csvField(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function buildStripeItemizedCsv(rows: FixtureRow[], extraColumns: string[] = []): string {
  const columns = [...COLUMNS, ...extraColumns];
  const lines = rows.map((row) =>
    columns.map((c) => csvField((row as unknown as Record<string, string | undefined>)[c] ?? "")).join(",")
  );
  return [columns.join(","), ...lines].join("\n") + "\n";
}

/** A charge: gross positive, fee positive, net = gross - fee. */
export function chargeRow(overrides: Partial<FixtureRow> = {}): FixtureRow {
  return {
    balance_transaction_id: "txn_1",
    automatic_payout_id: "po_1",
    automatic_payout_effective_at_utc: "2026-01-15 00:00:00",
    currency: "usd",
    gross: "100.00",
    fee: "3.20",
    net: "96.80",
    reporting_category: "charge",
    ...overrides,
  };
}

/**
 * A standalone Stripe fee row (reporting_category = "fee").
 *
 * CONFIRMED from Stripe's published fee formulas: on these rows the fee
 * COLUMN is 0 and the amount sits in gross/net as a NEGATIVE number. A tool
 * that totals only the fee column misses these entirely — which is exactly
 * the bug this fixture exists to catch.
 */
export function standaloneFeeRow(overrides: Partial<FixtureRow> = {}): FixtureRow {
  return {
    balance_transaction_id: "txn_fee_1",
    automatic_payout_id: "po_1",
    automatic_payout_effective_at_utc: "2026-01-15 00:00:00",
    currency: "usd",
    gross: "-25.00",
    fee: "0.00",
    net: "-25.00",
    reporting_category: "fee",
    ...overrides,
  };
}

/** A refund: gross negative, net = gross - fee. */
export function refundRow(overrides: Partial<FixtureRow> = {}): FixtureRow {
  return {
    balance_transaction_id: "txn_refund_1",
    automatic_payout_id: "po_1",
    automatic_payout_effective_at_utc: "2026-01-15 00:00:00",
    currency: "usd",
    gross: "-20.00",
    fee: "0.00",
    net: "-20.00",
    reporting_category: "refund",
    ...overrides,
  };
}
