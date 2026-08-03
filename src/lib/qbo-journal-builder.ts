import { toCsv } from "./csv.js";
import { centsToDecimalString } from "./money.js";
import type { ReconciliationReport } from "../validators/stripe-payout-itemized.js";

/**
 * Builds a QuickBooks Online journal-entry CSV from an already-reconciled
 * report. Gated behind ALLOW_QBO_EXPORT at the route level — this module
 * assumes the caller has already checked that flag; it does not check it
 * itself, since "does this feature run at all" and "is this specific
 * output safe to produce" are different questions.
 */

export interface AccountMappings {
  stripeClearing: string;
  revenue: string;
  refundsAndReturns: string;
  processingFees: string;
  disputesAndChargebacks: string;
  otherAdjustments: string;
}

const REQUIRED_MAPPING_KEYS: (keyof AccountMappings)[] = [
  "stripeClearing",
  "revenue",
  "refundsAndReturns",
  "processingFees",
  "disputesAndChargebacks",
  "otherAdjustments",
];

export interface JournalBuildError {
  code: string;
  message: string;
}

export type JournalBuildResult = { ok: true; csv: string } | { ok: false; error: JournalBuildError };

export function validateAccountMappings(mappings: Partial<AccountMappings> | null | undefined): JournalBuildError | null {
  if (!mappings) {
    return { code: "missing_account_mappings", message: "No account mappings were provided." };
  }
  for (const key of REQUIRED_MAPPING_KEYS) {
    const value = mappings[key];
    if (typeof value !== "string" || value.trim() === "") {
      return { code: "missing_account_mapping", message: `Missing required account mapping for "${key}".` };
    }
  }
  return null;
}

/**
 * Derives a stable journal number from the payout ID itself — never a
 * PS1/PS2-style sequential counter, which would silently collide or shift
 * across separate runs/uploads of the same payout.
 */
function journalNumberFor(payoutId: string): string {
  const cleaned = payoutId.replace(/[^a-zA-Z0-9]/g, "");
  return `PS-${cleaned}`.slice(0, 21); // QBO journal-number fields are conventionally capped around 21 chars
}

function signedLine(account: string, signedCents: number): { account: string; debit: number; credit: number } {
  return {
    account,
    debit: signedCents > 0 ? signedCents : 0,
    credit: signedCents < 0 ? -signedCents : 0,
  };
}

export function buildQboJournalCsv(
  report: ReconciliationReport,
  mappings: AccountMappings
): JournalBuildResult {
  const mappingError = validateAccountMappings(mappings);
  if (mappingError) return { ok: false, error: mappingError };

  if (report.payouts.length === 0) {
    return { ok: false, error: { code: "no_payouts", message: "Reconciliation report has no payouts to journal." } };
  }

  const header = ["JournalNo", "JournalDate", "AccountName", "Debits", "Credits", "Description"];
  const rows: (string | number)[][] = [];

  for (const payout of report.payouts) {
    if (payout.varianceCents !== 0) {
      return {
        ok: false,
        error: {
          code: "unreconciled_payout",
          message: `Payout ${payout.payoutId} does not reconcile (variance ${payout.varianceCents} cent(s)) — cannot generate a journal entry until this is resolved.`,
        },
      };
    }
    if (payout.otherTotalCents !== 0) {
      return {
        ok: false,
        error: {
          code: "unclassified_category",
          message: `Payout ${payout.payoutId} includes ${payout.otherTotalCents} cent(s) in reporting categories that aren't mapped to a QuickBooks account (charge/refund/dispute/adjustment only). Refusing to guess an account rather than misclassify it as revenue.`,
        },
      };
    }
    if (!payout.effectiveDate) {
      return {
        ok: false,
        error: {
          code: "missing_effective_date",
          message: `Payout ${payout.payoutId} has no parseable payout effective date; the journal date must be the payout effective date, not a transaction date.`,
        },
      };
    }

    const journalNo = journalNumberFor(payout.payoutId);
    const description = `Stripe payout ${payout.payoutId}`;
    const lines = [
      signedLine(mappings.stripeClearing, payout.calculatedNetCents),
      signedLine(mappings.revenue, -payout.chargeTotalCents),
      signedLine(mappings.refundsAndReturns, -payout.refundTotalCents),
      signedLine(mappings.processingFees, payout.feeTotalCents),
      signedLine(mappings.disputesAndChargebacks, -payout.disputeTotalCents),
      signedLine(mappings.otherAdjustments, -payout.adjustmentTotalCents),
    ].filter((l) => l.debit !== 0 || l.credit !== 0);

    for (const line of lines) {
      rows.push([
        journalNo,
        payout.effectiveDate,
        line.account,
        line.debit > 0 ? centsToDecimalString(line.debit, payout.currency) : "",
        line.credit > 0 ? centsToDecimalString(line.credit, payout.currency) : "",
        description,
      ]);
    }
  }

  return { ok: true, csv: toCsv(header, rows) };
}
