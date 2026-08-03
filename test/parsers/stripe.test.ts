import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseStripe } from "../../src/parsers/stripe.js";
import { UnrecognizedFormatError } from "../../src/types.js";

const fixture = readFileSync(new URL("../fixtures/stripe-sample.csv", import.meta.url), "utf-8");

describe("parseStripe", () => {
  it("excludes payout-category rows", () => {
    const txns = parseStripe(fixture);
    expect(txns.every((t) => t.description !== "Payout po_1")).toBe(true);
    expect(txns).toHaveLength(4); // 3 for po_1 (2 charges + 1 refund) + 1 for po_2
  });

  it("groups by Payout ID with correct totals", () => {
    const txns = parseStripe(fixture);
    const po1 = txns.filter((t) => t.payoutId === "po_1");
    const grossSum = po1.reduce((s, t) => s + t.grossCents, 0);
    const feeSum = po1.reduce((s, t) => s + t.feeCents, 0);
    const netSum = po1.reduce((s, t) => s + t.netCents, 0);
    expect(grossSum).toBe(13000);
    expect(feeSum).toBe(437);
    expect(netSum).toBe(12563);
  });

  it("throws UnrecognizedFormatError on missing columns", () => {
    expect(() => parseStripe("Foo,Bar\n1,2\n")).toThrow(UnrecognizedFormatError);
  });
});
