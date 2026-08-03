/**
 * Builds synthetic Stripe Payout Reconciliation Itemized CSV fixtures for
 * tests. Column set matches src/validators/stripe-payout-itemized.ts's
 * REQUIRED_COLUMNS plus the optional effective-at/status/description columns.
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
  const header = columns.join(",");
  const lines = rows.map((row) =>
    columns
      .map((c) => csvField((row as unknown as Record<string, string | undefined>)[c] ?? ""))
      .join(",")
  );
  return [header, ...lines].join("\n") + "\n";
}

/** One reconciling charge + fee row for a single payout, net = gross - fee exactly. */
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
