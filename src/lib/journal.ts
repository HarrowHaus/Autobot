import type { PayoutGroup } from "./group.js";

export interface JournalLine {
  account: string;
  debitCents: number;
  creditCents: number;
  memo: string;
}

/**
 * Turns a single grouped payout into the 3 journal lines that make the
 * bank deposit reconcile cleanly: the clearing account gets debited for
 * exactly the net amount that will match the bank feed, fees are booked
 * as an expense, and sales income is credited for the gross.
 *
 * Uses a "positive = debit" signed-amount convention throughout so the
 * journal balances exactly by construction: net + fee - gross = 0, always,
 * because netCents is derived as grossCents - feeCents upstream.
 */
export function buildPayoutJournalLines(group: PayoutGroup): JournalLine[] {
  const toLine = (account: string, signedCents: number, memo: string): JournalLine => ({
    account,
    debitCents: signedCents > 0 ? signedCents : 0,
    creditCents: signedCents < 0 ? -signedCents : 0,
    memo,
  });

  const memo = `Payout ${group.payoutId} (${group.transactions.length} transaction${group.transactions.length === 1 ? "" : "s"})`;

  return [
    toLine("Undeposited Funds", group.totalNetCents, memo),
    toLine("Merchant Processing Fees", group.totalFeeCents, memo),
    toLine("Sales Income", -group.totalGrossCents, memo),
  ];
}
