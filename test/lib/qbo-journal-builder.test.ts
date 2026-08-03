import { describe, expect, it } from "vitest";
import { buildQboJournalCsv, validateAccountMappings, type AccountMappings } from "../../src/lib/qbo-journal-builder.js";
import { validateStripePayoutItemized } from "../../src/validators/stripe-payout-itemized.js";
import { buildStripeItemizedCsv, chargeRow } from "../support/stripe-fixture.js";

const VALID_MAPPINGS: AccountMappings = {
  stripeClearing: "Stripe Clearing",
  revenue: "Sales Income",
  refundsAndReturns: "Refunds and Returns",
  processingFees: "Merchant Processing Fees",
  disputesAndChargebacks: "Disputes and Chargebacks",
  otherAdjustments: "Other Adjustments",
};

async function reconcilingReport() {
  const csv = buildStripeItemizedCsv([chargeRow({ gross: "100.00", fee: "3.20", net: "96.80" })]);
  const result = await validateStripePayoutItemized(csv);
  if (!result.ok) throw new Error("fixture should reconcile");
  return result.report!;
}

describe("validateAccountMappings", () => {
  it("rejects missing mappings entirely", () => {
    expect(validateAccountMappings(null)).toMatchObject({ code: "missing_account_mappings" });
    expect(validateAccountMappings(undefined)).toMatchObject({ code: "missing_account_mappings" });
  });

  it("rejects a partial mapping set", () => {
    const { stripeClearing, ...rest } = VALID_MAPPINGS;
    void stripeClearing;
    expect(validateAccountMappings(rest)).toMatchObject({ code: "missing_account_mapping" });
  });

  it("rejects blank-string mappings", () => {
    expect(validateAccountMappings({ ...VALID_MAPPINGS, revenue: "  " })).toMatchObject({ code: "missing_account_mapping" });
  });

  it("accepts a complete mapping set", () => {
    expect(validateAccountMappings(VALID_MAPPINGS)).toBeNull();
  });
});

describe("buildQboJournalCsv — refuses to produce a misleading journal", () => {
  it("refuses when a payout has a nonzero variance", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ gross: "100.00", fee: "3.20", net: "90.00" })]);
    const result = await validateStripePayoutItemized(csv);
    const built = buildQboJournalCsv(result.report!, VALID_MAPPINGS);
    expect(built).toMatchObject({ ok: false, error: { code: "unreconciled_payout" } });
  });

  it('refuses when a payout has an unclassified ("other") category, rather than counting it as revenue', async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1", gross: "100.00", fee: "3.20", net: "96.80" }),
      chargeRow({ balance_transaction_id: "t2", reporting_category: "transfer", gross: "5.00", fee: "0", net: "5.00" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    const built = buildQboJournalCsv(result.report!, VALID_MAPPINGS);
    expect(built).toMatchObject({ ok: false, error: { code: "unclassified_category" } });
  });

  it("refuses when a payout has no parseable effective date", async () => {
    const report = await reconcilingReport();
    report.payouts[0]!.effectiveDate = null;
    const built = buildQboJournalCsv(report, VALID_MAPPINGS);
    expect(built).toMatchObject({ ok: false, error: { code: "missing_effective_date" } });
  });

  it("refuses when there are no payouts at all", async () => {
    const report = await reconcilingReport();
    report.payouts = [];
    const built = buildQboJournalCsv(report, VALID_MAPPINGS);
    expect(built).toMatchObject({ ok: false, error: { code: "no_payouts" } });
  });

  it("refuses when account mappings are incomplete, before touching the report", async () => {
    const report = await reconcilingReport();
    const built = buildQboJournalCsv(report, { ...VALID_MAPPINGS, revenue: "" });
    expect(built).toMatchObject({ ok: false, error: { code: "missing_account_mapping" } });
  });
});

describe("buildQboJournalCsv — balanced output", () => {
  it("produces a journal whose debits equal credits for a reconciling payout", async () => {
    const report = await reconcilingReport();
    const built = buildQboJournalCsv(report, VALID_MAPPINGS);
    expect(built.ok).toBe(true);
    if (!built.ok) return;

    const lines = built.csv.trim().split("\r\n");
    const [, ...dataLines] = lines;
    let totalDebits = 0;
    let totalCredits = 0;
    for (const line of dataLines) {
      const cells = line.split(",");
      const debit = Number(cells[3] || 0);
      const credit = Number(cells[4] || 0);
      totalDebits += debit;
      totalCredits += credit;
    }
    expect(totalDebits).toBeCloseTo(totalCredits, 2);
  });

  it("derives a stable journal number from the payout ID, not a sequential counter", async () => {
    const report = await reconcilingReport();
    const first = buildQboJournalCsv(report, VALID_MAPPINGS);
    const second = buildQboJournalCsv(report, VALID_MAPPINGS);
    expect(first.ok && second.ok).toBe(true);
    if (!first.ok || !second.ok) return;
    // Same payout, two independent builds -> identical journal number.
    expect(first.csv.split("\n")[1]!.split(",")[0]).toBe(second.csv.split("\n")[1]!.split(",")[0]);
    expect(first.csv.split("\n")[1]!.split(",")[0]).toContain("po_1".replace(/[^a-zA-Z0-9]/g, ""));
  });

  it("neutralizes a formula-injection payload in an account mapping name in the output CSV", async () => {
    const report = await reconcilingReport();
    const built = buildQboJournalCsv(report, { ...VALID_MAPPINGS, revenue: "=cmd|'/C calc'!A0" });
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(built.csv).not.toContain('"=cmd');
    expect(built.csv).toContain("'=cmd");
  });
});
