import { toCsv } from "../lib/csv.js";
import { centsToDecimalString } from "../lib/money.js";
import { buildPayoutJournalLines } from "../lib/journal.js";
import type { PayoutGroup } from "../lib/group.js";

/**
 * QuickBooks Online's native journal-entry importer
 * (Settings > Import Data > Journal Entries) expects: JournalNo, JournalDate,
 * AccountName, Debits, Credits, Description — all lines sharing a JournalNo
 * form one journal entry.
 */
export function mapToQboJournal(groups: PayoutGroup[]): string {
  const header = ["JournalNo", "JournalDate", "AccountName", "Debits", "Credits", "Description"];
  const rows: (string | number)[][] = [];

  groups.forEach((group, i) => {
    const journalNo = `PS${i + 1}`;
    for (const line of buildPayoutJournalLines(group)) {
      rows.push([
        journalNo,
        group.date,
        line.account,
        line.debitCents > 0 ? centsToDecimalString(line.debitCents) : "",
        line.creditCents > 0 ? centsToDecimalString(line.creditCents) : "",
        line.memo,
      ]);
    }
  });

  return toCsv(header, rows);
}
