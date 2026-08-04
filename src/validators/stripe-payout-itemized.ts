import { parseCsvStructured } from "../lib/csv.js";
import { parseCalendarDate } from "../lib/dates.js";
import { parseStrictMoney, isSupportedCurrency, minorDigitsFor, centsToDecimalString, type ValidationError } from "../lib/money.js";
import { CATEGORY_SPECS, isFeeInGross, isKnownCategory, isPayoutEvent, isUnclassified, specFor } from "./stripe-categories.js";

/**
 * Validator for exactly one documented Stripe export: the itemized Payout
 * Reconciliation report (docs.stripe.com/reports/report-types/payout-reconciliation),
 * report type `payout_reconciliation.itemized.7`.
 *
 * It produces a RECONCILIATION REPORT, not an accounting-ready import. Every
 * number is either taken directly from the file or independently recomputed
 * and compared against it, with any disagreement surfaced rather than
 * smoothed over.
 *
 * ── The arithmetic identity ────────────────────────────────────────────────
 * `net = gross - fee`, with `fee` a POSITIVE magnitude.
 *
 * Provenance, because this is the single most load-bearing assumption here:
 * the reports documentation defines gross/fee/net without ever stating a
 * sign convention or an identity. The statement exists only in the
 * BalanceTransaction API reference, verbatim: fee is "Represented as a
 * positive integer when assessed", and "You can calculate the net impact of
 * a transaction on a balance by `amount` - `fee`". Two v7 columns
 * independently corroborate a positive fee: `withheld_tax` is "already
 * included within the fee column", and `fee_net_of_withheld_tax` is
 * "Calculated as fee minus withheld_tax" — both incoherent if fee were a
 * signed negative deduction.
 *
 * Stripe publishes NO example CSV rows for any financial report, so this
 * could not be confirmed against real data. It is therefore enforced on
 * EVERY ROW, and when a row fails, the error explicitly names the opposite
 * convention as a candidate cause — so a real export using the other
 * convention produces a loud, diagnostic failure instead of silently wrong
 * totals. See identityError() below.
 *
 * ── What this validator CANNOT do ──────────────────────────────────────────
 * It cannot verify that the export is complete. There is no payout-total
 * column, row count, or checksum anywhere in the 80-column v7 schema, and
 * the Reports API accepts `currency` and `reporting_category` filters whose
 * use is NOT recorded in the output file. A filtered export is structurally
 * indistinguishable from a full one. The report says so explicitly rather
 * than implying the totals are whole.
 */

export const PARSER_VERSION = "stripe-payout-itemized-v2-alpha";
export const MAX_ROWS = 50_000;
export const MAX_REPORTED_ERRORS = 100;

const REQUIRED_COLUMNS = [
  "balance_transaction_id",
  "automatic_payout_id",
  "currency",
  "gross",
  "fee",
  "net",
  "reporting_category",
] as const;

// `automatic_payout_effective_at` is the v7 DEFAULT column (rendered in the
// timezone the report run requested); `_utc` is non-default but unambiguous.
// Prefer _utc when both are present.
const EFFECTIVE_AT_UTC_COLUMN = "automatic_payout_effective_at_utc";
const EFFECTIVE_AT_COLUMN = "automatic_payout_effective_at";

export interface RowAuditEntry {
  rowNumber: number; // 1-based, header excluded, matches original file order
  status: "included" | "excluded" | "error";
  reasonCode?: string;
  reasonMessage?: string;
  balanceTransactionId?: string;
  automaticPayoutId?: string;
  reportingCategory?: string;
}

/**
 * Per-category totals, deliberately mirroring the four columns Stripe's own
 * summary reports use (count/gross/fee/net) so a user can cross-check this
 * against `payout_reconciliation.by_id.summary.1` line by line.
 */
export interface CategoryTotal {
  category: string;
  rowCount: number;
  grossCents: number;
  feeColumnCents: number;
  netCents: number;
  /** Booking treatment, or "unclassified" where Stripe doesn't document one. */
  classification: string;
  /** Stripe's documented balance direction, and how confident that is. */
  direction: string;
  directionConfidence: string;
  note?: string;
}

export interface PayoutReconciliationLine {
  payoutId: string;
  /** Always a validated calendar date: an unparseable date blocks the file. */
  effectiveDate: string;
  currency: string;
  rowCount: number;
  /** EVERY category present in this payout, by name. There is no "other" bucket. */
  categories: CategoryTotal[];
  grossTotalCents: number;
  /** Sum of the `fee` COLUMN only. */
  feeColumnTotalCents: number;
  /** Sum of gross for fee-in-gross categories (fee, network_cost, contribution, financing_paydown). Negative. */
  feeInGrossTotalCents: number;
  /** Stripe's published fee-total formula, as a positive magnitude. */
  totalFeesPerStripeFormulaCents: number;
  sourceNetCents: number;
  calculatedNetCents: number;
  varianceCents: number;
  warnings: string[];
}

export interface ReconciliationReport {
  parserVersion: string;
  sourceFileSha256: string;
  currency: string;
  currencyMinorDigits: number;
  generatedAt: string;
  totalRowsInFile: number;
  includedRowCount: number;
  excludedRowCount: number;
  payouts: PayoutReconciliationLine[];
  rowAudit: RowAuditEntry[];
  fileWarnings: string[];
  /** Always present. Completeness is never asserted, because it cannot be verified. */
  completenessDisclosure: string[];
}

export interface StripeValidationOutcome {
  ok: boolean;
  report: ReconciliationReport | null;
  blockingErrors: ValidationError[];
  /** True when errors were truncated at MAX_REPORTED_ERRORS. */
  errorsTruncated: boolean;
}

function findColumn(header: string[], name: string): string | null {
  const idx = header.map((h) => h.trim().toLowerCase()).indexOf(name);
  return idx === -1 ? null : header[idx]!;
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function fail(errors: ValidationError[]): StripeValidationOutcome {
  return { ok: false, report: null, blockingErrors: errors, errorsTruncated: false };
}

/**
 * Builds the per-row identity error. When the values happen to satisfy
 * `gross + fee` instead, that is called out by name — if this tool has the
 * sign convention backwards, this message is how we find out, rather than
 * shipping quietly wrong numbers.
 */
function identityError(
  rowNumber: number,
  grossCents: number,
  feeCents: number,
  netCents: number,
  currency: string
): ValidationError {
  const g = centsToDecimalString(grossCents, currency);
  const f = centsToDecimalString(feeCents, currency);
  const n = centsToDecimalString(netCents, currency);
  const expected = centsToDecimalString(grossCents - feeCents, currency);

  const satisfiesOppositeSign = grossCents + feeCents === netCents;
  const suffix = satisfiesOppositeSign
    ? ` NOTE: these values DO satisfy net = gross + fee. That would mean this export reports fees as signed negatives, a convention this tool does not implement. Do not rely on any figure from this file — please report it along with the Stripe report version used, so the parser can be corrected.`
    : ` Every row must satisfy Stripe's documented identity net = gross - fee. A row that doesn't means either the file was edited or this tool has misread the schema.`;

  return {
    code: "row_identity_violation",
    field: "net",
    message: `Row ${rowNumber}: net (${n}) does not equal gross - fee (${g} - ${f} = ${expected}).${suffix}`,
  };
}

export async function validateStripePayoutItemized(csvText: string): Promise<StripeValidationOutcome> {
  const sourceFileSha256 = await sha256Hex(csvText);

  const structure = parseCsvStructured(csvText);
  if (!structure.ok) {
    return fail(structure.errors.slice(0, MAX_REPORTED_ERRORS));
  }

  const rows = structure.records;
  const header = structure.header;

  if (rows.length === 0) {
    return fail([{ code: "empty_file", field: "file", message: "The uploaded file has a header but no data rows." }]);
  }
  if (rows.length > MAX_ROWS) {
    return fail([
      {
        code: "row_limit_exceeded",
        field: "file",
        message: `File has ${rows.length} rows, which exceeds the ${MAX_ROWS}-row limit.`,
      },
    ]);
  }

  // ── Column presence ───────────────────────────────────────────────────────
  const missing: string[] = REQUIRED_COLUMNS.filter((col) => findColumn(header, col) === null);
  const hasEffectiveAtUtc = findColumn(header, EFFECTIVE_AT_UTC_COLUMN) !== null;
  const hasEffectiveAt = findColumn(header, EFFECTIVE_AT_COLUMN) !== null;
  if (!hasEffectiveAtUtc && !hasEffectiveAt) {
    missing.push("automatic_payout_effective_at (or automatic_payout_effective_at_utc)");
  }

  if (missing.length > 0) {
    const missingPayoutId = missing.includes("automatic_payout_id");
    const hint = missingPayoutId
      ? " Note: a default-column export of report version 6 omits automatic_payout_id entirely and cannot be grouped by payout. Re-run the report as payout_reconciliation.itemized.7, or add the automatic_payout_id and automatic_payout_effective_at columns."
      : "";
    return fail([
      {
        code: "missing_columns",
        field: "header",
        message: `This doesn't look like a Stripe Payout Reconciliation Itemized (v7) export. Missing required column(s): ${missing.join(", ")}.${hint}`,
      },
    ]);
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
  };

  // ── File-level currency ───────────────────────────────────────────────────
  const distinctCurrencies = new Set(
    rows.map((r) => (r[col.currency] ?? "").trim().toUpperCase()).filter((c) => c !== "")
  );
  if (distinctCurrencies.size > 1) {
    return fail([
      {
        code: "mixed_currency",
        field: col.currency,
        message: `File contains more than one currency (${[...distinctCurrencies].sort().join(", ")}). Stripe reports are produced per settlement currency — export each currency separately and upload them one at a time.`,
      },
    ]);
  }
  const fileCurrency = [...distinctCurrencies][0] ?? "";
  if (fileCurrency === "" || !isSupportedCurrency(fileCurrency)) {
    return fail([
      {
        code: "unsupported_currency",
        field: col.currency,
        message: `Currency "${fileCurrency || "(blank)"}" is not supported by this alpha.`,
      },
    ]);
  }
  const minorDigits = minorDigitsFor(fileCurrency);

  // ── Row pass ──────────────────────────────────────────────────────────────
  const blocking: ValidationError[] = [];
  const rowAudit: RowAuditEntry[] = [];
  const seenTransactionIds = new Map<string, number>();

  interface IncludedRow {
    payoutId: string;
    effectiveDate: string;
    grossCents: number;
    feeCents: number;
    netCents: number;
    category: string;
  }
  const included: IncludedRow[] = [];

  for (const [i, row] of rows.entries()) {
    const rowNumber = i + 1;
    const balanceTransactionId = (row[col.balanceTransactionId] ?? "").trim();
    const automaticPayoutId = (row[col.automaticPayoutId] ?? "").trim();
    const category = (row[col.reportingCategory] ?? "").trim().toLowerCase();

    const errorRow = (reasonCode: string, reasonMessage: string) => {
      rowAudit.push({
        rowNumber,
        status: "error",
        reasonCode,
        reasonMessage,
        balanceTransactionId: balanceTransactionId || undefined,
        automaticPayoutId: automaticPayoutId || undefined,
        reportingCategory: category || undefined,
      });
    };

    if (balanceTransactionId === "") {
      blocking.push({
        code: "missing_balance_transaction_id",
        field: col.balanceTransactionId,
        message: `Row ${rowNumber}: missing balance_transaction_id.`,
      });
      errorRow("missing_balance_transaction_id", "Missing balance_transaction_id");
      continue;
    }

    // Duplicate transaction IDs mean the same money counted twice.
    const firstSeenAt = seenTransactionIds.get(balanceTransactionId);
    if (firstSeenAt !== undefined) {
      blocking.push({
        code: "duplicate_balance_transaction_id",
        field: col.balanceTransactionId,
        message: `Row ${rowNumber}: balance_transaction_id "${balanceTransactionId}" already appeared on row ${firstSeenAt}. Duplicate transactions would be counted twice, so the file is rejected.`,
      });
      errorRow("duplicate_balance_transaction_id", `Duplicate of row ${firstSeenAt}`);
      continue;
    }
    seenTransactionIds.set(balanceTransactionId, rowNumber);

    if (category === "") {
      blocking.push({
        code: "missing_reporting_category",
        field: col.reportingCategory,
        message: `Row ${rowNumber}: missing reporting_category.`,
      });
      errorRow("missing_reporting_category", "Missing reporting_category");
      continue;
    }
    if (!isKnownCategory(category)) {
      blocking.push({
        code: "unknown_reporting_category",
        field: col.reportingCategory,
        message: `Row ${rowNumber}: unrecognized reporting_category "${category}". Stripe does not publish a closed list of these values and reserves the right to emit new ones, so this tool refuses to guess how to treat it. Please report this category so it can be added deliberately.`,
      });
      errorRow("unknown_reporting_category", `Unrecognized reporting_category "${category}"`);
      continue;
    }

    // ── Money ───────────────────────────────────────────────────────────────
    const grossResult = parseStrictMoney(row[col.gross], fileCurrency, "gross");
    const feeResult = parseStrictMoney(row[col.fee], fileCurrency, "fee");
    const netResult = parseStrictMoney(row[col.net], fileCurrency, "net");

    let moneyFailed = false;
    for (const [label, result] of [
      ["gross", grossResult],
      ["fee", feeResult],
      ["net", netResult],
    ] as const) {
      if (!result.ok) {
        moneyFailed = true;
        blocking.push({
          code: result.error.code,
          field: result.error.field,
          message: `Row ${rowNumber} (${label}): ${result.error.message}`,
        });
      }
    }
    if (moneyFailed || !grossResult.ok || !feeResult.ok || !netResult.ok) {
      errorRow("unparseable_amount", "One or more money fields could not be parsed.");
      continue;
    }

    // ── The identity, enforced on EVERY row ─────────────────────────────────
    // A payout-level aggregate check is not sufficient: two rows with equal
    // and opposite errors cancel out and leave a clean-looking total.
    if (grossResult.cents - feeResult.cents !== netResult.cents) {
      blocking.push(identityError(rowNumber, grossResult.cents, feeResult.cents, netResult.cents, fileCurrency));
      errorRow("row_identity_violation", "net != gross - fee");
      continue;
    }

    // ── Scope filtering (non-blocking, always recorded) ──────────────────────
    if (automaticPayoutId === "") {
      rowAudit.push({
        rowNumber,
        status: "excluded",
        reasonCode: "no_automatic_payout_id",
        reasonMessage:
          "Not associated with an automatic payout — not yet paid out, or this account uses manual/instant payouts, which Stripe states cannot be reconciled this way.",
        balanceTransactionId,
        reportingCategory: category,
      });
      continue;
    }

    if (isPayoutEvent(category)) {
      rowAudit.push({
        rowNumber,
        status: "excluded",
        reasonCode: "payout_event_row",
        reasonMessage: `reporting_category "${category}" is the payout event itself, not activity inside it.`,
        balanceTransactionId,
        automaticPayoutId,
        reportingCategory: category,
      });
      continue;
    }

    // ── Date ────────────────────────────────────────────────────────────────
    const parsedDate = parseCalendarDate(row[col.effectiveAt]);
    if (!parsedDate.ok) {
      blocking.push({
        code: "invalid_effective_date",
        field: col.effectiveAt,
        message: `Row ${rowNumber}: payout effective date is invalid — ${parsedDate.reason}.`,
      });
      errorRow("invalid_effective_date", parsedDate.reason ?? "Invalid date");
      continue;
    }

    included.push({
      payoutId: automaticPayoutId,
      effectiveDate: parsedDate.date!,
      grossCents: grossResult.cents,
      feeCents: feeResult.cents,
      netCents: netResult.cents,
      category,
    });
    rowAudit.push({ rowNumber, status: "included", balanceTransactionId, automaticPayoutId, reportingCategory: category });
  }

  if (blocking.length > 0) {
    return {
      ok: false,
      report: null,
      blockingErrors: blocking.slice(0, MAX_REPORTED_ERRORS),
      errorsTruncated: blocking.length > MAX_REPORTED_ERRORS,
    };
  }

  if (included.length === 0) {
    return fail([
      {
        code: "no_payout_rows",
        field: "file",
        message:
          "No rows in this file belong to a completed automatic payout, so there is nothing to reconcile. This usually means the export covers a period with no payouts, or the account uses manual/instant payouts.",
      },
    ]);
  }

  // ── Group by payout ───────────────────────────────────────────────────────
  const byPayout = new Map<string, IncludedRow[]>();
  for (const row of included) {
    const list = byPayout.get(row.payoutId) ?? [];
    list.push(row);
    byPayout.set(row.payoutId, list);
  }

  const payouts: PayoutReconciliationLine[] = [];
  for (const [payoutId, payoutRows] of byPayout) {
    // Every row of one payout must agree on its effective date. Disagreement
    // means the grouping key is not what we think it is.
    const dates = new Set(payoutRows.map((r) => r.effectiveDate));
    if (dates.size > 1) {
      return fail([
        {
          code: "inconsistent_payout_date",
          field: col.effectiveAt,
          message: `Payout ${payoutId} has rows with different effective dates (${[...dates].sort().join(", ")}). A single payout settles on one date, so this file cannot be interpreted reliably.`,
        },
      ]);
    }

    const byCategory = new Map<string, IncludedRow[]>();
    for (const row of payoutRows) {
      const list = byCategory.get(row.category) ?? [];
      list.push(row);
      byCategory.set(row.category, list);
    }

    const categories: CategoryTotal[] = [...byCategory.entries()]
      .map(([category, catRows]) => {
        const s = specFor(category)!;
        return {
          category,
          rowCount: catRows.length,
          grossCents: catRows.reduce((a, r) => a + r.grossCents, 0),
          feeColumnCents: catRows.reduce((a, r) => a + r.feeCents, 0),
          netCents: catRows.reduce((a, r) => a + r.netCents, 0),
          classification: s.classification,
          direction: s.direction,
          directionConfidence: s.directionConfidence,
          ...(s.note ? { note: s.note } : {}),
        };
      })
      .sort((a, b) => a.category.localeCompare(b.category));

    const grossTotalCents = payoutRows.reduce((a, r) => a + r.grossCents, 0);
    const feeColumnTotalCents = payoutRows.reduce((a, r) => a + r.feeCents, 0);
    const feeInGrossTotalCents = payoutRows
      .filter((r) => isFeeInGross(r.category))
      .reduce((a, r) => a + r.grossCents, 0);
    const sourceNetCents = payoutRows.reduce((a, r) => a + r.netCents, 0);
    const calculatedNetCents = grossTotalCents - feeColumnTotalCents;

    const warnings: string[] = [];
    const unclassified = categories.filter((c) => isUnclassified(c.category));
    if (unclassified.length > 0) {
      warnings.push(
        `${unclassified.length} categor${unclassified.length === 1 ? "y is" : "ies are"} recognized but have no documented accounting treatment (${unclassified.map((c) => c.category).join(", ")}). They are shown above with their own totals and are deliberately not folded into revenue or fees.`
      );
    }
    const lowConfidence = categories.filter((c) => c.directionConfidence !== "confirmed");
    if (lowConfidence.length > 0) {
      warnings.push(
        `Stripe does not explicitly document the balance direction for: ${lowConfidence.map((c) => c.category).join(", ")}. Verify the sign of these amounts against your Stripe Dashboard.`
      );
    }

    payouts.push({
      payoutId,
      effectiveDate: payoutRows[0]!.effectiveDate,
      currency: fileCurrency,
      rowCount: payoutRows.length,
      categories,
      grossTotalCents,
      feeColumnTotalCents,
      feeInGrossTotalCents,
      // Stripe's formula: fee column total + the gross of fee-in-gross rows.
      // Expressed as a positive magnitude; fee-in-gross rows are negative.
      totalFeesPerStripeFormulaCents: feeColumnTotalCents - feeInGrossTotalCents,
      sourceNetCents,
      calculatedNetCents,
      varianceCents: calculatedNetCents - sourceNetCents,
      warnings,
    });
  }

  payouts.sort((a, b) => a.effectiveDate.localeCompare(b.effectiveDate) || a.payoutId.localeCompare(b.payoutId));

  // ── File-level warnings and completeness disclosure ────────────────────────
  const fileWarnings: string[] = [];
  const excludedCount = rowAudit.filter((r) => r.status === "excluded").length;
  if (excludedCount > 0) {
    fileWarnings.push(`${excludedCount} row(s) were excluded from totals — see the row audit for the reason for each.`);
  }
  if (!hasEffectiveAtUtc && hasEffectiveAt) {
    fileWarnings.push(
      "This export uses automatic_payout_effective_at, which Stripe renders in the timezone the report run requested. Dates near midnight may fall on a different calendar day than the UTC-based automatic_payout_effective_at_utc column would give."
    );
  }

  const distinctCategories = new Set(included.map((r) => r.category));
  if (distinctCategories.size === 1) {
    fileWarnings.push(
      `Every row in this file has the same reporting_category ("${[...distinctCategories][0]}"). That is possible for a small account, but it is also exactly what a category-filtered export looks like — see the completeness note below.`
    );
  }

  const completenessDisclosure = [
    "Payout completeness CANNOT be verified from this file. The itemized report has no payout-total column, no row count, and no checksum, so there is nothing in it to check the totals against.",
    "The Stripe Reports API accepts currency and reporting_category filters, and the resulting CSV does not record which filters were applied. A partial export is structurally identical to a complete one.",
    "To verify completeness, run payout_reconciliation.by_id.summary.1 for a specific payout and compare its count, gross, fee, and net per reporting_category against the per-category table above. (payout_reconciliation.summary.2 will NOT work for this — despite the name it carries no payout ID.)",
    "Whether Stripe includes the payout's own balance transaction as a row in this report is undocumented. Rows with reporting_category payout or payout_reversal are excluded from activity totals here; confirm that matches your export.",
  ];

  const report: ReconciliationReport = {
    parserVersion: PARSER_VERSION,
    sourceFileSha256,
    currency: fileCurrency,
    currencyMinorDigits: minorDigits,
    generatedAt: new Date().toISOString(),
    totalRowsInFile: rows.length,
    includedRowCount: included.length,
    excludedRowCount: excludedCount,
    payouts,
    rowAudit,
    fileWarnings,
    completenessDisclosure,
  };

  return { ok: true, report, blockingErrors: [], errorsTruncated: false };
}

/** Exposed for tests and documentation tooling. */
export { CATEGORY_SPECS };
