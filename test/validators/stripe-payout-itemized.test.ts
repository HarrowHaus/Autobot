import { describe, expect, it } from "vitest";
import { validateStripePayoutItemized, MAX_ROWS, PARSER_VERSION } from "../../src/validators/stripe-payout-itemized.js";
import { buildStripeItemizedCsv, chargeRow } from "../support/stripe-fixture.js";

describe("validateStripePayoutItemized — happy path", () => {
  it("accepts a minimal reconciling file and computes correct totals", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "txn_1", gross: "100.00", fee: "3.20", net: "96.80" }),
      chargeRow({ balance_transaction_id: "txn_2", automatic_payout_id: "po_1", reporting_category: "fee", gross: "0", fee: "0", net: "0" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    expect(result.blockingErrors).toEqual([]);
    const report = result.report!;
    expect(report.parserVersion).toBe(PARSER_VERSION);
    expect(report.payouts).toHaveLength(1);
    const payout = report.payouts[0]!;
    expect(payout.payoutId).toBe("po_1");
    expect(payout.chargeTotalCents).toBe(10000);
    expect(payout.feeTotalCents).toBe(320);
    expect(payout.sourceNetCents).toBe(9680);
    expect(payout.calculatedNetCents).toBe(9680);
    expect(payout.varianceCents).toBe(0);
    expect(payout.warnings).toEqual([]);
  });

  it("groups multiple payouts and sums each independently", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1", automatic_payout_id: "po_1", gross: "50.00", fee: "1.00", net: "49.00" }),
      chargeRow({ balance_transaction_id: "t2", automatic_payout_id: "po_2", gross: "75.00", fee: "2.00", net: "73.00" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    expect(result.report!.payouts.map((p) => p.payoutId).sort()).toEqual(["po_1", "po_2"]);
  });

  it("sums refund/dispute/adjustment categories into their own buckets", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1", gross: "100.00", fee: "3.00", net: "97.00" }),
      chargeRow({ balance_transaction_id: "t2", reporting_category: "refund", gross: "-20.00", fee: "0", net: "-20.00" }),
      chargeRow({ balance_transaction_id: "t3", reporting_category: "dispute", gross: "-10.00", fee: "-15.00", net: "-25.00" }),
      chargeRow({ balance_transaction_id: "t4", reporting_category: "adjustment", gross: "-1.00", fee: "0", net: "-1.00" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    const payout = result.report!.payouts[0]!;
    expect(payout.chargeTotalCents).toBe(10000);
    expect(payout.refundTotalCents).toBe(-2000);
    expect(payout.disputeTotalCents).toBe(-1000);
    expect(payout.adjustmentTotalCents).toBe(-100);
    expect(payout.otherTotalCents).toBe(0);
  });

  it("is idempotent: the same input file produces the same source hash and totals across repeated runs", async () => {
    const csv = buildStripeItemizedCsv([chargeRow()]);
    const first = await validateStripePayoutItemized(csv);
    const second = await validateStripePayoutItemized(csv);
    expect(first.report!.sourceFileSha256).toBe(second.report!.sourceFileSha256);
    expect(first.report!.payouts).toEqual(second.report!.payouts);
  });

  it("accepts the non-UTC effective-at column when the _utc column is absent", async () => {
    const csv = buildStripeItemizedCsv([chargeRow()]).replace(
      "automatic_payout_effective_at_utc",
      "automatic_payout_effective_at"
    );
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    expect(result.report!.payouts[0]!.effectiveDate).toBe("2026-01-15");
  });
});

describe("validateStripePayoutItemized — file-level rejections", () => {
  it("rejects a completely empty file", async () => {
    const result = await validateStripePayoutItemized("");
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("empty_file");
  });

  it("rejects a file missing required columns rather than guessing", async () => {
    const csv = "foo,bar\n1,2\n";
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("missing_columns");
  });

  it("rejects a file with more than MAX_ROWS data rows", async () => {
    const rows = Array.from({ length: MAX_ROWS + 1 }, (_, i) => chargeRow({ balance_transaction_id: `t${i}`, automatic_payout_id: `po_${i}` }));
    const csv = buildStripeItemizedCsv(rows);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("row_limit_exceeded");
  }, 20000);

  it("rejects mixed currencies across the file rather than silently converting", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1", currency: "usd" }),
      chargeRow({ balance_transaction_id: "t2", currency: "eur" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("mixed_currency");
  });

  it("rejects an unsupported currency", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ currency: "xyz" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("unsupported_currency");
  });

  it("rejects inconsistent payout-status values for the same payout ID", async () => {
    const csv = buildStripeItemizedCsv(
      [
        chargeRow({ balance_transaction_id: "t1", automatic_payout_status: "paid" }),
        chargeRow({ balance_transaction_id: "t2", automatic_payout_status: "in_transit" }),
      ],
      ["automatic_payout_status"]
    );
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors[0]!.code).toBe("inconsistent_payout_status");
  });
});

describe("validateStripePayoutItemized — row-level blocking errors (fail whole file)", () => {
  it("rejects a row with a missing balance_transaction_id", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ balance_transaction_id: "" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors.some((e) => e.code === "missing_balance_transaction_id")).toBe(true);
  });

  it("rejects a row with a missing reporting_category", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ reporting_category: "" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors.some((e) => e.code === "missing_reporting_category")).toBe(true);
  });

  it("rejects an unrecognized reporting_category rather than guessing its accounting treatment", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ reporting_category: "some_new_category_stripe_added" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors.some((e) => e.code === "unknown_reporting_category")).toBe(true);
  });

  it("rejects a row with a malformed money field", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ gross: "$100.00" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(false);
    expect(result.blockingErrors.length).toBeGreaterThan(0);
  });
});

describe("validateStripePayoutItemized — row-level exclusions (non-blocking, always recorded)", () => {
  it("excludes rows with no automatic_payout_id instead of failing the whole file, and records why", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1" }),
      chargeRow({ balance_transaction_id: "t2", automatic_payout_id: "" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    expect(result.report!.excludedRowCount).toBe(1);
    const excluded = result.report!.rowAudit.find((r) => r.status === "excluded");
    expect(excluded?.reasonCode).toBe("no_automatic_payout_id");
    expect(result.report!.fileWarnings.some((w) => w.includes("excluded"))).toBe(true);
  });

  it("excludes payout-event rows ('payout') from totals but keeps the file valid", async () => {
    const csv = buildStripeItemizedCsv([
      chargeRow({ balance_transaction_id: "t1" }),
      chargeRow({ balance_transaction_id: "t2", reporting_category: "payout", gross: "96.80", fee: "0", net: "96.80" }),
    ]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    expect(result.report!.payouts[0]!.rowCount).toBe(1);
    const excluded = result.report!.rowAudit.find((r) => r.reportingCategory === "payout");
    expect(excluded?.status).toBe("excluded");
    expect(excluded?.reasonCode).toBe("payout_event_row");
  });
});

describe("validateStripePayoutItemized — variance detection", () => {
  it("flags a non-reconciling payout with a variance and a warning, but does not fail the file", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ gross: "100.00", fee: "3.20", net: "90.00" })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    const payout = result.report!.payouts[0]!;
    expect(payout.calculatedNetCents).toBe(9680);
    expect(payout.sourceNetCents).toBe(9000);
    expect(payout.varianceCents).toBe(680);
    expect(payout.warnings.some((w) => w.includes("differs from the source file's net"))).toBe(true);
  });
});

describe("validateStripePayoutItemized — file warnings", () => {
  it("notes when no payout-status column is present (the expected, common case)", async () => {
    const csv = buildStripeItemizedCsv([chargeRow()]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
    expect(result.report!.fileWarnings.some((w) => w.includes("payout-status column"))).toBe(true);
  });
});

describe("validateStripePayoutItemized — fuzz / malformed-CSV robustness", () => {
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

  it("never throws on random garbage input and always returns a well-formed outcome shape", async () => {
    const rand = mulberry32(99);
    const chars = "abc,\"\n\r;=+@\t 0123456789.-_XYZ";
    for (let i = 0; i < 100; i++) {
      const len = Math.floor(rand() * 300);
      let raw = "";
      for (let j = 0; j < len; j++) raw += chars[Math.floor(rand() * chars.length)];
      const result = await validateStripePayoutItemized(raw);
      expect(typeof result.ok).toBe("boolean");
      expect(Array.isArray(result.blockingErrors)).toBe(true);
    }
  });

  it("never throws on a well-formed header with random garbage row values", async () => {
    const rand = mulberry32(123);
    const chars = "abc,\"\n=+@ 0123456789.-";
    for (let i = 0; i < 50; i++) {
      const csv = buildStripeItemizedCsv([
        chargeRow({
          gross: Array.from({ length: 10 }, () => chars[Math.floor(rand() * chars.length)]).join(""),
        }),
      ]);
      await expect(validateStripePayoutItemized(csv)).resolves.toBeDefined();
    }
  });

  it("does not crash on a single absurdly long field", async () => {
    const csv = buildStripeItemizedCsv([chargeRow({ description: "x".repeat(200_000) })]);
    const result = await validateStripePayoutItemized(csv);
    expect(result.ok).toBe(true);
  });
});
