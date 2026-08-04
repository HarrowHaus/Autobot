import { describe, expect, it } from "vitest";
import {
  validateStripePayoutItemized,
  MAX_ROWS,
  MAX_REPORTED_ERRORS,
  PARSER_VERSION,
} from "../../src/validators/stripe-payout-itemized.js";
import { buildStripeItemizedCsv, chargeRow, refundRow, standaloneFeeRow } from "../support/stripe-fixture.js";

function categoryOf(payout: { categories: { category: string }[] }, name: string) {
  return payout.categories.find((c) => c.category === name);
}

describe("happy path", () => {
  it("accepts a minimal file and computes totals", async () => {
    const csv = buildStripeItemizedCsv([chargeRow()]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    const payout = result.report!.payouts[0]!;
    expect(result.report!.parserVersion).toBe(PARSER_VERSION);
    expect(payout.payoutId).toBe("po_1");
    expect(payout.effectiveDate).toBe("2026-01-15");
    expect(payout.grossTotalCents).toBe(10000);
    expect(payout.feeColumnTotalCents).toBe(320);
    expect(payout.sourceNetCents).toBe(9680);
    expect(payout.calculatedNetCents).toBe(9680);
    expect(payout.varianceCents).toBe(0);
  });

  it("reports the currency minor-unit exponent so clients don't assume 2", async () => {
    const usd = await validateStripePayoutItemized(buildStripeItemizedCsv([chargeRow()]));
    expect(usd.report!.currencyMinorDigits).toBe(2);

    const jpy = await validateStripePayoutItemized(
      buildStripeItemizedCsv([chargeRow({ currency: "jpy", gross: "1000", fee: "32", net: "968" })])
    );
    expect(jpy.ok).toBe(true);
    expect(jpy.report!.currencyMinorDigits).toBe(0);
    expect(jpy.report!.payouts[0]!.grossTotalCents).toBe(1000);
  });

  it("is idempotent across repeated runs of the same input", async () => {
    const csv = buildStripeItemizedCsv([chargeRow()]);
    const a = await validateStripePayoutItemized(csv);
    const b = await validateStripePayoutItemized(csv);
    expect(a.report!.sourceFileSha256).toBe(b.report!.sourceFileSha256);
    expect(a.report!.payouts).toEqual(b.report!.payouts);
  });
});

describe("per-row identity: net = gross - fee", () => {
  it("rejects a row that violates the identity", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ gross: "100.00", fee: "3.20", net: "90.00" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("row_identity_violation");
  });

  it("names the opposite sign convention explicitly when the data fits gross + fee", async () => {
    // If Stripe really reports fees as signed negatives, this is the message
    // that tells us — rather than the tool silently producing wrong totals.
    const csv = buildStripeItemizedCsv([chargeRow({ gross: "100.00", fee: "-3.20", net: "96.80" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("row_identity_violation");
    expect(result.blockingErrors[0]!.message).toContain("net = gross + fee");
    expect(result.blockingErrors[0]!.message).toContain("signed negatives");
  });

  it("catches two rows whose errors cancel out at the payout level", async () => {
    // The whole reason per-row enforcement exists: these two rows sum to a
    // perfectly clean payout total while both being individually wrong.
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1", gross: "100.00", fee: "3.00", net: "92.00" }), // -5.00 off
      chargeRow({ balance_transaction_id: "t2", gross: "100.00", fee: "3.00", net: "102.00" }), // +5.00 off
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors.filter((e) => e.code === "row_identity_violation")).toHaveLength(2);
  });

  it("accepts a negative-gross refund that satisfies the identity", async () => {
    const csv = buildStripeItemizedCsv([refundRow({ gross: "-20.00", fee: "0.50", net: "-20.50" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
  });
});

describe("fee totalling — standalone fee rows carry the amount in gross", () => {
  it("includes reporting_category=fee rows in the Stripe fee formula", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1", gross: "100.00", fee: "3.20", net: "96.80" }),
      standaloneFeeRow({ balance_transaction_id: "t2", gross: "-25.00", fee: "0.00", net: "-25.00" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    const payout = result.report!.payouts[0]!;

    expect(payout.feeColumnTotalCents).toBe(320); // fee column alone
    expect(payout.feeInGrossTotalCents).toBe(-2500); // gross of fee-type rows
    // Stripe's formula: fee column + gross of fee/network_cost/contribution/financing_paydown
    expect(payout.totalFeesPerStripeFormulaCents).toBe(320 + 2500);
  });

  it.each(["fee", "network_cost", "contribution", "financing_paydown"])(
    "treats %s as carrying its amount in gross, per Stripe's published formula",
    async (category) => {
      const csv = buildStripeItemizedCsv([
        chargeRow({ balance_transaction_id: "t1" }),
        chargeRow({ balance_transaction_id: "t2", reporting_category: category, gross: "-10.00", fee: "0.00", net: "-10.00" }),
      ]);
      const result = await validateStripePayoutItemized(csv);
      expect(result.ok).toBe(true);
      expect(result.report!.payouts[0]!.feeInGrossTotalCents).toBe(-1000);
      expect(result.report!.payouts[0]!.totalFeesPerStripeFormulaCents).toBe(320 + 1000);
    }
  );

  it("does not treat an ordinary category as fee-in-gross", async () => {
    const csv = buildStripeItemizedCsv([chargeRow(), refundRow({ balance_transaction_id: "t2" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.report!.payouts[0]!.feeInGrossTotalCents).toBe(0);
  });
});

describe("every category is exposed by name — nothing is hidden in an 'other' bucket", () => {
  it("emits a per-category breakdown with count, gross, fee, and net", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1" }),
      chargeRow({ balance_transaction_id: "t2" }),
      refundRow({ balance_transaction_id: "t3" }),
      standaloneFeeRow({ balance_transaction_id: "t4" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    const payout = result.report!.payouts[0]!;

    expect(payout.categories.map((c) => c.category).sort()).toEqual(["charge", "fee", "refund"]);
    expect(categoryOf(payout, "charge")).toMatchObject({ rowCount: 2, grossCents: 20000, feeColumnCents: 640, netCents: 19360 });
    expect(categoryOf(payout, "refund")).toMatchObject({ rowCount: 1, grossCents: -2000 });
    expect(categoryOf(payout, "fee")).toMatchObject({ rowCount: 1, grossCents: -2500 });
  });

  it("surfaces a recognized-but-unclassified category by name rather than absorbing it", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1" }),
      chargeRow({ balance_transaction_id: "t2", reporting_category: "transfer", gross: "-5.00", fee: "0.00", net: "-5.00" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    const payout = result.report!.payouts[0]!;
    expect(categoryOf(payout, "transfer")).toMatchObject({ classification: "unclassified", grossCents: -500 });
    expect(payout.warnings.some((w) => w.includes("no documented accounting treatment"))).toBe(true);
    expect(payout.warnings.some((w) => w.includes("transfer"))).toBe(true);
  });

  it("carries Stripe's documented direction and our confidence in it", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1" }),
      chargeRow({ balance_transaction_id: "t2", reporting_category: "other_adjustment", gross: "-1.00", fee: "0.00", net: "-1.00" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    const payout = result.report!.payouts[0]!;
    expect(categoryOf(payout, "charge")).toMatchObject({ direction: "increase", directionConfidence: "confirmed" });
    // Stripe explicitly describes other_adjustment as a bidirectional catch-all.
    expect(categoryOf(payout, "other_adjustment")).toMatchObject({ direction: "unknown", directionConfidence: "unknown" });
    expect(payout.warnings.some((w) => w.includes("does not explicitly document the balance direction"))).toBe(true);
  });
});

describe("category recognition", () => {
  it("rejects an unrecognized category rather than guessing its treatment", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ reporting_category: "some_category_stripe_just_added" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("unknown_reporting_category");
  });

  it("rejects `adjustment`, which is NOT a real Stripe category (the real one is other_adjustment)", async () => {
    const bad = await validateStripePayoutItemized(buildStripeItemizedCsv([chargeRow({ reporting_category: "adjustment" })]));
    expect(bad.ok).toBe(false);
    expect(bad.blockingErrors[0]!.code).toBe("unknown_reporting_category");

    const good = await validateStripePayoutItemized(
      buildStripeItemizedCsv([chargeRow({ reporting_category: "other_adjustment" })])
    );
    expect(good.ok).toBe(true);
  });

  it.each([
    "revenue_share",
    "refund_failure",
    "dispute_reversal",
    "network_cost",
    "contribution",
    "financing_paydown",
    "platform_fee_transfer",
    "issuing_dispute_provisional_credit_reversal",
    "unreconciled_customer_funds",
  ])("recognizes the current-2026 category %s", async (category) => {
    const csv = buildStripeItemizedCsv([chargeRow({ reporting_category: category })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
  });
});

describe("completeness", () => {
  it("always states that completeness cannot be verified", async () => {
    const csv = buildStripeItemizedCsv([chargeRow()]);
    const result = await validateStripePayoutItemized(csv);
    const disclosure = result.report!.completenessDisclosure.join(" ");
    expect(disclosure).toContain("CANNOT be verified");
    expect(disclosure).toContain("payout_reconciliation.by_id.summary.1");
    // The summary.2 trap: it has no payout ID despite the name.
    expect(disclosure).toContain("summary.2");
  });

  it("rejects duplicate balance_transaction_id values", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "txn_dup" }),
      chargeRow({ balance_transaction_id: "txn_dup" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("duplicate_balance_transaction_id");
    expect(result.blockingErrors[0]!.message).toContain("row 1");
  });

  it("rejects a file with zero included payouts", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ automatic_payout_id: "" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("no_payout_rows");
  });

  it("flags a single-category file as indistinguishable from a filtered export", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1" }),
      chargeRow({ balance_transaction_id: "t2" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.report!.fileWarnings.some((w) => w.includes("category-filtered export"))).toBe(true);
  });

  it("rejects a payout whose rows disagree on the effective date", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1", automatic_payout_effective_at_utc: "2026-01-15" }),
      chargeRow({ balance_transaction_id: "t2", automatic_payout_effective_at_utc: "2026-01-16" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("inconsistent_payout_date");
  });

  it("rejects an impossible calendar date", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ automatic_payout_effective_at_utc: "2026-02-30" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("invalid_effective_date");
  });
});

describe("file-level rejections", () => {
  it("rejects an empty file", async () => {
    expect((await validateStripePayoutItemized("")).ok).toBe(false);
  });

  it("rejects a file missing required columns, naming the v6 default-export trap", async () => {
    const csv = buildStripeItemizedCsv([chargeRow()]).replace("automatic_payout_id", "unrelated_column");
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("missing_columns");
    expect(result.blockingErrors[0]!.message).toContain("version 6");
  });

  it("rejects mixed currencies", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1", currency: "usd" }),
      chargeRow({ balance_transaction_id: "t2", currency: "eur" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("mixed_currency");
  });

  it("rejects an unsupported currency", async () => {
    const result = await validateStripePayoutItemized(buildStripeItemizedCsv([chargeRow({ currency: "xyz" })]));
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("unsupported_currency");
  });

  it("rejects a file over the row limit", async () => {
    const rows = Array.from({ length: MAX_ROWS + 1 }, (_, i) =>
      chargeRow({ balance_transaction_id: `t${i}`, automatic_payout_id: `po_${i}` })
    );
    const result = await validateStripePayoutItemized(buildStripeItemizedCsv(rows));
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("row_limit_exceeded");
  }, 30000);

  it("caps reported errors and says it truncated them", async () => {
    const rows = Array.from({ length: MAX_REPORTED_ERRORS + 50 }, (_, i) =>
      chargeRow({ balance_transaction_id: `t${i}`, reporting_category: `bogus_${i}` })
    );
    const result = await validateStripePayoutItemized(buildStripeItemizedCsv(rows));
    expect(result.ok).toBe(false);
    expect(result.blockingErrors).toHaveLength(MAX_REPORTED_ERRORS);
    expect(result.errorsTruncated).toBe(true);
  });
});

describe("row exclusions are recorded, never silent", () => {
  it("excludes rows with no payout ID and records the reason", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1" }),
      chargeRow({ balance_transaction_id: "t2", automatic_payout_id: "" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    expect(result.report!.excludedRowCount).toBe(1);
    expect(result.report!.rowAudit.find((r) => r.status === "excluded")?.reasonCode).toBe("no_automatic_payout_id");
  });

  it("excludes payout-event rows from activity totals", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1" }),
      chargeRow({ balance_transaction_id: "t2", reporting_category: "payout", gross: "-96.80", fee: "0.00", net: "-96.80" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    expect(result.report!.payouts[0]!.rowCount).toBe(1);
    expect(result.report!.rowAudit.find((r) => r.reportingCategory === "payout")?.reasonCode).toBe("payout_event_row");
  });
});

describe("structural robustness", () => {
  function mulberry32(seed: number) {
    let a = seed;
    return () => {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  it("never throws on random garbage and always returns a well-formed outcome", async () => {
    const rand = mulberry32(99);
    const chars = 'abc,"\n\r;=+@\t 0123456789.-_XYZ';
    for (let i = 0; i < 100; i++) {
      const len = Math.floor(rand() * 300);
      let raw = "";
      for (let j = 0; j < len; j++) raw += chars[Math.floor(rand() * chars.length)];
      const result = await validateStripePayoutItemized(raw);
      expect(typeof result.ok).toBe("boolean");
      expect(Array.isArray(result.blockingErrors)).toBe(true);
      if (!result.ok) expect(result.report).toBeNull();
    }
  });

  it("rejects a structurally malformed file before any money logic runs", async () => {
    const result = await validateStripePayoutItemized('balance_transaction_id,gross\n"unterminated,1\n');
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("malformed_quotes");
  });
});
