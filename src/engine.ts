import { parsePayPal } from "./parsers/paypal.js";
import { parseStripe } from "./parsers/stripe.js";
import { groupByPayout } from "./lib/group.js";
import { mapToQboJournal } from "./mappers/qbo-journal.js";
import { mapToQboBankMatch } from "./mappers/qbo-bankmatch.js";
import { mapToXeroJournal } from "./mappers/xero-journal.js";
import { mapToXeroBankMatch } from "./mappers/xero-bankmatch.js";
import type { AccountingTarget, ConversionResult, Processor } from "./types.js";

const PARSERS: Record<Processor, (csv: string) => ReturnType<typeof parseStripe>> = {
  stripe: parseStripe,
  paypal: parsePayPal,
  square: () => {
    throw new Error("Square is not supported yet");
  },
};

export function convert(csvText: string, processor: Processor, target: AccountingTarget): ConversionResult {
  const parser = PARSERS[processor];
  if (!parser) throw new Error(`Unknown processor: ${processor}`);

  const transactions = parser(csvText);
  const groups = groupByPayout(transactions);

  const journalContent = target === "qbo" ? mapToQboJournal(groups) : mapToXeroJournal(groups);
  const bankMatchContent = target === "qbo" ? mapToQboBankMatch(groups) : mapToXeroBankMatch(groups);

  const totalGrossCents = groups.reduce((s, g) => s + g.totalGrossCents, 0);
  const totalFeeCents = groups.reduce((s, g) => s + g.totalFeeCents, 0);
  const totalNetCents = groups.reduce((s, g) => s + g.totalNetCents, 0);

  return {
    journalFile: {
      filename: `${processor}-${target}-journal-entries.csv`,
      content: journalContent,
      mimeType: "text/csv",
    },
    bankMatchFile: {
      filename: `${processor}-${target}-bank-match.csv`,
      content: bankMatchContent,
      mimeType: "text/csv",
    },
    summary: {
      payoutCount: groups.length,
      transactionCount: transactions.length,
      totalGrossCents,
      totalFeeCents,
      totalNetCents,
    },
  };
}
