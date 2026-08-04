import { toCsv } from "./csv.js";
import { centsToDecimalString } from "./money.js";
import type { ReconciliationReport } from "../validators/stripe-payout-itemized.js";
import { specFor } from "../validators/stripe-categories.js";

/**
 * Builds a QuickBooks Online journal-entry CSV from an already-reconciled
 * report.
 *
 * Gated behind ALLOW_QBO_EXPORT at the route level — this module assumes the
 * caller checked that flag. It has NEVER been imported into a real
 * QuickBooks company, so it must stay disabled until that happens.
 *
 * The governing rule: refuse rather than guess. Every category present must
 * map to an account the caller explicitly nominated. Anything Stripe does
 * not document a booking treatment for blocks the whole journal, because the
 * failure mode of guessing — silently classifying an unknown movement as
 * revenue — is exactly the kind of error nobody notices until an audit.
 */

export interface AccountMappings {
  stripeClearing: string;
  revenue: string;
  refundsAndReturns: string;
  processingFees: string;
  disputesAndChargebacks: string;
}

const REQUIRED_MAPPING_KEYS: (keyof AccountMappings)[] = [
  "stripeClearing",
  "revenue",
  "refundsAndReturns",
  "processingFees",
  "disputesAndChargebacks",
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
 * Journal number derived from the payout ID itself — never a PS1/PS2
 * sequential counter, which would collide or shift across separate runs of
 * the same payout and destroy the audit trail.
 */
function journalNumberFor(payoutId: string): string {
  return `PS-${payoutId.replace(/[^a-zA-Z0-9]/g, "")}`.slice(0, 21);
}

function signedLine(account: string, signedCents: number): { account: string; debit: number; credit: number } {
  return {
    account,
    debit: signedCents > 0 ? signedCents : 0,
    credit: signedCents < 0 ? -signedCents : 0,
  };
}

export function buildQboJournalCsv(report: ReconciliationReport, mappings: AccountMappings): JournalBuildResult {
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
          message: `Payout ${payout.payoutId} does not reconcile (variance ${payout.varianceCents}). Refusing to journal it.`,
        },
      };
    }
    if (!payout.effectiveDate) {
      return {
        ok: false,
        error: {
          code: "missing_effective_date",
          message: `Payout ${payout.payoutId} has no payout effective date; the journal date must be the payout date, not a transaction date.`,
        },
      };
    }

    // Every category must have a documented booking treatment AND an account.
    const unbookable = payout.categories.filter((c) => {
      const classification = specFor(c.category)?.classification;
      return classification === undefined || classification === "unclassified";
    });
    if (unbookable.length > 0) {
      return {
        ok: false,
        error: {
          code: "unclassified_category",
          message: `Payout ${payout.payoutId} contains categor${unbookable.length === 1 ? "y" : "ies"} with no documented accounting treatment: ${unbookable
            .map((c) => `${c.category} (${centsToDecimalString(c.grossCents, payout.currency)})`)
            .join(", ")}. Refusing to guess an account rather than misclassify it — most dangerously, as revenue.`,
        },
      };
    }

    // Accumulate by booking treatment. Fees come from BOTH the fee column and
    // the gross of fee-in-gross categories (Stripe's published formula) —
    // totalling only the fee column would understate them.
    let revenueGross = 0;
    let refundGross = 0;
    let disputeGross = 0;
    for (const c of payout.categories) {
      switch (specFor(c.category)!.classification) {
        case "revenue":
          revenueGross += c.grossCents;
          break;
        case "refund":
          refundGross += c.grossCents;
          break;
        case "dispute":
          disputeGross += c.grossCents;
          break;
        case "fee":
          break; // handled via totalFeesPerStripeFormulaCents below
        default:
          break;
      }
    }

    const feesDebit = payout.totalFeesPerStripeFormulaCents;

    const lines = [
      signedLine(mappings.stripeClearing, payout.calculatedNetCents),
      signedLine(mappings.revenue, -revenueGross),
      signedLine(mappings.refundsAndReturns, -refundGross),
      signedLine(mappings.disputesAndChargebacks, -disputeGross),
      signedLine(mappings.processingFees, feesDebit),
    ].filter((l) => l.debit !== 0 || l.credit !== 0);

    // Balance is a property of the arithmetic, not an aspiration. Assert it
    // rather than trusting it: an unbalanced journal that reaches QuickBooks
    // is worse than no journal at all.
    const totalDebits = lines.reduce((a, l) => a + l.debit, 0);
    const totalCredits = lines.reduce((a, l) => a + l.credit, 0);
    if (totalDebits !== totalCredits) {
      return {
        ok: false,
        error: {
          code: "unbalanced_journal",
          message: `Internal check failed: journal for payout ${payout.payoutId} does not balance (debits ${totalDebits}, credits ${totalCredits}). This is a bug in PayoutSplit — please report it. No journal was produced.`,
        },
      };
    }

    const journalNo = journalNumberFor(payout.payoutId);
    const description = `Stripe payout ${payout.payoutId}`;
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
