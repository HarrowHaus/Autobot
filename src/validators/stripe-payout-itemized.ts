import { parseCsvRecords } from "../lib/csv.js";
import { parseStrictMoney, isSupportedCurrency, type ValidationError } from "../lib/money.js";

/**
 * Validator for exactly one documented Stripe export: the itemized Payout
 * Reconciliation report (docs.stripe.com/reports/payout-reconciliation,
 * report types payout_reconciliation.itemized.7 /
 * balance_change_from_activity.itemized.*). Confirmed columns are
 * lower_snake_case plain-decimal exports — see column constants below.
 *
 * This module produces a RECONCILIATION REPORT, not an accounting-ready
 * import file. It never claims correctness beyond what it can verify from
 * the file itself: every number is either taken directly from the source
 * file or independently recomputed and compared against the source,
 * exposed as an explicit variance rather than silently trusted.
 */

export const PARSER_VERSION = "stripe-payout-itemized-v1-alpha";
export const MAX_ROWS = 50_000;

// Exact, single documented schema. Case-insensitive / trim-only matching —
// deliberately NOT fuzzy: an export using different column names is a
// different (unsupported) report and should fail loudly, not get silently
// matched to the wrong field.
const REQUIRED_COLUMNS = [
  "balance_transaction_id",
  "automatic_payout_id",
  "currency",
  "gross",
  "fee",
  "net",
  "reporting_category",
] as const;

// automatic_payout_effective_at_utc is Stripe's confirmed unambiguous-UTC
// column (present on report versions 1/2/3/6/7); automatic_payout_effective_at
// is the "or UTC equivalent" the spec allows when the _utc column isn't
// present. The _utc column is preferred whenever both exist.
const EFFECTIVE_AT_UTC_COLUMN = "automatic_payout_effective_at_utc";
const EFFECTIVE_AT_COLUMN = "automatic_payout_effective_at";

// Confirmed present in real exports; not required for the core reconciliation
// math but retained for the audit trail when available.
const DESCRIPTION_COLUMN = "description";

// Stripe does NOT include payout status in this report (confirmed against
// docs.stripe.com/reports/payout-reconciliation — status lives only on the
// Payout API object). This column is therefore essentially never present in
// a real export; it's read defensively in case a user hand-edits the file
// or a future report version adds it, but its absence is normal and never
// an error. See REPORT-LEVEL CAVEAT below.
const PAYOUT_STATUS_COLUMNS = ["automatic_payout_status", "payout_status", "status"];

/**
 * reporting_category allowlist, by confidence level. Stripe does not
 * publish a single authoritative complete enum for this field (confirmed by
 * research — only docs.stripe.com/reports/reporting-categories, which lists
 * categories that are *renamed* relative to the underlying balance
 * transaction `type`). CONFIRMED values come directly from that page.
 * LIKELY values are inferred from the balance-transaction `type` enum
 * (docs.stripe.com/api/balance_transactions/object) passing through
 * unchanged, but are NOT independently confirmed as reporting_category
 * values and need validation against a real export before being trusted.
 * Anything outside this combined list is a blocking error — see
 * "unknown reporting_category is a blocking error" in the spec. This list
 * is intentionally narrow; expanding it requires a real export, not a guess.
 */
const CONFIRMED_CATEGORIES = new Set([
  "charge",
  "refund",
  "payout_reversal",
  "transfer",
  "transfer_reversal",
  "platform_earning",
  "platform_earning_refund",
  "fee",
  "connect_reserved_funds",
  "risk_reserved_funds",
  "partial_capture_reversal",
]);
const LIKELY_UNVERIFIED_CATEGORIES = new Set(["payout", "adjustment", "dispute", "topup", "topup_reversal", "tax"]);
const KNOWN_CATEGORIES = new Set([...CONFIRMED_CATEGORIES, ...LIKELY_UNVERIFIED_CATEGORIES]);

// Categories representing the payout event itself (or its reversal), not an
// underlying transaction to reconcile — excluded from per-payout totals,
// but every exclusion is recorded in the row audit, never silent.
const EXCLUDED_FROM_TOTALS = new Set(["payout", "payout_reversal"]);

type CategoryBucket = "charge" | "refund" | "dispute" | "adjustment" | "other";

function bucketFor(category: string): CategoryBucket {
  if (category === "charge") return "charge";
  if (category === "refund") return "refund";
  if (category === "dispute") return "dispute";
  if (category === "adjustment") return "adjustment";
  return "other";
}

export interface RowAuditEntry {
  rowNumber: number; // 1-based, header excluded, matches original file order
  status: "included" | "excluded" | "error";
  reasonCode?: string;
  reasonMessage?: string;
  balanceTransactionId?: string;
  automaticPayoutId?: string;
  reportingCategory?: string;
}

export interface PayoutReconciliationLine {
  payoutId: string;
  effectiveDate: string | null; // YYYY-MM-DD; null if the file's date value couldn't be parsed
  currency: string;
  chargeTotalCents: number;
  refundTotalCents: number;
  feeTotalCents: number;
  disputeTotalCents: number;
  adjustmentTotalCents: number;
  otherTotalCents: number;
  sourceNetCents: number;
  calculatedNetCents: number;
  varianceCents: number;
  rowCount: number;
  warnings: string[];
}

export interface ReconciliationReport {
  parserVersion: string;
  sourceFileSha256: string;
  currency: string;
  generatedAt: string;
  totalRowsInFile: number;
  includedRowCount: number;
  excludedRowCount: number;
  errorRowCount: number;
  payouts: PayoutReconciliationLine[];
  rowAudit: RowAuditEntry[];
  fileWarnings: string[];
}

export interface StripeValidationOutcome {
  ok: boolean;
  report: ReconciliationReport | null;
  blockingErrors: ValidationError[];
}

function findColumn(header: string[], name: string): string | null {
  const normalized = header.map((h) => h.trim().toLowerCase());
  const idx = normalized.indexOf(name);
  return idx === -1 ? null : header[idx]!;
}

async function sha256Hex(text: string): Promise<string> {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function parseIsoDatePrefix(raw: string): string | null {
  const m = raw.trim().match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1]! : null;
}

export async function validateStripePayoutItemized(csvText: string): Promise<StripeValidationOutcome> {
  const sourceFileSha256 = await sha256Hex(csvText);
  const blocking: ValidationError[] = [];

  const rows = parseCsvRecords(csvText);
  if (rows.length === 0) {
    return {
      ok: false,
      report: null,
      blockingErrors: [{ code: "empty_file", field: "file", message: "The uploaded file has no data rows." }],
    };
  }

  if (rows.length > MAX_ROWS) {
    return {
      ok: false,
      report: null,
      blockingErrors: [
        {
          code: "row_limit_exceeded",
          field: "file",
          message: `File has ${rows.length} rows, which exceeds the ${MAX_ROWS}-row limit.`,
        },
      ],
    };
  }

  const header = Object.keys(rows[0]!);
  const missing: string[] = REQUIRED_COLUMNS.filter((col) => findColumn(header, col) === null);
  const hasEffectiveAtUtc = findColumn(header, EFFECTIVE_AT_UTC_COLUMN) !== null;
  const hasEffectiveAt = findColumn(header, EFFECTIVE_AT_COLUMN) !== null;
  if (!hasEffectiveAtUtc && !hasEffectiveAt) {
    missing.push("automatic_payout_effective_at (or automatic_payout_effective_at_utc)");
  }

  if (missing.length > 0) {
    return {
      ok: false,
      report: null,
      blockingErrors: [
        {
          code: "missing_columns",
          field: "header",
          message: `This doesn't look like a Stripe Payout Reconciliation Itemized export. Missing required column(s): ${missing.join(", ")}.`,
        },
      ],
    };
  }

  const col = {
    balanceTransactionId: findColumn(header, "balance_transaction_id")!,
    automaticPayoutId: findColumn(header, "automatic_payout_id")!,
    effectiveAt: hasEffectiveAtUtc ? findColumn(header, EFFECTIVE_AT_UTC_COLUMN)! : findColumn(header, EFFECTIVE_AT_COLUMN)!,
    currency: findColumn(header, "currency")!,
    gross: findColumn(header, "gross")!,
    fee: findColumn(header, "fee")!,
    net: findColumn(header, "net")!,
    reportingCategory: findColumn(header, "reporting_category")!,
    description: findColumn(header, DESCRIPTION_COLUMN),
    payoutStatus: PAYOUT_STATUS_COLUMNS.map((c) => findColumn(header, c)).find((c) => c !== null) ?? null,
  };

  // Rule: exactly one currency per file. Collected across ALL rows
  // (including ones that will otherwise error) because mixing currencies
  // makes every subsequent total meaningless — this must fail the whole
  // file, not just the offending rows.
  const distinctCurrencies = new Set(
    rows.map((r) => (r[col.currency] ?? "").trim().toUpperCase()).filter((c) => c !== "")
  );
  if (distinctCurrencies.size > 1) {
    return {
      ok: false,
      report: null,
      blockingErrors: [
        {
          code: "mixed_currency",
          field: col.currency,
          message: `File contains more than one currency (${[...distinctCurrencies].join(", ")}). Split the export by currency and upload each separately.`,
        },
      ],
    };
  }
  const fileCurrency = [...distinctCurrencies][0] ?? "";
  if (fileCurrency === "" || !isSupportedCurrency(fileCurrency)) {
    return {
      ok: false,
      report: null,
      blockingErrors: [
        {
          code: "unsupported_currency",
          field: col.currency,
          message: `Currency "${fileCurrency || "(blank)"}" is not supported by this alpha.`,
        },
      ],
    };
  }

  const rowAudit: RowAuditEntry[] = [];
  const payoutStatusByPayout = new Map<string, Set<string>>();

  type IncludedRow = {
    rowNumber: number;
    payoutId: string;
    effectiveDate: string | null;
    grossCents: number;
    feeCents: number;
    sourceNetCents: number;
    calculatedNetCents: number;
    category: string;
    bucket: CategoryBucket;
  };
  const included: IncludedRow[] = [];

  rows.forEach((row, i) => {
    const rowNumber = i + 1;
    const balanceTransactionId = row[col.balanceTransactionId]?.trim() ?? "";
    const automaticPayoutId = row[col.automaticPayoutId]?.trim() ?? "";
    const category = (row[col.reportingCategory] ?? "").trim().toLowerCase();

    if (balanceTransactionId === "") {
      blocking.push({
        code: "missing_balance_transaction_id",
        field: col.balanceTransactionId,
        message: `Row ${rowNumber}: missing ${col.balanceTransactionId}.`,
      });
      rowAudit.push({ rowNumber, status: "error", reasonCode: "missing_balance_transaction_id", reasonMessage: "Missing balance_transaction_id" });
      return;
    }

    // Rule: only automatic payouts. This report type is by definition
    // scoped to automatic payouts (confirmed: Stripe explicitly says the
    // manual-payout case belongs to a different report), so a row with no
    // payout ID at all is out of scope for what this tool reconciles —
    // excluded, not a whole-file failure, but always recorded.
    if (automaticPayoutId === "") {
      rowAudit.push({
        rowNumber,
        status: "excluded",
        reasonCode: "no_automatic_payout_id",
        reasonMessage: "Not associated with an automatic payout (not yet paid out, or a manual-payout account).",
        balanceTransactionId,
        reportingCategory: category,
      });
      return;
    }

    if (category === "") {
      blocking.push({
        code: "missing_reporting_category",
        field: col.reportingCategory,
        message: `Row ${rowNumber}: missing reporting_category.`,
      });
      rowAudit.push({ rowNumber, status: "error", reasonCode: "missing_reporting_category", reasonMessage: "Missing reporting_category", balanceTransactionId, automaticPayoutId });
      return;
    }
    if (!KNOWN_CATEGORIES.has(category)) {
      blocking.push({
        code: "unknown_reporting_category",
        field: col.reportingCategory,
        message: `Row ${rowNumber}: unknown reporting_category "${category}". This alpha only recognizes a deliberately narrow, verified set of categories — see the report's known-limitations notice.`,
      });
      rowAudit.push({ rowNumber, status: "error", reasonCode: "unknown_reporting_category", reasonMessage: `Unknown reporting_category "${category}"`, balanceTransactionId, automaticPayoutId, reportingCategory: category });
      return;
    }

    const rowCurrency = (row[col.currency] ?? "").trim().toUpperCase();
    const grossResult = parseStrictMoney(row[col.gross], rowCurrency || fileCurrency, "gross");
    const feeResult = parseStrictMoney(row[col.fee], rowCurrency || fileCurrency, "fee");
    const netResult = parseStrictMoney(row[col.net], rowCurrency || fileCurrency, "net");

    for (const [label, result] of [
      ["gross", grossResult],
      ["fee", feeResult],
      ["net", netResult],
    ] as const) {
      if (!result.ok) {
        blocking.push({ code: result.error.code, field: result.error.field, message: `Row ${rowNumber} (${label}): ${result.error.message}` });
      }
    }
    if (!grossResult.ok || !feeResult.ok || !netResult.ok) {
      rowAudit.push({ rowNumber, status: "error", reasonCode: "unparseable_amount", reasonMessage: "One or more money fields could not be parsed.", balanceTransactionId, automaticPayoutId, reportingCategory: category });
      return;
    }

    const effectiveDate = parseIsoDatePrefix(row[col.effectiveAt] ?? "");
    if (col.payoutStatus) {
      const status = (row[col.payoutStatus] ?? "").trim().toLowerCase();
      if (status !== "") {
        const set = payoutStatusByPayout.get(automaticPayoutId) ?? new Set<string>();
        set.add(status);
        payoutStatusByPayout.set(automaticPayoutId, set);
      }
    }

    if (EXCLUDED_FROM_TOTALS.has(category)) {
      rowAudit.push({
        rowNumber,
        status: "excluded",
        reasonCode: "payout_event_row",
        reasonMessage: `reporting_category "${category}" represents the payout event itself, not a transaction to reconcile.`,
        balanceTransactionId,
        automaticPayoutId,
        reportingCategory: category,
      });
      return;
    }

    included.push({
      rowNumber,
      payoutId: automaticPayoutId,
      effectiveDate,
      grossCents: grossResult.cents,
      feeCents: feeResult.cents,
      sourceNetCents: netResult.cents,
      calculatedNetCents: grossResult.cents - feeResult.cents,
      category,
      bucket: bucketFor(category),
    });
    rowAudit.push({ rowNumber, status: "included", balanceTransactionId, automaticPayoutId, reportingCategory: category });
  });

  if (blocking.length > 0) {
    return { ok: false, report: null, blockingErrors: blocking };
  }

  // Rule: payout status consistency. The report almost never carries this
  // column at all (confirmed: Stripe's itemized reconciliation export does
  // not include payout status — see PAYOUT_STATUS_COLUMNS comment above).
  // When present, rows sharing a payout ID reporting different statuses is
  // an internal inconsistency worth failing on; it should never happen for
  // a genuine export.
  for (const [payoutId, statuses] of payoutStatusByPayout) {
    if (statuses.size > 1) {
      return {
        ok: false,
        report: null,
        blockingErrors: [
          {
            code: "inconsistent_payout_status",
            field: col.payoutStatus ?? "payout_status",
            message: `Payout ${payoutId} has inconsistent status values across its rows (${[...statuses].join(", ")}).`,
          },
        ],
      };
    }
  }

  // Group included rows by payout and compute the reconciliation totals.
  const byPayout = new Map<string, IncludedRow[]>();
  for (const row of included) {
    const list = byPayout.get(row.payoutId) ?? [];
    list.push(row);
    byPayout.set(row.payoutId, list);
  }

  const payouts: PayoutReconciliationLine[] = [];
  for (const [payoutId, payoutRows] of byPayout) {
    const line: PayoutReconciliationLine = {
      payoutId,
      effectiveDate: payoutRows.find((r) => r.effectiveDate)?.effectiveDate ?? null,
      currency: fileCurrency,
      chargeTotalCents: 0,
      refundTotalCents: 0,
      feeTotalCents: 0,
      disputeTotalCents: 0,
      adjustmentTotalCents: 0,
      otherTotalCents: 0,
      sourceNetCents: 0,
      calculatedNetCents: 0,
      varianceCents: 0,
      rowCount: payoutRows.length,
      warnings: [],
    };

    for (const row of payoutRows) {
      line.feeTotalCents += row.feeCents;
      line.sourceNetCents += row.sourceNetCents;
      line.calculatedNetCents += row.calculatedNetCents;
      switch (row.bucket) {
        case "charge":
          line.chargeTotalCents += row.grossCents;
          break;
        case "refund":
          line.refundTotalCents += row.grossCents;
          break;
        case "dispute":
          line.disputeTotalCents += row.grossCents;
          break;
        case "adjustment":
          line.adjustmentTotalCents += row.grossCents;
          break;
        default:
          line.otherTotalCents += row.grossCents;
      }
    }

    line.varianceCents = line.calculatedNetCents - line.sourceNetCents;
    if (line.varianceCents !== 0) {
      line.warnings.push(
        `Calculated net differs from the source file's net by ${line.varianceCents} cent(s) — review before relying on this payout's totals.`
      );
    }
    if (!line.effectiveDate) {
      line.warnings.push("No parseable payout effective date found for this payout.");
    }
    payouts.push(line);
  }
  payouts.sort((a, b) => (a.effectiveDate ?? "").localeCompare(b.effectiveDate ?? "") || a.payoutId.localeCompare(b.payoutId));

  const fileWarnings: string[] = [];
  if (!col.payoutStatus) {
    fileWarnings.push(
      "This file does not include a payout-status column (expected — Stripe's itemized reconciliation report doesn't carry one). Payout finality (paid vs. pending/failed/reversed) could not be checked here; verify current status in the Stripe Dashboard before relying on this report."
    );
  }
  const excludedCount = rowAudit.filter((r) => r.status === "excluded").length;
  if (excludedCount > 0) {
    fileWarnings.push(`${excludedCount} row(s) were excluded from totals — see rowAudit for the reason for each.`);
  }

  const report: ReconciliationReport = {
    parserVersion: PARSER_VERSION,
    sourceFileSha256,
    currency: fileCurrency,
    generatedAt: new Date().toISOString(),
    totalRowsInFile: rows.length,
    includedRowCount: included.length,
    excludedRowCount: excludedCount,
    errorRowCount: 0,
    payouts,
    rowAudit,
    fileWarnings,
  };

  return { ok: true, report, blockingErrors: [] };
}
