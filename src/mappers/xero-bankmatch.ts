import { toCsv } from "../lib/csv.js";
import { centsToDecimalString } from "../lib/money.js";
import type { PayoutGroup } from "../lib/group.js";

/**
 * Xero's bank statement CSV import (Date, Amount, Payee, Description/Reference).
 * One row per payout, amount = net deposit, for a clean single-row bank match.
 */
export function mapToXeroBankMatch(groups: PayoutGroup[]): string {
  const header = ["Date", "Amount", "Payee", "Reference"];
  const rows = groups.map((group) => [
    group.date,
    centsToDecimalString(group.totalNetCents),
    "Payment Processor",
    `Payout ${group.payoutId}`,
  ]);
  return toCsv(header, rows);
}
