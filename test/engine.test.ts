import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { convert } from "../src/engine.js";
import { parseCsvRecords } from "../src/lib/csv.js";

const stripeFixture = readFileSync(new URL("./fixtures/stripe-sample.csv", import.meta.url), "utf-8");
const paypalFixture = readFileSync(new URL("./fixtures/paypal-sample.csv", import.meta.url), "utf-8");

describe("convert (Stripe -> QBO)", () => {
  const result = convert(stripeFixture, "stripe", "qbo");

  it("produces two payout groups", () => {
    expect(result.summary.payoutCount).toBe(2);
    expect(result.summary.transactionCount).toBe(4);
  });

  it("every journal entry balances (debits == credits) per JournalNo", () => {
    const rows = parseCsvRecords(result.journalFile.content);
    const byJournal = new Map<string, { debits: number; credits: number }>();
    for (const row of rows) {
      const key = row.JournalNo!;
      const entry = byJournal.get(key) ?? { debits: 0, credits: 0 };
      entry.debits += Number(row.Debits || 0);
      entry.credits += Number(row.Credits || 0);
      byJournal.set(key, entry);
    }
    expect(byJournal.size).toBe(2);
    for (const { debits, credits } of byJournal.values()) {
      expect(debits).toBeCloseTo(credits, 2);
    }
  });

  it("bank-match file has one row per payout with the net amount", () => {
    const rows = parseCsvRecords(result.bankMatchFile.content);
    expect(rows).toHaveLength(2);
    const po1Row = rows.find((r) => r.Description!.includes("po_1"))!;
    expect(Number(po1Row.Amount)).toBeCloseTo(125.63, 2);
  });
});

describe("convert (Stripe -> Xero)", () => {
  it("journal balances and bank-match totals match", () => {
    const result = convert(stripeFixture, "stripe", "xero");
    const journalRows = parseCsvRecords(result.journalFile.content).filter((r) => r.Date);
    const totalDebits = journalRows.reduce((s, r) => s + Number(r.Debit || 0), 0);
    const totalCredits = journalRows.reduce((s, r) => s + Number(r.Credit || 0), 0);
    expect(totalDebits).toBeCloseTo(totalCredits, 2);

    const bankRows = parseCsvRecords(result.bankMatchFile.content);
    expect(bankRows).toHaveLength(2);
  });
});

describe("convert (PayPal -> QBO)", () => {
  it("treats each PayPal transaction as its own payout", () => {
    const result = convert(paypalFixture, "paypal", "qbo");
    expect(result.summary.payoutCount).toBe(3);
    expect(result.summary.transactionCount).toBe(3);
  });
});
