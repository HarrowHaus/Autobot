import { toCsv } from "../lib/csv.js";
import { centsToDecimalString } from "../lib/money.js";
import { buildPayoutJournalLines } from "../lib/journal.js";
import type { PayoutGroup } from "../lib/group.js";

/**
 * Xero's manual-journal CSV import template: Date, Narration, Account,
 * Debit, Credit — multiple lines sharing a Date+Narration form one journal,
 * separated by a blank row between journals.
 *
 * Note: Xero's importer maps the "Account" text against your existing
 * chart of accounts by name during the import wizard, since we have no way
 * to know a given user's account codes ahead of time.
 */
export function mapToXeroJournal(groups: PayoutGroup[]): string {
  const header = ["Date", "Narration", "Account", "Debit", "Credit"];
  const rows: (string | number)[][] = [];

  groups.forEach((group, i) => {
    if (i > 0) rows.push(["", "", "", "", ""]); // blank row delimits journals
    const narration = `Payout ${group.payoutId}`;
    for (const line of buildPayoutJournalLines(group)) {
      rows.push([
        group.date,
        narration,
        line.account,
        line.debitCents > 0 ? centsToDecimalString(line.debitCents) : "",
        line.creditCents > 0 ? centsToDecimalString(line.creditCents) : "",
      ]);
    }
  });

  return toCsv(header, rows);
}
