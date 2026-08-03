import { toCsv } from "../lib/csv.js";
import { centsToDecimalString } from "../lib/money.js";
import type { PayoutGroup } from "../lib/group.js";

/**
 * QuickBooks Online's generic bank-transaction CSV import (3 columns:
 * Date, Description, Amount). One row per payout, amount = net deposit,
 * so it matches the bank feed as a single clean line instead of the
 * "bundled payout won't match" failure mode.
 */
export function mapToQboBankMatch(groups: PayoutGroup[]): string {
  const header = ["Date", "Description", "Amount"];
  const rows = groups.map((group) => [
    group.date,
    `Payout ${group.payoutId}`,
    centsToDecimalString(group.totalNetCents),
  ]);
  return toCsv(header, rows);
}
