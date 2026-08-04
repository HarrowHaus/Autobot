import { describe, expect, it } from "vitest";
import { buildQboJournalCsv, validateAccountMappings, type AccountMappings } from "../../src/lib/qbo-journal-builder.js";
import { validateStripePayoutItemized } from "../../src/validators/stripe-payout-itemized.js";
import { buildStripeItemizedCsv, chargeRow, refundRow, standaloneFeeRow } from "../support/stripe-fixture.js";

const VALID_MAPPINGS: AccountMappings = {
  stripeClearing: "Stripe Clearing",
  revenue: "Sales Income",
  refundsAndReturns: "Refunds and Returns",
  processingFees: "Merchant Processing Fees",
  disputesAndChargebacks: "Disputes and Chargebacks",
};

async function reportFor(rows: Parameters<typeof buildStripeItemizedCsv>[0]) {
  const result = await validateStripePayoutItemized(buildStripeItemizedCsv(rows));
  if (!result.ok) throw new Error(`fixture failed validation: ${result.blockingErrors[0]?.message}`);
  return result.report!;
}

function sumDebitsAndCredits(csv: string): { debits: number; credits: number } {
  const [, ...lines] = csv.trim().split("\r\n");
  let debits = 0;
  let credits = 0;
  for (const line of lines) {
    const cells = line.split(",");
    debits += Number(cells[3] || 0);
    credits += Number(cells[4] || 0);
  }
  return { debits, credits };
}

describe("validateAccountMappings", () => {
  it("rejects missing mappings", () => {
    expect(validateAccountMappings(null)).toMatchObject({ code: "missing_account_mappings" });
    expect(validateAccountMappings(undefined)).toMatchObject({ code: "missing_account_mappings" });
  });

  it("rejects a partial or blank mapping set", () => {
    const { stripeClearing: _omitted, ...rest } = VALID_MAPPINGS;
    expect(validateAccountMappings(rest)).toMatchObject({ code: "missing_account_mapping" });
    expect(validateAccountMappings({ ...VALID_MAPPINGS, revenue: "  " })).toMatchObject({ code: "missing_account_mapping" });
  });

  it("accepts a complete mapping set", () => {
    expect(validateAccountMappings(VALID_MAPPINGS)).toBeNull();
  });
});

describe("refuses to produce a misleading journal", () => {
  it("refuses when any category has no documented accounting treatment", async () => {
    const report = await reportFor([
      chargeRow({ balance_transaction_id: "t1" }),
      chargeRow({ balance_transaction_id: "t2", reporting_category: "transfer", gross: "-5.00", fee: "0.00", net: "-5.00" }),
    ]);
    const built = buildQboJournalCsv(report, VALID_MAPPINGS);
    expect(built).toMatchObject({ ok: false, error: { code: "unclassified_category" } });
    if (!built.ok) expect(built.error.message).toContain("transfer");
  });

  it.each(["contribution", "financing_paydown"])(
    "refuses on %s — it is in Stripe's fee formula but is NOT economically a fee",
    async (category) => {
      // Stripe groups these with fees for revenue-recognition purposes, but a
      // Climate donation and a loan repayment must not be booked to a fee
      // account without a human deciding that.
      const report = await reportFor([
        chargeRow({ balance_transaction_id: "t1" }),
        chargeRow({ balance_transaction_id: "t2", reporting_category: category, gross: "-10.00", fee: "0.00", net: "-10.00" }),
      ]);
      const built = buildQboJournalCsv(report, VALID_MAPPINGS);
      expect(built).toMatchObject({ ok: false, error: { code: "unclassified_category" } });
    }
  );

  it("refuses when there are no payouts", async () => {
    const report = await reportFor([chargeRow()]);
    report.payouts = [];
    expect(buildQboJournalCsv(report, VALID_MAPPINGS)).toMatchObject({ ok: false, error: { code: "no_payouts" } });
  });

  it("refuses when a payout does not reconcile", async () => {
    const report = await reportFor([chargeRow()]);
    report.payouts[0]!.varianceCents = 1;
    expect(buildQboJournalCsv(report, VALID_MAPPINGS)).toMatchObject({ ok: false, error: { code: "unreconciled_payout" } });
  });

  it("refuses when account mappings are incomplete, before reading the report", async () => {
    const report = await reportFor([chargeRow()]);
    expect(buildQboJournalCsv(report, { ...VALID_MAPPINGS, revenue: "" })).toMatchObject({
      ok: false,
      error: { code: "missing_account_mapping" },
    });
  });
});

describe("balanced output", () => {
  it("balances for a simple charge-only payout", async () => {
    const report = await reportFor([chargeRow()]);
    const built = buildQboJournalCsv(report, VALID_MAPPINGS);
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    const { debits, credits } = sumDebitsAndCredits(built.csv);
    expect(debits).toBeCloseTo(credits, 2);
    expect(debits).toBeCloseTo(100.0, 2);
  });

  it("balances when a standalone fee row carries its amount in gross", async () => {
    // This is the case that silently broke before: the fee amount is in
    // gross, not the fee column, so a journal that totals only the fee
    // column would be out of balance by the fee.
    const report = await reportFor([
      chargeRow({ balance_transaction_id: "t1", gross: "100.00", fee: "3.20", net: "96.80" }),
      standaloneFeeRow({ balance_transaction_id: "t2", gross: "-25.00", fee: "0.00", net: "-25.00" }),
    ]);
    const built = buildQboJournalCsv(report, VALID_MAPPINGS);
    expect(built.ok).toBe(true);
    if (!built.ok) return;

    const { debits, credits } = sumDebitsAndCredits(built.csv);
    expect(debits).toBeCloseTo(credits, 2);
    // Fees debited = fee column (3.20) + standalone fee gross (25.00).
    expect(built.csv).toContain("Merchant Processing Fees,28.20,");
  });

  it("balances with charges, refunds, and fees together", async () => {
    const report = await reportFor([
      chargeRow({ balance_transaction_id: "t1", gross: "100.00", fee: "3.20", net: "96.80" }),
      refundRow({ balance_transaction_id: "t2", gross: "-20.00", fee: "0.00", net: "-20.00" }),
      standaloneFeeRow({ balance_transaction_id: "t3" }),
    ]);
    const built = buildQboJournalCsv(report, VALID_MAPPINGS);
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    const { debits, credits } = sumDebitsAndCredits(built.csv);
    expect(debits).toBeCloseTo(credits, 2);
  });

  it("derives a stable journal number from the payout ID, not a counter", async () => {
    const report = await reportFor([chargeRow()]);
    const first = buildQboJournalCsv(report, VALID_MAPPINGS);
    const second = buildQboJournalCsv(report, VALID_MAPPINGS);
    expect(first.ok && second.ok).toBe(true);
    if (!first.ok || !second.ok) return;
    const journalNo = first.csv.split("\r\n")[1]!.split(",")[0];
    expect(second.csv.split("\r\n")[1]!.split(",")[0]).toBe(journalNo);
    expect(journalNo).toBe("PS-po1");
  });

  it("uses the payout effective date as the journal date", async () => {
    const report = await reportFor([chargeRow()]);
    const built = buildQboJournalCsv(report, VALID_MAPPINGS);
    if (!built.ok) throw new Error("expected success");
    expect(built.csv.split("\r\n")[1]).toContain("2026-01-15");
  });

  it("neutralizes a formula-injection payload in an account name", async () => {
    const report = await reportFor([chargeRow()]);
    const built = buildQboJournalCsv(report, { ...VALID_MAPPINGS, revenue: "=cmd|'/C calc'!A0" });
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(built.csv).toContain("'=cmd");
    expect(built.csv).not.toMatch(/,=cmd/);
  });
});
