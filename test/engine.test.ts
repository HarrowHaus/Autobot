import { describe, expect, it } from "vitest";
import { convert, isSupportedProcessor } from "../src/engine.js";
import { buildStripeItemizedCsv, chargeRow } from "./support/stripe-fixture.js";

describe("isSupportedProcessor", () => {
  it("supports only stripe", () => {
    expect(isSupportedProcessor("stripe")).toBe(true);
    expect(isSupportedProcessor("paypal")).toBe(false);
    expect(isSupportedProcessor("xero")).toBe(false);
    expect(isSupportedProcessor("")).toBe(false);
  });
});

describe("convert", () => {
  it("rejects unsupported processors (paypal is disabled at this layer, not just in the UI)", async () => {
    const result = await convert("anything", "paypal");
    expect(result.validation.ok).toBe(false);
    expect(result.validation.blockingErrors[0]!.code).toBe("unsupported_processor");
    expect(result.qboJournal).toBeNull();
  });

  it("validates a stripe file and returns no QBO journal when qboExport isn't requested", async () => {
    const csv = buildStripeItemizedCsv([chargeRow()]);
    const result = await convert(csv, "stripe");
    expect(result.validation.ok).toBe(true);
    expect(result.qboJournal).toBeNull();
  });

  it("builds a QBO journal only when the caller explicitly opts in with mappings", async () => {
    const csv = buildStripeItemizedCsv([chargeRow()]);
    const result = await convert(csv, "stripe", {
      qboExport: {
        mappings: {
          stripeClearing: "Stripe Clearing",
          revenue: "Sales Income",
          refundsAndReturns: "Refunds and Returns",
          processingFees: "Merchant Processing Fees",
          disputesAndChargebacks: "Disputes and Chargebacks",
        },
      },
    });
    expect(result.validation.ok).toBe(true);
    expect(result.qboJournal).not.toBeNull();
    expect(result.qboJournal!.ok).toBe(true);
  });

  it("does not attempt to build a QBO journal when the underlying validation fails", async () => {
    const result = await convert("not,a,valid,file", "stripe", {
      qboExport: {
        mappings: {
          stripeClearing: "a",
          revenue: "b",
          refundsAndReturns: "c",
          processingFees: "d",
          disputesAndChargebacks: "e",
        },
      },
    });
    expect(result.validation.ok).toBe(false);
    expect(result.qboJournal).toBeNull();
  });
});
