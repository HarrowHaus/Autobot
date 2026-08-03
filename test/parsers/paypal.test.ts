import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parsePayPal } from "../../src/parsers/paypal.js";
import { UnrecognizedFormatError } from "../../src/types.js";

const fixture = readFileSync(new URL("../fixtures/paypal-sample.csv", import.meta.url), "utf-8");

describe("parsePayPal", () => {
  it("parses transactions and derives net from gross/fee", () => {
    const txns = parsePayPal(fixture);
    expect(txns).toHaveLength(3);

    const [first, , refund] = txns;
    expect(first).toMatchObject({
      date: "2026-01-15",
      grossCents: 10000,
      feeCents: 320,
      netCents: 9680,
      payoutId: "TXN001",
    });
    expect(refund).toMatchObject({
      type: "refund",
      grossCents: -2000,
      netCents: -2000,
    });
  });

  it("maintains the gross = fee + net identity for every row", () => {
    for (const txn of parsePayPal(fixture)) {
      expect(txn.netCents).toBe(txn.grossCents - txn.feeCents);
    }
  });

  it("throws UnrecognizedFormatError on missing columns", () => {
    expect(() => parsePayPal("Foo,Bar\n1,2\n")).toThrow(UnrecognizedFormatError);
  });
});
