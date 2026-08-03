import { describe, expect, it } from "vitest";
import { centsToDecimalString, parseMoneyToCents } from "../../src/lib/money.js";

describe("parseMoneyToCents", () => {
  it("parses plain decimals", () => {
    expect(parseMoneyToCents("100.00")).toBe(10000);
    expect(parseMoneyToCents("1.5")).toBe(150);
    expect(parseMoneyToCents("0")).toBe(0);
  });

  it("parses negatives", () => {
    expect(parseMoneyToCents("-20.00")).toBe(-2000);
    expect(parseMoneyToCents("-1.75")).toBe(-175);
  });

  it("parses accounting-style parenthetical negatives", () => {
    expect(parseMoneyToCents("(20.00)")).toBe(-2000);
  });

  it("strips currency symbols and thousands separators", () => {
    expect(parseMoneyToCents("$1,234.56")).toBe(123456);
  });

  it("treats empty string as zero", () => {
    expect(parseMoneyToCents("")).toBe(0);
  });
});

describe("centsToDecimalString", () => {
  it("round-trips", () => {
    expect(centsToDecimalString(10000)).toBe("100.00");
    expect(centsToDecimalString(-2000)).toBe("-20.00");
    expect(centsToDecimalString(5)).toBe("0.05");
  });
});
